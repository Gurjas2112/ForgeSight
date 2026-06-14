"""Guardrail tests — the anti-hallucination gates run in code, not the LLM."""

from __future__ import annotations

from backend.agent.governance import AgentGuardrails
from backend.schemas.agent_models import Citation, GuardReport
from backend.schemas.cards import ChecklistCard, DiagnosisCard, RootCause


def _state(card: dict, citations: list[Citation]) -> dict:
    return {"draft_card": card, "citations": citations, "tool_results": {}}


def test_valid_diagnosis_card_passes():
    card = DiagnosisCard(
        fault="DC bus overvoltage", confidence="High",
        summary="Regen energy not dissipated.",
        root_causes=[RootCause(rank=1, cause="Braking resistor open-circuit",
                               confidence="High", citation_refs=["BR-2024-0312"])],
        citation_refs=["BR-2024-0312"],
    ).model_dump()
    report = AgentGuardrails.guard_output(_state(card, [Citation(kind="history", ref="BR-2024-0312")]))
    assert report.passed, report.violations


def test_fabricated_citation_is_caught():
    card = DiagnosisCard(
        fault="x", confidence="Low", summary="y",
        root_causes=[RootCause(rank=1, cause="z", confidence="Low", citation_refs=[])],
        citation_refs=["BR-9999-FAKE"],
    ).model_dump()
    report = AgentGuardrails.guard_output(_state(card, [Citation(kind="history", ref="BR-2024-0312")]))
    assert not report.passed
    assert any(v.startswith("fabricated_citation") for v in report.violations)


def test_uncited_claim_is_caught():
    card = DiagnosisCard(
        fault="x", confidence="Low", summary="y",
        root_causes=[RootCause(rank=1, cause="z", confidence="Low", citation_refs=[])],
        citation_refs=[],
    ).model_dump()
    report = AgentGuardrails.guard_output(_state(card, []))
    assert not report.passed
    assert "uncited_claims" in report.violations


def test_loto_not_first_is_caught():
    card = ChecklistCard(
        title="Braking resistor check",
        steps=[{"text": "Measure resistance", "safety": False},
               {"text": "Apply LOTO", "safety": True}],
        citation_refs=["SOP-HSM-ELEC-09 — Lockout / Tagout"],
    ).model_dump()
    state = _state(card, [Citation(kind="sop", ref="SOP-HSM-ELEC-09 — Lockout / Tagout")])
    report = AgentGuardrails.guard_output(state)
    assert not report.passed
    assert "safety_steps_not_first" in report.violations


def test_loto_first_passes():
    card = ChecklistCard(
        title="Braking resistor check",
        steps=[{"text": "Apply LOTO", "safety": True},
               {"text": "Measure resistance", "safety": False, "expected": "8.0–8.4 Ω"}],
        citation_refs=["SOP-HSM-ELEC-09 — Lockout / Tagout"],
    ).model_dump()
    state = _state(card, [Citation(kind="sop", ref="SOP-HSM-ELEC-09 — Lockout / Tagout")])
    report = AgentGuardrails.guard_output(state)
    assert report.passed, report.violations


def test_priority_score_must_originate_from_matrix():
    card = {"card_type": "priority", "priority_score": 80.0, "citation_refs": ["x"],
            "factors": [], "rationale": "r"}
    # tool_results lacks score_priority → provenance violation
    state = {"draft_card": card, "citations": [Citation(kind="priority_matrix", ref="x")],
             "tool_results": {}}
    report = AgentGuardrails.guard_output(state)
    assert "priority_not_from_matrix" in report.violations


def test_missing_card_fails():
    report = AgentGuardrails.guard_output({"draft_card": None, "citations": []})
    assert not report.passed and "no_draft_card" in report.violations
