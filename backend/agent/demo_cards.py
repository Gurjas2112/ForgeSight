"""
ForgeSight — DEMO_MODE golden cards. Top of the cache chain so a scripted demo query returns a
perfect card instantly even if Ollama/DB stalls mid-recording (forgesight-v3-final.md §1.8).
Keyed `<equipment_id>::<normalized query>` to match CacheChain.lookup.
"""

from __future__ import annotations

F3_DIAGNOSIS = {
    "card_type": "diagnosis",
    "fault": "HSM-F3-VFD-0247",
    "confidence": "High",
    "summary": "F3 tripped on DC-bus overvoltage: the braking resistor is not dissipating regen "
               "energy during deceleration — matches a verified past breakdown on this stand.",
    "root_causes": [
        {"rank": 1, "cause": "Braking resistor element open-circuit; regen energy not dissipated",
         "confidence": "High", "citation_refs": ["BR-2024-0312"]},
        {"rank": 2, "cause": "Deceleration ramp set too aggressive",
         "confidence": "Medium", "citation_refs": ["BR-2024-0155"]},
    ],
    "recommended_next": "Check the braking resistor per SOP-HSM-ELEC-09 (LOTO first).",
    "citation_refs": ["BR-2024-0312", "BR-2024-0155", "SOP-HSM-ELEC-09 — Resistance Measurement"],
}


def golden_demo_cache() -> dict[str, dict]:
    """A few exact-match entries for the scripted demo queries."""
    cache: dict[str, dict] = {}
    for q in ("diagnose the f3 stand — it tripped on fault 0247.",
              "diagnose f3 fault 0247", "diagnose the f3 trip",
              "why did f3 trip on 0247"):
        cache[f"hsm-f3-stand::{q}"] = F3_DIAGNOSIS
    return cache
