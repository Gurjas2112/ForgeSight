# finetune/ — SLM fine-tune (Phase 3, deferred to Pass 5)

Unsloth QLoRA on Qwen2.5-3B-Instruct (Colab T4). Until this lands, the runtime uses **base
Qwen2.5-3B-Instruct** via Ollama (`OLLAMA_MODEL=qwen2.5:3b-instruct`) — the design's sanctioned
fallback. See `sft-dataset-spec.md` for the ~2,150-pair dataset and `BUILD_GUIDE.md §4`.

## Train on a free Colab T4 (recommended)

Open **`colab_finetune.ipynb`** in Colab, set the runtime to **T4 GPU**, and `Run all`. Cell 2
opens an upload dialog — upload **`finetune.zip`** (build it with `python build_finetune_zip.py`
from the repo root) or the 3 loose files (`colab_train.py`, `sft_train.jsonl`, `sft_eval.jsonl`).
The notebook installs Unsloth, runs `colab_train.py` (max_seq=2048, bsz 2×4, **2 epochs**, **lr 1e-4**),
exports the GGUF, and downloads it as **`qwen-forgesight.Q4_K_M.gguf`**. Drop that file at
`finetune/export/qwen-forgesight.Q4_K_M.gguf` (the path `Modelfile` points to), then
`ollama create qwen-forgesight -f finetune/Modelfile`.

**Regenerate dataset after corpus changes:** `python data/corpus/seed_corpus.py --out-sql data/corpus/corpus_ingest.sql` → `python backend/db/apply_migrations.py` → `python finetune/dataset/generate_sft.py` → `python build_finetune_zip.py`. Current corpus: **56 doc_chunks** (23 breakdown records + 6 SOPs + 15 OEM fault-code rows) → **~214 train / 23 eval** SFT pairs.

A 6 GB local GPU also works via
`colab_train.py --max-seq 1024 --batch-size 1 --grad-accum 8` (Unsloth is smoothest under WSL2 on
Windows).

Critical parity rule: `dataset/prompt_builder.py` is the **same** context-block serializer used at
runtime (`backend/agent/prompt_builder.py`). Build/freeze it before generating data.

Promotion rule: ship the fine-tune only if it beats base Qwen on citation compliance AND number
fidelity; otherwise ship base + few-shot and present the FT as in-progress.
