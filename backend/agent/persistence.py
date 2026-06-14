"""
ForgeSight — turn persistence (respond node egress) + HITL commit.
The controller's single egress writes chat_messages (+ agent_name, timestamps), bumps the
session, and (later) mirrors to Langfuse. COMMIT-class proposals persist via commit_action only
AFTER the human_gate approves (forgesight-v3-final.md §Tier 2).

Two implementations:
  - NullPersistence    : no-op + console (scripts / tests without a session row)
  - SupabasePersistence : best-effort writes to chat_messages / pending_actions
"""

from __future__ import annotations

import json
from typing import Any


class NullPersistence:
    """Used by scripts: proves the egress path runs without requiring an auth.users session."""

    def write_turn(self, state: dict) -> None:
        card = state.get("draft_card") or {}
        n_cites = len(state.get("citations", []))
        print(f"  [persist] (null) turn → card_type={card.get('card_type')} · citations={n_cites}")

    def commit_action(self, action: dict, user: Any) -> None:
        print(f"  [persist] (null) commit_action approved: {action}")


class SupabasePersistence:
    def __init__(self, pool):
        self.pool = pool

    def write_turn(self, state: dict) -> None:
        session_id = state.get("session_id")
        card = state.get("draft_card")
        if not session_id or card is None:
            return
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                # agent_event rows for the delegation stream
                for d in state.get("delegations", []):
                    dd = d.model_dump() if hasattr(d, "model_dump") else d
                    cur.execute(
                        "INSERT INTO chat_messages (session_id, role, content, agent_name) "
                        "VALUES (%s, 'agent_event', %s, %s)",
                        (session_id, dd.get("text"), dd.get("agent")))
                # the assistant card
                cur.execute(
                    "INSERT INTO chat_messages (session_id, role, content, card_json, agent_name) "
                    "VALUES (%s, 'assistant', %s, %s::jsonb, %s)",
                    (session_id, card.get("summary") or card.get("message", ""),
                     json.dumps(card, default=str), _agent_for_card(card)))
                cur.execute("UPDATE chat_sessions SET updated_at = now() WHERE id = %s",
                            (session_id,))
        except Exception as e:  # noqa: BLE001 — egress must not crash the turn
            print(f"  [persist] write_turn failed (non-fatal): {e}")

    def commit_action(self, action: dict, user: Any) -> None:
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pending_actions (session_id, proposal, status, decided_by, decided_at) "
                    "VALUES (%s, %s::jsonb, 'approved', %s, now())",
                    (action.get("session_id"), json.dumps(action, default=str),
                     getattr(user, "id", None)))
        except Exception as e:  # noqa: BLE001
            print(f"  [persist] commit_action failed (non-fatal): {e}")


def _agent_for_card(card: dict) -> str:
    return {"diagnosis": "diagnostic_agent", "checklist": "diagnostic_agent",
            "rul": "reliability_agent", "risk": "reliability_agent",
            "priority": "supervisor_agent", "spares": "planner_agent"}.get(
        card.get("card_type", ""), "orchestrator")
