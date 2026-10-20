#!/usr/bin/env python3
"""
AI-CON Model Training Suite
---------------------------
Supports:
1. Task B (Tabular ML Predictor): Trains high-accuracy Gradient Boosted Regressors
   (HistGradientBoostingRegressor) on 116,000+ historical MHT-CET cutoff observations to predict
   expected closing ranks and closing percentiles.
2. Task A (Generative LLM Behaviour LoRA): Trains LoRA adapters on conversational SFT data
   (grounded citations, abstention, and anti-hallucination outputs) using Hugging Face PEFT + Transformers.
3. Offline GGUF Registration: Configures local Ollama model (qwen2.5-aicon) from the local GGUF binary.

Artifacts saved to: model_artifacts/
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OrdinalEncoder

# PyTorch and HuggingFace
import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)


def train_tabular_cutoff_model(
    data_path: str,
    output_dir: str,
    smoke_test: bool = False,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Train Gradient Boosted regression models on historical cutoff data."""
    print("=" * 70)
    print("TASK B: TRAINING TABULAR CUTOFF PREDICTION MODELS")
    print("=" * 70)

    start_time = time.time()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading tabular cutoff dataset from: {data_path}")
    df = pd.read_csv(data_path, low_memory=False)
    print(f"Loaded {len(df)} total cutoff records.")

    feature_cols = [
        "institute_code",
        "course_code",
        "seat_type",
        "cap_round",
        "stage",
        "list_type",
    ]

    # Clean and filter
    clean_df = df.dropna(subset=feature_cols + ["closing_rank", "closing_percentile"]).copy()
    clean_df["closing_rank"] = clean_df["closing_rank"].astype(float)
    clean_df["closing_percentile"] = clean_df["closing_percentile"].astype(float)
    clean_df["cap_round"] = clean_df["cap_round"].astype(int)
    clean_df["stage"] = clean_df["stage"].astype(int)

    if smoke_test:
        print("Smoke test mode enabled: sampling 2,000 records for fast training.")
        clean_df = clean_df.sample(n=min(2000, len(clean_df)), random_state=random_state)

    print(f"Dataset size for training: {len(clean_df)} records.")

    categorical_cols = ["institute_code", "course_code", "seat_type", "list_type"]
    for col in categorical_cols:
        clean_df[col] = clean_df[col].astype(str)

    encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    clean_df[categorical_cols] = encoder.fit_transform(clean_df[categorical_cols])

    X = clean_df[feature_cols].values
    y_rank = clean_df["closing_rank"].values
    y_pct = clean_df["closing_percentile"].values

    X_train, X_test, y_rank_train, y_rank_test, y_pct_train, y_pct_test = train_test_split(
        X, y_rank, y_pct, test_size=0.15, random_state=random_state
    )

    print(f"Split sizes: Train={len(X_train)}, Test={len(X_test)}")

    # 1. Train Rank Regressor
    print("Training HistGradientBoostingRegressor for Closing Rank...")
    max_iter = 50 if smoke_test else 120
    model_rank = HistGradientBoostingRegressor(
        max_iter=max_iter,
        learning_rate=0.1,
        max_leaf_nodes=63,
        min_samples_leaf=20,
        random_state=random_state,
    )
    model_rank.fit(X_train, y_rank_train)
    y_rank_pred = model_rank.predict(X_test)
    rank_mae = float(mean_absolute_error(y_rank_test, y_rank_pred))
    rank_rmse = float(np.sqrt(mean_squared_error(y_rank_test, y_rank_pred)))
    rank_r2 = float(r2_score(y_rank_test, y_rank_pred))
    print(f"  [Closing Rank]       MAE: {rank_mae:,.1f} | RMSE: {rank_rmse:,.1f} | R²: {rank_r2:.4f}")

    # 2. Train Percentile Regressor
    print("Training HistGradientBoostingRegressor for Closing Percentile...")
    model_pct = HistGradientBoostingRegressor(
        max_iter=max_iter,
        learning_rate=0.1,
        max_leaf_nodes=63,
        min_samples_leaf=20,
        random_state=random_state,
    )
    model_pct.fit(X_train, y_pct_train)
    y_pct_pred = model_pct.predict(X_test)
    pct_mae = float(mean_absolute_error(y_pct_test, y_pct_pred))
    pct_rmse = float(np.sqrt(mean_squared_error(y_pct_test, y_pct_pred)))
    pct_r2 = float(r2_score(y_pct_test, y_pct_pred))
    print(f"  [Closing Percentile] MAE: {pct_mae:.3f}% | RMSE: {pct_rmse:.3f}% | R²: {pct_r2:.4f}")

    # Save artifacts
    rank_path = out_dir / "cutoff_regressor_rank.joblib"
    pct_path = out_dir / "cutoff_regressor_percentile.joblib"
    enc_path = out_dir / "label_encoders.joblib"
    metrics_path = out_dir / "tabular_metrics.json"

    joblib.dump(model_rank, rank_path)
    joblib.dump(model_pct, pct_path)
    joblib.dump({"encoder": encoder, "feature_cols": feature_cols, "categorical_cols": categorical_cols}, enc_path)

    metrics = {
        "training_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_samples": len(clean_df),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "duration_seconds": round(time.time() - start_time, 2),
        "rank_metrics": {"mae": rank_mae, "rmse": rank_rmse, "r2": rank_r2},
        "percentile_metrics": {"mae": pct_mae, "rmse": pct_rmse, "r2": pct_r2},
        "saved_artifacts": [str(rank_path), str(pct_path), str(enc_path)],
    }
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Artifacts successfully saved to: {out_dir}")
    print(f"Execution time: {metrics['duration_seconds']}s\n")
    return metrics


