"""
Unit and regression tests for Task 16: API, UI and PDF Output Contract.
Tests structured API discovery envelopes, distinct unique college vs branch counts,
and PDF export alignment with wrapped names.
"""
import unittest
from unittest.mock import MagicMock
from scripts.agents.orchestrator import Orchestrator
from scripts.pdf_generator import generate_college_list_pdf


class TestApiUiContract(unittest.TestCase):
    def setUp(self):
        self.orch = Orchestrator(cutoff_agent=None, college_info_agent=None)

    def test_01_discovery_response_contract_fields(self):
        """Discovery response must provide structured metadata so UI does not parse prose."""
        d_col = MagicMock()
        d_col.institute_code = "06006"
        d_col.institute_name = "COEP Technological University"
        d_col.matching_branches = [MagicMock(canonical_name="Computer Engineering", academic_year="2023-24", round_no=1)]
        d_col.total_matching_branches = 1
        d_col.best_cutoff_percentile = 99.8
        d_col.best_closing_rank = 150
        d_col.evidence_id = "EV-06006-COMP-GOPENS-R1"

        self.orch.discovery_service = MagicMock()
        self.orch.discovery_service.discover_colleges.return_value = {"colleges": [d_col]}

        parsed = {
            "intent": "college_discovery",
            "percentile": 95.0,
            "rank": 6000,
            "category": "GOPENS",
            "location": "Pune",
            "preferred_branches": ["Computer Engineering"],
            "requested_unique_colleges": 30,
        }

        resp = self.orch._handle_multi_college_discovery(
            question="30 colleges in Pune for Computer Engineering with 95 percentile",
            parsed=parsed,
        )

        # Check required Task 16 response contract fields
        self.assertIn("request_id", resp)
        self.assertIn("session_id", resp)
        self.assertIn("parsed_student_profile", resp)
        self.assertIn("geographic_scope", resp)
        self.assertIn("requested_unique_colleges", resp)
        self.assertIn("actual_unique_colleges_count", resp)
        self.assertIn("ranking_method", resp)
        self.assertIn("ordered_colleges", resp)
        self.assertIn("citations", resp)
        self.assertIn("warnings", resp)

        self.assertEqual(resp["requested_unique_colleges"], 30)
        self.assertEqual(resp["actual_unique_colleges_count"], 1)
        self.assertEqual(resp["geographic_scope"], "Pune")
        self.assertGreater(len(resp["citations"]), 0)
        self.assertGreater(len(resp["warnings"]), 0)

    def test_02_pdf_export_contract_and_wrapping(self):
        """PDF generation must accept structured discovery response colleges with long names without overflowing."""
        colleges = [
            {
                "institute_code": "06006",
                "institute_name": "College of Engineering, Pune (An Autonomous Institute of Government of Maharashtra)",
                "district": "Pune Metropolitan Region",
                "autonomy_type": "State Government Autonomous",
                "branch": "Computer Engineering and Artificial Intelligence & Data Science (Integrated Dual Degree)",
                "cutoff_percentile": 99.85,
                "closing_rank": 120,
                "popularity_score": None,
                "roi_tier": "Not computable (Missing official fee structure)",
            }
        ]
        pdf_bytes = generate_college_list_pdf("Task 16 Verified Shortlist", colleges)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 2000)


if __name__ == "__main__":
    unittest.main()
