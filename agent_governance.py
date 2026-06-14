"""
ForgeSight — Agent Governance & Orchestration Layer
====================================================
Governance layer for the Agent.

Four components, composed into one LangGraph StateGraph:

  1. AgentState   — typed, reducer-backed shared state (single source of truth per turn)
  2. AgentAuthority — WHO may do WHAT: capability registry, role overlay, budgets,
                      escalation policy. Checked BEFORE execution, audited ALWAYS.
  3. AgentGuardrails — input / tool / output guards with a retry-then-degrade policy.
                       Code, not LLM. The LLM is never the judge of its own output.
  4. AgentController — the orchestration graph: nodes, conditional + unconditional
                       edges, parallel fan-out (Send), human-in-the-loop gate,
                       checkpointed per chat session (thread_id = session_id).

Design rules enforced structurally (not by prompt):
  - Sub-agents are shallow ReAct agents (recursion-capped) with SCOPED toolsets.
  - Role separation at tool level: an agent cannot call a tool it was never bound to,
    and Authority re-checks at runtime (defense in depth, audited).
  - Deterministic tools (priority matrix, procurement rule, severity rules) are pure
    code; agents narrate results, never compute them.
  - Every delegation/citation flows through state reducers -> UI activity stream,
    chat_messages audit trail, and Langfuse spans, from ONE source of truth.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Callable, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import InjectedState, create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.types import Command, Send, interrupt
from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------------------
# 0. Shared structured-output models (frontend cards bind to these — schema-first)
# ----------------------------------------------------------------------------------

class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["manual", "sop", "history", "trend", "spares_record",
                  "priority_matrix", "model_output"]
    ref: str                      # e.g. "SOP-HSM-ELEC-09 §3.2", "BR-2024-0312"
    chunk_id: str | None = None   # matches doc_chunks.id and Langfuse span metadata


class DelegationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str
    text: str                     # "checking SKF 22230 lead time…"
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GuardReport(BaseModel):
    passed: bool
    violations: list[str] = []
    degraded: bool = False        # True when we fell back to raw-retrieval response


class AuthUser(BaseModel):
    id: str
    role: Literal["engineer", "admin"]


# ----------------------------------------------------------------------------------
# 1. AGENT STATE — reducer-backed channels (concurrent Send branches merge safely)
# ----------------------------------------------------------------------------------

def reduce_list(left: list | None, right: list | None) -> list:
    return (left or []) + (right or [])

def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}

def sum_budget(left: "Budget | None", right: "Budget | None") -> "Budget":
    """Budgets consumed by parallel branches are additive."""
    l, r = left or Budget(), right or Budget()
    return Budget(tool_calls=l.tool_calls + r.tool_calls,
                  llm_calls=l.llm_calls + r.llm_calls)


class Budget(BaseModel):
    tool_calls: int = 0
    llm_calls: int = 0


class ForgeState(AgentState):
    """Graph state. `messages` channel inherited from AgentState."""
    # --- identity & context (set once at ingest, read-only afterwards) ---
    user: AuthUser | None
    session_id: str | None
    equipment_id: str | None              # route-derived context (FR-3)
    # --- routing decisions (set by controller nodes) ---
    intent: str | None                    # diagnosis | health_query | priority_query | ...
    query_class: str | None               # knowledge | live_status | action (cache rule)
    target_agents: list[str] | None       # chosen by plan_route
    # --- accumulated by sub-agents via reducers (parallel-safe) ---
    delegations: Annotated[list[DelegationEvent], reduce_list]   # -> UI activity stream
    citations:   Annotated[list[Citation], reduce_list]          # -> evidence chips
    tool_results: Annotated[dict[str, Any], merge_dicts]         # keyed by tool name
    consumed:    Annotated[Budget, sum_budget]                   # budget accounting
    # --- synthesis & guarding ---
    draft_card: dict | None               # candidate structured answer
    guard_report: GuardReport | None
    repair_attempted: bool                # retry-once policy flag
    pending_action: dict | None           # action awaiting human approval (HITL)
    cache_hit: dict | None


# ----------------------------------------------------------------------------------
# 2. AGENT AUTHORITY — governance registry: capabilities, scopes, budgets, escalation
# ----------------------------------------------------------------------------------

class ActionClass(str, Enum):
    READ = "read"            # queries, retrieval, ML inference
    WRITE = "write"          # logbook entries, alert ack, feedback persistence
    REPORT = "report"        # PDF generation
    COMMIT = "commit"        # reserve spare / draft PO  -> REQUIRES human approval
    SIMULATE = "simulate"    # fault injection           -> admin-only, never agent


@dataclass(frozen=True)
class AgentCharter:
    """One agent's complete authority. If it isn't in the charter, it can't happen."""
    name: str
    persona_prompt: str
    allowed_tools: frozenset[str]
    action_classes: frozenset[ActionClass]
    data_scopes: frozenset[str]           # tables this agent's tools may touch
    recursion_limit: int = 8              # SHALLOW by construction
    max_tool_calls: int = 6               # per-turn budget
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
        allowed_tools=frozenset({"check_equipment_health", "estimate_rul", "analyze_defect"}),
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
}

