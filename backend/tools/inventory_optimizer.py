"""Inventory optimizer — shortage risk and production exposure."""

from __future__ import annotations

from typing import Any

from backend.tools.deterministic import procurement_rule
from backend.tools.plant_summary import BASE_INR_PER_HR, DEFAULT_DOWNTIME_HRS


def list_spares_catalog(conn, *, equipment_id: str | None = None, low_stock: bool = False) -> list[dict]:
    sql = (
        "SELECT s.part_no, s.equipment_id, e.name, s.description, s.stock_qty, "
        "s.lead_time_days, s.supplier, s.unit_cost_inr, h.rul_days "
        "FROM spares s LEFT JOIN equipment e ON e.id = s.equipment_id "
        "LEFT JOIN equipment_health h ON h.equipment_id = s.equipment_id WHERE 1=1 "
    )
    params: list[Any] = []
    if equipment_id:
        sql += "AND s.equipment_id = %s "
        params.append(equipment_id)
    if low_stock:
        sql += "AND s.stock_qty <= 1 "
    sql += "ORDER BY s.stock_qty ASC, s.lead_time_days DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    out = []
    for r in rows:
        rul = float(r[8]) if r[8] is not None else None
        proc = procurement_rule(lead_time_days=r[5] or 0, rul_days=rul, stock_qty=r[4] or 0)
        out.append({
            "part_no": r[0],
            "equipment_id": r[1],
            "equipment_name": r[2],
            "description": r[3],
            "stock_qty": r[4],
            "lead_time_days": r[5],
            "supplier": r[6],
            "unit_cost_inr": r[7] or 0,
            "rul_days": rul,
            "procurement_action": proc.action,
            "procurement_note": proc.rationale,
        })
    return out


def compute_optimizer(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.part_no, s.equipment_id, e.name, e.criticality, s.stock_qty, "
            "s.lead_time_days, s.unit_cost_inr, h.rul_days, h.is_anomalous "
            "FROM spares s JOIN equipment e ON e.id = s.equipment_id "
            "LEFT JOIN equipment_health h ON h.equipment_id = s.equipment_id"
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT equipment_id, total_downtime_hrs, breakdowns FROM v_downtime_by_equipment"
        )
        dt_rows = {r[0]: (float(r[1] or 0) / max(int(r[2] or 1), 1)) for r in cur.fetchall()}

    items = []
    total_exposure = 0.0
    for r in rows:
        part_no, eq_id, eq_name, crit, stock, lead, cost, rul, anom = r
        rul_f = float(rul) if rul is not None else None
        shortage_risk = (stock or 0) <= 0 or (
            rul_f is not None and lead and rul_f < lead and (stock or 0) < 2
        )
        avg_hrs = dt_rows.get(eq_id, DEFAULT_DOWNTIME_HRS)
        exposure = 0.0
        if shortage_risk and (anom or (rul_f is not None and rul_f < 14)):
            exposure = avg_hrs * BASE_INR_PER_HR * float(crit or 1)
            total_exposure += exposure
        proc = procurement_rule(lead_time_days=lead or 0, rul_days=rul_f, stock_qty=stock or 0)
        items.append({
            "part_no": part_no,
            "equipment_id": eq_id,
            "equipment_name": eq_name,
            "criticality": crit,
            "stock_qty": stock,
            "lead_time_days": lead,
            "unit_cost_inr": cost or 0,
            "rul_days": rul_f,
            "shortage_risk": shortage_risk,
            "production_exposure_inr": round(exposure),
            "production_exposure_label": _inr_label(exposure),
            "recommended_action": proc.action,
            "rationale": proc.rationale,
        })
    items.sort(key=lambda x: x["production_exposure_inr"], reverse=True)
    return {
        "items": items,
        "total_production_exposure_inr": round(total_exposure),
        "total_production_exposure_label": _inr_label(total_exposure),
        "at_risk_parts": sum(1 for i in items if i["shortage_risk"]),
    }


def _inr_label(inr: float) -> str:
    if inr >= 100_000:
        return f"₹{round(inr / 100_000)}L"
    if inr >= 1_000:
        return f"₹{round(inr / 1_000)}K"
    return f"₹{int(round(inr))}"
