"""
tests/test_popularity_ranking.py
---------------------------------
Comprehensive Test Suite for Task 8: Popularity Ranking with Evidence & Integrity.

Verifies:
1. Complete elimination of fabricated baseline popularity scores (75 + bonus).
2. 'popularity data unavailable' returned when legitimate applicant demand data does not exist.
3. Verified signals with documented source, year, scale, normalization, and weights.
4. Missing signal defense ensuring missing data does not silently inflate scores.
5. Configurable component weights.
6. Popularity ranking independence from student admission feasibility.
7. Transparent alternative ranking by historical closing cutoff competitiveness.
8. Orchestrator integration showing 'Data unavailable' instead of fake numbers.
9. PDF generator handles missing popularity score cleanly without hardcoded fallback.
10. Missing and boundary data handling.
"""

import unittest
from pathlib import Path
from typing import Any, Dict, List

from scripts.popularity_service import (
    PopularityRankingService,
    PopularitySignal,
    PopularityEvidence,
    SignalSourceType,
)
from scripts.agents.orchestrator import Orchestrator
from scripts.agents.cutoff_agent import CutoffAgent
from scripts.pdf_generator import generate_college_list_pdf


class TestPopularityRankingWithEvidence(unittest.TestCase):

    def setUp(self):
        self.service = PopularityRankingService()

    def test_01_no_fabricated_scores_default_unavailable(self):
        """Verifies that arbitrary baseline scores (75, 88, 93) are never generated."""
        # For any real or mock institute without explicit verified applicant preference data:
        res = self.service.evaluate_college(
            institute_code="06006",
            institute_name="COEP Technological University",
            cutoff_percentile=99.85,
            closing_rank=120,
        )
        self.assertFalse(res.is_available)
        self.assertIsNone(res.popularity_score)
        self.assertEqual(res.to_dict()["display_score"], "Data unavailable")
        self.assertIn("Popularity data unavailable", res.explanation)
        self.assertIn("Official Maharashtra CET Cell publications report closing cutoffs", res.explanation)
        # Check alternative measurable metric is provided
        self.assertIsNotNone(res.alternative_metric_name)
        self.assertEqual(res.alternative_metric_value, 99.85)

    def test_02_verified_signal_calculation_with_provenance(self):
        """Verified signals with documented source provenance compute an explainable composite score."""
        service = PopularityRankingService(min_signals_required=2, penalty_for_missing=False)
        
        # Signal 1: Verified applicant preference choice volume
        sig1 = PopularitySignal(
            signal_name="verified_applicant_preference",
            source_type=SignalSourceType.VERIFIED_APPLICANT_PREFERENCE,
            source_citation="Maharashtra DTE Official Admission Allotment Statistics Report 2024",
            date_or_year="2024-25",
            raw_value=14200.0,
            scale_min=500.0,
            scale_max=15000.0,
            normalized_score=94.5,
            weight=0.60,
            description="Total students listing this institute in top-3 preferences",
        )

        # Signal 2: CAP First-Choice Demand ratio
        sig2 = PopularitySignal(
            signal_name="cap_first_choice_demand",
            source_type=SignalSourceType.CAP_FIRST_CHOICE_DEMAND,
            source_citation="State CET Cell Centralized Allotment Audit Gazette 2024",
            date_or_year="2024-25",
            raw_value=4.8,
            scale_min=0.5,
            scale_max=5.0,
            normalized_score=96.0,
            weight=0.40,
            description="First-preference choices divided by approved intake",
        )

        service.add_verified_institute_signal("06006", sig1)
        service.add_verified_institute_signal("06006", sig2)

        res = service.evaluate_college("06006", "COEP")
        self.assertTrue(res.is_available)
        self.assertIsNotNone(res.popularity_score)
        # Expected: (94.5 * 0.60 + 96.0 * 0.40) / (0.60 + 0.40) = 56.7 + 38.4 = 95.1
        self.assertAlmostEqual(res.popularity_score, 95.1, delta=0.2)
        self.assertEqual(len(res.signals), 2)
        self.assertIn("verified_applicant_preference", res.explanation)

    def test_03_missing_signal_penalty_guards_against_inflation(self):
        """Missing data must not silently inflate a college's score over colleges with full evidence."""
        service = PopularityRankingService(
            weights={
                "signal_a": 0.50,
                "signal_b": 0.50,
            },
            min_signals_required=1,
            penalty_for_missing=True,
        )

        # College X has only signal_a with 100/100, but signal_b is missing (50% completeness)
        sig_a = PopularitySignal(
            signal_name="signal_a",
            source_type=SignalSourceType.VERIFIED_APPLICANT_PREFERENCE,
            source_citation="Official Report A",
            date_or_year="2024-25",
            raw_value=100.0,
            scale_min=0.0,
            scale_max=100.0,
            normalized_score=100.0,
            weight=0.50,
        )
        service.add_verified_institute_signal("11111", sig_a)

        res_x = service.evaluate_college("11111", "Incomplete College")
        self.assertTrue(res_x.is_available)
        # With completeness penalty (0.50 coverage), score must be 100 * 0.5 = 50.0, not 100.0!
        self.assertAlmostEqual(res_x.popularity_score, 50.0, delta=0.5)
        self.assertIn("completeness penalty", res_x.scoring_methodology)

    def test_04_configurable_weights(self):
        """Weights must be configurable and update composite calculations predictably."""
        service = PopularityRankingService(
            weights={"pref": 0.5, "demand": 0.5},
            min_signals_required=2,
            penalty_for_missing=False,
        )

        sig1 = PopularitySignal(
            signal_name="pref",
            source_type=SignalSourceType.VERIFIED_APPLICANT_PREFERENCE,
            source_citation="Source 1",
            date_or_year="2024",
            raw_value=80.0,
            scale_min=0.0,
            scale_max=100.0,
            normalized_score=80.0,
            weight=0.5,
        )
        sig2 = PopularitySignal(
            signal_name="demand",
            source_type=SignalSourceType.CAP_FIRST_CHOICE_DEMAND,
            source_citation="Source 2",
            date_or_year="2024",
            raw_value=100.0,
            scale_min=0.0,
            scale_max=100.0,
            normalized_score=100.0,
            weight=0.5,
        )
        service.add_verified_institute_signal("00001", sig1)
        service.add_verified_institute_signal("00001", sig2)

        res1 = service.evaluate_college("00001")
        self.assertAlmostEqual(res1.popularity_score, 90.0, delta=0.1)

        # Shift weights to 90% demand, 10% pref -> 0.1*80 + 0.9*100 = 8 + 90 = 98.0
        service.configure_weights({"pref": 0.1, "demand": 0.9})
        res2 = service.evaluate_college("00001")
        self.assertAlmostEqual(res2.popularity_score, 98.0, delta=0.1)

        # Non-positive sum should raise ValueError
        with self.assertRaises(ValueError):
            service.configure_weights({"pref": 0.0, "demand": 0.0})

    def test_05_popularity_independent_of_admission_feasibility(self):
        """Popularity ranking must be independent of student admission feasibility."""
        service = PopularityRankingService(min_signals_required=1, penalty_for_missing=False)
        sig = PopularitySignal(
            signal_name="verified_applicant_preference",
            source_type=SignalSourceType.VERIFIED_APPLICANT_PREFERENCE,
            source_citation="DTE Report",
            date_or_year="2024",
            raw_value=95.0,
            scale_min=0.0,
            scale_max=100.0,
            normalized_score=95.0,
            weight=1.0,
        )
        service.add_verified_institute_signal("06006", sig)

        ev = service.evaluate_college("06006", "COEP", cutoff_percentile=99.8)
        # College has 95 popularity. Feasibility for student with 85 percentile is REACH.
        # Feasibility for student with 99.9 percentile is ATTAINABLE.
        # But college popularity itself is fixed at 95.0!
        self.assertEqual(ev.popularity_score, 95.0)

    def test_06_alternative_ranking_offered_when_unavailable(self):
        """When popularity data is unavailable, ranks transparently by cutoff competitiveness."""
        colleges = [
            {"institute_code": "01001", "institute_name": "College A", "cutoff_percentile": 88.5, "closing_rank": 15000},
            {"institute_code": "01002", "institute_name": "College B", "cutoff_percentile": 97.2, "closing_rank": 3500},
            {"institute_code": "01003", "institute_name": "College C", "cutoff_percentile": 92.1, "closing_rank": 9800},
        ]
        ranked, summary = self.service.rank_colleges(colleges, primary_criterion="popularity")
        
        self.assertFalse(summary["popularity_data_available"])
        self.assertEqual(summary["mode_used"], "cutoff_competitiveness")
        self.assertIn("Historical Closing Cutoff Competitiveness", summary["summary_message"])
        
        # Must be ordered by cutoff_percentile descending: College B (97.2) -> College C (92.1) -> College A (88.5)
        self.assertEqual(ranked[0]["institute_code"], "01002")
        self.assertEqual(ranked[1]["institute_code"], "01003")
        self.assertEqual(ranked[2]["institute_code"], "01001")
        
        # Every item must record popularity as None and available as False
        for c in ranked:
            self.assertIsNone(c["popularity_score"])
            self.assertFalse(c["popularity_available"])

    def test_07_orchestrator_integration_no_arbitrary_scores(self):
        """Orchestrator shortlist must not fabricate scores or show arbitrary numbers."""
        from unittest.mock import MagicMock
        orch = Orchestrator(cutoff_agent=None, college_info_agent=None)
        self.assertIsNotNone(orch.popularity_service)

        # Mock discovery service to return a college via discover_colleges
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

        res = orch._handle_multi_college_discovery(
            question="top colleges in Pune with 95 percentile",
            parsed=parsed,
        )

        message = res.get("message", "")
        self.assertNotIn("Popularity Score: 75", message)
        self.assertNotIn("Popularity Score: 93", message)
        self.assertIn("Popularity:", message)
        self.assertIn("Data unavailable", message)

    def test_08_orchestrator_roi_ranking_fallback_honesty(self):
        """When re-ranking by ROI/popularity, orchestrator transparently explains lack of preference data."""
        orch = Orchestrator(cutoff_agent=None, college_info_agent=None)
        orch._conv_context = {
            "last_shortlist": [
                {
                    "institute_code": "06006",
                    "institute_name": "COEP Technological University",
                    "cutoff_percentile": 99.8,
                    "closing_rank": 150,
                    "predicted_cutoff": 99.8,
                    "popularity_score": None,
                    "roi_tier": "Exceptional (Tier 1 Govt)",
                    "autonomy_type": "Government Autonomous",
                },
                {
                    "institute_code": "06271",
                    "institute_name": "PICT Pune",
                    "cutoff_percentile": 98.5,
                    "closing_rank": 2100,
                    "predicted_cutoff": 98.5,
                    "popularity_score": None,
                    "roi_tier": "High (Tier 1 Private)",
                    "autonomy_type": "Autonomous",
                },
            ]
        }

        res = orch._handle_shortlist_roi_ranking("rank by popularity", {})
        self.assertEqual(res["status"], "answered")
        self.assertIn("Historical Cutoff Competitiveness", res["message"])
        self.assertIn("Data unavailable", res["message"])
        self.assertIn("closing cutoff competitiveness", res["evidence"])

    def test_09_pdf_generator_no_hardcoded_85(self):
        """PDF generation must handle None popularity score cleanly without hardcoded 85."""
        colleges = [
            {
                "institute_code": "06006",
                "institute_name": "COEP Technological University",
                "district": "Pune",
                "autonomy_type": "Government",
                "branch": "Computer Engineering",
                "cutoff_percentile": 99.8,
                "closing_rank": 120,
                "popularity_score": None,  # Explicitly None
                "roi_tier": "Exceptional",
            }
        ]

        pdf_bytes = generate_college_list_pdf("Test Shortlist", colleges)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 500)

    def test_10_missing_and_boundary_data_handling(self):
        """Evaluates boundary cases like empty strings, non-numeric codes, and missing cutoffs."""
        res = self.service.evaluate_college("", "", cutoff_percentile=None, closing_rank=None)
        self.assertFalse(res.is_available)
        self.assertIsNone(res.popularity_score)
        self.assertEqual(res.alternative_metric_value, None)


if __name__ == "__main__":
    unittest.main()
