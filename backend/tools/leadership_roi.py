"""Leadership ROI metrics — shutdown cost, failure cost, savings, recommended actions."""

from __future__ import annotations

from typing import Any

from backend.tools.deterministic import procurement_rule
from backend.tools.plant_summary import BASE_INR_PER_HR, DEFAULT_DOWNTIME_HRS, compute_plant_summary


def compute_leadership_roi(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.name, e.zone, e.criticality, h.is_anomalous, h.rul_days, h.rul_band, h.anomaly_score "
            "FROM equipment e LEFT JOIN equipment_health h ON h.equipment_id = e.id"
        )
        eq_rows = cur.fetchall()
        cur.execute("SELECT equipment_id, total_downtime_hrs, breakdowns FROM v_downtime_by_equipment")
        dt = {r[0]: (float(r[1] or 0) / max(int(r[2] or 1), 1)) for r in cur.fetchall()}
        cur.execute(
            "SELECT equipment_id, max(severity) FROM alerts WHERE acked_at IS NULL GROUP BY equipment_id"
        )
        alerts = [{"equipment_id": r[0], "severity": r[1]} for r in cur.fetchall()]
        cur.execute(
            "SELECT equipment_id, min(stock_qty), min(lead_time_days), min(unit_cost_inr) "
            "FROM spares GROUP BY equipment_id"
        )
        spares = {r[0]: {"stock": r[1], "lead": r[2], "cost": r[3] or 50000} for r in cur.fetchall()}

    eq = [{"id": r[0], "criticality": r[3], "is_anomalous": r[4], "rul_days": r[5]} for r in eq_rows]
    summary = compute_plant_summary(eq, [{"equipment_id": k, "total_downtime_hrs": v * 8, "breakdowns": 1}
                                           for k, v in dt.items()], alerts)

    recommendations = []
    for r in eq_rows:
        eq_id, name, zone, crit, anom, rul, rul_band, anomaly = r
        avg_hrs = dt.get(eq_id, DEFAULT_DOWNTIME_HRS)
        failure_cost = avg_hrs * BASE_INR_PER_HR * float(crit or 1)
        sp = spares.get(eq_id, {"stock": 1, "lead": 14, "cost": 50000})
        intervention_cost = float(sp["cost"]) + 150_000  # spare + labor estimate
        savings = max(0.0, failure_cost - intervention_cost)
        roi = round(savings / intervention_cost, 2) if intervention_cost > 0 else 0.0
        band = rul_band.get("band", [None, None]) if isinstance(rul_band, dict) else [None, None]
        band_width = (band[1] - band[0]) if band[0] is not None and band[1] is not None else 14
        confidence = "High" if band_width < 7 else "Medium" if band_width < 14 else "Low"
        if not anom and (rul is None or float(rul) > 14):
            continue
        proc = procurement_rule(lead_time_days=sp["lead"] or 14, rul_days=float(rul) if rul else None,
                                stock_qty=sp["stock"] or 0)
        recommendations.append({
            "equipment_id": eq_id,
            "name": name,
            "zone": zone,
            "criticality": crit,
            "shutdown_cost_inr": round(failure_cost * 0.3),
            "shutdown_cost_label": _inr(failure_cost * 0.3),
            "potential_failure_cost_inr": round(failure_cost),
            "potential_failure_cost_label": _inr(failure_cost),
            "intervention_cost_inr": round(intervention_cost),
            "expected_savings_inr": round(savings),
            "expected_savings_label": _inr(savings),
            "roi": roi,
            "confidence": confidence,
            "recommended_action": proc.action.replace("_", " "),
            "rul_days": rul,
            "anomaly_score": anomaly,
            "copilot_prompt": f"Assess risk and recommend action for {name} — RUL {rul}d, anomaly {anomaly}",
        })
    recommendations.sort(key=lambda x: x["expected_savings_inr"], reverse=True)

    top = recommendations[0] if recommendations else None
    return {
        "plant_summary": summary,
        "shutdown_cost_inr": round(summary.get("downtime_at_risk_inr", 0) * 0.25),
        "shutdown_cost_label": _inr(summary.get("downtime_at_risk_inr", 0) * 0.25),
        "potential_failure_cost_inr": summary.get("downtime_at_risk_inr", 0),
        "potential_failure_cost_label": summary.get("downtime_at_risk_label", "—"),
        "expected_savings_inr": round(sum(r["expected_savings_inr"] for r in recommendations)),
        "expected_savings_label": _inr(sum(r["expected_savings_inr"] for r in recommendations)),
        "assumptions": summary.get("assumptions", {}),
        "recommendations": recommendations,
        "top_recommendation": top,
    }


def _inr(v: float) -> str:
    if v >= 100_000:
        return f"₹{round(v / 100_000)}L"
    if v >= 1_000:
        return f"₹{round(v / 1_000)}K"
    return f"₹{int(round(v))}"
