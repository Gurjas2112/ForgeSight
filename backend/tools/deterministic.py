"""
ForgeSight — deterministic decision rules (pure code, fully unit-tested).
These MUST be exactly right and auditable as code — never LLM-generated (GOLDEN RULE 2/4).
The SLM only NARRATES these results; it never computes or adjusts them.

  - score_priority   : the auditable priority matrix (criticality · delay · spares · lead time)
  - procurement_rule : lead-time-vs-RUL reservation decision (§5.3)
  - severity_rule    : the alert severity ladder (§1.6)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ----------------------------------------------------------------------------------
# Priority matrix  (PS §5.2 — prioritization by criticality / delay / spares / lead time)
# ----------------------------------------------------------------------------------

# Weights sum to 1.0. Frozen here so every score is reproducible and explainable.
PRIORITY_WEIGHTS: dict[str, float] = {
    "criticality": 0.35,
    "delay_severity": 0.30,
    "spares": 0.20,
    "lead_time": 0.15,
}


class PriorityFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["criticality", "delay_severity", "spares", "lead_time"]
    raw: float                       # normalized 0..1 risk contribution of this factor
    weight: float
    contribution: float              # raw * weight * 100 (points added to the score)


class PriorityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority_score: float = Field(ge=0, le=100)
    factors: list[PriorityFactor]
    rationale: str


def score_priority(
    *,
    criticality: int,                # equipment criticality 1..10
    delay_severity: float,           # 0..10 (operational impact of the delay)
    spares_in_stock: bool,           # is the needed spare on hand?
    lead_time_days: int,             # procurement lead time
    rul_days: float | None = None,   # remaining useful life, if known
) -> PriorityResult:
    """Deterministic weighted priority score in [0, 100]. Higher = tackle sooner."""
    crit_n = _clamp(criticality / 10.0)
    delay_n = _clamp(delay_severity / 10.0)
    spares_n = 0.0 if spares_in_stock else 1.0                 # out-of-stock is higher risk
    if rul_days is not None and lead_time_days > rul_days:
        lead_n = 1.0                                            # spare won't arrive in time
    else:
        lead_n = _clamp(lead_time_days / 30.0)

    raws = {"criticality": crit_n, "delay_severity": delay_n,
            "spares": spares_n, "lead_time": lead_n}
    factors = [
        PriorityFactor(name=name, raw=round(raws[name], 4),  # type: ignore[arg-type]
                       weight=PRIORITY_WEIGHTS[name],
                       contribution=round(raws[name] * PRIORITY_WEIGHTS[name] * 100, 2))
        for name in ("criticality", "delay_severity", "spares", "lead_time")
    ]
    score = round(sum(f.contribution for f in factors), 1)
    top = max(factors, key=lambda f: f.contribution)
    rationale = (f"Score {score}/100 — dominated by {top.name.replace('_', ' ')} "
                 f"(+{top.contribution}). Deterministic scoring · auditable.")
    return PriorityResult(priority_score=score, factors=factors, rationale=rationale)


# ----------------------------------------------------------------------------------
# Procurement rule  (PS §5.3 — spare procurement strategy: lead time vs RUL)
# ----------------------------------------------------------------------------------

class ProcurementDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["reserve_now", "order_now", "monitor"]
    rationale: str
    lead_time_days: int
    rul_days: float | None = None
    requires_approval: bool = True               # any commitment passes the human_gate


def procurement_rule(*, lead_time_days: int, rul_days: float | None,
                     stock_qty: int) -> ProcurementDecision:
    """If the spare can't arrive before failure, act now; reserve from stock if available."""
    if rul_days is not None and lead_time_days > rul_days:
        if stock_qty > 0:
            return ProcurementDecision(
                action="reserve_now", lead_time_days=lead_time_days, rul_days=rul_days,
                rationale=(f"Lead time ({lead_time_days} d) > RUL ({rul_days:g} d): "
                           f"reserve the in-stock unit now ({stock_qty} available)."))
        return ProcurementDecision(
            action="order_now", lead_time_days=lead_time_days, rul_days=rul_days,
            rationale=(f"Lead time ({lead_time_days} d) > RUL ({rul_days:g} d) and 0 in stock: "
                       f"raise a PO immediately and plan interim mitigation."))
    if rul_days is not None and lead_time_days > 0.5 * rul_days:
        return ProcurementDecision(
            action="order_now", lead_time_days=lead_time_days, rul_days=rul_days,
            rationale=(f"Lead time ({lead_time_days} d) is a large fraction of RUL "
                       f"({rul_days:g} d): order now to keep margin."))
    return ProcurementDecision(
        action="monitor", lead_time_days=lead_time_days, rul_days=rul_days,
        requires_approval=False,
        rationale="Lead time comfortably within RUL: continue monitoring, no action yet.")


# ----------------------------------------------------------------------------------
# Severity ladder  (§1.6 deterministic severity rules)
# ----------------------------------------------------------------------------------

Severity = Literal["info", "warning", "high", "critical"]


def severity_rule(*, anomaly_score: float, sustained_windows: int,
                  projected_crossing_days: float | None,
                  rul_days: float | None, lead_time_days: int | None,
                  limit_breached_now: bool) -> Severity:
    """Escalation ladder. Checked most-severe first.
      critical = limit breached now OR rul_days < spares lead_time
      high     = projected threshold crossing < 14 d
      warning  = anomaly score > 0.6 sustained over 3 windows
      info     = otherwise
    """
    if limit_breached_now or (
        rul_days is not None and lead_time_days is not None and rul_days < lead_time_days
    ):
        return "critical"
    if projected_crossing_days is not None and projected_crossing_days < 14:
        return "high"
    if anomaly_score > 0.6 and sustained_windows >= 3:
        return "warning"
    return "info"
