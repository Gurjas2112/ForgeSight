"""FR-6 — prove /feedback measurably changes future answers (retrieval re-rank + exemplar
injection). Pure-function tests, no DB / no LLM required."""

from __future__ import annotations

import pytest

from backend.agent.synthesis import _exemplar_block
from backend.tools import feedback_store as fb
from backend.tools.rag import RetrievedChunk, apply_feedback_ranking


def _chunk(ref: str, score: float, verified: bool = False) -> RetrievedChunk:
    section = ref + (" [VERIFIED]" if verified else "")
    return RetrievedChunk(id=ref, content="…", section_ref=section,
                          doc_type="report", source="breakdown_history", score=score)


@pytest.fixture(autouse=True)
def _clean():
    fb.reset()
    yield
    fb.reset()


def test_downvote_demotes_the_cited_record():
    eq, fault = "hsm-f3-stand", "HSM-F3-VFD-0247"
    hits = [_chunk("BR-2024-0312", 0.9), _chunk("BR-2024-0155", 0.5)]

    before = apply_feedback_ranking(list(hits), eq, fault)
    assert before[0].section_ref == "BR-2024-0312"          # top before feedback

    fb.record("down", equipment_id=eq, fault_code=fault, citation_ref="BR-2024-0312")
    after = apply_feedback_ranking(list(hits), eq, fault)
    assert after[0].section_ref == "BR-2024-0155"           # a different cause floats up
    assert after[-1].section_ref == "BR-2024-0312"          # down-voted record sinks


def test_group_downvote_without_ref_demotes_current_top():
    eq, fault = "sinter-fan-2", "SNT-FAN-VIB-HI"
    hits = [_chunk("BR-A", 0.8), _chunk("BR-B", 0.4)]
    fb.record("down", equipment_id=eq, fault_code=fault)     # no explicit ref
    after = apply_feedback_ranking(list(hits), eq, fault)
    assert after[0].section_ref == "BR-B"


def test_fixed_verdict_injects_verified_exemplar_into_synthesis_context():
    eq, fault = "hsm-f3-stand", "HSM-F3-VFD-0247"
    tool_results = {"_equipment": {"id": eq},
                    "match_history": [{"ref": "BR-2024-0312", "fault_code": fault}]}

    assert _exemplar_block(tool_results) == ""               # cold system: prompt unchanged

    fb.record("fixed", equipment_id=eq, fault_code=fault,
              root_cause="Braking resistor open-circuit", fix="Replaced resistor element")
    block = _exemplar_block(tool_results)
    assert "ENGINEER-VERIFIED FIXES" in block
    assert "Braking resistor open-circuit" in block          # confirmed cause now steers synthesis
