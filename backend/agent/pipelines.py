"""
ForgeSight — charter PIPELINES (deterministic tool sequences, NOT ReAct loops).
==============================================================================
forgesight-v3-final.md §1.3 / BUILD_GUIDE §5.4: each agent's tool order is fully determined by
intent, so we replace "LLM decides the next tool" with "the charter defines the pipeline". This
keeps Authority enforcement + audit identical to governed_tool (check_tool + check_budget BEFORE
each call) while removing the one capability that demanded a large hosted model. The SLM is
invoked only later at the controller's synthesize node.

Each pipeline is a RunnableLambda so it plugs into the controller exactly where the provided
graph expects a sub-agent (`agent.with_config({"recursion_limit": ...})`) and returns the same
reducer-channel updates: delegations · citations · tool_results · consumed.

Pass 1 ships the Diagnostic pipeline (retrieve_rag → match_history). The Reliability / Supervisor
/ Planner pipelines follow the same template in Pass 2/3.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.runnables import RunnableLambda

from backend.agent.governance import ActionClass, AgentAuthority
from backend.schemas.agent_models import Budget, Citation, DelegationEvent, sum_budget
from backend.tools.deterministic import procurement_rule, score_priority
from backend.tools.ml_tools import check_equipment_health, estimate_rul
from backend.tools.rag import match_history, retrieve_rag, to_citations
from backend.tools.spares import check_spares
from backend.tools.text_to_sql import query_records

_FAULT_RE = re.compile(r"\b([A-Z]{2,}-[A-Z0-9-]*\d{2,}|[A-Z]?\d{3,5})\b")


def _last_user_text(state: dict) -> str:
    for m in reversed(state.get("messages", [])):
        role = getattr(m, "type", None) or getattr(m, "role", None) or (
            m.get("role") if isinstance(m, dict) else None)
        if role in ("human", "user"):
            content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
            return content if isinstance(content, str) else str(content)
    return ""


def _extract_fault_code(text: str) -> str | None:
    m = _FAULT_RE.search(text or "")
    return m.group(1) if m else None


def _fetch_equipment(conn, equipment_id: str | None) -> dict | None:
    if not equipment_id:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, zone, criticality FROM equipment WHERE id = %s",
                    (equipment_id,))
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "zone": row[2], "criticality": row[3]}


def make_diagnostic_pipeline(authority: AgentAuthority, pool) -> RunnableLambda:
    """Diagnostic Agent: retrieve_rag (manuals/SOPs) → match_history (verified-first records).
    Pure code orders the tools; Authority re-checks each at runtime (audited)."""
    agent = "diagnostic_agent"

    def _run(state: dict) -> dict:
        user = state["user"]
        eq = state.get("equipment_id")
        query = _last_user_text(state)
        fault = _extract_fault_code(query)

        delegations: list[DelegationEvent] = []
        citations: list = []
        tool_results: dict[str, Any] = {}
        consumed = state.get("consumed") or Budget()

        with pool.connection() as conn:
            tool_results["_equipment"] = _fetch_equipment(conn, eq)

            # --- step 1: retrieve_rag (manuals + SOPs) ---
            authority.check_tool(agent, "retrieve_rag", ActionClass.READ, user)
            authority.check_budget(agent, consumed)
            chunks = retrieve_rag(conn, query, equipment_id=eq,
                                  doc_types=["manual", "sop"], k=6)
            citations += to_citations(chunks)
            tool_results["retrieve_rag"] = [
                {"ref": c.section_ref, "excerpt": c.content, "doc_type": c.doc_type}
                for c in chunks
            ]
            delegations.append(DelegationEvent(
                agent=agent, text=f"searching manuals & SOPs for {fault or 'the fault'}…"))
            consumed = sum_budget(consumed, Budget(tool_calls=1))

            # --- step 2: match_history (similar past breakdowns, verified-first) ---
            authority.check_tool(agent, "match_history", ActionClass.READ, user)
            authority.check_budget(agent, consumed)
            records = match_history(conn, equipment_id=eq or "", fault_code=fault,
                                    symptoms=query, k=4)
            citations += to_citations(records)
            tool_results["match_history"] = [
                {"ref": r.section_ref.replace(" [VERIFIED]", ""), "excerpt": r.content,
                 "fault_code": fault, "verified": "[VERIFIED]" in r.section_ref}
                for r in records
            ]
            delegations.append(DelegationEvent(
                agent=agent, text="matching past breakdown records…"))

        return {
            "delegations": delegations,
            "citations": citations,
            "tool_results": tool_results,
            "consumed": Budget(tool_calls=2),       # this node's delta (reducer sums across branches)
        }

    return RunnableLambda(_run, name=agent)


def _equipment_row(conn, eq: str | None) -> dict | None:
    if not eq:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, zone, criticality FROM equipment WHERE id = %s", (eq,))
        r = cur.fetchone()
    return {"id": r[0], "name": r[1], "zone": r[2], "criticality": r[3]} if r else None


def make_reliability_pipeline(authority: AgentAuthority, pool) -> RunnableLambda:
    """Reliability Agent: check_equipment_health → estimate_rul (narrates ML tool outputs)."""
    agent = "reliability_agent"

    def _run(state: dict) -> dict:
        user, eq = state["user"], state.get("equipment_id")
        deleg, cites, tr = [], [], {}
        with pool.connection() as conn:
            tr["_equipment"] = _equipment_row(conn, eq)
            authority.check_tool(agent, "check_equipment_health", ActionClass.READ, user)
            authority.check_budget(agent, state.get("consumed") or Budget())
            health = check_equipment_health(conn, eq or "")
            tr["check_equipment_health"] = health.model_dump()
            cites.append(Citation(kind="model_output", ref="IsolationForest anomaly scan"))
            deleg.append(DelegationEvent(agent=agent, text=f"scanning health (score {health.anomaly_score})…"))

            authority.check_tool(agent, "estimate_rul", ActionClass.READ, user)
            rul = estimate_rul(conn, eq or "")
            tr["estimate_rul"] = rul.model_dump()
            cites.append(Citation(kind="trend", ref=f"{eq} vibration trend → {rul.target_limit_mm_s} mm/s"))
            deleg.append(DelegationEvent(agent=agent, text=f"projecting RUL ≈ {rul.rul_days} d…"))
        return {"delegations": deleg, "citations": cites, "tool_results": tr,
                "consumed": Budget(tool_calls=2)}

    return RunnableLambda(_run, name=agent)


def make_supervisor_pipeline(authority: AgentAuthority, pool) -> RunnableLambda:
    """Supervisor Agent: score_priority (deterministic) → narration. Never computes the score."""
    agent = "supervisor_agent"

    def _run(state: dict) -> dict:
        user, eq = state["user"], state.get("equipment_id")
        deleg, cites, tr = [], [], {}
        with pool.connection() as conn:
            row = _equipment_row(conn, eq)
            tr["_equipment"] = row
            spares = check_spares(conn, eq or "")
            in_stock = any(s.stock_qty > 0 for s in spares)
            lead = min((s.lead_time_days for s in spares), default=0)
            rul = None
            try:
                rul = estimate_rul(conn, eq or "").rul_days
            except Exception:  # noqa: BLE001
                pass
            authority.check_tool(agent, "score_priority", ActionClass.READ, user)
            authority.check_budget(agent, state.get("consumed") or Budget())
            result = score_priority(criticality=(row or {}).get("criticality", 5) or 5,
                                    delay_severity=7.0, spares_in_stock=in_stock,
                                    lead_time_days=lead, rul_days=rul)
            tr["score_priority"] = result.model_dump()
            cites.append(Citation(kind="priority_matrix", ref="deterministic priority matrix"))
            deleg.append(DelegationEvent(agent=agent, text=f"scoring urgency → {result.priority_score}/100…"))
        return {"delegations": deleg, "citations": cites, "tool_results": tr,
                "consumed": Budget(tool_calls=1)}

    return RunnableLambda(_run, name=agent)


def make_planner_pipeline(authority: AgentAuthority, pool) -> RunnableLambda:
    """Planner Agent: check_spares → procurement_rule (→ propose_reservation as a COMMIT)."""
    agent = "planner_agent"

    def _run(state: dict) -> dict:
        user, eq = state["user"], state.get("equipment_id")
        query = _last_user_text(state).lower()
        deleg, cites, tr = [], [], {}
        update: dict[str, Any] = {}
        with pool.connection() as conn:
            tr["_equipment"] = _equipment_row(conn, eq)
            authority.check_tool(agent, "check_spares", ActionClass.READ, user)
            authority.check_budget(agent, state.get("consumed") or Budget())
            spares = check_spares(conn, eq or "")
            tr["check_spares"] = [s.model_dump() for s in spares]
            for s in spares:
                cites.append(Citation(kind="spares_record", ref=s.part_no))
            deleg.append(DelegationEvent(agent=agent, text="checking spares stock & lead time…"))

            rul = None
            try:
                rul = estimate_rul(conn, eq or "").rul_days
            except Exception:  # noqa: BLE001
                pass
            top = spares[0] if spares else None
            if top:
                authority.check_tool(agent, "procurement_rule", ActionClass.READ, user)
                decision = procurement_rule(lead_time_days=top.lead_time_days, rul_days=rul,
                                            stock_qty=top.stock_qty)
                tr["procurement_rule"] = decision.model_dump()
                deleg.append(DelegationEvent(agent=agent, text=f"procurement rule → {decision.action}"))
                # COMMIT only when the user explicitly asks to reserve/order (HITL gate)
                if decision.action in ("reserve_now", "order_now") and any(
                        w in query for w in ("reserve", "go ahead", "order", "raise a po", "approve")):
                    authority.check_tool(agent, "propose_reservation", ActionClass.COMMIT, user)
                    update["pending_action"] = {
                        "type": "reserve_spare", "part_no": top.part_no,
                        "equipment_id": eq, "qty": 1, "session_id": state.get("session_id"),
                        "rationale": decision.rationale}
        return {"delegations": deleg, "citations": cites, "tool_results": tr,
                "consumed": Budget(tool_calls=3), **update}

    return RunnableLambda(_run, name=agent)


def make_analyst_pipeline(authority: AgentAuthority, pool, llm=None) -> RunnableLambda:
    """Analyst Agent (§1.7b): query_records — governed text-to-SQL over curated read-only views.
    The generated SELECT is the citation; rows are returned verbatim (no SLM number invention)."""
    agent = "analyst_agent"

    def _run(state: dict) -> dict:
        user = state["user"]
        query = _last_user_text(state)
        deleg, cites, tr = [], [], {}
        with pool.connection() as conn:
            authority.check_tool(agent, "query_records", ActionClass.READ, user)
            authority.check_budget(agent, state.get("consumed") or Budget())
            result = query_records(conn, query, llm=llm)
            tr["query_records"] = result
            if result.get("sql"):
                cites.append(Citation(kind="sql_query", ref=result["sql"]))
            deleg.append(DelegationEvent(
                agent=agent, text=f"querying records — {result.get('narration', '')[:60]}"))
        return {"delegations": deleg, "citations": cites, "tool_results": tr,
                "consumed": Budget(tool_calls=1)}

    return RunnableLambda(_run, name=agent)


def build_sub_agents(authority: AgentAuthority, pool, llm=None) -> dict[str, RunnableLambda]:
    """Name → pipeline runnable, consumed by AgentController. All five chartered agents."""
    return {
        "diagnostic_agent": make_diagnostic_pipeline(authority, pool),
        "reliability_agent": make_reliability_pipeline(authority, pool),
        "supervisor_agent": make_supervisor_pipeline(authority, pool),
        "planner_agent": make_planner_pipeline(authority, pool),
        "analyst_agent": make_analyst_pipeline(authority, pool, llm),
    }
