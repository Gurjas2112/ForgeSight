"""Prompt-builder parity tests — train/serve serialization must be stable and deterministic."""

from __future__ import annotations

from backend.agent.prompt_builder import build_context, citations_block, equipment_header


def test_equipment_header():
    h = equipment_header({"id": "hsm-f3-stand", "name": "F3 Stand", "zone": "Rolling",
                          "criticality": 9})
    assert h.startswith("EQUIPMENT: hsm-f3-stand")
    assert "criticality 9" in h


def test_empty_citations_warns_to_refuse():
    assert "refuse" in citations_block([]).lower()


def test_citations_numbered_and_truncated():
    block = citations_block([{"ref": "BR-2024-0312", "excerpt": "x" * 400}])
    assert "[1] BR-2024-0312" in block
    assert "…" in block                      # long excerpt truncated


def test_build_context_is_deterministic_and_ordered():
    kwargs = dict(equipment={"id": "hsm-f3-stand"},
                  tool_results={"retrieve_rag": [{"ref": "SOP-1"}]},
                  citations=[{"ref": "BR-2024-0312", "excerpt": "regen energy"}],
                  user_query="diagnose 0247")
    a = build_context(**kwargs)
    b = build_context(**kwargs)
    assert a == b                            # deterministic (parity)
    # static-first ordering: EQUIPMENT before TOOL_RESULTS before CITATIONS before query
    assert a.index("EQUIPMENT:") < a.index("TOOL_RESULTS:") < a.index("CITATIONS:") < a.index("USER QUERY:")
