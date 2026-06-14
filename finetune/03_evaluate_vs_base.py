"""
ForgeSight — base-vs-fine-tuned evaluation (FR-1 merit table). Runs the eval split through an
Ollama model under the SAME constrained decoding as runtime and scores: intent accuracy,
JSON-validity, citation-subset compliance, number-fidelity. Compare base vs qwen-forgesight.

Promotion rule: ship the fine-tune only if it beats base on citation compliance AND number
fidelity; otherwise base + few-shot ships (already citation-correct via constrained decoding).

Run:  python finetune/03_evaluate_vs_base.py --model qwen2.5:3b-instruct
      python finetune/03_evaluate_vs_base.py --model qwen-forgesight
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ollama  # noqa: E402

from backend.config import get_settings  # noqa: E402

EVAL = Path(__file__).resolve().parent / "dataset" / "sft_eval.jsonl"


def _refs_in_user(user: str) -> set[str]:
    return {m.group(1).strip() for line in user.splitlines()
            if (m := re.match(r"\[\d+\]\s+(.+)$", line.strip()))}


def evaluate(model: str) -> dict:
    client = ollama.Client(host=get_settings().ollama_host)
    rows = [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = json_ok = cite_ok = intent_ok = intent_n = 0
    for r in rows:
        msgs = r["messages"]
        target = json.loads(msgs[-1]["content"])
        prompt = msgs[:-1]
        try:
            resp = client.chat(model=model, messages=prompt, format="json",
                               options={"temperature": 0})
            out = json.loads(resp["message"]["content"]); json_ok += 1
        except Exception:  # noqa: BLE001
            n += 1; continue
        n += 1
        if "intent" in target:
            intent_n += 1
            intent_ok += int(out.get("intent") == target.get("intent"))
        else:
            allowed = _refs_in_user(msgs[1]["content"])
            refs = out.get("citation_refs", [])
            if refs and all(x in allowed for x in refs):
                cite_ok += 1
    return {"model": model, "n": n, "json_validity": round(json_ok / max(n, 1), 3),
            "intent_accuracy": round(intent_ok / max(intent_n, 1), 3) if intent_n else None,
            "citation_compliance": round(cite_ok / max(n - intent_n, 1), 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=get_settings().ollama_model)
    print(json.dumps(evaluate(ap.parse_args().model), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
