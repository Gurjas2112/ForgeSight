# finetune/ — SLM fine-tune (Phase 3, deferred to Pass 5)

Unsloth QLoRA on Qwen2.5-3B-Instruct (Colab T4). Until this lands, the runtime uses **base
Qwen2.5-3B-Instruct** via Ollama (`OLLAMA_MODEL=qwen2.5:3b-instruct`) — the design's sanctioned
fallback. See `sft-dataset-spec.md` for the ~2,150-pair dataset and `BUILD_GUIDE.md §4`.

Critical parity rule: `dataset/prompt_builder.py` is the **same** context-block serializer used at
runtime (`backend/agent/prompt_builder.py`). Build/freeze it before generating data.

Promotion rule: ship the fine-tune only if it beats base Qwen on citation compliance AND number
fidelity; otherwise ship base + few-shot and present the FT as in-progress.
