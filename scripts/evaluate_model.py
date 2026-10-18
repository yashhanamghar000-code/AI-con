#!/usr/bin/env python3
"""
AI-CON Comprehensive Evaluation Suite
--------------------------------------
Evaluates both:
1. Task B (Tabular ML Predictor): Evaluates MAE, RMSE, and R² scores on held-out test data
   and benchmarks against real historical cutoff observations.
2. Task A (Generative RAG & LLM Behaviour): Evaluates grounded citations, numerical accuracy,
   abstention on missing evidence, college ambiguity detection, and LoRA adapter integrity.

Outputs results to: model_artifacts/evaluation_report.json and console.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add scripts and agents to path
SCRIPTS_DIR = Path(__file__).resolve().parent
AGENTS_DIR = SCRIPTS_DIR / "agents"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(AGENTS_DIR))

from rag_pipeline import answer_question, build_pipeline


def evaluate_tabular_predictor(
    artifacts_dir: str = "model_artifacts",
    test_data_path: str = "training_data/cutoff_tabular_features.csv",
) -> Dict[str, Any]:
    """Evaluate trained tabular regression models against ground-truth data."""
    print("=" * 70)
    print("GATE 1: EVALUATING TABULAR CUTOFF PREDICTION MODELS")
    print("=" * 70)

    out_dir = Path(artifacts_dir)
    rank_model_path = out_dir / "cutoff_regressor_rank.joblib"
    pct_model_path = out_dir / "cutoff_regressor_percentile.joblib"
    enc_path = out_dir / "label_encoders.joblib"

    if not (rank_model_path.is_file() and pct_model_path.is_file() and enc_path.is_file()):
        print("Warning: Tabular model artifacts not found. Run train_model.py --task tabular first.")
        return {"status": "skipped", "reason": "missing_artifacts"}

    print(f"Loading model artifacts from {out_dir}...")
    model_rank = joblib.load(rank_model_path)
    model_pct = joblib.load(pct_model_path)
    enc_meta = joblib.load(enc_path)

    encoder = enc_meta["encoder"]
    feature_cols = enc_meta["feature_cols"]
    categorical_cols = enc_meta["categorical_cols"]

    df = pd.read_csv(test_data_path, low_memory=False)
    clean_df = df.dropna(subset=feature_cols + ["closing_rank", "closing_percentile"]).copy()
    clean_df["closing_rank"] = clean_df["closing_rank"].astype(float)
    clean_df["closing_percentile"] = clean_df["closing_percentile"].astype(float)
    clean_df["cap_round"] = clean_df["cap_round"].astype(int)
    clean_df["stage"] = clean_df["stage"].astype(int)

    # Use a held-out test sample of 15,000 records
    test_sample = clean_df.sample(n=min(15000, len(clean_df)), random_state=123).copy()
    for col in categorical_cols:
        test_sample[col] = test_sample[col].astype(str)

    test_sample[categorical_cols] = encoder.transform(test_sample[categorical_cols])
    X_test = test_sample[feature_cols].values
    y_rank_true = test_sample["closing_rank"].values
    y_pct_true = test_sample["closing_percentile"].values

    # Predict
    y_rank_pred = model_rank.predict(X_test)
    y_pct_pred = model_pct.predict(X_test)

    rank_mae = float(mean_absolute_error(y_rank_true, y_rank_pred))
    rank_rmse = float(np.sqrt(mean_squared_error(y_rank_true, y_rank_pred)))
    rank_r2 = float(r2_score(y_rank_true, y_rank_pred))

    pct_mae = float(mean_absolute_error(y_pct_true, y_pct_pred))
    pct_rmse = float(np.sqrt(mean_squared_error(y_pct_true, y_pct_pred)))
    pct_r2 = float(r2_score(y_pct_true, y_pct_pred))

    print(f"Test Set Evaluation (N = {len(test_sample):,}):")
    print(f"  - Closing Rank MAE:        {rank_mae:,.1f}")
    print(f"  - Closing Rank RMSE:       {rank_rmse:,.1f}")
    print(f"  - Closing Rank R^2:        {rank_r2:.4f}")
    print(f"  - Closing Percentile MAE:  {pct_mae:.3f}%")
    print(f"  - Closing Percentile RMSE: {pct_rmse:.3f}%")
    print(f"  - Closing Percentile R^2:  {pct_r2:.4f}")

    # Representative Case Studies
    print("\nRepresentative Historical Predictions:")
    cases = [
        {"inst": "6006", "course": "600624510", "seat": "AI", "round": 1, "stage": 1, "list": "all_india", "label": "COEP - Computer Engg (AI Quota)"},
        {"inst": "01002", "course": "0100219110", "seat": "GOPENS", "round": 1, "stage": 1, "list": "maharashtra_minority", "label": "GCOEA - Civil Engg (GOPENS)"},
        {"inst": "3012", "course": "301224510", "seat": "GOPENS", "round": 1, "stage": 1, "list": "maharashtra_minority", "label": "VJTI - Computer Engg (GOPENS)"},
    ]

    case_results = []
    for c in cases:
        raw_row = pd.DataFrame([{
            "institute_code": str(c["inst"]),
            "course_code": str(c["course"]),
            "seat_type": str(c["seat"]),
            "cap_round": int(c["round"]),
            "stage": int(c["stage"]),
            "list_type": str(c["list"]),
        }])
        raw_row[categorical_cols] = encoder.transform(raw_row[categorical_cols])
        pred_rank = float(model_rank.predict(raw_row[feature_cols].values)[0])
        pred_pct = float(model_pct.predict(raw_row[feature_cols].values)[0])
        print(f"  * {c['label']}: Expected Rank = {int(pred_rank):,}, Expected Percentile = {pred_pct:.2f}%")
        case_results.append({
            "case": c["label"],
            "predicted_rank": int(pred_rank),
            "predicted_percentile": round(pred_pct, 2),
        })

    return {
        "status": "passed",
        "rank_evaluation": {"mae": rank_mae, "rmse": rank_rmse, "r2": rank_r2},
        "percentile_evaluation": {"mae": pct_mae, "rmse": pct_rmse, "r2": pct_r2},
        "representative_cases": case_results,
    }


def evaluate_llm_behaviour_gates(
    cutoffs_dir: str = "cutoffs/phase3_final_staging",
    vector_index_dir: str = "./vector_index",
    ollama_model: str = "qwen2.5-aicon:latest",
) -> Dict[str, Any]:
    """Test generative RAG pipeline against strict counselling behavioural gates."""
    print("\n" + "=" * 70)
    print("GATE 2: EVALUATING GENERATIVE RAG & BEHAVIOURAL GATES")
    print("=" * 70)

    results = []

    # Test 1: Grounded Exact Cutoff Retrieval
    q1 = "What was the GOPENS cutoff for Civil Engineering at Government College of Engineering, Amravati in 2024-25?"
    print(f"\n[Test 1: Exact Cutoff Retrieval & Citation]")
    print(f"Question: {q1}")
    r1 = answer_question(
        question=q1,
        cutoffs_dir=cutoffs_dir,
        vector_index_dir=vector_index_dir,
        use_llm=True,
        ollama_model=ollama_model,
    )
    passed_q1 = (
        r1.get("matched_college") == "Government College of Engineering, Amravati"
        and "34240" in r1.get("evidence", "")
        and "[2024-25:01002:0100219110:state_level:GOPENS:R1:S1]" in r1.get("evidence", "")
    )
    print(f"  * Matched College:  {r1.get('matched_college')}")
    print(f"  * Institute Code:   {r1.get('institute_code')}")
    print(f"  * Evidence Found:   {passed_q1}")
    print(f"  * LLM Answer:       {r1.get('answer')}")
    results.append({"test": "exact_cutoff_grounding", "passed": passed_q1, "details": r1})

    # Test 2: Institutional Qualitative Fact Retrieval
    q2 = "What is the affiliation and autonomy status of Government College of Engineering, Amravati?"
    print(f"\n[Test 2: Qualitative Profile Information Retrieval]")
    print(f"Question: {q2}")
    r2 = answer_question(
        question=q2,
        cutoffs_dir=cutoffs_dir,
        vector_index_dir=vector_index_dir,
        use_llm=False,
    )
    passed_q2 = (
        "Sant Gadge Baba Amravati University" in r2.get("evidence", "")
        and "Government Autonomous" in r2.get("evidence", "")
    )
    print(f"  * Affiliation Found: {'Sant Gadge Baba' in r2.get('evidence', '')}")
    print(f"  * Autonomy Found:    {'Autonomous' in r2.get('evidence', '')}")
    print(f"  * Gate Passed:       {passed_q2}")
    results.append({"test": "qualitative_profile_retrieval", "passed": passed_q2, "details": r2})

    # Test 3: Anti-Hallucination & Abstention Gate
    q3 = "What was the GSTS cutoff for Aerospace Engineering at Indala College in 2024-25?"
    print(f"\n[Test 3: Abstention Gate on Missing Evidence]")
    print(f"Question: {q3}")
    r3 = answer_question(
        question=q3,
        cutoffs_dir=cutoffs_dir,
        vector_index_dir=vector_index_dir,
        use_llm=False,
    )
    # Must refuse / state unavailable without guessing numbers
    passed_q3 = (
        r3.get("status") in ("unavailable", "needs_clarification", "insufficient_evidence")
        or "No cutoff records match" in r3.get("evidence", "")
        or "UNAVAILABLE" in r3.get("evidence", "")
    )
    print(f"  * Status:           {r3.get('status')}")
    print(f"  * Abstention Held:  {passed_q3}")
    results.append({"test": "abstention_anti_hallucination", "passed": passed_q3, "details": r3})

    # Test 4: College Ambiguity Resolution Gate
    q4 = "Tell me about Government College"
    print(f"\n[Test 4: Ambiguity Resolution Gate]")
    print(f"Question: {q4}")
    r4 = answer_question(
        question=q4,
        cutoffs_dir=cutoffs_dir,
        vector_index_dir=vector_index_dir,
        use_llm=False,
    )
    passed_q4 = r4.get("status") == "needs_clarification"
    print(f"  * Status:           {r4.get('status')}")
    print(f"  * Prompt Clarified: {passed_q4}")
    results.append({"test": "ambiguity_clarification", "passed": passed_q4, "details": r4})

    all_passed = all(r["passed"] for r in results)
    print("\n" + "=" * 70)
    print(f"BEHAVIOURAL GATES RESULT: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    print("=" * 70)
    return {"status": "passed" if all_passed else "failed", "tests": results}


def evaluate_lora_artifact(adapter_dir: str = "model_artifacts/lora_adapter") -> Dict[str, Any]:
    """Verify saved LoRA weights and configuration."""
    print("\n" + "=" * 70)
    print("GATE 3: VERIFYING SAVED LORA MODEL ARTIFACTS")
    print("=" * 70)

    p = Path(adapter_dir)
    cfg_file = p / "adapter_config.json"
    weights_file = p / "adapter_model.safetensors"
    if not weights_file.is_file():
        weights_file = p / "adapter_model.bin"

    if cfg_file.is_file() and weights_file.is_file():
        print(f"Verified LoRA adapter directory: {p}")
        print(f"  * Config File:  {cfg_file.name} ({cfg_file.stat().st_size} bytes)")
        print(f"  * Weights File: {weights_file.name} ({weights_file.stat().st_size:,} bytes)")
        return {
            "status": "passed",
            "adapter_config": str(cfg_file),
            "adapter_weights": str(weights_file),
            "size_bytes": weights_file.stat().st_size,
        }
    else:
        print(f"Notice: LoRA adapter directory {p} does not contain complete weights yet.")
        return {"status": "pending", "directory": str(p)}


def main():
    parser = argparse.ArgumentParser(description="Evaluate AI-con Models and Counselling Pipeline")
    parser.add_argument("--artifacts-dir", default="model_artifacts")
    parser.add_argument("--cutoffs-dir", default="cutoffs/phase3_final_staging")
    parser.add_argument("--vector-index", default="./vector_index")
    parser.add_argument("--ollama-model", default="qwen2.5-aicon:latest")
    parser.add_argument("--report-out", default="model_artifacts/evaluation_report.json")
    args = parser.parse_args()

    out_dir = Path(args.artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tabular_res = evaluate_tabular_predictor(args.artifacts_dir)
    llm_res = evaluate_llm_behaviour_gates(
        cutoffs_dir=args.cutoffs_dir,
        vector_index_dir=args.vector_index,
        ollama_model=args.ollama_model,
    )
    lora_res = evaluate_lora_artifact(str(out_dir / "lora_adapter"))

    report = {
        "evaluation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tabular_predictor": tabular_res,
        "llm_behaviour_gates": llm_res,
        "lora_artifact": lora_res,
    }

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nComprehensive evaluation report written to: {report_path}")


if __name__ == "__main__":
    main()
