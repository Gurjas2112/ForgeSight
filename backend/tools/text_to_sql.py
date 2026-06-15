"""
ForgeSight — governed text-to-SQL (§1.7b). Answers open-ended ANALYTICAL questions over records
and logs that no fixed tool pre-covers ("how many F3 trips and the most common root cause?",
"which equipment had the most downtime?", "list unacked critical alerts"). RAG retrieves
documents; this counts and aggregates.

Guarantees (structural, not prompted):
  - reaches ONLY four curated read-only VIEWS (whitelist below) — raw tables unreachable;
  - SELECT-only: any write keyword / multiple statements / non-whitelisted name is rejected;
  - EXPLAIN-validated before execution; the SQL is RETURNED and shown (visible query = explainability)
    and becomes the card's citation.
Generation is template-first (deterministic, demo-safe); an optional SLM pass is validated by the
same guards, so an unreliable model can never produce an unsafe or hallucinated query.
"""
from __future__ import annotations

import re

ALLOWED_VIEWS = ("v_breakdown_stats", "v_spares_status", "v_alert_feed", "v_downtime_by_equipment")
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|merge|copy|"
    r"call|do|vacuum|analyze)\b", re.IGNORECASE)
_VIEW_TOKEN = re.compile(r"\b(v_[a-z_]+)\b", re.IGNORECASE)

SCHEMA_HINT = (
    "v_breakdown_stats(equipment_id, fault_code, occurrences, avg_downtime_hrs, last_seen) · "
    "v_spares_status(part_no, equipment_id, equipment_name, description, stock_qty, lead_time_days, supplier) · "
    "v_alert_feed(id, equipment_id, equipment_name, severity, title, target_role, created_at, acknowledged) · "
    "v_downtime_by_equipment(equipment_id, equipment_name, total_downtime_hrs, breakdowns)")


def _template_sql(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("downtime", "down time", "lost time")):
        return ("SELECT equipment_name, total_downtime_hrs, breakdowns "
                "FROM v_downtime_by_equipment ORDER BY total_downtime_hrs DESC NULLS LAST LIMIT 10")
    if any(w in q for w in ("spare", "stock", "lead time", "procure", "part")):
        return ("SELECT part_no, equipment_name, stock_qty, lead_time_days, supplier "
                "FROM v_spares_status ORDER BY lead_time_days DESC LIMIT 10")
    if any(w in q for w in ("alert", "unack", "critical", "warning", "open issue")):
        return ("SELECT severity, equipment_name, title, created_at, acknowledged "
                "FROM v_alert_feed ORDER BY created_at DESC LIMIT 10")
    # default: breakdown / trip / fault / root-cause frequency
    return ("SELECT equipment_id, fault_code, occurrences, avg_downtime_hrs, last_seen "
            "FROM v_breakdown_stats ORDER BY occurrences DESC LIMIT 10")


def is_safe_select(sql: str) -> tuple[bool, str]:
    """Structural SELECT-only + whitelist guard. Returns (ok, reason)."""
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        return False, "multiple_statements"
    if "--" in s or "/*" in s:
        return False, "sql_comment"
    if not re.match(r"(?is)^\s*(select|with)\b", s):
        return False, "not_select_only"
    if _FORBIDDEN.search(s):
        return False, "write_keyword"
    views = {v.lower() for v in _VIEW_TOKEN.findall(s)}
    # every v_* token referenced must be whitelisted; and at least one whitelisted view present
    if not views or not views.issubset({v.lower() for v in ALLOWED_VIEWS}):
        return False, "non_whitelisted_view"
    if not any(v in s.lower() for v in ALLOWED_VIEWS):
        return False, "no_whitelisted_view"
    return True, "ok"


def generate_sql(question: str, llm=None) -> str:
    """Template-first SQL; optional SLM refinement validated by the same guard (falls back on fail)."""
    base = _template_sql(question)
    if llm is None:
        return base
    try:
        sys_msg = (
            "You translate a maintenance question into ONE read-only PostgreSQL SELECT over EXACTLY "
            "these views (no other tables, no writes):\n" + SCHEMA_HINT +
            "\nReturn ONLY JSON: {\"sql\": \"SELECT ...\"}. Always add an ORDER BY and LIMIT 10.")
        data = llm._chat_json(  # reuse the synthesizer's backend-agnostic JSON call
            {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
            sys_msg, f"QUESTION: {question}", temperature=0)
        cand = (data.get("sql") or "").strip()
        ok, _ = is_safe_select(cand)
        return cand if ok else base
    except Exception:  # noqa: BLE001 — any SLM failure → deterministic template
        return base


def query_records(conn, question: str, llm=None, k: int = 10) -> dict:
    """Generate → guard → EXPLAIN → execute. Returns a SqlCard-ready dict (rows verbatim)."""
    sql = generate_sql(question, llm)
    ok, reason = is_safe_select(sql)
    if not ok:
        return {"ok": False, "error": reason, "sql": sql, "question": question,
                "columns": [], "rows": [], "narration": f"Query rejected by guard ({reason})."}
    try:
        with conn.cursor() as cur:
            cur.execute("EXPLAIN " + sql)          # validate plan before running
            cur.execute(sql)
            columns = [d.name for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(k)]
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"execution_error:{type(e).__name__}", "sql": sql,
                "question": question, "columns": [], "rows": [],
                "narration": "The analytical query could not be executed."}
    return {"ok": True, "sql": sql, "question": question, "columns": columns,
            "rows": [[_jsonable(v) for v in row] for row in rows],
            "narration": f"Returned {len(rows)} row(s) from {_view_of(sql)}."}


def _view_of(sql: str) -> str:
    m = _VIEW_TOKEN.search(sql)
    return m.group(1) if m else "the analytics views"


def _jsonable(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)
