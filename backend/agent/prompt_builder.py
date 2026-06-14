"""
ForgeSight — context-block serializer (the train/serve PARITY module).
=======================================================================
This exact file is shared by the SFT data-generation script (finetune/dataset/prompt_builder.py)
and the runtime synthesis node. Byte-format-identical context between training and inference is
the #1 correctness decision for a small fine-tune (sft-dataset-spec.md §4).

Ordering: static fields first (equipment header), volatile last (tool_results, citations,
history, then the query) — also preserves prefix-cache hits at runtime.

The CITATIONS block is the ONLY set of refs the model may cite; TOOL_RESULTS is the ONLY source
of numbers. The guardrail enforces both downstream — this module just presents them consistently.
"""

from __future__ import annotations

import json
from typing import Any


def _compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str, ensure_ascii=False)


def equipment_header(equipment: dict | None) -> str:
    if not equipment:
        return "EQUIPMENT: (none in context)"
    parts = [str(equipment.get("id", "?"))]
    if equipment.get("name"):
        parts.append(str(equipment["name"]))
    if equipment.get("zone"):
        parts.append(f"zone {equipment['zone']}")
    if equipment.get("criticality") is not None:
        parts.append(f"criticality {equipment['criticality']}")
    return "EQUIPMENT: " + " · ".join(parts)


def citations_block(citations: list[dict]) -> str:
    """Numbered list of (ref + excerpt). `ref` is what the model must cite verbatim."""
    if not citations:
        return "CITATIONS: (none retrieved — if you cannot support a claim, refuse)"
    lines = ["CITATIONS:"]
    for i, c in enumerate(citations, 1):
        ref = c.get("ref", "?")
        excerpt = (c.get("excerpt") or "").strip().replace("\n", " ")
        if len(excerpt) > 240:
            excerpt = excerpt[:237] + "…"
        lines.append(f"[{i}] {ref}" + (f" — {excerpt}" if excerpt else ""))
    return "\n".join(lines)


def build_context(
    *,
    equipment: dict | None,
    tool_results: dict | None,
    citations: list[dict] | None,
    user_query: str,
    history: str | None = None,
) -> str:
    """Assemble the user-message context block. Identical at train and serve time."""
    blocks = [
        equipment_header(equipment),
        "TOOL_RESULTS: " + _compact(tool_results or {}),
        citations_block(citations or []),
    ]
    if history:
        blocks.append("HISTORY: " + history.strip())
    blocks.append("")                       # blank line before the query
    blocks.append(f"USER QUERY: {user_query.strip()}")
    return "\n".join(blocks)
