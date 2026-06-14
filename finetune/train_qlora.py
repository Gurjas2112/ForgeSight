"""
ForgeSight — Unsloth QLoRA fine-tune of Qwen2.5-3B-Instruct (Colab T4 / local GPU).
Runs the SFT pairs from finetune/dataset/sft_train.jsonl. Exports GGUF (Q4_K_M → Ollama) +
merged (→ vLLM). NOT run on the demo laptop (needs CUDA); base Qwen ships if FT not promoted.

Colab: pip install "unsloth[colab-new]" trl peft accelerate bitsandbytes, then run this.
Refs: https://github.com/unslothai/unsloth · https://huggingface.co/Qwen/Qwen2.5-3B-Instruct
"""

from __future__ import annotations

import json
from pathlib import Path

MAX_SEQ = 4096
HERE = Path(__file__).resolve().parent


def main() -> None:
    from datasets import Dataset
    from trl import SFTTrainer, SFTConfig
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import get_chat_template

    model, tokenizer = FastLanguageModel.from_pretrained(
        "unsloth/Qwen2.5-3B-Instruct", max_seq_length=MAX_SEQ, load_in_4bit=True)
    model = FastLanguageModel.get_peft_model(
        model, r=16, lora_alpha=16, lora_dropout=0.0, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth", random_state=42)
    tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")

    rows = [json.loads(l) for l in (HERE / "dataset" / "sft_train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    def _fmt(ex):
        return {"text": tokenizer.apply_chat_template(ex["messages"], tokenize=False)}
    ds = Dataset.from_list(rows).map(_fmt)

    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer, train_dataset=ds, dataset_text_field="text",
        max_seq_length=MAX_SEQ, packing=True,
        args=SFTConfig(per_device_train_batch_size=2, gradient_accumulation_steps=4,
                       warmup_steps=5, num_train_epochs=3, learning_rate=2e-4,
                       logging_steps=5, optim="adamw_8bit", seed=42, output_dir="outputs"))
    trainer.train()

    out = HERE / "export"
    out.mkdir(exist_ok=True)
    model.save_pretrained_gguf(str(out / "qwen-forgesight"), tokenizer, quantization_method="q4_k_m")
    model.save_pretrained_merged(str(out / "qwen-forgesight-merged"), tokenizer, save_method="merged_16bit")
    print(f"exported GGUF + merged → {out}. Next: ollama create qwen-forgesight -f finetune/Modelfile")


if __name__ == "__main__":
    main()
