"""Plant KPI header — prove the dashboard numbers are computed deterministically from plant
state (no hardcoded 92% / ₹18L). Pure-function tests, no DB."""

from __future__ import annotations

from backend.tools.plant_summary import compute_plant_summary

# 4 assets; 2 anomalous. sinter-fan-2 has a critical alert; caster-1 anomalous w/ RUL < 7.
EQUIPMENT = [
    {"id": "caster-1", "criticality": 10, "is_anomalous": True, "rul_days": 3.3},
    {"id": "hsm-f3-stand", "criticality": 9, "is_anomalous": False, "rul_days": 365.0},
    {"id": "sinter-fan-2", "criticality": 8, "is_anomalous": True, "rul_days": 120.0},
    {"id": "bf-stove-3", "criticality": 6, "is_anomalous": False, "rul_days": 800.0},
]
DOWNTIME = [
    {"equipment_id": "caster-1", "total_downtime_hrs": 40.0, "breakdowns": 4},   # avg 10h
    {"equipment_id": "sinter-fan-2", "total_downtime_hrs": 12.0, "breakdowns": 2},  # avg 6h
]
ALERTS = [{"equipment_id": "sinter-fan-2", "severity": "critical"},
          {"equipment_id": "caster-1", "severity": "warning"}]


def test_availability_is_criticality_weighted():
    s = compute_plant_summary(EQUIPMENT, DOWNTIME, ALERTS)
    # at-risk = caster-1 (anomalous, RUL<7) + sinter-fan-2 (critical alert) = crit 18.
    # not-at-risk = hsm-f3 (9) + bf-stove-3 (6) = 15; total = 33 → 45.5% available.
    assert s["availability_pct"] == round(100 * 15 / 33, 1)
    assert 0.0 <= s["availability_pct"] <= 100.0


def test_at_risk_and_downtime_value_are_computed():
    s = compute_plant_summary(EQUIPMENT, DOWNTIME, ALERTS, base_inr_per_hr=50_000)
    # at-risk: sinter-fan-2 (critical alert) + caster-1 (anomalous, RUL 3.3 < 7). hsm/bf are not.
    assert s["at_risk_count"] == 2
    # caster-1: 10h × 50000 × 10 = 5,000,000 ; sinter-fan-2: 6h × 50000 × 8 = 2,400,000
    assert s["downtime_at_risk_inr"] == 5_000_000 + 2_400_000
    assert s["downtime_at_risk_label"] == "₹74L"
    assert s["open_alerts"] == 2


def test_default_downtime_when_no_history():
    eq = [{"id": "x", "criticality": 5, "is_anomalous": True, "rul_days": 2.0}]
    s = compute_plant_summary(eq, [], [], base_inr_per_hr=50_000, default_downtime_hrs=8.0)
    assert s["at_risk_count"] == 1
    assert s["downtime_at_risk_inr"] == 8 * 50_000 * 5      # uses the documented default


def test_deterministic_recompute():
    a = compute_plant_summary(EQUIPMENT, DOWNTIME, ALERTS)
    b = compute_plant_summary(EQUIPMENT, DOWNTIME, ALERTS)
    assert a == b


def test_healthy_plant_is_100pct_and_zero_risk():
    eq = [{"id": "a", "criticality": 5, "is_anomalous": False, "rul_days": 900.0}]
    s = compute_plant_summary(eq, [], [])
    assert s["availability_pct"] == 100.0
    assert s["at_risk_count"] == 0
    assert s["downtime_at_risk_inr"] == 0
    assert s["downtime_at_risk_label"] == "₹0"
