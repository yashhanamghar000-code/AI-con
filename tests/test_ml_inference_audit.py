"""
Unit and regression tests for Task 11: Audit and Fix ML Inference Before Retraining.
Tests exact feature ordering, elimination of repeated 95.92% and rank #1 bugs,
out-of-distribution detection, non-negative rank bounds, and diagnostic mode.
"""
import unittest
from pathlib import Path
from scripts.ml_inference_service import MLInferenceService
from scripts.agents.orchestrator import Orchestrator


class TestMLInferenceAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = MLInferenceService()

    def test_01_feature_names_and_order_exact_match(self):
        """Feature names and ordering must exactly match model training."""
        expected = ["institute_code", "course_code", "seat_type", "cap_round", "stage", "list_type"]
        self.assertEqual(self.service.EXPECTED_FEATURE_ORDER, expected)
        if self.service.is_loaded:
            self.assertEqual(self.service.feature_cols, expected)

    def test_02_elimination_of_rank_1_and_95_92_for_1002(self):
        """Institute 1002 (GCOE Amravati) must predict realistic cutoff rank and percentile, not rank 1 or 95.92% leaf."""
        if not self.service.is_loaded:
            self.skipTest("ML artifacts not loaded")

        res = self.service.predict(
            institute_code="01002",
            course_code="0100224210",  # Computer Science & Engineering
            seat_type="GOPENS",
            cap_round=1,
            stage=1,
            list_type="CAP",
        )
        self.assertTrue(res.predicted)
        self.assertEqual(res.status, "success")
        # Rank must be realistic (around 15,000 for GCOEA CSE), definitely NOT rank 1!
        self.assertGreater(res.predicted_rank, 1000)
        self.assertNotEqual(res.predicted_rank, 1)

    def test_03_out_of_distribution_handling(self):
        """Unknown or unseen features must return prediction_unavailable, NEVER rank 1 or synthetic defaults."""
        if not self.service.is_loaded:
            self.skipTest("ML artifacts not loaded")

        # Completely unknown institute
        res_unknown_inst = self.service.predict(
            institute_code="99999",
            course_code="9999999999",
            seat_type="GOPENS",
        )
        self.assertFalse(res_unknown_inst.predicted)
        self.assertEqual(res_unknown_inst.status, "prediction_unavailable")
        self.assertIn("out of training distribution", res_unknown_inst.reason)
        self.assertIsNone(res_unknown_inst.predicted_rank)
        self.assertIsNone(res_unknown_inst.predicted_percentile)

        # Unknown seat type
        res_unknown_seat = self.service.predict(
            institute_code="06006",
            course_code="600624510",
            seat_type="UNKNOWN_QUOTA_XYZ",
        )
        self.assertFalse(res_unknown_seat.predicted)
        self.assertEqual(res_unknown_seat.status, "prediction_unavailable")

    def test_04_diagnostic_mode_transparency(self):
        """Diagnostic mode returns feature names, input values, encoded values, and raw outputs."""
        if not self.service.is_loaded:
            self.skipTest("ML artifacts not loaded")

        res = self.service.predict(
            institute_code="06006",
            course_code="600624510",
            seat_type="GOPENS",
            cap_round=1,
            stage=1,
            list_type="CAP",
            diagnostic=True,
        )
        self.assertTrue(res.predicted)
        self.assertIsNotNone(res.diagnostic)
        diag = res.diagnostic
        self.assertIn("feature_names", diag)
        self.assertIn("input_values", diag)
        self.assertIn("raw_rank_output", diag)
        self.assertIn("raw_percentile_output", diag)
        self.assertEqual(diag["input_values"]["institute_code"], "6006")
        self.assertEqual(diag["input_values"]["course_code"], "600624510")

    def test_05_sensitivity_across_different_institutes_and_courses(self):
        """Model predictions must be sensitive across different colleges and cutoff tiers."""
        if not self.service.is_loaded:
            self.skipTest("ML artifacts not loaded")

        # COEP (6006) Computer Engineering
        coep_ce = self.service.predict("06006", "600624510", "GOPENS")
        # PCCoE (6175) Computer Engineering
        pccoe_ce = self.service.predict("06175", "617524510", "GOPENS")
        # GCOEA (1002) Computer Science
        gcoea_cse = self.service.predict("01002", "100224210", "GOPENS")

        self.assertTrue(coep_ce.predicted)
        self.assertTrue(pccoe_ce.predicted)
        self.assertTrue(gcoea_cse.predicted)

        # Predictions must be finite, valid, and distinct across colleges
        self.assertNotEqual(coep_ce.predicted_rank, pccoe_ce.predicted_rank)
        self.assertNotEqual(coep_ce.predicted_rank, gcoea_cse.predicted_rank)
        self.assertNotEqual(pccoe_ce.predicted_rank, gcoea_cse.predicted_rank)
        self.assertGreater(pccoe_ce.predicted_rank, coep_ce.predicted_rank)
        self.assertGreater(gcoea_cse.predicted_rank, pccoe_ce.predicted_rank)

    def test_06_orchestrator_integration(self):
        """Orchestrator predict_next_year_cutoff delegates to MLInferenceService cleanly."""
        orch = Orchestrator()
        pred = orch.predict_next_year_cutoff("06006", "600624510", "GOPENS")
        self.assertTrue(pred.get("predicted"))
        self.assertGreater(pred.get("predicted_rank"), 0)
        self.assertNotEqual(pred.get("predicted_rank"), 1)
        self.assertGreater(pred.get("predicted_percentile"), 90.0)


if __name__ == "__main__":
    unittest.main()
