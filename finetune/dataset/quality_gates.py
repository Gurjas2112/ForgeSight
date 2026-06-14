"""
ForgeSight — SFT quality gates (sft-dataset-spec.md §6). 100%-automated checks on every pair:
JSON valid · validates against the card schema · citation_refs ⊆ CITATIONS · enums legal ·
LOTO-first in checklists. Run after generate_sft.py.

Run:  python finetune/dataset/quality_gates.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.schemas.cards import CARD_SCHEMAS  # noqa: E402

HERE = Path(__file__).resolve().parent


def _citations_in_context(user: str) -> set[str]:
    refs: set[str] = set()
    # SFT context lines are "[n] <ref>" (excerpt empty in generation). Refs may contain " — ",
    # so capture the WHOLE remainder as the ref rather than splitting on the em-dash.
    for line in user.splitlines():
        m = re.match(r"\[\d+\]\s+(.+)$", line.strip())
        if m:
            refs.add(m.group(1).strip())
    return refs


def check_file(path: Path) -> tuple[int, int, list[str]]:
    ok = bad = 0
    errors: list[str] = []
    for ln, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            sample = json.loads(raw)
            msgs = {m["role"]: m["content"] for m in sample["messages"]}
            card = json.loads(msgs["assistant"])
        except Exception as e:  # noqa: BLE001
            bad += 1; errors.append(f"{path.name}:{ln} not-parseable: {e}"); continue

        ct = card.get("card_type")
        problems = []
        # intent-classification samples have no card_type; validate their shape instead
        if ct is None:
            if not ({"intent", "query_class"} <= card.keys()):
                problems.append("intent sample missing fields")
        else:
            schema = CARD_SCHEMAS.get(ct)
            if schema is None:
                problems.append(f"unknown card_type {ct}")
            else:
                try:
                    schema.model_validate(card)
                except Exception as e:  # noqa: BLE001
                    problems.append(f"schema_invalid:{type(e).__name__}")
            allowed = _citations_in_context(msgs.get("user", ""))
            for ref in card.get("citation_refs", []):
                if allowed and ref not in allowed:
                    problems.append(f"citation_not_in_context:{ref}")
            steps = card.get("steps", [])
            if steps:
                fs = next((i for i, s in enumerate(steps) if s.get("safety")), None)
                fn = next((i for i, s in enumerate(steps) if not s.get("safety")), None)
                if fs is not None and fn is not None and fn < fs:
                    problems.append("loto_not_first")
        if problems:
            bad += 1; errors.append(f"{path.name}:{ln} {problems}")
        else:
            ok += 1
    return ok, bad, errors


def main() -> int:
    total_ok = total_bad = 0
    for fn in ("sft_train.jsonl", "sft_eval.jsonl"):
        p = HERE / fn
        if not p.exists():
            print(f"  [skip] {fn} not found — run generate_sft.py first"); continue
        ok, bad, errs = check_file(p)
        total_ok += ok; total_bad += bad
        print(f"  {fn}: {ok} pass · {bad} fail")
        for e in errs[:10]:
            print(f"     {e}")
    print(f"\nQUALITY GATES: {total_ok} pass · {total_bad} fail "
          f"({'PASS' if total_bad == 0 else 'FIX ABOVE'})")
    return 0 if total_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
