"""Unified evidence search across docs, incidents, spares, work orders, sensor events."""

from __future__ import annotations

from typing import Any

from backend.tools.rag import retrieve_rag


def unified_search(
    conn,
    *,
    q: str = "",
    types: list[str] | None = None,
    equipment_id: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return ranked search hits with citation-compatible refs."""
    items: list[dict[str, Any]] = []
    want = set(types or ["manual", "sop", "report", "incident", "spare", "work_order", "sensor"])

    if q.strip() and want & {"manual", "sop", "report"}:
        doc_types = [t for t in ("manual", "sop", "report") if t in want]
        for ch in retrieve_rag(conn, q, equipment_id=equipment_id, doc_types=doc_types or None, k=limit):
            items.append({
                "type": ch.doc_type,
                "ref": ch.section_ref,
                "title": ch.section_ref,
                "excerpt": ch.content[:240].replace("\n", " "),
                "equipment_id": equipment_id,
                "ts": None,
                "score": round(ch.score, 4),
            })

    if want & {"incident"}:
        sql = (
            "SELECT id, equipment_id, occurred_at, fault_code, symptoms, root_cause "
            "FROM breakdown_history WHERE (%s::text IS NULL OR equipment_id = %s) "
        )
        params: list[Any] = [equipment_id, equipment_id]
        if q.strip():
            sql += "AND (fault_code ILIKE %s OR symptoms ILIKE %s OR root_cause ILIKE %s OR id ILIKE %s) "
            like = f"%{q}%"
            params.extend([like, like, like, like])
        sql += "ORDER BY occurred_at DESC NULLS LAST LIMIT %s"
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                items.append({
                    "type": "incident",
                    "ref": r[0],
                    "title": f"{r[3] or 'Incident'} — {r[0]}",
                    "excerpt": (r[4] or r[5] or "")[:240],
                    "equipment_id": r[1],
                    "ts": str(r[2]) if r[2] else None,
                    "score": 0.8,
                })

    if want & {"spare"}:
        sql = (
            "SELECT part_no, equipment_id, description, stock_qty, lead_time_days "
            "FROM spares WHERE (%s::text IS NULL OR equipment_id = %s) "
        )
        params = [equipment_id, equipment_id]
        if q.strip():
            sql += "AND (part_no ILIKE %s OR description ILIKE %s) "
            like = f"%{q}%"
            params.extend([like, like])
        sql += "ORDER BY part_no LIMIT %s"
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                items.append({
                    "type": "spare",
                    "ref": r[0],
                    "title": f"{r[0]} — {r[2]}",
                    "excerpt": f"Stock {r[3]} · lead {r[4]} d",
                    "equipment_id": r[1],
                    "ts": None,
                    "score": 0.7,
                })

    if want & {"work_order"}:
        sql = (
            "SELECT id, equipment_id, title, description, status, created_at "
            "FROM work_orders WHERE status NOT IN ('completed','cancelled') "
            "AND (%s::text IS NULL OR equipment_id = %s) "
        )
        params = [equipment_id, equipment_id]
        if q.strip():
            sql += "AND (title ILIKE %s OR description ILIKE %s) "
            like = f"%{q}%"
            params.extend([like, like])
        sql += "ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                items.append({
                    "type": "work_order",
                    "ref": str(r[0]),
                    "title": r[2],
                    "excerpt": (r[3] or "")[:240],
                    "equipment_id": r[1],
                    "ts": str(r[5]),
                    "score": 0.75,
                })

    if want & {"sensor"}:
        sql = (
            "SELECT e.id, e.name, h.anomaly_score, h.contributing_sensors, h.computed_at "
            "FROM equipment e JOIN equipment_health h ON h.equipment_id = e.id "
            "WHERE h.is_anomalous = true AND (%s::text IS NULL OR e.id = %s) "
        )
        params = [equipment_id, equipment_id]
        if q.strip():
            sql += "AND (e.name ILIKE %s OR e.id ILIKE %s) "
            like = f"%{q}%"
            params.extend([like, like])
        sql += "ORDER BY h.anomaly_score DESC LIMIT %s"
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                sensors = ", ".join(r[3] or []) if r[3] else "—"
                items.append({
                    "type": "sensor",
                    "ref": f"trend-{r[0]}",
                    "title": f"Anomaly — {r[1]}",
                    "excerpt": f"Score {r[2]} · contributing: {sensors}",
                    "equipment_id": r[0],
                    "ts": str(r[4]) if r[4] else None,
                    "score": float(r[2] or 0),
                })

    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return items[:limit]
