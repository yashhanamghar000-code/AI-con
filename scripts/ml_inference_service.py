"""
ML Inference Service (Task 11)
------------------------------
Provides audited, verified ML inference for historical cutoff predictions.
Eliminates the defect where multiple colleges predicted identical 95.92% cutoffs
and rank #1 fallbacks.

Rules & Anti-Hallucination Contracts (Task 11):
1. The inference feature names and order exactly match training:
   ['institute_code', 'course_code', 'seat_type', 'cap_round', 'stage', 'list_type']
2. Categorical values are strictly checked against fitted encoder categories.
   If an institute, course, seat type, or list type is out of distribution, the
   service returns 'prediction_unavailable' instead of fabricating rank #1 or 95.92%.
3. Negative or non-physical model predictions are rejected as invalid, NEVER clamped to rank 1.
4. Correctly maps Maharashtra State CAP seats to 'maharashtra_minority' and All-India seats to 'all_india'.
5. Diagnostic mode exposes feature names, encoded values, and raw model outputs without secrets.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MLPredictionResult:
    predicted: bool
    status: str  # "success" | "prediction_unavailable" | "model_not_loaded"
    predicted_rank: Optional[int] = None
    predicted_percentile: Optional[float] = None
    target_year: str = "2026-27"
    reason: Optional[str] = None
    confidence_warning: Optional[str] = None
    diagnostic: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "predicted": self.predicted,
            "status": self.status,
            "predicted_rank": self.predicted_rank,
            "predicted_percentile": self.predicted_percentile,
            "target_year": self.target_year,
        }
        if self.reason:
            res["reason"] = self.reason
        if self.confidence_warning:
            res["confidence_warning"] = self.confidence_warning
        if self.diagnostic:
            res["diagnostic"] = self.diagnostic
        return res


class MLInferenceService:
    """Service to execute verified ML inference for expected next-year cutoff percentiles and ranks."""

    EXPECTED_FEATURE_ORDER = [
        "institute_code",
        "course_code",
        "seat_type",
        "cap_round",
        "stage",
        "list_type",
    ]

    def __init__(self, artifacts_dir: Optional[Path] = None):
        if artifacts_dir is None:
            # Default to repo_staging/model_artifacts
            proj_root = Path(__file__).resolve().parent.parent
            artifacts_dir = proj_root / "model_artifacts"

        self.artifacts_dir = Path(artifacts_dir)
        self.is_loaded = False
        self.rank_model = None
        self.pct_model = None
        self.encoder = None
        self.feature_cols = []
        self.categorical_cols = []

        self._load_artifacts()

    def _load_artifacts(self) -> None:
        """Load joblib model artifacts and fitted encoders."""
        try:
            import joblib
            rank_p = self.artifacts_dir / "cutoff_regressor_rank.joblib"
            pct_p = self.artifacts_dir / "cutoff_regressor_percentile.joblib"
            enc_p = self.artifacts_dir / "label_encoders.joblib"

            if rank_p.exists() and pct_p.exists() and enc_p.exists():
                self.rank_model = joblib.load(rank_p)
                self.pct_model = joblib.load(pct_p)
                enc_info = joblib.load(enc_p)
                self.encoder = enc_info.get("encoder")
                self.feature_cols = enc_info.get("feature_cols", self.EXPECTED_FEATURE_ORDER)
                self.categorical_cols = enc_info.get("categorical_cols", ["institute_code", "course_code", "seat_type", "list_type"])
                self.is_loaded = True
        except Exception as exc:
            logger.warning(f"MLInferenceService could not load artifacts from {self.artifacts_dir}: {exc}")
            self.is_loaded = False

    def normalize_institute_code(self, code: str) -> str:
        """Normalize code to match encoder training strings (e.g. '06006' -> '6006')."""
        clean = str(code).strip()
        stripped = clean.lstrip('0')
        return stripped if stripped else clean

    def normalize_course_code(self, institute_code: str, course_code: Optional[str] = None) -> str:
        """Normalize course code to match encoder training strings without leading zeros."""
        inst_clean = self.normalize_institute_code(institute_code)
        if course_code:
            c_clean = str(course_code).strip()
            # If course_code has leading zero e.g. '0100224210', strip to '100224210'
            stripped = c_clean.lstrip('0')
            return stripped if stripped else c_clean
        # Default course code fallback based on institute prefix
        return f"{inst_clean}24510"

    def normalize_list_type(self, list_type: str, seat_type: str) -> str:
        """Correctly map quota/seat type to training list_type categories."""
        s_upper = str(seat_type).upper().strip()
        l_lower = str(list_type).lower().strip()

        if s_upper == "AI" or "all_india" in l_lower or "all india" in l_lower:
            return "all_india"
        # All Maharashtra State CAP seats (GOPENS, LOPENS, EWS, TFWS, OBC, etc.)
        return "maharashtra_minority"

    def predict(
        self,
        institute_code: str,
        course_code: Optional[str] = None,
        seat_type: str = "GOPENS",
        cap_round: int = 1,
        stage: int = 1,
        list_type: str = "CAP",
        diagnostic: bool = False,
    ) -> MLPredictionResult:
        """Execute validated ML prediction with strict out-of-distribution guards."""
        if not self.is_loaded or self.rank_model is None or self.pct_model is None or self.encoder is None:
            return MLPredictionResult(
                predicted=False,
                status="model_not_loaded",
                reason="ML prediction models or encoders are not loaded.",
            )

        # 1. Normalize feature values
        inst_str = self.normalize_institute_code(institute_code)
        c_code_str = self.normalize_course_code(institute_code, course_code)
        s_type_str = str(seat_type).upper().strip()
        l_type_str = self.normalize_list_type(list_type, seat_type)
        round_int = int(cap_round)
        stage_int = int(stage)

        # 2. Out-of-Distribution (OOD) checks against fitted encoder categories
        inst_cats = self.encoder.categories_[0]
        course_cats = self.encoder.categories_[1]
        seat_cats = self.encoder.categories_[2]
        list_cats = self.encoder.categories_[3]

        missing_dims = []
        if inst_str not in inst_cats:
            missing_dims.append(f"institute_code '{inst_str}'")
        if c_code_str not in course_cats:
            missing_dims.append(f"course_code '{c_code_str}'")
        if s_type_str not in seat_cats:
            missing_dims.append(f"seat_type '{s_type_str}'")
        if l_type_str not in list_cats:
            missing_dims.append(f"list_type '{l_type_str}'")

        if missing_dims:
            # Task 11: Never pass unknown values that collapse into encoder -1 unknown leaf!
            reason = f"Input feature out of training distribution: unknown {', '.join(missing_dims)}."
            diag = None
            if diagnostic:
                diag = {
                    "feature_names": self.feature_cols,
                    "input_values": {
                        "institute_code": inst_str,
                        "course_code": c_code_str,
                        "seat_type": s_type_str,
                        "cap_round": round_int,
                        "stage": stage_int,
                        "list_type": l_type_str,
                    },
                    "missing_dimensions": missing_dims,
                }
            return MLPredictionResult(
                predicted=False,
                status="prediction_unavailable",
                reason=reason,
                diagnostic=diag,
            )

        # 3. Transform categories using fitted encoder
        cat_vals = np.array([[inst_str, c_code_str, s_type_str, l_type_str]])
        encoded_cat = self.encoder.transform(cat_vals)

        # 4. Construct input vector in exact training feature order:
        # ["institute_code", "course_code", "seat_type", "cap_round", "stage", "list_type"]
        row = np.array([[
            encoded_cat[0][0],  # institute_code
            encoded_cat[0][1],  # course_code
            encoded_cat[0][2],  # seat_type
            round_int,          # cap_round
            stage_int,          # stage
            encoded_cat[0][3],  # list_type
        ]])

        # 5. Predict raw values
        raw_rank = float(self.rank_model.predict(row)[0])
        raw_pct = float(self.pct_model.predict(row)[0])

        # 6. Sanity validation: Never output negative ranks or clamp -17000 to 1!
        if raw_rank <= 0:
            return MLPredictionResult(
                predicted=False,
                status="prediction_unavailable",
                reason=f"Model output non-physical negative rank ({raw_rank:.1f}). Clamping to 1 is rejected.",
                diagnostic={"raw_rank": raw_rank, "raw_pct": raw_pct} if diagnostic else None,
            )

        if raw_rank > 300000:
            return MLPredictionResult(
                predicted=False,
                status="prediction_unavailable",
                reason=f"Model output rank ({raw_rank:,.0f}) exceeds total candidate pool.",
                diagnostic={"raw_rank": raw_rank, "raw_pct": raw_pct} if diagnostic else None,
            )

        # Format clean, valid predictions
        final_rank = int(round(raw_rank))
        final_pct = round(float(np.clip(raw_pct, 0.01, 99.99)), 2)

        confidence_warning = (
            "ML predictions represent statistical regressions on historical cutoff data for 2026-27 decision support. "
            "They are decision-support estimates, not official CET Cell allotments or admission guarantees."
        )

        diag = None
        if diagnostic:
            diag = {
                "feature_names": self.feature_cols,
                "input_values": {
                    "institute_code": inst_str,
                    "course_code": c_code_str,
                    "seat_type": s_type_str,
                    "cap_round": round_int,
                    "stage": stage_int,
                    "list_type": l_type_str,
                },
                "encoded_values": encoded_cat[0].tolist(),
                "raw_rank_output": raw_rank,
                "raw_percentile_output": raw_pct,
                "artifact_version": "HistGradientBoostingRegressor_v1",
            }

        return MLPredictionResult(
            predicted=True,
            status="success",
            predicted_rank=final_rank,
            predicted_percentile=final_pct,
            confidence_warning=confidence_warning,
            diagnostic=diag,
        )
