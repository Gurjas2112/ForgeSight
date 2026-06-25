# Finetuning Workflow — ForgeSight SLM

The reasoning layer is a **small language model** (Qwen2.5-3B-Instruct) that narrates deterministic
tool outputs into typed, cited cards. ForgeSight ships a domain fine-tune, **`qwen-forgesight`**
(QLoRA via Unsloth), and gates its promotion behind a measured win over the base model.

- **Base:** `qwen2.5:3b-instruct`
- **Method:** QLoRA (Unsloth, LoRA r=16) on Colab T4 or a local CUDA GPU
- **Export:** merged 16-bit → GGUF (Q4_K_M) for Ollama / llama.cpp
- **Artifact:** `finetune/export/qwen-forgesight.Q4_K_M.gguf` (~1.9 GB, **gitignored** — see below)

---

## 1. Pipeline

```
data/corpus + real backend tools ─► dataset/generate_sft.py ─► sft_train.jsonl / sft_eval.jsonl
                                          │ (deterministic, seed=42)
                                          ▼
                                 dataset/quality_gates.py  (must print PASS)
                                          ▼
                          colab_train.py (QLoRA) ─► merged 16-bit ─► GGUF (Q4_K_M)
                                          ▼
                       finetune/export/qwen-forgesight.Q4_K_M.gguf
                                          ▼
            ollama create qwen-forgesight -f finetune/Modelfile  ─► 03_evaluate_vs_base.py
```

**Parity rule (critical):** `dataset/prompt_builder.py` is byte-identical to the runtime
`backend/agent/prompt_builder.py` — the model trains on exactly the context blocks it will see in
production. Freeze it before generating data.

---

## 2. Generate the SFT dataset

The pairs are built by running the **real** backend tools against the seeded corpus, so labels are
grounded in actual RAG evidence and real ML numbers:

```bash
uv run python finetune/dataset/generate_sft.py     # DATABASE_URL set → sft_train.jsonl / sft_eval.jsonl
uv run python finetune/dataset/quality_gates.py    # JSON valid · schema · citations ⊆ CITATIONS · LOTO-first
```

Current corpus (~56 doc_chunks) yields **~214 train / 23 eval** chat-format pairs. Quality gates must
print **PASS** before training.

---

## 3. Train (Colab T4 — free)

Open **`colab_finetune.ipynb`**, set runtime to **T4 GPU**, `Run all`. Upload `finetune.zip`
(`python build_finetune_zip.py`) or the loose `colab_train.py` + `sft_*.jsonl`. It installs Unsloth,
runs `colab_train.py` (max_seq=2048, batch 2×4, 2 epochs, lr 1e-4), exports the GGUF, and downloads
`qwen-forgesight.Q4_K_M.gguf`. Place it at `finetune/export/`. A 6 GB local GPU works too:
`colab_train.py --max-seq 1024 --batch-size 1 --grad-accum 8` (smoothest under WSL2 on Windows).

---

## 4. Deploy locally (verified)

The exported GGUF is a **complete, self-contained** model (merged weights + tokenizer), not a bare LoRA
adapter — it is directly servable. Verified working with **Ollama 0.30.10**:

```bash
cd finetune
ollama create qwen-forgesight -f Modelfile          # imports export/qwen-forgesight.Q4_K_M.gguf  → "success"
echo 'Diagnose the F3 trip; respond with a JSON diagnosis card.' \
  | ollama run qwen-forgesight --format json         # → {"card_type":"diagnosis_card", ...}
```

Then point the backend at it (on-prem only):

```bash
# .env
SYNTHESIS_BACKEND=ollama
OLLAMA_MODEL=qwen-forgesight
```

`GET /healthz` then reports `model: qwen-forgesight`.

---

## 5. Promotion rule

Ship the fine-tune **only if it beats base** on BOTH metrics; otherwise keep base Qwen:

```bash
uv run python finetune/03_evaluate_vs_base.py --model qwen2.5:3b-instruct
uv run python finetune/03_evaluate_vs_base.py --model qwen-forgesight
# promote (set OLLAMA_MODEL=qwen-forgesight) iff qwen-forgesight wins on
#   (a) citation compliance  AND  (b) number fidelity
```

This is safe because citation compliance is already structural via constrained decoding — base Qwen is
never wrong on citations, only (potentially) less fluent.

---

## 6. Production note (no GPU)

The public deployment runs on **Railway, which has no GPU**, so production uses the hosted Groq fallback
(`SYNTHESIS_BACKEND=hosted`, `llama-3.3-70b-versatile`) — the fine-tuned GGUF is an **on-prem** option.
The 1.9 GB GGUF is **gitignored** (`finetune/export/*`, keeping only `README.md`); it is reproducible
from `colab_train.py` + the committed `sft_train.jsonl`, so it is never pushed to the repo or to Vercel.

See [`../ml/Ml_workflow.md`](../ml/Ml_workflow.md) for how the SLM fits the broader model stack and
[`export/README.md`](export/README.md) for the export artifact layout.