# Actions that MUST pass through the human-in-the-loop gate before persisting:
ESCALATION_REQUIRED: frozenset[ActionClass] = frozenset({ActionClass.COMMIT})

# User-role overlay: what each human role may trigger at all (UI gating is convenience;
# this is enforcement — checked at ingest and again at tool time).
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
        self._audit = audit_sink            # writes to audit_log table + Langfuse event

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
# ----------------------------------------------------------------------------------

def governed_tool(agent_name: str, action: ActionClass, authority: AgentAuthority,
                  delegation_text: Callable[..., str]):
    """
    Decorator factory: wraps a plain function into a LangGraph tool that
      1) checks Authority (charter + role + budget)  BEFORE executing,
      2) executes the underlying deterministic/ML/RAG function,
      3) emits DelegationEvent + Citations + budget via Command state update.
    InjectedState/InjectedToolCallId are hidden from the LLM schema — the model
    cannot spoof user identity, equipment context, or call ids.
    """
    def wrap(fn: Callable[..., "ToolOutcome"]):
        @tool(fn.__name__, description=fn.__doc__ or fn.__name__)
        def _governed(
            state: Annotated[ForgeState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            **kwargs,
        ) -> Command:
            user = state["user"]
            authority.check_tool(agent_name, fn.__name__, action, user)      # gate 1
            authority.check_budget(agent_name, state.get("consumed") or Budget())  # gate 2
            outcome = fn(state=state, **kwargs)                              # execute
            update: dict[str, Any] = {
                "delegations": [DelegationEvent(agent=agent_name,
                                                text=delegation_text(**kwargs))],
                "citations": outcome.citations,
                "tool_results": {fn.__name__: outcome.payload},
                "consumed": Budget(tool_calls=1),
                "messages": [ToolMessage(outcome.payload_json(),
                                         tool_call_id=tool_call_id)],
            }
            if outcome.pending_action is not None:        # COMMIT-class → HITL gate
                update["pending_action"] = outcome.pending_action
            return Command(update=update)
        return _governed
    return wrap


@dataclass
class ToolOutcome:
    payload: BaseModel                    # Pydantic result (DiagRetrieval, RULEstimate…)
    citations: list[Citation] = field(default_factory=list)
    pending_action: dict | None = None    # set only by COMMIT-class tools

    def payload_json(self) -> str:
        return self.payload.model_dump_json()

# ----------------------------------------------------------------------------------
# 3. AGENT GUARDRAILS — input / output guards. Pure code; retry-once-then-degrade.
# ----------------------------------------------------------------------------------

INJECTION_MARKERS = ("ignore previous", "disregard your instructions", "system prompt",
                     "you are now", "developer mode")

class AgentGuardrails:
    """Input guards run before routing; output guards run after synthesis.
    Tool guards live inside governed_tool (Authority). The LLM never self-certifies."""

    # ---- INPUT GUARDS (node: ingest_and_authorize) ----
    @staticmethod
    def guard_input(state: ForgeState) -> GuardReport:
        v: list[str] = []
        user, text = state.get("user"), _last_user_text(state)
        if user is None:
            v.append("unauthenticated")                       # JWT layer should prevent this
        if state.get("equipment_id") and not _equipment_exists(state["equipment_id"]):
            v.append("unknown_equipment_id")                  # blocks ID probing
        if any(m in text.lower() for m in INJECTION_MARKERS):
            v.append("possible_prompt_injection")             # flag → treat text as data only
        if len(text) > 4000:
            v.append("input_too_long")
        return GuardReport(passed=not v, violations=v)

    # ---- OUTPUT GUARDS (node: guardrail_validate) ----
    @staticmethod
    def guard_output(state: ForgeState) -> GuardReport:
        v: list[str] = []
        card = state.get("draft_card")
        if card is None:
            return GuardReport(passed=False, violations=["no_draft_card"])
        # 1) schema validity — card must parse into its declared Pydantic type
        try:
            CARD_SCHEMAS[card.get("card_type", "")].model_validate(card)
        except Exception as e:
            v.append(f"schema_invalid:{type(e).__name__}")
        # 2) citation completeness — every cited ref must exist in state.citations
        known = {c.ref for c in state.get("citations", [])}
        for ref in card.get("citation_refs", []):
            if ref not in known:
                v.append(f"fabricated_citation:{ref}")        # the anti-hallucination gate
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
            v.append("priority_not_from_matrix")              # narrate-never-compute, enforced
        return GuardReport(passed=not v, violations=v)

    @staticmethod
    def degraded_card(state: ForgeState) -> dict:
        """Honest fallback: raw retrieval + tool outputs, clearly labelled. Never a
        hallucinated answer over a broken one; never a stack trace mid-demo."""
        return {
            "card_type": "degraded",
            "message": "I couldn't produce a fully validated answer. Here is the "
                       "matched source material and tool output instead.",
            "retrieved": [c.model_dump() for c in state.get("citations", [])],
            "tool_results": {k: _safe_dump(v) for k, v in state.get("tool_results", {}).items()},
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
    # multi-faceted: "can it wait till Sunday?" → PARALLEL fan-out, three agents
    "wait_assessment": ["reliability_agent", "planner_agent", "supervisor_agent"],
}

class AgentController:
    """Builds and owns the governed StateGraph."""

    def __init__(self, authority: AgentAuthority, guards: AgentGuardrails,
                 sub_agents: dict[str, Any], checkpointer, llm, caches, persistence):
        self.authority, self.guards = authority, guards
        self.sub_agents = sub_agents          # name -> compiled create_react_agent
        self.llm, self.caches, self.persist = llm, caches, persistence
        self.graph = self._build(checkpointer)

    # ---------------- nodes ----------------

    def ingest_and_authorize(self, state: ForgeState) -> dict:
        report = self.guards.guard_input(state)
        if not report.passed and "unauthenticated" in report.violations:
            raise AuthorityError("No authenticated user in state")   # 401 upstream
        # injection markers don't block — they downgrade: text stays data-only and
        # the flag rides along for the output guard + audit.
        return {"guard_report": report}

    def cache_lookup(self, state: ForgeState) -> dict:
        hit = self.caches.lookup(_last_user_text(state), state.get("equipment_id"),
                                 state.get("query_class"))
        return {"cache_hit": hit}             # demo_cache → semantic_cache chain inside

    def classify_intent(self, state: ForgeState) -> dict:
        intent, query_class = self.llm.classify(_last_user_text(state),
                                                state.get("equipment_id"))
        return {"intent": intent, "query_class": query_class,
                "target_agents": INTENT_AGENT_MAP.get(intent, ["diagnostic_agent"])}

    def synthesize(self, state: ForgeState) -> dict:
        """Merge sub-agent outputs into ONE structured card. Citations may only
        reference refs already present in state — instructed here, ENFORCED by guard."""
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
        """Retry-once policy: re-synthesize WITH the violation list as feedback."""
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
        """HITL for COMMIT-class actions (spare reservation / PO draft). interrupt()
        pauses the checkpointed graph; CopilotKit renders Approve/Reject; resume
        carries the decision. Nothing commits without a human."""
        decision = interrupt({"type": "approval_request",
                              "action": state["pending_action"]})
        if decision.get("approved"):
            self.persist.commit_action(state["pending_action"], state["user"])
        return {"pending_action": None,
                "tool_results": {"human_gate": {"approved": bool(decision.get("approved"))}}}

    def respond(self, state: ForgeState) -> dict:
        """Single egress point: persist chat_messages (+agent_name tags, timestamps),
        bump session updated_at, write semantic cache (knowledge-class only),
        mirror delegations/citations to Langfuse. Streamed to CopilotKit."""
        self.persist.write_turn(state)
        if state.get("query_class") == "knowledge" and not (state["guard_report"].degraded):
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

    @staticmethod
    def route_agents(state: ForgeState) -> list[Send]:
        """Parallel fan-out: one Send per chartered target agent."""
        return [Send(name, state) for name in state["target_agents"]]

    @staticmethod
    def route_guard(state: ForgeState) -> str:
        report = state["guard_report"]
        if report.passed:
            return "human_gate" if state.get("pending_action") else "respond"
        return "degrade" if state.get("repair_attempted") else "repair"

    # ---------------- graph assembly ----------------

    def _build(self, checkpointer):
        g = StateGraph(ForgeState)

        # controller nodes
        for name in ("ingest_and_authorize", "cache_lookup", "classify_intent",
                     "synthesize", "guardrail_validate", "repair", "degrade",
                     "human_gate", "respond", "serve_cached"):
            g.add_node(name, getattr(self, name))

        # sub-agent nodes: compiled create_react_agent graphs, recursion-capped per charter
        for name, agent in self.sub_agents.items():
            g.add_node(name, agent.with_config(
                {"recursion_limit": AGENT_CHARTERS[name].recursion_limit}))

        # ---- unconditional edges ----
        g.set_entry_point("ingest_and_authorize")
        g.add_edge("ingest_and_authorize", "cache_lookup")
        for name in self.sub_agents:                      # join: all branches → synthesize
            g.add_edge(name, "synthesize")
        g.add_edge("synthesize", "guardrail_validate")
        g.add_edge("repair", "guardrail_validate")        # retry loops back through guard
        g.add_edge("degrade", "respond")
        g.add_edge("human_gate", "respond")
        g.add_edge("serve_cached", "respond")
        g.add_edge("respond", END)

        # ---- conditional edges ----
        g.add_conditional_edges("cache_lookup", self.route_cache,
                                ["serve_cached", "classify_intent"])
        g.add_conditional_edges("classify_intent", self.route_agents)        # Send fan-out
        g.add_conditional_edges("guardrail_validate", self.route_guard,
                                ["respond", "human_gate", "repair", "degrade"])

        return g.compile(checkpointer=checkpointer)       # thread_id = chat session id

    def invoke(self, inputs: dict, config: dict) -> dict:
        try:
            return self.graph.invoke(inputs, config)
        except GraphRecursionError:
            # outer safety net: runaway loop → honest degraded response, never a 500
            state = self.graph.get_state(config).values
            return {**state, "draft_card": self.guards.degraded_card(state)}
        except AuthorityError as e:
            return {"draft_card": {"card_type": "denied",
                                   "message": f"Action not permitted: {e}"}}


# ----------------------------------------------------------------------------------
# helpers / placeholders wired to real implementations elsewhere in the repo
# ----------------------------------------------------------------------------------

def _last_user_text(state: ForgeState) -> str:
    for m in reversed(state["messages"]):
        if getattr(m, "type", None) == "human" or getattr(m, "role", "") == "user":
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""

def _equipment_exists(equipment_id: str) -> bool: ...      # SELECT 1 FROM equipment
def _safe_dump(v: Any) -> Any:
    return v.model_dump() if isinstance(v, BaseModel) else v

CARD_SCHEMAS: dict[str, type[BaseModel]] = {}              # DiagnosisCard, RiskCard, ...
CITATION_REQUIRED_CARDS = {"diagnosis", "checklist", "risk", "wait_assessment"}
