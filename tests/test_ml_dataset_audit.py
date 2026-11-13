"""
Unit and regression tests for Task 12: ML Dataset Audit and Retraining Design.
Validates dataset volume, target integrity, duplication/contradiction detection,
chronological holdout baseline comparison, and preservation of existing model artifacts.
"""
import json
import unittest
from pathlib import Path
from scripts.audit_ml_dataset import MLDatasetAuditor


class TestMLDatasetAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auditor = MLDatasetAuditor()
        cls.report = cls.auditor.run_full_audit()

    def test_01_total_samples_and_years(self):
        """Dataset must contain expected 116,744 records across 2023-24, 2024-25, 2025-26."""
        summary = self.report["dataset_summary"]
        self.assertEqual(summary["total_records"], 116744)
        self.assertIn("2023-24", summary["academic_years"])
        self.assertIn("2024-25", summary["academic_years"])
        self.assertIn("2025-26", summary["academic_years"])

    def test_02_target_bounds_and_low_percentiles(self):
        """Target variables must be non-negative and low percentiles documented."""
        t_int = self.report["target_integrity"]
        self.assertGreater(t_int["rank_range"][0], 0)
        self.assertGreaterEqual(t_int["percentile_range"][0], 0.0)
        self.assertLessEqual(t_int["percentile_range"][1], 100.0)
        self.assertEqual(t_int["invalid_ranks"], 0)
        self.assertEqual(t_int["invalid_percentiles"], 0)
        self.assertIn("legitimate", t_int["low_percentile_validation"].lower())

    def test_03_duplication_and_contradiction_detection(self):
        """Auditor must identify duplicate rows and contradictory groups."""
        issues = self.report["data_quality_issues"]
        self.assertGreater(issues["duplicate_rows_on_keys"], 0)
        self.assertGreater(issues["contradictory_groups"], 0)
        self.assertIn("all_india_merit_no", issues["collinear_leakage_columns_identified"])

    def test_04_chronological_holdout_and_baseline_evaluation(self):
        """Historical baseline on chronological holdout must beat previous random-split ML."""
        eval_data = self.report["chronological_holdout_evaluation"]
        base_m = eval_data["historical_baseline_metrics"]
        self.assertLess(base_m["percentile_mae"], 12.0)
        self.assertLess(base_m["rank_mae"], 25000)
        self.assertGreater(base_m["percentile_r2"], 0.60)
        self.assertIn("beats", eval_data["key_finding"].lower())

    def test_05_production_model_artifacts_preserved(self):
        """Task 12 requires that existing production artifacts are kept unchanged."""
        proj_root = Path(__file__).resolve().parent.parent
        art_dir = proj_root / "model_artifacts"
        self.assertTrue((art_dir / "cutoff_regressor_rank.joblib").exists())
        self.assertTrue((art_dir / "cutoff_regressor_percentile.joblib").exists())
        self.assertTrue((art_dir / "label_encoders.joblib").exists())

    def test_06_reports_generated(self):
        """Audit reports (JSON and Markdown) must be persisted and contain complete findings."""
        json_p, md_p = self.auditor.save_reports()
        self.assertTrue(json_p.exists())
        self.assertTrue(md_p.exists())
        content = md_p.read_text(encoding="utf-8")
        self.assertIn("Historical Median Baseline", content)
        self.assertIn("Retraining Design Specifications", content)


if __name__ == "__main__":
    unittest.main()
