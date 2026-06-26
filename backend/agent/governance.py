"""
ForgeSight — Agent Governance & Orchestration Layer  (completed from agent_governance.py)
=========================================================================================
The design deliverable lives at repo-root agent_governance.py; THIS is the runnable copy with
the placeholders filled:
  - shared state models imported from schemas.agent_models (one definition, no duplication)
  - CARD_SCHEMAS / CITATION_REQUIRED_CARDS imported from schemas.cards (was empty {})
  - _equipment_exists implemented against the DB pool (was `...`)
  - route_agents made robust to the Pass-1 sub-agent set (filters to registered pipelines)

Four components composed into one LangGraph StateGraph: AgentState · AgentAuthority ·
AgentGuardrails · AgentController. See forgesight-v3-final.md §1.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Callable, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import InjectedState
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.types import Command, Send, interrupt
from pydantic import BaseModel

from backend.schemas.agent_models import (
    AuthUser, Budget, Citation, DelegationEvent, GuardReport,
    merge_dicts, reduce_list, sum_budget,
)
from backend.schemas.cards import CARD_SCHEMAS, CITATION_REQUIRED_CARDS

# ----------------------------------------------------------------------------------
# 1. AGENT STATE — reducer-backed channels (concurrent Send branches merge safely)
# ----------------------------------------------------------------------------------

class ForgeState(AgentState):
    """Graph state. `messages` channel inherited from AgentState."""
    user: AuthUser | None
    session_id: str | None
    equipment_id: str | None
    intent: str | None
    query_class: str | None
    target_agents: list[str] | None
    delegations: Annotated[list[DelegationEvent], reduce_list]
    citations:   Annotated[list[Citation], reduce_list]
    tool_results: Annotated[dict[str, Any], merge_dicts]
    consumed:    Annotated[Budget, sum_budget]
    draft_card: dict | None
    guard_report: GuardReport | None
    repair_attempted: bool
    pending_action: dict | None
    cache_hit: dict | None


# ----------------------------------------------------------------------------------
# 2. AGENT AUTHORITY — governance registry: capabilities, scopes, budgets, escalation
# ----------------------------------------------------------------------------------

class ActionClass(str, Enum):
    READ = "read"
    WRITE = "write"
    REPORT = "report"
    COMMIT = "commit"
    SIMULATE = "simulate"


@dataclass(frozen=True)
class AgentCharter:
    """One agent's complete authority. If it isn't in the charter, it can't happen."""
    name: str
    persona_prompt: str
    allowed_tools: frozenset[str]
    action_classes: frozenset[ActionClass]
    data_scopes: frozenset[str]
    recursion_limit: int = 8
    max_tool_calls: int = 6
    model_tier: Literal["orchestrator", "slm"] = "orchestrator"


