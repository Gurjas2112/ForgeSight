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
from backend.schemas.agent_models import Budget, DelegationEvent, sum_budget
from backend.tools.rag import match_history, retrieve_rag, to_citations

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


def build_sub_agents(authority: AgentAuthority, pool) -> dict[str, RunnableLambda]:
    """Name → pipeline runnable, consumed by AgentController. Pass 1: diagnostic only."""
    return {
        "diagnostic_agent": make_diagnostic_pipeline(authority, pool),
        # Pass 2/3: reliability_agent, supervisor_agent, planner_agent
    }
