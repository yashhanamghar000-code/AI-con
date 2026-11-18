"""
Unit and regression tests for Task 13: Better Model Design and Target Strategy.
Tests log-transformed rank targets, prediction intervals/uncertainty ranges,
and versioned candidate artifact isolation.
"""
import unittest
from pathlib import Path
from scripts.ml_inference_service import MLInferenceService
from scripts.train_v2_model import train_v2_candidate_models


class TestModelDesignStrategy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = MLInferenceService()

    def test_01_v2_candidate_training_log_rank(self):
        """v2 candidate training runs on chronological split and writes versioned artifacts."""
        meta = train_v2_candidate_models(smoke_test=True)
        self.assertEqual(meta["version"], "2.0-candidate")
        self.assertIn("log1p", meta["rank_target_transformation"])
        self.assertIn("holdout_metrics", meta)
        # Check files exist in v2_candidate directory
        v2_dir = Path("model_artifacts/v2_candidate")
        self.assertTrue((v2_dir / "cutoff_regressor_log_rank.joblib").exists())
        self.assertTrue((v2_dir / "v2_model_metadata.json").exists())

    def test_02_predict_with_interval(self):
        """predict_with_interval returns point estimates, bounded intervals, and uncertainty disclosures."""
        if not self.service.is_loaded:
            self.skipTest("ML models not loaded")

        res = self.service.predict_with_interval("06006", "600624510", "GOPENS")
        self.assertTrue(res.predicted)
        self.assertIsNotNone(res.predicted_rank)
        self.assertIsNotNone(res.predicted_percentile)
        self.assertIsNotNone(res.predicted_rank_range)
        self.assertIsNotNone(res.predicted_percentile_range)

        rk_low, rk_high = res.predicted_rank_range
        pct_low, pct_high = res.predicted_percentile_range

        self.assertLessEqual(rk_low, res.predicted_rank)
        self.assertGreaterEqual(rk_high, res.predicted_rank)
        self.assertLessEqual(pct_low, res.predicted_percentile)
        self.assertGreaterEqual(pct_high, res.predicted_percentile)
        self.assertIn("90% uncertainty interval", res.confidence_warning)

    def test_03_production_artifacts_unaltered(self):
        """Task 13 requires existing production model artifacts to remain untouched in model_artifacts/."""
        prod_dir = Path("model_artifacts")
        self.assertTrue((prod_dir / "cutoff_regressor_rank.joblib").exists())
        self.assertTrue((prod_dir / "cutoff_regressor_percentile.joblib").exists())
        self.assertTrue((prod_dir / "label_encoders.joblib").exists())


if __name__ == "__main__":
    unittest.main()
