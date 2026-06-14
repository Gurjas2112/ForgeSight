"""
ForgeSight — audit_log writer. The single sink AgentAuthority calls for every allow/deny
decision (forgesight-v3-final.md §Tier 2: "every authority decision — allow AND deny — is
audited"). Also mirrors to Langfuse in later passes.

Design: never let auditing failure break the request path — a DB hiccup must not crash a
governance check. Failures are swallowed and the decision still stands (it was already
enforced in code); the write is best-effort.
"""

from __future__ import annotations

import json
from typing import Any

INSERT_SQL = """
INSERT INTO audit_log (user_id, agent_name, action, resource, allowed, reason, detail, ts)
VALUES (%(user_id)s, %(agent_name)s, %(action)s, %(resource)s,
        %(allowed)s, %(reason)s, %(detail)s::jsonb, COALESCE(%(ts)s::timestamptz, now()))
"""


def make_audit_sink(pool) -> "callable":
    """Return an audit_sink(decision: dict) -> None bound to a psycopg pool.

    `decision` is the dict AgentAuthority emits: agent, tool, action, user_id, role, ts,
    allowed, optional reason. We map it onto the audit_log columns.
    """

    def _sink(decision: dict[str, Any]) -> None:
        row = {
            "user_id": _as_uuid(decision.get("user_id")),
            "agent_name": decision.get("agent"),
            "action": decision.get("action"),
            "resource": decision.get("tool"),
            "allowed": bool(decision.get("allowed", False)),
            "reason": decision.get("reason"),
            "detail": json.dumps({k: v for k, v in decision.items()
                                  if k not in {"user_id", "agent", "action", "tool",
                                               "allowed", "reason", "ts"}}),
            "ts": decision.get("ts"),
        }
        try:
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(INSERT_SQL, row)
        except Exception as e:  # noqa: BLE001 — best-effort; never break the gate
            print(f"  [audit] write failed (non-fatal): {e}")

    return _sink


def _as_uuid(v: Any) -> Any:
    """Demo/system user ids may be non-UUID strings; store NULL rather than error."""
    if v is None:
        return None
    s = str(v)
    return s if (len(s) == 36 and s.count("-") == 4) else None


def console_audit_sink(decision: dict[str, Any]) -> None:
    """Stdout sink for scripts / tests without a DB (still proves allow+deny are emitted)."""
    flag = "ALLOW" if decision.get("allowed") else "DENY "
    print(f"  [audit] {flag} {decision.get('agent')}::{decision.get('tool')} "
          f"({decision.get('action')}) {('· ' + decision['reason']) if decision.get('reason') else ''}")
