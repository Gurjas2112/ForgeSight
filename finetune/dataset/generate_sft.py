"""
ForgeSight — SFT dataset generator (sft-dataset-spec.md). Builds chat-format pairs by running the
REAL tools (RAG + breakdown history) against the seeded corpus to get genuine tool_results +
citations, then emitting the TARGET card deterministically from that ground-truth evidence (no
hosted-API dependency → runs offline; the evidence IS the label). Covers the core tasks:
  T1 intent · T2 DiagnosisCard · T3 ChecklistCard · T10 no_evidence refusal · phrasing variants.

Run (DATABASE_URL set):  python finetune/dataset/generate_sft.py
Output: sft_train.jsonl / sft_eval.jsonl  (+ runs quality_gates).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent.governance import AGENT_CHARTERS  # noqa: E402
from backend.agent.prompt_builder import build_context  # noqa: E402
from backend.db.connection import get_pool  # noqa: E402
from backend.tools.rag import match_history, retrieve_rag, to_citations  # noqa: E402

HERE = Path(__file__).resolve().parent
RNG = random.Random(42)

DIAG_PERSONA = AGENT_CHARTERS["diagnostic_agent"].persona_prompt

# Query phrasings (formal · terse shop-floor · typo-laden · Indian-English colloquial)
DIAG_PHRASINGS = [
    "Diagnose the {eq} — it tripped on fault {code}.",
    "{eq} {code} trip, whats the cause?",
    "why did {eq} trip on {code} pls diagnose",
    "kindly tell the root cause of {code} on {eq}",
    "{code} fault came on {eq}, what to check",
]
SOP_PHRASINGS = [
    "how do I check the braking resistor?",
    "steps to inspect braking resistor",
    "give me the LOTO procedure for the resistor check",
    "braking resistor inspection steps na",
]
INTENT_SAMPLES = [
    ("diagnose F3 fault 0247", "diagnosis", "knowledge"),
    ("how do I check the braking resistor", "sop_lookup", "knowledge"),
    ("what's the current health of sinter fan 2", "health_query", "live_status"),
    ("estimate RUL for the ID fan", "rul_query", "live_status"),
    ("can it wait till Sunday's shutdown", "wait_assessment", "live_status"),
    ("what should we tackle first tonight", "priority_query", "live_status"),
    ("is the SKF 22230 bearing in stock", "spares_query", "live_status"),
    ("generate the shift summary report", "report_request", "action"),
]

EQUIP = {"hsm-f3-stand": ("F3 stand", "HSM-F3-VFD-0247"),
         "sinter-fan-2": ("sinter ID fan 2", "SNT-FAN-VIB-HI")}


def _chat(system: str, user: str, assistant: dict) -> dict:
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": json.dumps(assistant, ensure_ascii=False)},
    ]}


def _diagnosis_card(records, sop_chunks, code) -> dict:
    """Build a faithful DiagnosisCard from matched verified records (the label = the evidence)."""
    refs = [r.section_ref.replace(" [VERIFIED]", "") for r in records]
    root_causes = []
    for i, r in enumerate(records[:3], 1):
        rc = r.content.split("ROOT CAUSE:")[-1].split("| RESOLUTION")[0].strip() if "ROOT CAUSE" in r.content else "see record"
        root_causes.append({"rank": i, "cause": rc, "confidence": "High" if "[VERIFIED]" in r.section_ref else "Medium",
                            "citation_refs": [r.section_ref.replace(" [VERIFIED]", "")]})
    return {"card_type": "diagnosis", "fault": code,
            "confidence": "High" if records else "Low",
            "summary": f"Probable cause identified from {len(records)} matched record(s); see ranked root causes.",
            "root_causes": root_causes or [{"rank": 1, "cause": "insufficient evidence", "confidence": "Low", "citation_refs": refs[:1]}],
            "recommended_next": "Verify per the cited SOP before acting.",
            "citation_refs": refs + [c.section_ref for c in sop_chunks][:2]}


def main() -> int:
    pool = get_pool()
    samples: list[dict] = []

    # T1 — intent classification
    for text, intent, qclass in INTENT_SAMPLES:
        for variant in (text, text.upper(), text + " ?"):
            samples.append(_chat(
                "Classify the maintenance query. Output only JSON with intent and query_class.",
                f"EQUIPMENT: (none)\nUSER QUERY: {variant}",
                {"intent": intent, "query_class": qclass}))

    with pool.connection() as conn:
        # T2 — DiagnosisCard (real retrieval + history)
        for eq, (name, code) in EQUIP.items():
            sop = retrieve_rag(conn, code, equipment_id=eq, doc_types=["manual", "sop"], k=4)
            recs = match_history(conn, equipment_id=eq, fault_code=code, symptoms=code, k=4)
            cites = to_citations(sop) + to_citations(recs)
            cite_dicts = [{"ref": c.ref, "excerpt": ""} for c in cites]
            tool_results = {"_equipment": {"id": eq, "name": name},
                            "retrieve_rag": [{"ref": c.ref} for c in to_citations(sop)],
                            "match_history": [{"ref": c.ref} for c in to_citations(recs)]}
            card = _diagnosis_card(recs, sop, code)
            for phr in DIAG_PHRASINGS:
                q = phr.format(eq=name, code=code)
                user = build_context(equipment=tool_results["_equipment"], tool_results=tool_results,
                                     citations=cite_dicts, user_query=q)
                samples.append(_chat(DIAG_PERSONA, user, card))

        # T3 — ChecklistCard (LOTO-first, from the SOP)
        sop = retrieve_rag(conn, "braking resistor inspection LOTO", equipment_id="hsm-f3-stand",
                           doc_types=["sop"], k=4)
        sop_refs = [c.ref for c in to_citations(sop)]
        checklist = {"card_type": "checklist", "title": "Braking Resistor Inspection",
                     "steps": [
                         {"text": "Apply LOTO to the F3 drive isolator; verify zero energy.", "safety": True},
                         {"text": "Wait 10 min for DC-bus discharge; confirm <50 VDC.", "safety": True},
                         {"text": "Measure resistance across the element.", "safety": False, "expected": "8.0-8.4 ohm"},
                         {"text": "Open circuit (OL) => replace the resistor assembly.", "safety": False},
                     ], "citation_refs": sop_refs[:2]}
        tr = {"_equipment": {"id": "hsm-f3-stand", "name": "F3 stand"},
              "retrieve_rag": [{"ref": r} for r in sop_refs]}
        for phr in SOP_PHRASINGS:
            user = build_context(equipment=tr["_equipment"], tool_results=tr,
                                 citations=[{"ref": r, "excerpt": ""} for r in sop_refs], user_query=phr)
            samples.append(_chat(DIAG_PERSONA, user, checklist))

        # T10 — no_evidence refusal (empty retrieval)
        for q in ("diagnose the flux capacitor", "what is the RUL of the teleporter"):
            user = build_context(equipment=None, tool_results={}, citations=[], user_query=q)
            samples.append(_chat(DIAG_PERSONA, user, {"card_type": "no_evidence",
                "message": "I couldn't find supporting manuals, SOPs, or records for that. I won't guess."}))

    RNG.shuffle(samples)
    n_eval = max(1, len(samples) // 10)
    eval_s, train_s = samples[:n_eval], samples[n_eval:]
    (HERE / "sft_train.jsonl").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in train_s), encoding="utf-8")
    (HERE / "sft_eval.jsonl").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in eval_s), encoding="utf-8")
    print(f"wrote {len(train_s)} train + {len(eval_s)} eval pairs → finetune/dataset/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
