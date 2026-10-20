#!/usr/bin/env python3
"""
AI-CON Qwen 3B Generative LLM LoRA Fine-Tuning Script
------------------------------------------------------
Fine-tunes a PEFT LoRA / QLoRA adapter on the Qwen 2.5 3B architecture
using actual pretrained weights from `Qwen/Qwen2.5-Coder-3B-Instruct`
(or compatible local pretrained checkpoint) on conversational supervised
fine-tuning (SFT) data for Maharashtra MHT-CET admissions counselling.

Key Guardrails:
1. NEVER initializes random weights with from_config(). Always uses
   AutoModelForCausalLM.from_pretrained() with full 36 transformer layers.
2. Checks CUDA availability and bitsandbytes. If CUDA is unavailable, stops
   before expensive CPU training and provides the exact environment fix
   (unless --allow-cpu is explicitly provided).
3. On CUDA with RTX 4060 (8GB VRAM), automatically configures 4-bit QLoRA
   (BitsAndBytesConfig nf4) to fit comfortably within VRAM.
4. Saves Qwen adapter artifacts strictly to: model_artifacts/qwen3b_lora_adapter/
   Preserves existing TinyLlama adapter in: model_artifacts/lora_adapter/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import torch
from datasets import load_dataset
from peft import (
    LoraConfig,
    TaskType,
    get_peft_model,
    prepare_model_for_kbit_training,
)
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

# Optional BitsAndBytes
try:
    from transformers import BitsAndBytesConfig
    HAS_BNB = True
except ImportError:
    BitsAndBytesConfig = None
    HAS_BNB = False


def check_cuda_and_environment(allow_cpu: bool = False) -> Dict[str, Any]:
    """Inspect GPU, CUDA availability, PyTorch build, and bitsandbytes stack."""
    print("=" * 75)
    print("AI-CON ENVIRONMENT & HARDWARE ACCELERATION AUDIT")
    print("=" * 75)

    cuda_available = torch.cuda.is_available()
    torch_version = torch.__version__
    print(f"PyTorch Version:   {torch_version}")
    print(f"CUDA Available:    {cuda_available}")

    gpu_info: Dict[str, Any] = {
        "cuda_available": cuda_available,
        "torch_version": torch_version,
        "device_name": None,
        "vram_gb": 0.0,
        "supports_bf16": False,
        "has_bitsandbytes": False,
        "quantization_mode": "none",
    }

    # Check bitsandbytes
    try:
        import bitsandbytes as bnb
        gpu_info["has_bitsandbytes"] = True
        bnb_version = getattr(bnb, "__version__", "unknown")
        print(f"BitsAndBytes:      Installed (v{bnb_version})")
    except ImportError:
        print("BitsAndBytes:      Not installed in active environment")

    if cuda_available:
        device_name = torch.cuda.get_device_name(0)
        total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        supports_bf16 = torch.cuda.is_bf16_supported()

        gpu_info["device_name"] = device_name
        gpu_info["vram_gb"] = round(total_vram, 2)
        gpu_info["supports_bf16"] = supports_bf16

        print(f"Active GPU:        {device_name}")
        print(f"Total VRAM:        {total_vram:.2f} GB")
        print(f"bfloat16 Support:  {supports_bf16}")

        if gpu_info["has_bitsandbytes"] and HAS_BNB:
            gpu_info["quantization_mode"] = "4bit_qlora"
            print("Selected Strategy: 4-bit QLoRA (NF4 double quantization with bitsandbytes)")
        else:
            gpu_info["quantization_mode"] = "fp16"
            print("Selected Strategy: FP16 native on CUDA (bitsandbytes not active)")
    else:
        print("Notice: No CUDA-capable device detected by active PyTorch.")
        if not allow_cpu:
            print("\n" + "!" * 75)
            print("CRITICAL STOP: CUDA ACCELERATION IS CURRENTLY UNAVAILABLE")
            print("!" * 75)
            print("You have an NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM), but the active")
            print(f"PyTorch binary in this environment ({torch_version}) is a CPU-only build.")
            print("Running full 36-layer Qwen 3B pretrained fine-tuning on CPU without CUDA")
            print("causes severe memory thrashing and multi-hour latency.\n")
            print("EXACT ENVIRONMENT FIX (Run in Windows PowerShell):")
            print("--------------------------------------------------")
            print("1. Install CUDA-enabled PyTorch (cu121):")
            print(r"   .\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
            print("\n2. Install bitsandbytes for 4-bit QLoRA:")
            print(r"   .\.venv\Scripts\python.exe -m pip install bitsandbytes")
            print("\n3. Re-run this training command to train seamlessly on your RTX 4060 GPU.")
            print("--------------------------------------------------")
            print("(If you explicitly wish to test on CPU despite these warnings, pass '--allow-cpu')")
            print("!" * 75 + "\n")
            sys.exit(1)
        else:
            print("WARNING: '--allow-cpu' was provided. Continuing on CPU with full 36 layers.")
            gpu_info["quantization_mode"] = "cpu_float32"

    print("=" * 75 + "\n")
    return gpu_info


def train_qwen_lora(
    train_file: str = "training_data/train.jsonl",
    val_file: str = "training_data/val.jsonl",
    output_dir: str = "model_artifacts/qwen3b_lora_adapter",
    base_model_id: str = "Qwen/Qwen2.5-Coder-3B-Instruct",
    smoke_test: bool = True,
    epochs: int = 1,
    batch_size: int = 1,
    lr: float = 2e-4,
    random_state: int = 42,
    allow_cpu: bool = False,
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """Fine-tune LoRA adapter using actual pretrained Qwen 3B weights."""
    # 1. Environment and hardware check
    env_info = check_cuda_and_environment(allow_cpu=allow_cpu)

    start_time = time.time()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading tokenizer from pretrained base: {base_model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or "<|endoftext|>"

    # 2. Load Pretrained Base Model (Verified from_pretrained, NEVER from_config)
    print(f"Loading pretrained base model: {base_model_id}")
    print("Architecture: Preserving full 36 transformer layers without truncation.")

    model_kwargs: Dict[str, Any] = {
        "low_cpu_mem_usage": True,
    }

    if env_info["quantization_mode"] == "4bit_qlora":
        compute_dtype = torch.bfloat16 if env_info["supports_bf16"] else torch.float16
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["quantization_config"] = bnb_config
        model_kwargs["device_map"] = "auto"
        print("Configured 4-bit QLoRA with BitsAndBytesConfig.")
    elif env_info["cuda_available"]:
        dtype = torch.bfloat16 if env_info["supports_bf16"] else torch.float16
        model_kwargs["torch_dtype"] = dtype
        model_kwargs["device_map"] = "auto"
        print(f"Configured CUDA device_map='auto' with dtype={dtype}.")
    else:
        # Fallback CPU mode when --allow-cpu is specified
        model_kwargs["torch_dtype"] = torch.float32
        print("Configured CPU mode with torch.float32 and low_cpu_mem_usage=True.")

    try:
        model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            **model_kwargs,
        )
    except Exception as exc:
        print(f"Error loading pretrained base model '{base_model_id}': {exc}")
        raise RuntimeError(
            f"Failed to load pretrained weights for {base_model_id}. "
            "Ensure the model is accessible or cached locally."
        ) from exc

    # Confirm full 36 layers
    num_layers = getattr(model.config, "num_hidden_layers", None)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Verified Pretrained Model: {num_layers} layers, {total_params:,} total parameters.")

    if env_info["quantization_mode"] == "4bit_qlora":
        model = prepare_model_for_kbit_training(model)

    # 3. Configure PEFT LoRA
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        base_model_name_or_path=base_model_id,
    )
    model = get_peft_model(model, lora_config)
    print("\nPEFT LoRA Adapter Attached:")
    model.print_trainable_parameters()

    # 4. Load & Preprocess Dataset
    print(f"\nLoading conversational SFT dataset:\n  Train: {train_file}\n  Val:   {val_file}")
    raw_dataset = load_dataset(
        "json",
        data_files={"train": train_file, "val": val_file},
    )

    if smoke_test:
        sample_train_count = 16
        sample_val_count = 4
        seq_max_length = 256
        print(f"Smoke test mode active: selecting {sample_train_count} train and {sample_val_count} val records.")
        train_ds = raw_dataset["train"].select(range(min(sample_train_count, len(raw_dataset["train"]))))
        val_ds = raw_dataset["val"].select(range(min(sample_val_count, len(raw_dataset["val"]))))
    else:
        seq_max_length = 1024
        train_ds = raw_dataset["train"]
        val_ds = raw_dataset["val"]

    def preprocess_function(examples):
        texts = []
        for conversation in examples["messages"]:
            formatted = tokenizer.apply_chat_template(
                conversation,
                tokenize=False,
                add_generation_prompt=False,
            )
            texts.append(formatted)
        encodings = tokenizer(
            texts,
            truncation=True,
            max_length=seq_max_length,
            padding="max_length",
        )
        encodings["labels"] = encodings["input_ids"].copy()
        return encodings

    print(f"Tokenizing conversations (max_length={seq_max_length})...")
    tokenized_train = train_ds.map(preprocess_function, batched=True, remove_columns=["messages"])
    tokenized_val = val_ds.map(preprocess_function, batched=True, remove_columns=["messages"])

    # 5. Training Arguments
    effective_max_steps = max_steps if max_steps is not None else (3 if smoke_test else -1)
    checkpoints_dir = out_dir / "checkpoints"

    use_cuda = env_info["cuda_available"]
    training_args = TrainingArguments(
        output_dir=str(checkpoints_dir),
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=lr,
        num_train_epochs=epochs,
        max_steps=effective_max_steps,
        logging_steps=1,
        eval_strategy="no" if smoke_test else "epoch",
        save_strategy="no" if smoke_test else "epoch",
        save_total_limit=1,
        fp16=(use_cuda and not env_info["supports_bf16"]),
        bf16=(use_cuda and env_info["supports_bf16"]),
        use_cpu=(not use_cuda),
        report_to="none",
        seed=random_state,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_val if not smoke_test else None,
    )

    print(f"\nBeginning training run (max_steps={effective_max_steps})...")
    train_result = trainer.train()

    # 6. Save Verified LoRA Adapter & Tokenizer
    print(f"\nSaving verified fine-tuned LoRA adapter to: {out_dir}")
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    duration = round(time.time() - start_time, 2)
    metrics = {
        "training_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_model": base_model_id,
        "base_model_layers": num_layers,
        "quantization_mode": env_info["quantization_mode"],
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "training_loss": float(train_result.training_loss),
        "global_steps": train_result.global_step,
        "duration_seconds": duration,
        "adapter_dir": str(out_dir),
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        "lora_r": 8,
        "lora_alpha": 16,
    }

    metrics_file = out_dir / "training_metrics.json"
    metrics_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Training successfully completed in {duration}s! Final Loss: {train_result.training_loss:.4f}")

    # Verify saved files
    expected_files = ["adapter_config.json", "adapter_model.safetensors", "training_metrics.json"]
    print("\nVerifying saved output files in output directory:")
    for fname in expected_files:
        fpath = out_dir / fname
        if fpath.is_file():
            print(f"  [OK] {fname} ({fpath.stat().st_size:,} bytes)")
        else:
            print(f"  [MISSING] {fname}")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen 3B LoRA Adapter for AI-con (Pretrained Weights)")
    parser.add_argument("--train-file", default="training_data/train.jsonl")
    parser.add_argument("--val-file", default="training_data/val.jsonl")
    parser.add_argument("--output-dir", default="model_artifacts/qwen3b_lora_adapter")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-Coder-3B-Instruct")
    parser.add_argument("--smoke-test", action="store_true", help="Execute 3-step verification run")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow-cpu", action="store_true", help="Allow CPU execution if CUDA is unavailable")
    parser.add_argument("--max-steps", type=int, default=None, help="Override maximum optimization steps")
    args = parser.parse_args()

    train_qwen_lora(
        train_file=args.train_file,
        val_file=args.val_file,
        output_dir=args.output_dir,
        base_model_id=args.base_model,
        smoke_test=args.smoke_test,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        random_state=args.seed,
        allow_cpu=args.allow_cpu,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    main()
