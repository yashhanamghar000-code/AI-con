"""
Unit and regression tests for Task 9: ROI Ranking with Verified Data.
Tests strict provenance, fee/placement normalization, elimination of fabricated tiers,
and transparent limitation disclosures.
"""
import unittest
from scripts.roi_service import ROIService, FeeData, PlacementData, ROIEvaluation
from scripts.agents.orchestrator import Orchestrator
from scripts.pdf_generator import generate_college_list_pdf


class TestROIRanking(unittest.TestCase):
    def setUp(self):
        self.service = ROIService()

    def test_01_missing_fee_or_placement_returns_not_computable(self):
        """When fee or placement data is absent, ROI must be not_computable with no fabricated tiers."""
        # Missing fee
        eval1 = self.service.compute_roi(None, PlacementData(amount=800000))
        self.assertFalse(eval1.is_computable)
        self.assertEqual(eval1.status, "not_computable")
        self.assertIsNone(eval1.ratio_proxy)
        self.assertIn("Missing fee data", eval1.display_summary)

        # Missing placement
        eval2 = self.service.compute_roi(FeeData(amount=100000), None)
        self.assertFalse(eval2.is_computable)
        self.assertEqual(eval2.status, "not_computable")
        self.assertIsNone(eval2.ratio_proxy)
        self.assertIn("Missing placement statistics", eval2.display_summary)

        # Both missing
        eval3 = self.service.compute_roi(None, None)
        self.assertFalse(eval3.is_computable)
        self.assertIsNone(eval3.ratio_proxy)

    def test_02_annual_vs_total_fee_normalization(self):
        """Annual fee must be multiplied across 4-year degree to prevent 1-year vs 4-year fee mismatch."""
        fee = FeeData(amount=125000, period="annual", course_duration_years=4)
        placement = PlacementData(amount=1000000, metric_type="median")

        # Total 4-year tuition = 125,000 * 4 = 500,000
        # Ratio = 1,000,000 / 500,000 = 2.0x
        res = self.service.compute_roi(fee, placement)
        self.assertTrue(res.is_computable)
        self.assertEqual(res.ratio_proxy, 2.0)
        self.assertEqual(res.ratio_display, "2.00x")
        self.assertIn("4-Year Tuition [₹500,000", res.formula_description)

    def test_03_median_vs_average_package_distinction(self):
        """Average packages must be explicitly identified and cautioned against outlier skew."""
        fee = FeeData(amount=100000, period="annual", course_duration_years=4)
        placement_avg = PlacementData(amount=800000, metric_type="average")

        res = self.service.compute_roi(fee, placement_avg)
        self.assertTrue(res.is_computable)
        self.assertIn("Average", res.metric_label)
        has_skew_warning = any("Average CTC" in lim and "outlier" in lim for lim in res.limitations)
        self.assertTrue(has_skew_warning)

    def test_04_branch_vs_institute_level_scope(self):
        """Placement scope (branch-specific vs institute-level) must be preserved in provenance."""
        fee = FeeData(amount=100000, period="annual")
        placement_inst = PlacementData(amount=600000, scope="institute_level")
        placement_br = PlacementData(amount=900000, scope="branch_level", branch_name="Computer Engineering")

        res_inst = self.service.compute_roi(fee, placement_inst)
        self.assertIn("institute-level", " ".join(res_inst.limitations))

        res_br = self.service.compute_roi(fee, placement_br)
        self.assertIn("branch-specific", " ".join(res_br.limitations))

    def test_05_non_positive_outliers_rejected(self):
        """Non-positive or zero amounts must be rejected as not_computable outliers."""
        fee_zero = FeeData(amount=0)
        placement = PlacementData(amount=600000)
        res = self.service.compute_roi(fee_zero, placement)
        self.assertFalse(res.is_computable)
        self.assertIn("Outlier", res.metric_label)

    def test_06_verified_provenance_and_limitations(self):
        """Every computable ROI evaluation must record source citations and proxy limitations."""
        fee = FeeData(amount=150000, source_citation="FRA Maharashtra 2024-25")
        placement = PlacementData(amount=900000, source_citation="NIRF 2024 Engineering")

        res = self.service.compute_roi(fee, placement)
        self.assertTrue(res.is_computable)
        self.assertIn("Proxy Metric", res.limitations[0])
        self.assertIn("Living Costs", res.limitations[2])
        d = res.to_dict()
        self.assertEqual(d["fee_source"], "FRA Maharashtra 2024-25")
        self.assertEqual(d["placement_source"], "NIRF 2024 Engineering")

    def test_07_orchestrator_eliminates_fabricated_roi_tiers(self):
        """Orchestrator must never fabricate 'Exceptional (Tier 1 Govt)' or 'Moderate (Tier 2)'."""
        from unittest.mock import MagicMock
        orch = Orchestrator(cutoff_agent=None, college_info_agent=None)

        d_col = MagicMock()
        d_col.institute_code = "06006"
        d_col.institute_name = "COEP Technological University"
        d_col.matching_branches = [MagicMock(canonical_name="Computer Engineering", academic_year="2023-24", round_no=1)]
        d_col.total_matching_branches = 1
        d_col.best_cutoff_percentile = 99.8
        d_col.best_closing_rank = 150
        d_col.evidence_id = "EV-06006-COMP-GOPENS-R1"

        orch.discovery_service = MagicMock()
        orch.discovery_service.discover_colleges.return_value = {"colleges": [d_col]}

        parsed = {
            "intent": "college_discovery",
            "percentile": 95.0,
            "rank": 6000,
            "category": "GOPENS",
            "normalized_seat_code": "GOPENS",
            "location": "Pune",
            "preferred_branches": ["Computer Engineering"],
            "requested_unique_colleges": 5,
        }

        resp = orch._handle_multi_college_discovery(
            question="best colleges in Pune for Computer Engineering with 95 percentile",
            parsed=parsed
        )
        college_list = resp.get("shortlist", [])
        self.assertGreater(len(college_list), 0)

        for c in college_list:
            roi_str = c.get("roi_tier", "")
            self.assertNotIn("Exceptional (Tier 1 Govt)", roi_str)
            self.assertNotIn("High (Tier 1 Private)", roi_str)
            self.assertNotIn("Moderate (Tier 2)", roi_str)
            self.assertIn("Not computable", roi_str)

    def test_08_orchestrator_roi_ranking_query_handling(self):
        """When user queries for ROI ranking on shortlist, system transparently explains absence of fee/placement data."""
        orch = Orchestrator(cutoff_agent=None, college_info_agent=None)
        orch._conv_context = {
            "last_shortlist": [
                {
                    "institute_code": "06006",
                    "institute_name": "COEP Technological University",
                    "cutoff_percentile": 99.8,
                    "closing_rank": 120,
                    "autonomy_type": "Government Autonomous",
                    "roi_tier": "Not computable (Missing fee data)",
                    "predicted_cutoff": 99.85,
                }
            ]
        }
        resp = orch._handle_shortlist_roi_ranking(
            question="rank these colleges by ROI",
            parsed={"intent": "reputation_roi_ranking"}
        )

        self.assertIn("Verified ROI Data Unavailable", resp["message"])
        self.assertIn("Per anti-hallucination rules, arbitrary ROI tiers", resp["message"])
        self.assertIn("Shortlist Re-ranked by ROI", resp["matched_college"])

    def test_09_pdf_generator_no_hardcoded_high_roi(self):
        """PDF generation must not default to 'ROI: High'."""
        colleges = [
            {
                "institute_code": "06006",
                "institute_name": "COEP Technological University",
                "city": "Pune",
                "roi_tier": None,  # Unspecified
                "popularity_score": None,
                "top_cutoff": {"closing_percentile": 99.8, "branch": "Computer Engineering"}
            }
        ]
        pdf_bytes = generate_college_list_pdf("Test Shortlist", colleges)
        self.assertGreater(len(pdf_bytes), 1000)

    def test_10_rank_by_roi_partitioning(self):
        """rank_by_roi partitions colleges into computable (sorted) and uncomputable cleanly."""
        colleges = [
            {
                "institute_code": "C1",
                "fee_data": {"amount": 100000, "period": "annual"},
                "placement_data": {"amount": 600000, "metric_type": "median"}
            },
            {
                "institute_code": "C2",
                "fee_data": {"amount": 100000, "period": "annual"},
                "placement_data": {"amount": 1000000, "metric_type": "median"}
            },
            {
                "institute_code": "C3",
                # Missing fee and placement
            }
        ]
        res = self.service.rank_by_roi(colleges)
        self.assertEqual(res["computable_count"], 2)
        self.assertEqual(res["not_computable_count"], 1)
        # C2 ratio = 10L / 4L = 2.5, C1 ratio = 6L / 4L = 1.5 -> C2 should be first
        self.assertEqual(res["ranked_colleges"][0]["institute_code"], "C2")
        self.assertEqual(res["ranked_colleges"][1]["institute_code"], "C1")
        self.assertEqual(res["unranked_colleges"][0]["institute_code"], "C3")


if __name__ == "__main__":
    unittest.main()
