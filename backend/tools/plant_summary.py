"""
ForgeSight — plant-level KPI computation for the dashboard header.

The dashboard's headline numbers (availability, open alerts, downtime-at-risk) used to be
hardcoded literals. This module computes them **deterministically from real plant state** so every
figure is traceable to data + a stated cost assumption — not a static claim.

`compute_plant_summary` is a pure function (no DB) so it unit-tests cleanly; the `/plant/summary`
route in `server.py` just feeds it query results from `equipment` / `equipment_health`,
`v_downtime_by_equipment`, and `alerts`.
"""
from __future__ import annotations

from typing import Iterable, Mapping

# Documented downtime-cost assumption (steel-plant scale). Cost scales with equipment criticality
# (1–10): a criticality-10 caster losing an hour costs far more than a low-criticality auxiliary.
BASE_INR_PER_HR = 50_000
# Expected outage length for an at-risk asset with no recorded breakdown history.
DEFAULT_DOWNTIME_HRS = 8.0
# Severities that mark an equipment as actively at risk.
_AT_RISK_SEVERITIES = {"high", "critical"}
_RUL_WARN_DAYS = 7.0


def _inr_label(inr: float) -> str:
    """Indian-format compact label: lakhs (₹XL) or thousands (₹XK)."""
    if inr >= 100_000:
        return f"₹{round(inr / 100_000)}L"
    if inr >= 1_000:
        return f"₹{round(inr / 1_000)}K"
    return f"₹{int(round(inr))}"


def compute_plant_summary(
    equipment: Iterable[Mapping],
    downtime: Iterable[Mapping],
    alerts: Iterable[Mapping],
    *,
    base_inr_per_hr: int = BASE_INR_PER_HR,
    default_downtime_hrs: float = DEFAULT_DOWNTIME_HRS,
) -> dict:
    """Deterministically derive plant KPIs.

    equipment : rows with `id`, `criticality`, `is_anomalous`, `rul_days`.
    downtime  : rows with `equipment_id`, `total_downtime_hrs`, `breakdowns` (v_downtime_by_equipment).
    alerts    : open-alert rows with `equipment_id`, `severity`.
    """
    eq = list(equipment)
    alerts = list(alerts)
    downtime = list(downtime)

    # avg historical downtime per equipment (hrs) from the breakdown view
    avg_hrs: dict[str, float] = {}
    for d in downtime:
        n = d.get("breakdowns") or 0
        total = d.get("total_downtime_hrs") or 0.0
        if n:
            avg_hrs[d["equipment_id"]] = float(total) / float(n)

    alerting_equipment = {
        a["equipment_id"] for a in alerts if (a.get("severity") in _AT_RISK_SEVERITIES)
    }

    total_crit = 0.0
    at_risk_crit = 0.0
    at_risk_count = 0
    downtime_at_risk = 0.0

    for e in eq:
        crit = float(e.get("criticality") or 0)
        total_crit += crit
        anomalous = bool(e.get("is_anomalous"))
        rul = e.get("rul_days")
        # An asset is "at operational risk" if it has a high/critical alert, or it is trending
        # anomalous AND its predicted RUL is inside the warning window. Merely-anomalous assets
        # with healthy RUL are still available (running under watch) — anomaly ≠ downtime.
        is_at_risk = (e["id"] in alerting_equipment) or (
            anomalous and rul is not None and float(rul) < _RUL_WARN_DAYS
        )
        if is_at_risk:
            at_risk_count += 1
            at_risk_crit += crit
            expected_hrs = avg_hrs.get(e["id"], default_downtime_hrs)
            downtime_at_risk += expected_hrs * base_inr_per_hr * crit

    # Availability = criticality-weighted share of plant capacity NOT under active downtime risk.
    availability_pct = round(100.0 * (total_crit - at_risk_crit) / total_crit, 1) if total_crit else 100.0
    downtime_inr = int(round(downtime_at_risk))

    return {
        "availability_pct": availability_pct,
        "open_alerts": len(alerts),
        "at_risk_count": at_risk_count,
        "downtime_at_risk_inr": downtime_inr,
        "downtime_at_risk_label": _inr_label(downtime_inr),
        "assumptions": {
            "availability": "criticality-weighted share of plant capacity not under active downtime risk",
            "downtime_at_risk": "Σ(expected_downtime_hrs × base_inr_per_hr × criticality) over at-risk assets",
            "at_risk_rule": "an open high/critical alert, or anomalous with RUL < 7 days",
            "base_inr_per_hr": base_inr_per_hr,
            "default_downtime_hrs": default_downtime_hrs,
        },
    }
