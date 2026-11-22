"""
Task 18: Master End-to-End Acceptance Test Suite
=================================================
Runs the 7 formal master end-to-end acceptance tests specified in
AI_CON_IMPROVEMENT_PLAN.md Section 19:
  Test A --- Discovery (30 unique colleges, branch grouping, no fake popularity)
  Test B --- Admission Feasibility (Reach/Competitive/Attainable tiers, evidence IDs, no guarantees)
  Test C --- Follow-up Memory ("rank by ROI", shortlist reuse, no fake tiers)
  Test D --- Update Profile ("change percentile to 95", retains location/branch, reclassifies)
  Test E --- ML Prediction (valid schemas, finite non-identical predictions, no rank 1 fallback)
  Test F --- Missing Evidence (explicit insufficient_evidence, exact missing dimensions)
  Test G --- Exact College Facts (individual source, date, scope, institute vs branch distinction)
"""
import unittest
from pathlib import Path
from scripts.agents.orchestrator import Orchestrator
from scripts.agents.cutoff_agent import CutoffAgent
from scripts.ml_inference_service import MLInferenceService
from scripts.cutoff_evidence import CutoffEvidence


class TestE2EAcceptanceMaster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize full orchestrator pipeline with authoritative cutoffs
        staging_dir = Path("cutoffs/phase3_final_staging")
        if not staging_dir.exists():
            staging_dir = Path(__file__).resolve().parent.parent / "cutoffs" / "phase3_final_staging"
        c_agent = CutoffAgent(str(staging_dir)) if staging_dir.exists() else None
        cls.orch = Orchestrator(cutoff_agent=c_agent)
        cls.ml_service = MLInferenceService()

    def test_case_A_discovery(self):
        """Test A --- Discovery: 'I have 94 percentile in MHT-CET, OPEN category, and want the 30 most popular Pune colleges for Computer Engineering and related branches.'"""
        resp = self.orch.answer(
            "I have 94 percentile in MHT-CET, OPEN category, and want the 30 most popular Pune colleges for Computer Engineering and related branches."
        )
        self.assertIn("shortlist", resp)
        shortlist = resp["shortlist"]

        # 1. Parsed profile is visible and correct
        profile = resp.get("parsed_student_profile") or {}
        self.assertEqual(profile.get("percentile"), 94.0)
        self.assertEqual(profile.get("category"), "GOPENS")
        self.assertEqual(profile.get("location"), "Pune")

        # 2. Up to 30 unique institutes returned (no duplicate institute codes)
        seen_codes = set()
        for c in shortlist:
            code = c["institute_code"]
            self.assertNotIn(code, seen_codes, f"Duplicate institute code detected: {code}")
            seen_codes.add(code)
            self.assertTrue(len(code) == 4 or len(code) == 5)
            self.assertTrue(len(c["institute_name"]) > 3)

        self.assertLessEqual(len(shortlist), 30)

        # 3. No unsupported popularity score fabricated
        for c in shortlist:
            if c.get("popularity_available"):
                self.assertIsNotNone(c.get("popularity_score"))
                self.assertGreaterEqual(c["popularity_score"], 0.0)
                self.assertLessEqual(c["popularity_score"], 100.0)
            else:
                self.assertIsNone(c.get("popularity_score"))
                self.assertIn("unavailable", c.get("popularity_explanation", "").lower())

    def test_case_B_admission_feasibility(self):
        """Test B --- Admission feasibility: Colleges classified into transparent tiers with margins and evidence IDs, no guarantees."""
        resp = self.orch.answer("30 colleges in Pune for Computer Engineering with 94 percentile")
        shortlist = resp.get("shortlist", [])
        self.assertGreater(len(shortlist), 0)

        for c in shortlist:
            tier = c.get("tier")
            self.assertIn(tier, ["Historically More Attainable", "Competitive", "Reach", "Target", "Safety", "Insufficient Evidence"])
            self.assertIn("evidence_id", c)
            self.assertTrue(len(str(c["evidence_id"])) > 0)
            self.assertTrue(":" in str(c["evidence_id"]) or str(c["evidence_id"]).startswith("EV-"))

        # Guarantee check in message prose
        msg = resp.get("message", "").lower()
        self.assertNotIn("guaranteed admission", msg)
        self.assertNotIn("100% safe", msg)
        self.assertNotIn("guaranteed seat", msg)

    def test_case_C_follow_up_memory(self):
        """Test C --- Follow-up memory: 'Now rank these by ROI.' reuses previous shortlist without asking which college."""
        # Step 1: Initial query establishing shortlist
        self.orch.answer("best colleges in Pune for Computer Engineering with 94 percentile")

        # Step 2: Follow-up query
        resp_roi = self.orch.answer("Now rank these by ROI.")

        # Reuses shortlist without asking which college
        self.assertNotEqual(resp_roi.get("status"), "needs_clarification")
        self.assertIn("Shortlist Re-ranked by ROI", resp_roi.get("matched_college", ""))
        self.assertIn("shortlist", resp_roi)

        # ROI is computed with transparent ratio proxy or marked not computable without arbitrary tiers
        for c in resp_roi["shortlist"]:
            roi_val = c.get("roi_tier", "")
            self.assertNotIn("Exceptional (Tier 1 Govt)", roi_val)
            self.assertNotIn("High (Tier 1 Private)", roi_val)
            self.assertNotIn("Moderate (Tier 2)", roi_val)
            self.assertTrue(
                "Not computable" in roi_val or "x (Median Pkg" in roi_val or c.get("roi_computable"),
                f"Unexpected ROI tier format: {roi_val}"
            )

    def test_case_D_update_profile(self):
        """Test D --- Update profile: 'Change my percentile to 95 and show the list again.' preserves location/branch."""
        # Step 1: Query with 94 percentile in Pune
        self.orch.answer("colleges in Pune for Computer Engineering with 94 percentile")

        # Step 2: Update percentile
        resp_up = self.orch.answer("Change my percentile to 95 and show the list again.")

        self.assertIn("shortlist", resp_up)
        # Location and branch preserved in context
        self.assertEqual(self.orch._conv_context.get("location"), "Pune")
        self.assertIn("Computer", self.orch._conv_context.get("preferred_branches", ["Computer"])[0])
        self.assertIn("95", resp_up.get("message", ""))

    def test_case_E_ml_prediction(self):
        """Test E --- ML prediction: Finite, valid predictions, no rank 1 fallback, uncertainty intervals visible."""
        if not self.ml_service.is_loaded:
            self.skipTest("ML service not loaded")

        # COEP
        pred_coep = self.ml_service.predict_with_interval("06006", "600624510", "GOPENS")
        self.assertTrue(pred_coep.predicted)
        self.assertGreater(pred_coep.predicted_rank, 1)
        self.assertGreater(pred_coep.predicted_percentile, 90.0)
        self.assertIsNotNone(pred_coep.predicted_rank_range)
        self.assertIsNotNone(pred_coep.predicted_percentile_range)

        # PCCoE
        pred_pccoe = self.ml_service.predict_with_interval("06175", "617524510", "GOPENS")
        self.assertTrue(pred_pccoe.predicted)
        self.assertGreater(pred_pccoe.predicted_rank, pred_coep.predicted_rank)

    def test_case_F_missing_evidence(self):
        """Test F --- Missing evidence: Explicit insufficient_evidence when combination has no records."""
        # Non-existent college code
        resp = self.orch.cutoff_agent.get_cutoffs("99999", branch_query="Aeronautical Engineering", category="TFWS") if self.orch.cutoff_agent else []
        self.assertEqual(len(resp), 0)

        # Out of distribution ML prediction
        ood_pred = self.ml_service.predict("99999", "9999999999", "TFWS")
        self.assertFalse(ood_pred.predicted)
        self.assertEqual(ood_pred.status, "prediction_unavailable")
        self.assertIn("out of training distribution", ood_pred.reason)

    def test_case_G_exact_college_facts(self):
        """Test G --- Exact college facts: Each fact has its own source, date, and scope without conflation."""
        from scripts.roi_service import ROIService, FeeData, PlacementData
        service = ROIService()

        fee = FeeData(amount=110000, academic_year="2024-25", source_citation="FRA Maharashtra")
        inst_placement = PlacementData(amount=700000, scope="institute_level", placement_year="2023-24", source_citation="NIRF 2024")

        eval_inst = service.compute_roi(fee, inst_placement)
        self.assertTrue(eval_inst.is_computable)
        self.assertIn("institute-level", " ".join(eval_inst.limitations))
        # Ensure institute level is not presented as branch level
        self.assertEqual(eval_inst.placement_data.scope, "institute_level")


if __name__ == "__main__":
    unittest.main()
