"""
ForgeSight — one-file Colab runner for the QLoRA fine-tune of Qwen2.5-3B-Instruct.
=================================================================================
Designed to run end-to-end on a free Colab T4 (16 GB). The laptop RTX 3060 (6 GB) is too
tight + native-Windows Unsloth is fragile, so training happens here and the exported GGUF is
downloaded and served locally via Ollama (see finetune/Modelfile).

HOW TO RUN (Colab, GPU runtime = T4):
  1) Upload this repo or just finetune/dataset/sft_train.jsonl + sft_eval.jsonl.
  2) In a cell:  !pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git" \
                     trl peft accelerate bitsandbytes datasets
  3) In a cell:  %run finetune/colab_train.py
     (or:  !python finetune/colab_train.py --data finetune/dataset/sft_train.jsonl)
  4) Download the GGUF that lands in finetune/export/qwen-forgesight/*.Q4_K_M.gguf
  5) Locally:    ollama create qwen-forgesight -f finetune/Modelfile
                 python finetune/03_evaluate_vs_base.py --model qwen2.5:3b-instruct
                 python finetune/03_evaluate_vs_base.py --model qwen-forgesight
     Promote (set OLLAMA_MODEL=qwen-forgesight) only if the fine-tune wins on citation
     compliance AND number fidelity (the design's promotion rule).

T4-tuned hyperparameters (override via CLI flags): r=16, max_seq_length=2048,
per_device_train_batch_size=2, grad_accum=4, epochs=3, lr=2e-4, seed=42 (deterministic).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "dataset" / "sft_train.jsonl"
EXPORT = HERE / "export"

# Hyperparameters (kept identical to finetune/train_qlora.py so the two paths agree)
MODEL_NAME = "unsloth/Qwen2.5-3B-Instruct"
MAX_SEQ = 2048
LORA_R = 16
LORA_ALPHA = 16
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
SEED = 42


def _load_rows(data_path: Path) -> list[dict]:
    rows = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    if not rows:
        raise SystemExit(f"No SFT pairs found in {data_path}. Run generate_sft.py first.")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="ForgeSight QLoRA fine-tune (Colab T4).")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="sft_train.jsonl path")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-seq", type=int, default=MAX_SEQ)
    ap.add_argument("--no-export", action="store_true", help="skip GGUF/merged export (debug)")
    args = ap.parse_args()

    # Heavy imports live inside main so importing this module never requires a GPU stack.
    import inspect
    import torch  # noqa: F401
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel, is_bfloat16_supported
    from unsloth.chat_templates import get_chat_template

    print(f"[1/5] loading {MODEL_NAME} (4-bit, max_seq={args.max_seq}) …")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME, max_seq_length=args.max_seq, dtype=None, load_in_4bit=True)

    print("[2/5] applying LoRA adapters (r=16, gradient checkpointing=unsloth) …")
    model = FastLanguageModel.get_peft_model(
        model, r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=0.0, bias="none",
        target_modules=TARGET_MODULES, use_gradient_checkpointing="unsloth",
        random_state=SEED, use_rslora=False, loftq_config=None)
    tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")

    print(f"[3/5] preparing dataset from {args.data} …")
    rows = _load_rows(args.data)

    def _fmt(ex):
        return {"text": tokenizer.apply_chat_template(ex["messages"], tokenize=False)}

    ds = Dataset.from_list(rows).map(_fmt, load_from_cache_file=False)
    print(f"      {len(ds)} training pairs")

    print(f"[4/5] training ({args.epochs} epochs, bsz={args.batch_size}x{args.grad_accum}) …")
    # TRL's API moves between releases: newer versions take `processing_class` instead of
    # `tokenizer`, fold dataset/length kwargs into SFTConfig, and renamed `max_seq_length`
    # to `max_length`. Place each kwarg wherever the installed signatures accept it so this
    # runs on whatever TRL the Colab install pulled.
    cfg_params = set(inspect.signature(SFTConfig.__init__).parameters)
    trainer_params = set(inspect.signature(SFTTrainer.__init__).parameters)
    seq_key = "max_seq_length" if "max_seq_length" in cfg_params else "max_length"
    optional = {seq_key: args.max_seq, "dataset_text_field": "text",
                "dataset_num_proc": 2, "packing": False}

    cfg_kwargs = dict(
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_steps=5, num_train_epochs=args.epochs, learning_rate=args.lr,
        fp16=not is_bfloat16_supported(), bf16=is_bfloat16_supported(),
        logging_steps=1, optim="adamw_8bit", weight_decay=0.01,
        lr_scheduler_type="linear", seed=SEED, output_dir=str(HERE / "outputs"),
        report_to="none")
    cfg_kwargs.update({k: v for k, v in optional.items() if k in cfg_params})

    trainer_kwargs = dict(model=model, train_dataset=ds, args=SFTConfig(**cfg_kwargs))
    trainer_kwargs["processing_class" if "processing_class" in trainer_params
                   else "tokenizer"] = tokenizer
    # Older TRL expects these on the trainer itself rather than on SFTConfig.
    trainer_kwargs.update({k: v for k, v in optional.items()
                           if k in trainer_params and k not in cfg_params})
    trainer = SFTTrainer(**trainer_kwargs)
    stats = trainer.train()
    print(f"      done — train_runtime={getattr(stats, 'metrics', {}).get('train_runtime', '?')}s")

    if args.no_export:
        print("[5/5] skipping export (--no-export). LoRA in finetune/outputs/.")
        return

    EXPORT.mkdir(exist_ok=True)
    print(f"[5/5] exporting GGUF (q4_k_m) + merged 16-bit → {EXPORT} …")
    model.save_pretrained_gguf(str(EXPORT / "qwen-forgesight"), tokenizer,
                               quantization_method="q4_k_m")
    model.save_pretrained_merged(str(EXPORT / "qwen-forgesight-merged"), tokenizer,
                                 save_method="merged_16bit")
    print("\nNEXT (locally):\n"
          "  ollama create qwen-forgesight -f finetune/Modelfile\n"
          "  python finetune/03_evaluate_vs_base.py --model qwen2.5:3b-instruct\n"
          "  python finetune/03_evaluate_vs_base.py --model qwen-forgesight\n"
          "  # promote: set OLLAMA_MODEL=qwen-forgesight in .env if the FT wins.")


if __name__ == "__main__":
    main()