AGENT_CHARTERS: dict[str, AgentCharter] = {
    "diagnostic_agent": AgentCharter(
        name="diagnostic_agent",
        persona_prompt=(
            "You are the Diagnostic Agent for a steel plant maintenance system. "
            "You diagnose equipment faults and identify root causes using ONLY the "
            "provided tools (manuals/SOP retrieval, breakdown-history matching). "
            "Every claim must be supported by a retrieved source. Rank root causes. "
            "Express confidence as High/Medium/Low, never percentages. "
            "If retrieval finds nothing relevant, say so — never invent references."
        ),
        allowed_tools=frozenset({"retrieve_rag", "match_history", "slm_diagnose"}),
        action_classes=frozenset({ActionClass.READ}),
        data_scopes=frozenset({"doc_chunks", "breakdown_history", "equipment"}),
    ),
    "reliability_agent": AgentCharter(
        name="reliability_agent",
        persona_prompt=(
            "You are the Reliability Agent. You assess current equipment health, "
            "estimate remaining useful life, and analyse process defects, strictly by "
            "calling the ML tools and reporting their outputs with their evidence "
            "(contributing sensors, thresholds, confidence bands). You never estimate "
            "numbers yourself; you narrate tool outputs."
        ),
        allowed_tools=frozenset({"check_equipment_health", "estimate_rul", "analyze_defect",
                                 "predict_failure", "predict_pdm_24h", "rul_benchmark"}),
        action_classes=frozenset({ActionClass.READ}),
        data_scopes=frozenset({"sensor_readings", "equipment_health", "equipment"}),
    ),
    "supervisor_agent": AgentCharter(
        name="supervisor_agent",
        persona_prompt=(
            "You are the Supervisor Agent. You assess urgency, plant bottlenecks and "
            "maintenance priority. Priority scores come ONLY from the deterministic "
            "score_priority tool — you narrate its factor breakdown, you never compute "
            "or adjust scores. You may draft shift summaries from provided results."
        ),
        allowed_tools=frozenset({"score_priority", "draft_shift_summary"}),
        action_classes=frozenset({ActionClass.READ, ActionClass.REPORT}),
        data_scopes=frozenset({"alerts", "equipment", "equipment_health", "reports"}),
    ),
    "planner_agent": AgentCharter(
        name="planner_agent",
        persona_prompt=(
            "You are the Planner Agent. You handle spare parts and procurement. "
            "You report stock and lead times from the spares tool, and apply the "
            "deterministic procurement rule (lead time vs RUL). A reservation or PO "
            "draft is only ever a PROPOSAL — it requires human approval downstream."
        ),
        allowed_tools=frozenset({"check_spares", "procurement_rule", "propose_reservation"}),
        action_classes=frozenset({ActionClass.READ, ActionClass.COMMIT}),
        data_scopes=frozenset({"spares", "equipment_health"}),
    ),
    "analyst_agent": AgentCharter(
        name="analyst_agent",
        persona_prompt=(
            "You are the Analyst Agent. You answer analytical questions over maintenance records "
            "and logs by generating a single read-only SELECT against curated views. The SQL is "
            "always shown as the citation; you never write data and never state a number absent "
            "from the returned rows."
        ),
        allowed_tools=frozenset({"query_records"}),
        action_classes=frozenset({ActionClass.READ}),
        data_scopes=frozenset({"v_breakdown_stats", "v_spares_status",
                               "v_alert_feed", "v_downtime_by_equipment"}),
    ),
}

ESCALATION_REQUIRED: frozenset[ActionClass] = frozenset({ActionClass.COMMIT})

ROLE_CAPABILITIES: dict[str, frozenset[ActionClass]] = {
    "engineer": frozenset({ActionClass.READ, ActionClass.WRITE,
                           ActionClass.REPORT, ActionClass.COMMIT}),
    "admin":    frozenset({ActionClass.READ, ActionClass.WRITE, ActionClass.REPORT,
                           ActionClass.COMMIT, ActionClass.SIMULATE}),
}


class AuthorityError(Exception):
    """Raised when a charter or role check fails. Always audited."""


class AgentAuthority:
    """Runtime governance checks. Every decision is emitted to the audit log."""

    def __init__(self, audit_sink: Callable[[dict], None]):
        self._audit = audit_sink

    def check_tool(self, agent: str, tool_name: str, action: ActionClass,
                   user: AuthUser) -> None:
        charter = AGENT_CHARTERS.get(agent)
        decision = {"agent": agent, "tool": tool_name, "action": action.value,
                    "user_id": user.id, "role": user.role,
                    "ts": datetime.now(timezone.utc).isoformat()}
        if charter is None:
            self._audit({**decision, "allowed": False, "reason": "unknown_agent"})
            raise AuthorityError(f"Unknown agent '{agent}'")
        if tool_name not in charter.allowed_tools:
            self._audit({**decision, "allowed": False, "reason": "tool_not_in_charter"})
            raise AuthorityError(f"{agent} is not chartered for tool '{tool_name}'")
        if action not in charter.action_classes:
            self._audit({**decision, "allowed": False, "reason": "action_not_in_charter"})
            raise AuthorityError(f"{agent} is not chartered for action '{action.value}'")
        if action not in ROLE_CAPABILITIES[user.role]:
            self._audit({**decision, "allowed": False, "reason": "role_denied"})
            raise AuthorityError(f"Role '{user.role}' may not trigger '{action.value}'")
        self._audit({**decision, "allowed": True})

    def check_budget(self, agent: str, consumed: Budget) -> None:
        charter = AGENT_CHARTERS[agent]
        if consumed.tool_calls >= charter.max_tool_calls:
            raise AuthorityError(f"{agent} exceeded per-turn tool budget "
                                 f"({charter.max_tool_calls})")

    def needs_human_approval(self, action: ActionClass) -> bool:
        return action in ESCALATION_REQUIRED


