"""
Task 13: Better Model Design and Target Strategy
-----------------------------------------------
Implements advanced model training with:
1. Chronological holdout validation (train on 2023-2025, validate on 2025-26).
2. Log-transformed rank target (np.log1p) with inverse exponential transformation (np.expm1)
   to eliminate non-physical negative rank predictions and model extreme skewness.
3. Quantile / uncertainty intervals (predicting ranges rather than false precision point estimates).
4. Strictly versioned artifact directory (model_artifacts/v2_candidate/) to preserve
   production artifacts in model_artifacts/ unchanged.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import OrdinalEncoder


def train_v2_candidate_models(
    data_path: str = "training_data/cutoff_tabular_features.csv",
    output_dir: str = "model_artifacts/v2_candidate",
    smoke_test: bool = False,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Train improved v2 models with log-rank transformation and chronological holdout."""
    start_time = time.time()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(data_path, low_memory=False)

    feature_cols = [
        "institute_code",
        "course_code",
        "seat_type",
        "cap_round",
        "stage",
        "list_type",
    ]
    categorical_cols = ["institute_code", "course_code", "seat_type", "list_type"]

    clean_df = df.dropna(subset=feature_cols + ["closing_rank", "closing_percentile"]).copy()
    clean_df = clean_df[(clean_df["closing_rank"] > 0) & (clean_df["closing_percentile"] >= 0.0) & (clean_df["closing_percentile"] <= 100.0)].copy()

    # Normalize codes to strings
    for col in categorical_cols:
        clean_df[col] = clean_df[col].astype(str)

    # 1. Chronological holdout split:
    # Train on 2023-24 and 2024-25; holdout on 2025-26
    train_mask = clean_df["academic_year"].isin(["2023-24", "2024-25"])
    test_mask = clean_df["academic_year"] == "2025-26"

    train_df = clean_df[train_mask].copy()
    test_df = clean_df[test_mask].copy()

    if smoke_test:
        train_df = train_df.sample(n=min(3000, len(train_df)), random_state=random_state)
        test_df = test_df.sample(n=min(1000, len(test_df)), random_state=random_state)

    # Fit encoder ONLY on training partition to prevent data leakage
    encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    train_df[categorical_cols] = encoder.fit_transform(train_df[categorical_cols])
    test_df[categorical_cols] = encoder.transform(test_df[categorical_cols])

    X_train = train_df[feature_cols].values
    X_test = test_df[feature_cols].values

    # Targets: Log-transform closing rank to guarantee strictly positive predictions!
    y_log_rank_train = np.log1p(train_df["closing_rank"].values)
    y_rank_test = test_df["closing_rank"].values

    y_pct_train = train_df["closing_percentile"].values
    y_pct_test = test_df["closing_percentile"].values

    max_iter = 40 if smoke_test else 100

    # 2. Train Log-Rank Model
    model_log_rank = HistGradientBoostingRegressor(
        max_iter=max_iter,
        learning_rate=0.1,
        max_leaf_nodes=45,
        min_samples_leaf=25,
        random_state=random_state,
    )
    model_log_rank.fit(X_train, y_log_rank_train)

    # Predict and inverse-transform
    pred_log_rank = model_log_rank.predict(X_test)
    pred_rank = np.expm1(pred_log_rank)

    rank_mae = float(mean_absolute_error(y_rank_test, pred_rank))
    rank_rmse = float(np.sqrt(mean_squared_error(y_rank_test, pred_rank)))
    rank_r2 = float(r2_score(y_rank_test, pred_rank))
    rank_residual_std = float(np.std(y_rank_test - pred_rank))

    # 3. Train Percentile Model
    model_pct = HistGradientBoostingRegressor(
        max_iter=max_iter,
        learning_rate=0.1,
        max_leaf_nodes=45,
        min_samples_leaf=25,
        random_state=random_state,
    )
    model_pct.fit(X_train, y_pct_train)
    pred_pct = np.clip(model_pct.predict(X_test), 0.01, 99.99)

    pct_mae = float(mean_absolute_error(y_pct_test, pred_pct))
    pct_rmse = float(np.sqrt(mean_squared_error(y_pct_test, pred_pct)))
    pct_r2 = float(r2_score(y_pct_test, pred_pct))
    pct_residual_std = float(np.std(y_pct_test - pred_pct))

    # 4. Save Versioned Artifacts
    rank_p = out_dir / "cutoff_regressor_log_rank.joblib"
    pct_p = out_dir / "cutoff_regressor_percentile.joblib"
    enc_p = out_dir / "label_encoders.joblib"
    meta_p = out_dir / "v2_model_metadata.json"

    joblib.dump(model_log_rank, rank_p)
    joblib.dump(model_pct, pct_p)
    joblib.dump({
        "encoder": encoder,
        "feature_cols": feature_cols,
        "categorical_cols": categorical_cols,
        "is_log_rank": True,
        "rank_residual_std": rank_residual_std,
        "pct_residual_std": pct_residual_std,
    }, enc_p)

    metadata = {
        "version": "2.0-candidate",
        "training_strategy": "Chronological holdout validation on unseen 2025-26 academic year",
        "rank_target_transformation": "log1p with expm1 inverse transformation",
        "sample_counts": {
            "train_samples": len(train_df),
            "holdout_samples": len(test_df),
        },
        "holdout_metrics": {
            "rank_mae": round(rank_mae, 1),
            "rank_rmse": round(rank_rmse, 1),
            "rank_r2": round(rank_r2, 4),
            "rank_residual_std": round(rank_residual_std, 1),
            "pct_mae": round(pct_mae, 2),
            "pct_rmse": round(pct_rmse, 2),
            "pct_r2": round(pct_r2, 4),
            "pct_residual_std": round(pct_residual_std, 2),
        },
        "saved_artifacts": [str(rank_p), str(pct_p), str(enc_p)],
        "duration_seconds": round(time.time() - start_time, 2),
    }
    meta_p.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke-test", action="store_true", help="Fast training for tests")
    args = ap.parse_args()
    meta = train_v2_candidate_models(smoke_test=args.smoke_test)
    print(f"v2 Candidate Model Training Complete:\n{json.dumps(meta['holdout_metrics'], indent=2)}")
