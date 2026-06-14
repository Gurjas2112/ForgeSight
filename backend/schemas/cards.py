"""
ForgeSight — structured card schemas (Pydantic v2). The system-wide contract
(forgesight-v3-final.md §1.11): one definition, four consumers — the SLM's constrained-decode
target, the guardrail's validation type, the API response model, and the React card props
(mirrored to frontend/lib/schemas.ts).

Every card carries `card_type` (the registry key) and `citation_refs` (validated against the
refs actually retrieved into ForgeState by the citation-existence guardrail). `extra="forbid"`
makes schema drift structurally impossible — the SLM cannot smuggle undeclared fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["High", "Medium", "Low"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class _Card(BaseModel):
    model_config = ConfigDict(extra="forbid")
    citation_refs: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------------
# Diagnostic pipeline cards (Scenario A — the Pass-1 slice)
# ----------------------------------------------------------------------------------

class RootCause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rank: int = Field(ge=1, le=9)
    cause: str
    confidence: Confidence
    citation_refs: list[str] = Field(default_factory=list)


class DiagnosisCard(_Card):
    card_type: Literal["diagnosis"] = "diagnosis"
    fault: str                                   # probable fault, e.g. "DC bus overvoltage"
    confidence: Confidence                       # words, never percentages
    summary: str                                 # one-line plain-language summary
    root_causes: list[RootCause]                 # ranked
    recommended_next: str | None = None          # e.g. "check the braking resistor (SOP-HSM-ELEC-09)"


class ChecklistStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    safety: bool = False                         # LOTO/isolation steps → guardrail enforces these FIRST
    expected: str | None = None                  # expected value/reading, e.g. "8.0–8.4 Ω"


class ChecklistCard(_Card):
    card_type: Literal["checklist"] = "checklist"
    title: str
    steps: list[ChecklistStep]


# ----------------------------------------------------------------------------------
# Reliability / Supervisor / Planner cards (Scenario B/C — schema-first, built later)
# ----------------------------------------------------------------------------------

class RiskCard(_Card):
    card_type: Literal["risk"] = "risk"
    risk_level: RiskLevel
    justification: str


class RULEstimate(_Card):
    card_type: Literal["rul"] = "rul"
    rul_days: float = Field(ge=0, le=3650)
    rul_band: list[float] | None = None          # [low, high]
    contributing_sensors: list[str] = Field(default_factory=list)
    note: str | None = None


class WaitAssessmentCard(_Card):
    card_type: Literal["wait_assessment"] = "wait_assessment"
    verdict: Literal["yes", "yes_with_conditions", "no"]
    rul_days: float | None = Field(default=None, ge=0, le=3650)
    days_to_window: float | None = None
    monitoring_plan: str | None = None
    procurement_callout: str | None = None
    summary: str


class PriorityFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["criticality", "delay_severity", "spares", "lead_time"]
    raw: float
    weight: float
    contribution: float


class PriorityCard(_Card):
    card_type: Literal["priority"] = "priority"
    priority_score: float                        # MUST originate from score_priority (matrix-provenance guard)
    rank: int | None = None
    factors: list[PriorityFactor] = Field(default_factory=list)
    rationale: str


class SparesCard(_Card):
    card_type: Literal["spares"] = "spares"
    part_no: str
    stock_qty: int
    lead_time_days: int
    procurement_note: str
    proposal: str | None = None                  # COMMIT proposal text (→ human_gate)


# ----------------------------------------------------------------------------------
# Honest-failure / control cards (not LLM-generated; bypass the output guard)
# ----------------------------------------------------------------------------------

class NoEvidenceCard(_Card):
    card_type: Literal["no_evidence"] = "no_evidence"
    message: str = ("I couldn't find supporting manuals, SOPs, or records for that. "
                    "I won't guess — try a fault code or rephrase.")


class DegradedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_type: Literal["degraded"] = "degraded"
    message: str
    retrieved: list[dict] = Field(default_factory=list)
    tool_results: dict = Field(default_factory=dict)
    violations: list[str] = Field(default_factory=list)
    served_from_cache: bool | None = None


class DeniedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_type: Literal["denied"] = "denied"
    message: str


# ----------------------------------------------------------------------------------
# Registries consumed by the guardrail (governance.py imports these)
# ----------------------------------------------------------------------------------

CARD_SCHEMAS: dict[str, type[BaseModel]] = {
    "diagnosis": DiagnosisCard,
    "checklist": ChecklistCard,
    "risk": RiskCard,
    "rul": RULEstimate,
    "wait_assessment": WaitAssessmentCard,
    "priority": PriorityCard,
    "spares": SparesCard,
    "no_evidence": NoEvidenceCard,
    "degraded": DegradedCard,
    "denied": DeniedCard,
}

# Cards that make claims requiring at least one citation (anti-hallucination gate).
CITATION_REQUIRED_CARDS: set[str] = {"diagnosis", "checklist", "risk", "wait_assessment"}
