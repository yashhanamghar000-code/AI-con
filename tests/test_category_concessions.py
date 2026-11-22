"""
Unit tests for Category Out-of-Pocket Fee Concessions (Step 2 - MahaDBT & AICTE).
Verifies:
  - Exact formula for OBC (50% tuition waiver + full dev fee).
  - Exact formula for TFWS (100% tuition waiver, development fee only).
  - Exact formula for SC & ST (nominal registration fee ~₹2,500).
  - EWS / EBC (Rajarshi Shahu Maharaj Scheme 50% tuition waiver).
  - OPEN / General (100% standard FRA fee).
  - Integration with CollegeMetricsService and Orchestrator.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("."))

from scripts.college_metrics_service import CategoryConcessionEngine, CategoryConcessionResult, CollegeMetricsService
from scripts.agents.cutoff_agent import CutoffAgent
from scripts.agents.orchestrator import Orchestrator


class TestCategoryConcessions(unittest.TestCase):

    def setUp(self):
        self.base_fee = 143000.0  # PCCOE annual base fee

    def test_01_open_category_pays_full(self):
        """OPEN/General pays 100% of base fee with 0% waiver."""
        res = CategoryConcessionEngine.calculate_concession(self.base_fee, "GOPENS")
        self.assertEqual(res.base_annual_fee, 143000.0)
        self.assertEqual(res.effective_annual_fee, 143000.0)
        self.assertEqual(res.annual_savings, 0.0)
        self.assertEqual(res.waiver_percentage, 0.0)
        self.assertIn("Standard", res.scheme_name)

    def test_02_obc_category_50_pct_tuition_waiver(self):
        """OBC pays 50% tuition + 100% dev fee = ₹82,225/yr for ₹143,000 base fee."""
        res = CategoryConcessionEngine.calculate_concession(self.base_fee, "GOBCS")
        # Tuition = 143000 * 0.85 = 121,550; Dev = 143000 * 0.15 = 21,450
        # Effective = (121550 * 0.5) + 21450 = 60,775 + 21,450 = 82,225
        self.assertAlmostEqual(res.effective_annual_fee, 82225.0, delta=1.0)
        self.assertAlmostEqual(res.annual_savings, 60775.0, delta=1.0)
        self.assertAlmostEqual(res.total_4yr_savings, 60775.0 * 4, delta=4.0)
        self.assertEqual(res.waiver_percentage, 42.5)
        self.assertIn("OBC", res.scheme_name)

    def test_03_tfws_category_100_pct_tuition_waiver(self):
        """TFWS pays only 15% dev fee = ₹21,450/yr for ₹143,000 base fee."""
        res = CategoryConcessionEngine.calculate_concession(self.base_fee, "TFWS")
        self.assertAlmostEqual(res.effective_annual_fee, 21450.0, delta=1.0)
        self.assertAlmostEqual(res.annual_savings, 121550.0, delta=1.0)
        self.assertEqual(res.waiver_percentage, 85.0)
        self.assertIn("AICTE", res.scheme_name)

    def test_04_sc_and_st_categories_nominal_fee(self):
        """SC and ST pay nominal fee (~₹2,500/yr), saving > 98% of degree cost."""
        res_sc = CategoryConcessionEngine.calculate_concession(self.base_fee, "GSCS")
        self.assertLessEqual(res_sc.effective_annual_fee, 2500.0)
        self.assertGreater(res_sc.waiver_percentage, 95.0)
        self.assertIn("SC", res_sc.scheme_name)

        res_st = CategoryConcessionEngine.calculate_concession(self.base_fee, "GSTS")
        self.assertLessEqual(res_st.effective_annual_fee, 2500.0)
        self.assertGreater(res_st.waiver_percentage, 95.0)
        self.assertIn("ST", res_st.scheme_name)

    def test_05_ews_and_ebc_category(self):
        """EWS/EBC pays 50% tuition under Rajarshi Shahu Maharaj Scheme."""
        res = CategoryConcessionEngine.calculate_concession(self.base_fee, "EWS")
        self.assertAlmostEqual(res.effective_annual_fee, 82225.0, delta=1.0)
        self.assertIn("Rajarshi", res.scheme_name)

    def test_06_college_metrics_service_integration(self):
        """CollegeMetricsService provides get_category_concession for PCCOE (06175)."""
        cms = CollegeMetricsService.get_instance()
        concession = cms.get_category_concession("06175", category="GOBCS")
        self.assertIsInstance(concession, CategoryConcessionResult)
        self.assertAlmostEqual(concession.effective_annual_fee, 82225.0, delta=1.0)

    def test_07_orchestrator_attaches_concession_data(self):
        """Orchestrator._handle_multi_college_discovery attaches concession_data to shortlist."""
        ca = CutoffAgent("cutoffs/phase3_final_staging")
        orch = Orchestrator(cutoff_agent=ca)
        parsed = {
            "location": "Pune",
            "percentile": 93.0,
            "category": "GOBCS",
            "preferred_branches": ["Computer Engineering"],
            "requested_unique_colleges": 5,
        }
        res = orch._handle_multi_college_discovery("colleges in pune for 93 percentile OBC", parsed)
        shortlist = res.get("shortlist", [])
        self.assertGreater(len(shortlist), 0)
        for item in shortlist:
            self.assertIn("concession_data", item)
            self.assertIsNotNone(item["concession_data"])
            self.assertIn("effective_annual_fee_str", item)
            self.assertTrue("waiver" in item["effective_annual_fee_str"].lower() or "fra" in item["effective_annual_fee_str"].lower())


if __name__ == "__main__":
    unittest.main()
