"""Work order CRUD and export helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.tools.reports import generate_work_order_report


def _row_to_wo(r) -> dict[str, Any]:
    return {
        "id": str(r[0]),
        "equipment_id": r[1],
        "alert_id": str(r[2]) if r[2] else None,
        "session_id": str(r[3]) if r[3] else None,
        "title": r[4],
        "description": r[5],
        "status": r[6],
        "priority": r[7],
        "assignee": str(r[8]) if r[8] else None,
        "steps": r[9] or [],
        "created_at": str(r[10]),
        "updated_at": str(r[11]),
        "completed_at": str(r[12]) if r[12] else None,
    }


def list_work_orders(conn, *, equipment_id: str | None = None, status: str | None = None) -> list[dict]:
    sql = (
        "SELECT wo.id, wo.equipment_id, wo.alert_id, wo.session_id, wo.title, wo.description, "
        "wo.status, wo.priority, wo.assignee, wo.steps, wo.created_at, wo.updated_at, wo.completed_at, "
        "e.name AS equipment_name FROM work_orders wo "
        "LEFT JOIN equipment e ON e.id = wo.equipment_id WHERE 1=1 "
    )
    params: list[Any] = []
    if equipment_id:
        sql += "AND wo.equipment_id = %s "
        params.append(equipment_id)
    if status:
        sql += "AND wo.status = %s "
        params.append(status)
    sql += "ORDER BY wo.priority DESC NULLS LAST, wo.created_at DESC LIMIT 50"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    out = []
    for r in rows:
        wo = _row_to_wo(r[:13])
        wo["equipment_name"] = r[13]
        out.append(wo)
    return out


def get_work_order(conn, wo_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT wo.id, wo.equipment_id, wo.alert_id, wo.session_id, wo.title, wo.description, "
            "wo.status, wo.priority, wo.assignee, wo.steps, wo.created_at, wo.updated_at, wo.completed_at, "
            "e.name, e.zone, e.criticality FROM work_orders wo "
            "LEFT JOIN equipment e ON e.id = wo.equipment_id WHERE wo.id = %s",
            (wo_id,),
        )
        r = cur.fetchone()
    if not r:
        return None
    wo = _row_to_wo(r[:13])
    wo["equipment_name"] = r[13]
    wo["zone"] = r[14]
    wo["criticality"] = r[15]
    return wo


def create_work_order(conn, *, equipment_id: str, title: str, description: str | None = None,
                      alert_id: str | None = None, session_id: str | None = None,
                      priority: int = 50, steps: list | None = None) -> dict:
    wo_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO work_orders (id, equipment_id, alert_id, session_id, title, description, "
            "priority, steps) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (wo_id, equipment_id, alert_id, session_id, title, description, priority,
             json.dumps(steps or [])),
        )
    return get_work_order(conn, wo_id)  # type: ignore[return-value]


def update_work_order(conn, wo_id: str, *, status: str | None = None,
                      steps: list | None = None, priority: int | None = None) -> dict | None:
    sets = ["updated_at = now()"]
    params: list[Any] = []
    if status:
        sets.append("status = %s")
        params.append(status)
        if status == "completed":
            sets.append("completed_at = now()")
    if steps is not None:
        sets.append("steps = %s")
        params.append(json.dumps(steps))
    if priority is not None:
        sets.append("priority = %s")
        params.append(priority)
    params.append(wo_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE work_orders SET {', '.join(sets)} WHERE id = %s", params)
    return get_work_order(conn, wo_id)


def export_work_order(conn, wo_id: str, fmt: str) -> tuple[bytes, str, str]:
    wo = get_work_order(conn, wo_id)
    if not wo:
        raise ValueError("work order not found")
    if fmt == "json":
        body = json.dumps(wo, indent=2).encode()
        return body, "application/json", f"work_order_{wo_id[:8]}.json"
    pdf = generate_work_order_report(wo=wo)
    return pdf, "application/pdf", f"work_order_{wo_id[:8]}.pdf"