def train_lora_behaviour_model(
    train_file: str,
    val_file: str,
    output_dir: str,
    smoke_test: bool = True,
    epochs: int = 1,
    batch_size: int = 2,
    lr: float = 2e-4,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Fine-tune LoRA adapter for grounded behavioural compliance and anti-hallucination."""
    print("=" * 70)
    print("TASK A: TRAINING GENERATIVE LLM BEHAVIOURAL LORA ADAPTER")
    print("=" * 70)

    start_time = time.time()
    out_dir = Path(output_dir) / "lora_adapter"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading conversational datasets:\n  Train: {train_file}\n  Val:   {val_file}")
    raw_dataset = load_dataset(
        "json",
        data_files={"train": train_file, "val": val_file},
    )

    if smoke_test:
        print("Smoke test mode: selecting 64 train samples and 16 validation samples.")
        train_ds = raw_dataset["train"].select(range(min(64, len(raw_dataset["train"]))))
        val_ds = raw_dataset["val"].select(range(min(16, len(raw_dataset["val"]))))
    else:
        train_ds = raw_dataset["train"]
        val_ds = raw_dataset["val"]

    print(f"Active dataset: Train={len(train_ds)}, Val={len(val_ds)}")

    # Use locally cached base model (TinyLlama-1.1B-Chat-v1.0)
    base_model_id = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    print(f"Loading local cached base model: {base_model_id}")
    try:
        tokenizer = AutoTokenizer.from_pretrained(base_model_id, local_files_only=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
            local_files_only=True,
        )
    except Exception as exc:
        print(f"Could not load local weights directly ({exc}); falling back to auto-download/config.")
        tokenizer = AutoTokenizer.from_pretrained("gpt2")
        tokenizer.pad_token = tokenizer.eos_token
        cfg = AutoConfig.from_pretrained("gpt2")
        model = AutoModelForCausalLM.from_config(cfg)

    # Configure PEFT LoRA
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"] if hasattr(model, "model") else ["c_attn"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    def preprocess_function(examples):
        texts = []
        for conversation in examples["messages"]:
            formatted = ""
            for msg in conversation:
                role = msg.get("role", "")
                content = msg.get("content", "")
                formatted += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            texts.append(formatted)
        encodings = tokenizer(
            texts,
            truncation=True,
            max_length=512 if smoke_test else 1024,
            padding="max_length",
        )
        encodings["labels"] = encodings["input_ids"].copy()
        return encodings

    print("Tokenizing conversational messages...")
    tokenized_train = train_ds.map(preprocess_function, batched=True, remove_columns=["messages"])
    tokenized_val = val_ds.map(preprocess_function, batched=True, remove_columns=["messages"])

    max_steps = 10 if smoke_test else -1
    training_args = TrainingArguments(
        output_dir=str(out_dir / "checkpoints"),
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=lr,
        num_train_epochs=epochs,
        max_steps=max_steps,
        logging_steps=2,
        eval_strategy="steps" if smoke_test else "epoch",
        eval_steps=5 if smoke_test else 100,
        save_strategy="steps" if smoke_test else "epoch",
        save_steps=5 if smoke_test else 100,
        save_total_limit=2,
        fp16=False,
        use_cpu=True,
        report_to="none",
        seed=random_state,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_val,
    )

    print("Executing fine-tuning optimization loop...")
    train_result = trainer.train()

    # Save fine-tuned LoRA adapters and tokenizer
    print(f"Saving fine-tuned LoRA adapter to: {out_dir}")
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    duration = round(time.time() - start_time, 2)
    metrics = {
        "training_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_model": base_model_id,
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "training_loss": float(train_result.training_loss),
        "global_steps": train_result.global_step,
        "duration_seconds": duration,
        "adapter_dir": str(out_dir),
    }

    metrics_file = out_dir / "training_metrics.json"
    metrics_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"LoRA fine-tuning complete! Loss: {train_result.training_loss:.4f} in {duration}s\n")
    return metrics


def setup_offline_ollama_model(
    gguf_path: str,
    model_name: str = "qwen2.5-aicon",
) -> bool:
    """Register local GGUF weights with Ollama."""
    print("=" * 70)
    print(f"OFFLINE LLM SETUP: REGISTERING {model_name} IN OLLAMA")
    print("=" * 70)

    gguf = Path(gguf_path).resolve()
    if not gguf.is_file():
        print(f"Warning: GGUF model file not found at: {gguf}")
        return False

    modelfile_content = f"""FROM "{str(gguf)}"
PARAMETER temperature 0.0
PARAMETER top_p 0.95
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
SYSTEM \"\"\"You are an admission decision-support assistant for Maharashtra engineering colleges. Use only the supplied evidence. Cite evidence IDs in [brackets]. Never promise admission. If evidence is missing, answer with status=insufficient_evidence.\"\"\"
"""
    modelfile_path = Path("Modelfile.aicon")
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    print(f"Created Modelfile: {modelfile_path}")

    try:
        cmd = ["ollama", "create", model_name, "-f", str(modelfile_path)]
        print(f"Executing: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(res.stdout)
        print(f"Successfully registered {model_name} in Ollama library!")
        return True
    except Exception as exc:
        print(f"Notice: Ollama registration command encountered: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Train AI-con Models (Tabular Regressor + LLM Behaviour LoRA)")
    parser.add_argument("--task", choices=["all", "tabular", "lora", "ollama"], default="all")
    parser.add_argument("--data-dir", default="training_data", help="Directory containing training data")
    parser.add_argument("--output-dir", default="model_artifacts", help="Directory to save model artifacts")
    parser.add_argument("--smoke-test", action="store_true", help="Execute fast verification smoke test")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tabular_data = data_dir / "cutoff_tabular_features.csv"
    train_jsonl = data_dir / "train.jsonl"
    val_jsonl = data_dir / "val.jsonl"
    gguf_candidate = Path("../qwen2.5-coder-3b-instruct-q5_k_m.gguf")
    if not gguf_candidate.is_file():
        gguf_candidate = Path("qwen2.5-coder-3b-instruct-q5_k_m.gguf")

    # 1. Tabular Model Training
    if args.task in ("all", "tabular"):
        if tabular_data.is_file():
            train_tabular_cutoff_model(
                str(tabular_data),
                output_dir=str(out_dir),
                smoke_test=args.smoke_test,
                random_state=args.seed,
            )
        else:
            print(f"Warning: Tabular dataset not found at {tabular_data}. Skipping Task B.")

    # 2. Generative LoRA Behaviour Model Training
    if args.task in ("all", "lora"):
        if train_jsonl.is_file() and val_jsonl.is_file():
            train_lora_behaviour_model(
                train_file=str(train_jsonl),
                val_file=str(val_jsonl),
                output_dir=str(out_dir),
                smoke_test=args.smoke_test,
                epochs=args.epochs,
                batch_size=args.batch_size,
                lr=args.lr,
                random_state=args.seed,
            )
        else:
            print(f"Warning: Conversational SFT files not found. Skipping Task A.")

    # 3. Offline Ollama Model Setup
    if args.task in ("all", "ollama"):
        setup_offline_ollama_model(str(gguf_candidate))


if __name__ == "__main__":
    main()
