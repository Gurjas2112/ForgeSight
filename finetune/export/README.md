# finetune/export — fine-tuned model artifacts (produced on GPU)

This directory receives the QLoRA fine-tune outputs of
[`../train_qlora.py`](../train_qlora.py). It is **empty in the repo by design**: the runtime ships
**base `qwen2.5:3b-instruct`** under constrained decoding, and the fine-tune is **promoted only if
it beats base** on citation compliance + number fidelity (see `../03_evaluate_vs_base.py`).

## What lands here after a GPU run
```
finetune/export/
  qwen-forgesight/         # GGUF export (q4_k_m) -> Ollama
  qwen-forgesight.Q4_K_M.gguf
  qwen-forgesight-merged/  # merged 16-bit weights -> vLLM
```

## How to produce them (Colab T4 or local CUDA GPU)
```bash
pip install "unsloth[colab-new]" trl peft accelerate bitsandbytes datasets
python finetune/dataset/generate_sft.py     # DATABASE_URL set; real RAG evidence -> labels
python finetune/dataset/quality_gates.py    # must print PASS (currently 40/40)
python finetune/train_qlora.py              # QLoRA r=16, 3 epochs, seed=42 -> writes here
ollama create qwen-forgesight -f finetune/Modelfile
python finetune/03_evaluate_vs_base.py      # promote only if it beats base
```

## Promotion (how the runtime picks the model)
Set `OLLAMA_MODEL=qwen-forgesight` in `.env` **only** if `03_evaluate_vs_base.py` shows the
fine-tune wins on citation compliance AND number fidelity; otherwise leave base Qwen — citation
compliance is already structural via constrained decoding, so base is safe to ship.

> Why empty here: GGUF artifacts are hundreds of MB and GPU-produced; committing them would bloat
> the repo and they are reproducible from `train_qlora.py` + the committed `sft_train.jsonl`.
