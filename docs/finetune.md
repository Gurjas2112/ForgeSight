# ForgeSight — Fine-tuning the SLM (hybrid serving)

ForgeSight serves synthesis from a small language model. **Locally** that is a QLoRA fine-tune of
`Qwen2.5-3B-Instruct` served through Ollama; **publicly** (Railway, no GPU) it falls back to Groq.
`GET /healthz` reports which backend + model is live, so the active SLM is never ambiguous.

## Why hybrid
The laptop GPU (RTX 3060, 6 GB) is too small for stable Unsloth training and the cloud box has no
GPU at all. So training happens on a **free Colab T4**, the exported GGUF is downloaded and run
locally via Ollama, and the public URL uses the hosted fallback. This is stated, not hidden.

## Reproduce the fine-tune
```bash
# 1. Build the SFT set from REAL tool evidence (DATABASE_URL set) + gate it
python finetune/dataset/generate_sft.py
python finetune/dataset/quality_gates.py            # must print PASS

# 2. Train on Colab (GPU runtime = T4)
#    upload the repo (or finetune/dataset/*.jsonl), then in a cell:
#    !pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git" trl peft accelerate bitsandbytes datasets
#    %run finetune/colab_train.py
#    → exports finetune/export/qwen-forgesight/*.Q4_K_M.gguf

# 3. Serve locally
ollama create qwen-forgesight -f finetune/Modelfile

# 4. Evaluate base vs fine-tune under the SAME constrained decoding
python finetune/03_evaluate_vs_base.py --model qwen2.5:3b-instruct
python finetune/03_evaluate_vs_base.py --model qwen-forgesight
```

## Promotion rule
Ship the fine-tune (`OLLAMA_MODEL=qwen-forgesight`, `SYNTHESIS_BACKEND=ollama`) **only if** it beats
base on **citation compliance AND number fidelity**. Otherwise base Qwen ships — citation compliance
is already structural under constrained decoding, so the system is correct either way; the fine-tune
buys phrasing/quality.

## Eval results (fill after the Colab run)
`finetune/03_evaluate_vs_base.py` emits this JSON per model; record both rows here:

| Model | JSON validity | Intent accuracy | Citation compliance | Promote? |
|-------|---------------|-----------------|---------------------|----------|
| `qwen2.5:3b-instruct` (base) | _run_ | _run_ | _run_ | baseline |
| `qwen-forgesight` (FT) | _run_ | _run_ | _run_ | iff it wins citation + number fidelity |

> The numbers are intentionally left blank until the GPU run is executed — ForgeSight does not
> publish fabricated metrics. The harness is deterministic (temperature 0) and reproducible.