# ----------------------------------------------------------------------------------
# 2b. GOVERNED TOOL WRAPPER — Authority enforced at the only place execution happens
#     (retained from the design; pipelines call Authority directly, see agent/pipelines.py)
# ----------------------------------------------------------------------------------

def governed_tool(agent_name: str, action: ActionClass, authority: AgentAuthority,
                  delegation_text: Callable[..., str]):
    def wrap(fn: Callable[..., "ToolOutcome"]):
        @tool(fn.__name__, description=fn.__doc__ or fn.__name__)
        def _governed(
            state: Annotated[ForgeState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            **kwargs,
        ) -> Command:
            user = state["user"]
            authority.check_tool(agent_name, fn.__name__, action, user)
            authority.check_budget(agent_name, state.get("consumed") or Budget())
            outcome = fn(state=state, **kwargs)
            update: dict[str, Any] = {
                "delegations": [DelegationEvent(agent=agent_name,
                                                text=delegation_text(**kwargs))],
                "citations": outcome.citations,
                "tool_results": {fn.__name__: outcome.payload},
                "consumed": Budget(tool_calls=1),
                "messages": [ToolMessage(outcome.payload_json(),
                                         tool_call_id=tool_call_id)],
            }
            if outcome.pending_action is not None:
                update["pending_action"] = outcome.pending_action
            return Command(update=update)
        return _governed
    return wrap


@dataclass
class ToolOutcome:
    payload: BaseModel
    citations: list[Citation] = field(default_factory=list)
    pending_action: dict | None = None

    def payload_json(self) -> str:
        return self.payload.model_dump_json()


# ----------------------------------------------------------------------------------
# 3. AGENT GUARDRAILS — input / output guards. Pure code; retry-once-then-degrade.
# ----------------------------------------------------------------------------------

INJECTION_MARKERS = ("ignore previous", "disregard your instructions", "system prompt",
                     "you are now", "developer mode")


class AgentGuardrails:
    """Input guards run before routing; output guards run after synthesis.
    Tool guards live inside the pipelines (Authority). The LLM never self-certifies."""

    @staticmethod
    def guard_input(state: ForgeState) -> GuardReport:
        v: list[str] = []
        user, text = state.get("user"), _last_user_text(state)
        if user is None:
            v.append("unauthenticated")
        if state.get("equipment_id") and not _equipment_exists(state["equipment_id"]):
            v.append("unknown_equipment_id")
        if any(m in text.lower() for m in INJECTION_MARKERS):
            v.append("possible_prompt_injection")
        if len(text) > 4000:
            v.append("input_too_long")
        return GuardReport(passed=not v, violations=v)

    @staticmethod
    def guard_output(state: ForgeState) -> GuardReport:
        v: list[str] = []
        card = state.get("draft_card")
        if card is None:
            return GuardReport(passed=False, violations=["no_draft_card"])
        # 1) schema validity
        try:
            CARD_SCHEMAS[card.get("card_type", "")].model_validate(card)
        except Exception as e:  # noqa: BLE001
            v.append(f"schema_invalid:{type(e).__name__}")
        # 2) citation completeness — every cited ref must exist in state.citations
        known = {c.ref for c in state.get("citations", [])}
        for ref in card.get("citation_refs", []):
            if ref not in known:
                v.append(f"fabricated_citation:{ref}")
        if card.get("card_type") in CITATION_REQUIRED_CARDS and not card.get("citation_refs"):
            v.append("uncited_claims")
        # 3) safety ordering — LOTO/isolation steps must come first in any checklist
        steps = card.get("steps", [])
        if steps:
            first_safety = next((i for i, s in enumerate(steps) if s.get("safety")), None)
            first_normal = next((i for i, s in enumerate(steps) if not s.get("safety")), None)
            if first_safety is not None and first_normal is not None and first_normal < first_safety:
                v.append("safety_steps_not_first")
        # 4) enum & numeric sanity
        if card.get("risk_level") not in (None, "low", "medium", "high", "critical"):
            v.append("invalid_risk_level")
        rul = card.get("rul_days")
        if rul is not None and not (0 <= float(rul) <= 3650):
            v.append("rul_out_of_range")
        if card.get("priority_score") is not None and "score_priority" not in state.get("tool_results", {}):
            v.append("priority_not_from_matrix")
        return GuardReport(passed=not v, violations=v)

    @staticmethod
    def degraded_card(state: ForgeState) -> dict:
        """Honest fallback: raw retrieval + tool outputs, clearly labelled."""
        return {
            "card_type": "degraded",
            "message": "I couldn't produce a fully validated answer. Here is the "
                       "matched source material and tool output instead.",
            "retrieved": [c.model_dump() for c in state.get("citations", [])],
            "tool_results": {k: _safe_dump(v) for k, v in state.get("tool_results", {}).items()
                             if not k.startswith("_")},
            "violations": (state.get("guard_report") or GuardReport(passed=False)).violations,
        }


# ----------------------------------------------------------------------------------
# 4. AGENT CONTROLLER — the orchestration graph (nodes, edges, fan-out, HITL)
# ----------------------------------------------------------------------------------

INTENT_AGENT_MAP: dict[str, list[str]] = {
    "diagnosis":       ["diagnostic_agent"],
    "sop_lookup":      ["diagnostic_agent"],
    "health_query":    ["reliability_agent"],
    "rul_query":       ["reliability_agent"],
    "defect_query":    ["reliability_agent"],
    "priority_query":  ["supervisor_agent"],
    "spares_query":    ["planner_agent"],
    "report_request":  ["supervisor_agent"],
    "analytical_query": ["analyst_agent"],
    "wait_assessment": ["reliability_agent", "planner_agent", "supervisor_agent"],
}


class AgentController:
    """Builds and owns the governed StateGraph."""

    def __init__(self, authority: AgentAuthority, guards: AgentGuardrails,
                 sub_agents: dict[str, Any], checkpointer, llm, caches, persistence):
        self.authority, self.guards = authority, guards
        self.sub_agents = sub_agents
        self.llm, self.caches, self.persist = llm, caches, persistence
        self.graph = self._build(checkpointer)

    # ---------------- nodes ----------------

    def ingest_and_authorize(self, state: ForgeState) -> dict:
        report = self.guards.guard_input(state)
        if not report.passed and "unauthenticated" in report.violations:
            raise AuthorityError("No authenticated user in state")
        # Reset the per-turn tool/LLM budget: the checkpointer persists `consumed` across turns in a
        # session, so without this the cap accumulates and later turns get spuriously denied.
        return {"guard_report": report, "consumed": Budget(reset=True)}

    def cache_lookup(self, state: ForgeState) -> dict:
        hit = self.caches.lookup(_last_user_text(state), state.get("equipment_id"),
                                 state.get("query_class"))
        return {"cache_hit": hit}

    def classify_intent(self, state: ForgeState) -> dict:
        text = _last_user_text(state)
        # If the caller gave no equipment (e.g. the global copilot), try to resolve one from the
        # text so asset questions return real cards instead of always degrading.
        eq = state.get("equipment_id") or _resolve_equipment_from_text(text)
        intent, query_class = self.llm.classify(text, eq)
        out = {"intent": intent, "query_class": query_class,
               "target_agents": INTENT_AGENT_MAP.get(intent, ["diagnostic_agent"])}
        if eq and not state.get("equipment_id"):
            out["equipment_id"] = eq
        return out

    def synthesize(self, state: ForgeState) -> dict:
        # §1.7b analytical queries: the SqlCard is assembled DETERMINISTICALLY from the
        # query_records tool output (rows are verbatim DB data — the SLM never regenerates them).
        if state.get("intent") == "analytical_query":
            qr = (state.get("tool_results", {}) or {}).get("query_records") or {}
            card = {"card_type": "sql", "question": qr.get("question", _last_user_text(state)),
                    "sql": qr.get("sql", ""), "columns": qr.get("columns", []),
                    "rows": qr.get("rows", []), "narration": qr.get("narration", ""),
                    "citation_refs": [qr["sql"]] if qr.get("sql") else []}
            return {"draft_card": card, "consumed": Budget(llm_calls=0)}
        card = self.llm.synthesize_card(
            intent=state["intent"],
            tool_results=state.get("tool_results", {}),
            citations=[c.model_dump() for c in state.get("citations", [])],
            history=state["messages"],
        )
        return {"draft_card": card, "consumed": Budget(llm_calls=1)}

    def guardrail_validate(self, state: ForgeState) -> dict:
        return {"guard_report": self.guards.guard_output(state)}

    def repair(self, state: ForgeState) -> dict:
        card = self.llm.synthesize_card_with_errors(
            previous=state["draft_card"],
            violations=state["guard_report"].violations,
            tool_results=state.get("tool_results", {}),
            citations=[c.model_dump() for c in state.get("citations", [])],
        )
        return {"draft_card": card, "repair_attempted": True,
                "consumed": Budget(llm_calls=1)}

    def degrade(self, state: ForgeState) -> dict:
        return {"draft_card": self.guards.degraded_card(state),
                "guard_report": GuardReport(passed=True, degraded=True)}

    def human_gate(self, state: ForgeState) -> dict:
        decision = interrupt({"type": "approval_request",
                              "action": state["pending_action"]})
        if decision.get("approved"):
            self.persist.commit_action(state["pending_action"], state["user"])
        return {"pending_action": None,
                "tool_results": {"human_gate": {"approved": bool(decision.get("approved"))}}}

    def respond(self, state: ForgeState) -> dict:
        self.persist.write_turn(state)
        gr = state.get("guard_report")
        if state.get("query_class") == "knowledge" and gr is not None and not gr.degraded:
            self.caches.store(_last_user_text(state), state.get("equipment_id"),
                              state["draft_card"])
        return {}

    def serve_cached(self, state: ForgeState) -> dict:
        return {"draft_card": {**state["cache_hit"], "served_from_cache": True},
                "guard_report": GuardReport(passed=True)}

    # ---------------- routing functions (conditional edges) ----------------

    @staticmethod
    def route_cache(state: ForgeState) -> str:
        return "serve_cached" if state.get("cache_hit") else "classify_intent"

    def route_agents(self, state: ForgeState) -> list[Send]:
        """Parallel fan-out: one Send per chartered target agent that is actually registered.
        (Pass 1 registers only diagnostic_agent; intents mapping to unbuilt agents fall back.)"""
        targets = [a for a in (state.get("target_agents") or []) if a in self.sub_agents]
        if not targets:
            targets = ["diagnostic_agent"] if "diagnostic_agent" in self.sub_agents \
                else list(self.sub_agents)[:1]
        return [Send(name, state) for name in targets]

    @staticmethod
    def route_guard(state: ForgeState) -> str:
        report = state["guard_report"]
        if report.passed:
            return "human_gate" if state.get("pending_action") else "respond"
        return "degrade" if state.get("repair_attempted") else "repair"

    # ---------------- graph assembly ----------------

    def _build(self, checkpointer):
        g = StateGraph(ForgeState)

        for name in ("ingest_and_authorize", "cache_lookup", "classify_intent",
                     "synthesize", "guardrail_validate", "repair", "degrade",
                     "human_gate", "respond", "serve_cached"):
            g.add_node(name, getattr(self, name))

        for name, agent in self.sub_agents.items():
            g.add_node(name, agent.with_config(
                {"recursion_limit": AGENT_CHARTERS[name].recursion_limit}))

        g.set_entry_point("ingest_and_authorize")
        g.add_edge("ingest_and_authorize", "cache_lookup")
        for name in self.sub_agents:
            g.add_edge(name, "synthesize")
        g.add_edge("synthesize", "guardrail_validate")
        g.add_edge("repair", "guardrail_validate")
        g.add_edge("degrade", "respond")
        g.add_edge("human_gate", "respond")
        g.add_edge("serve_cached", "respond")
        g.add_edge("respond", END)

        g.add_conditional_edges("cache_lookup", self.route_cache,
                                ["serve_cached", "classify_intent"])
        g.add_conditional_edges("classify_intent", self.route_agents,
                                list(self.sub_agents))
        g.add_conditional_edges("guardrail_validate", self.route_guard,
                                ["respond", "human_gate", "repair", "degrade"])

        return g.compile(checkpointer=checkpointer)

    def invoke(self, inputs: dict, config: dict) -> dict:
        try:
            return self.graph.invoke(inputs, config)
        except GraphRecursionError:
            state = self.graph.get_state(config).values
            return self._error_fallback(inputs) or {
                **state, "draft_card": self.guards.degraded_card(state)}
        except AuthorityError as e:
            return {"draft_card": {"card_type": "denied",
                                   "message": f"Action not permitted: {e}"}}
        except Exception as e:  # noqa: BLE001 — ANY mid-turn failure degrades to an honest card, never a 500
            print(f"  [controller] turn failed, degrading (non-fatal): {e}")
            fb = self._error_fallback(inputs)
            if fb is not None:
                return fb
            # Universal safety net: a failure in any node (agent/tool/synthesis/guardrail) for ANY
            # input still terminates in a degraded card rather than a 500.
            try:
                state = self.graph.get_state(config).values
            except Exception:  # noqa: BLE001
                state = dict(inputs)
            return {**state, "draft_card": self.guards.degraded_card(state),
                    "guard_report": GuardReport(passed=True, degraded=True)}

    def _error_fallback(self, inputs: dict) -> dict | None:
        """Error/timeout fallback ONLY: if the live governed turn fails, serve the pre-baked
        golden card for a scripted query so a demo never dies on a spinner. The happy path is
        always the real pipeline (DEMO_MODE defaults false); this is the safety net, not the norm."""
        demo = getattr(self.caches, "demo", None) or {}
        if not demo:
            return None
        text = _last_user_text(inputs if "messages" in inputs else {"messages": inputs.get("messages", [])})
        key = f"{inputs.get('equipment_id') or ''}::{' '.join((text or '').lower().split())}"
        card = demo.get(key)
        if card is None:
            return None
        return {"draft_card": {**card, "served_from_cache": True},
                "citations": [], "delegations": [],
                "intent": "diagnosis", "query_class": "knowledge"}


# ----------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------

def _last_user_text(state: ForgeState) -> str:
    for m in reversed(state["messages"]):
        if getattr(m, "type", None) == "human" or getattr(m, "role", "") == "user":
            return m.content if isinstance(m.content, str) else str(m.content)
        if isinstance(m, dict) and m.get("role") == "user":
            return m.get("content", "")
    return ""


def _equipment_exists(equipment_id: str) -> bool:
    """SELECT 1 FROM equipment. Fail-open on DB error — the tool layer re-validates IDs,
    so a transient DB hiccup must not block a legitimate query at the input guard."""
    try:
        from backend.db.connection import get_pool
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM equipment WHERE id = %s", (equipment_id,))
            return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return True


_EQUIPMENT_ALIASES = {
    "f3": "hsm-f3-stand", "f3 stand": "hsm-f3-stand", "hot strip mill": "hsm-f3-stand",
    "sinter fan 2": "sinter-fan-2", "sinter fan #2": "sinter-fan-2", "id fan 2": "sinter-fan-2",
    "sinter fan 1": "sinter-fan-1", "sinter fan #1": "sinter-fan-1", "id fan 1": "sinter-fan-1",
    "caster": "caster-1", "continuous caster": "caster-1",
    "blast furnace stove": "bf-stove-a", "stove a": "bf-stove-a", "bf stove": "bf-stove-a",
    "ladle crane": "ladle-crane-4", "crane 4": "ladle-crane-4", "ladle crane 4": "ladle-crane-4",
}


def _resolve_equipment_from_text(text: str) -> str | None:
    """Best-effort map of free text → a known equipment id, so asset questions asked from the
    global copilot (which sends no equipment_id) still resolve. Conservative: returns a hit only on
    an exact id, a known alias, or a UNIQUE name substring; otherwise None (caller leaves it unset
    and the pipeline degrades gracefully). Never raises."""
    if not text:
        return None
    t = " ".join(text.lower().split())
    try:
        from backend.db.connection import get_pool
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, name FROM equipment")
            rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return None
    ids = {r[0] for r in rows}
    for eid, _ in rows:                                   # 1) exact equipment id mentioned
        if eid.lower() in t:
            return eid
    for alias, eid in _EQUIPMENT_ALIASES.items():         # 2) known alias
        if alias in t and eid in ids:
            return eid
    name_hits = [eid for eid, name in rows if name and name.lower() in t]
    if len(name_hits) == 1:                               # 3) unique full-name substring
        return name_hits[0]
    return None


def _safe_dump(v: Any) -> Any:
    return v.model_dump() if isinstance(v, BaseModel) else v
