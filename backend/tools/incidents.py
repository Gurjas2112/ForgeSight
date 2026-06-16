"""Incident replay and lessons learned from breakdown_history."""

from __future__ import annotations

from typing import Any

from backend.tools.plant_summary import BASE_INR_PER_HR
from backend.tools.rag import match_history


def _impact_inr(downtime_hrs: float | None, criticality: int) -> float:
    hrs = float(downtime_hrs or 8.0)
    return hrs * BASE_INR_PER_HR * float(criticality or 1)


def list_incidents(conn, *, equipment_id: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT b.id, b.equipment_id, e.name, e.criticality, b.occurred_at, b.fault_code, "
        "b.symptoms, b.root_cause, b.downtime_hrs, b.verified "
        "FROM breakdown_history b LEFT JOIN equipment e ON e.id = b.equipment_id "
        "WHERE (%s::text IS NULL OR b.equipment_id = %s) ORDER BY b.occurred_at DESC LIMIT 30"
    )
    with conn.cursor() as cur:
        cur.execute(sql, (equipment_id, equipment_id))
        rows = cur.fetchall()
    return [{
        "id": r[0],
        "equipment_id": r[1],
        "equipment_name": r[2],
        "criticality": r[3],
        "occurred_at": str(r[4]) if r[4] else None,
        "fault_code": r[5],
        "symptoms": r[6],
        "root_cause": r[7],
        "downtime_hrs": r[8],
        "verified": r[9],
        "production_impact_inr": _impact_inr(r[8], r[3] or 1),
        "production_impact_label": _inr_label(_impact_inr(r[8], r[3] or 1)),
    } for r in rows]


def _inr_label(inr: float) -> str:
    if inr >= 100_000:
        return f"₹{round(inr / 100_000)}L"
    if inr >= 1_000:
        return f"₹{round(inr / 1_000)}K"
    return f"₹{int(round(inr))}"


def get_incident(conn, incident_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT b.id, b.equipment_id, e.name, e.zone, e.criticality, b.occurred_at, "
            "b.fault_code, b.symptoms, b.root_cause, b.resolution, b.downtime_hrs, b.verified "
            "FROM breakdown_history b LEFT JOIN equipment e ON e.id = b.equipment_id WHERE b.id = %s",
            (incident_id,),
        )
        r = cur.fetchone()
    if not r:
        return None
    impact = _impact_inr(r[10], r[4] or 1)
    return {
        "id": r[0],
        "equipment_id": r[1],
        "equipment_name": r[2],
        "zone": r[3],
        "criticality": r[4],
        "occurred_at": str(r[5]) if r[5] else None,
        "fault_code": r[6],
        "symptoms": r[7],
        "root_cause": r[8],
        "resolution": r[9],
        "downtime_hrs": r[10],
        "verified": r[11],
        "production_impact_inr": impact,
        "production_impact_label": _inr_label(impact),
        "failure_progression": [
            {"stage": "Symptoms observed", "detail": r[7]},
            {"stage": "Root cause identified", "detail": r[8]},
            {"stage": "Corrective action", "detail": r[9]},
        ],
    }


def incident_replay(conn, incident_id: str) -> dict | None:
    inc = get_incident(conn, incident_id)
    if not inc or not inc.get("occurred_at"):
        return None
    eq_id = inc["equipment_id"]
    occurred = inc["occurred_at"]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ts, vibration_de, bearing_temp, motor_current FROM sensor_readings "
            "WHERE equipment_id = %s AND ts BETWEEN %s::date - interval '7 days' "
            "AND %s::date + interval '7 days' ORDER BY ts",
            (eq_id, occurred, occurred),
        )
        sensors = [{"ts": str(r[0]), "vibration_de": float(r[1] or 0),
                    "bearing_temp": float(r[2] or 0), "motor_current": float(r[3] or 0)}
                   for r in cur.fetchall()]
    similar = []
    if inc.get("fault_code"):
        try:
            for ch in match_history(conn, eq_id, fault_code=inc["fault_code"], k=5):
                similar.append({"ref": ch.section_ref, "excerpt": ch.content[:200], "score": ch.score})
        except Exception:  # noqa: BLE001
            pass
    return {"incident": inc, "sensors": sensors, "similar_failures": similar}


def incident_lessons(conn, incident_id: str) -> dict:
    inc = get_incident(conn, incident_id)
    if not inc:
        return {"lessons": [], "logbook": []}
    fault = inc.get("fault_code")
    lessons = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, equipment_id, occurred_at, root_cause, resolution, verified "
            "FROM breakdown_history WHERE fault_code = %s AND id != %s AND verified = true "
            "ORDER BY occurred_at DESC LIMIT 5",
            (fault, incident_id),
        )
        for r in cur.fetchall():
            lessons.append({
                "id": r[0], "equipment_id": r[1], "occurred_at": str(r[2]),
                "root_cause": r[3], "resolution": r[4], "verified": r[5],
            })
        cur.execute(
            "SELECT id, content, created_at FROM logbook WHERE equipment_id = %s "
            "ORDER BY created_at DESC LIMIT 10",
            (inc["equipment_id"],),
        )
        logbook = [{"id": str(r[0]), "content": r[1], "created_at": str(r[2])} for r in cur.fetchall()]
    return {"lessons": lessons, "logbook": logbook, "fault_code": fault}
