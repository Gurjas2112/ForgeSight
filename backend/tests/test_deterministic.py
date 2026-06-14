"""Unit tests for the deterministic rules — these MUST be exactly right (GOLDEN RULE 2)."""

from __future__ import annotations

from backend.tools.deterministic import (
    PRIORITY_WEIGHTS, procurement_rule, score_priority, severity_rule,
)


def test_priority_weights_sum_to_one():
    assert abs(sum(PRIORITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_priority_max_case():
    # max criticality, max delay, no spare, lead > rul → every factor at full risk → 100
    r = score_priority(criticality=10, delay_severity=10, spares_in_stock=False,
                       lead_time_days=30, rul_days=5)
    assert r.priority_score == 100.0
    assert {f.name for f in r.factors} == {"criticality", "delay_severity", "spares", "lead_time"}


def test_score_priority_min_case():
    r = score_priority(criticality=0, delay_severity=0, spares_in_stock=True,
                       lead_time_days=0, rul_days=100)
    assert r.priority_score == 0.0


def test_score_priority_factor_contributions():
    # criticality 10 (1.0 * .35 * 100 = 35), in-stock spare → spares contribution 0
    r = score_priority(criticality=10, delay_severity=0, spares_in_stock=True,
                       lead_time_days=0, rul_days=None)
    crit = next(f for f in r.factors if f.name == "criticality")
    spares = next(f for f in r.factors if f.name == "spares")
    assert crit.contribution == 35.0
    assert spares.contribution == 0.0
    assert r.priority_score == 35.0


def test_score_priority_is_deterministic():
    a = score_priority(criticality=8, delay_severity=6, spares_in_stock=False,
                       lead_time_days=21, rul_days=9)
    b = score_priority(criticality=8, delay_severity=6, spares_in_stock=False,
                       lead_time_days=21, rul_days=9)
    assert a.model_dump() == b.model_dump()


def test_procurement_reserve_now_when_lead_exceeds_rul_and_in_stock():
    d = procurement_rule(lead_time_days=21, rul_days=9, stock_qty=1)
    assert d.action == "reserve_now"
    assert d.requires_approval is True
    assert "21" in d.rationale and "9" in d.rationale


def test_procurement_order_now_when_lead_exceeds_rul_no_stock():
    d = procurement_rule(lead_time_days=21, rul_days=9, stock_qty=0)
    assert d.action == "order_now"


def test_procurement_monitor_when_comfortable():
    d = procurement_rule(lead_time_days=5, rul_days=100, stock_qty=2)
    assert d.action == "monitor"
    assert d.requires_approval is False


def test_severity_critical_on_limit_breach():
    assert severity_rule(anomaly_score=0.2, sustained_windows=0,
                         projected_crossing_days=None, rul_days=None,
                         lead_time_days=None, limit_breached_now=True) == "critical"


def test_severity_critical_when_rul_below_lead_time():
    assert severity_rule(anomaly_score=0.1, sustained_windows=0,
                         projected_crossing_days=None, rul_days=9,
                         lead_time_days=21, limit_breached_now=False) == "critical"


def test_severity_high_on_near_crossing():
    assert severity_rule(anomaly_score=0.5, sustained_windows=1,
                         projected_crossing_days=10, rul_days=None,
                         lead_time_days=None, limit_breached_now=False) == "high"


def test_severity_warning_then_info():
    assert severity_rule(anomaly_score=0.7, sustained_windows=3,
                         projected_crossing_days=None, rul_days=None,
                         lead_time_days=None, limit_breached_now=False) == "warning"
    assert severity_rule(anomaly_score=0.3, sustained_windows=1,
                         projected_crossing_days=None, rul_days=None,
                         lead_time_days=None, limit_breached_now=False) == "info"
