"""Predictive reliability analytics — curves, failure probability, relationship graph."""

from __future__ import annotations

from typing import Any


def reliability_for_equipment(conn, eq_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.name, e.zone, e.criticality, h.anomaly_score, h.is_anomalous, "
            "h.rul_days, h.rul_band, h.contributing_sensors FROM equipment e "
            "LEFT JOIN equipment_health h ON h.equipment_id = e.id WHERE e.id = %s",
            (eq_id,),
        )
        e = cur.fetchone()
        if not e:
            return {}
        cur.execute(
            "SELECT ts, vibration_de, bearing_temp FROM sensor_readings "
            "WHERE equipment_id = %s ORDER BY ts DESC LIMIT 288",
            (eq_id,),
        )
        sensors = [{"ts": str(r[0]), "vibration_de": float(r[1] or 0),
                    "bearing_temp": float(r[2] or 0)} for r in reversed(cur.fetchall())]
        cur.execute(
            "SELECT id, fault_code, occurred_at FROM breakdown_history "
            "WHERE equipment_id = %s ORDER BY occurred_at DESC LIMIT 5",
            (eq_id,),
        )
        incidents = [{"id": r[0], "fault_code": r[1], "occurred_at": str(r[2])} for r in cur.fetchall()]
        cur.execute("SELECT part_no, description, stock_qty FROM spares WHERE equipment_id = %s", (eq_id,))
        spares = [{"part_no": r[0], "description": r[1], "stock_qty": r[2]} for r in cur.fetchall()]

    failure_prob = min(1.0, max(0.0, float(e[4] or 0) * 0.85 + (0.15 if e[5] else 0)))
    rul_band = e[7] or {}
    band = rul_band.get("band", [None, None]) if isinstance(rul_band, dict) else [None, None]

    # trend buckets (24h rolling avg of vibration)
    trend = []
    if sensors:
        window = max(1, len(sensors) // 12)
        for i in range(0, len(sensors), window):
            chunk = sensors[i:i + window]
            avg = sum(s["vibration_de"] for s in chunk) / len(chunk)
            trend.append({"ts": chunk[-1]["ts"], "vibration_avg": round(avg, 3)})

    graph = _build_graph(eq_id, e[1], e[8] or [], spares, incidents)
    return {
        "equipment_id": e[0],
        "name": e[1],
        "zone": e[2],
        "criticality": e[3],
        "anomaly_score": e[4],
        "is_anomalous": e[5],
        "rul_days": e[6],
        "rul_band": band,
        "failure_probability": round(failure_prob, 3),
        "contributing_sensors": e[8] or [],
        "sensor_series": sensors,
        "trend_analysis": trend,
        "graph": graph,
    }


def reliability_plant(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.name, e.criticality, h.anomaly_score, h.is_anomalous, h.rul_days "
            "FROM equipment e LEFT JOIN equipment_health h ON h.equipment_id = e.id "
            "ORDER BY e.criticality DESC"
        )
        assets = [{
            "equipment_id": r[0], "name": r[1], "criticality": r[2],
            "anomaly_score": r[3], "is_anomalous": r[4], "rul_days": r[5],
            "failure_probability": round(min(1.0, max(0.0, float(r[3] or 0) * 0.85)), 3),
        } for r in cur.fetchall()]
    return {"assets": assets, "count": len(assets)}


def _build_graph(eq_id: str, eq_name: str, sensors: list, spares: list, incidents: list) -> dict:
    nodes = [{"id": eq_id, "type": "equipment", "label": eq_name}]
    edges = []
    for s in sensors:
        sid = f"sensor-{s}"
        nodes.append({"id": sid, "type": "sensor", "label": s})
        edges.append({"source": eq_id, "target": sid, "relation": "monitors"})
    for sp in spares:
        pid = sp["part_no"]
        nodes.append({"id": pid, "type": "spare", "label": sp["part_no"]})
        edges.append({"source": eq_id, "target": pid, "relation": "requires"})
    for inc in incidents:
        nodes.append({"id": inc["id"], "type": "incident", "label": inc["fault_code"] or inc["id"]})
        edges.append({"source": eq_id, "target": inc["id"], "relation": "history"})
    return {"nodes": nodes, "edges": edges}
