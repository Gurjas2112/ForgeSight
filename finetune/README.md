# finetune/ — SLM fine-tune (Phase 3, deferred to Pass 5)

Unsloth QLoRA on Qwen2.5-3B-Instruct (Colab T4). Until this lands, the runtime uses **base
Qwen2.5-3B-Instruct** via Ollama (`OLLAMA_MODEL=qwen2.5:3b-instruct`) — the design's sanctioned
fallback. See `sft-dataset-spec.md` for the ~2,150-pair dataset and `BUILD_GUIDE.md §4`.

## Train on a free Colab T4 (recommended)

Open **`colab_finetune.ipynb`** in Colab (`File → Open notebook → GitHub`, or upload it), set the
runtime to **T4 GPU**, and `Run all`. It clones the repo, installs Unsloth, runs
`colab_train.py` (max_seq=2048, bsz 2×4, 3 epochs), exports `unsloth.Q4_K_M.gguf`, and downloads
it. Drop the file in `finetune/export/qwen-forgesight/`, then `ollama create qwen-forgesight -f
finetune/Modelfile`. Headless alternative: `%run finetune/colab_train.py`. A 6 GB local GPU also
works via `colab_train.py --max-seq 1024 --batch-size 1 --grad-accum 8` (Unsloth is smoothest under
WSL2 on Windows).

Critical parity rule: `dataset/prompt_builder.py` is the **same** context-block serializer used at
runtime (`backend/agent/prompt_builder.py`). Build/freeze it before generating data.

Promotion rule: ship the fine-tune only if it beats base Qwen on citation compliance AND number
fidelity; otherwise ship base + few-shot and present the FT as in-progress.
