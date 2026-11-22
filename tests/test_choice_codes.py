"""
Tests for Official Maharashtra DTE 9-Digit Choice Code Generation and Propagation (Step 1).
Verifies:
  - Format canonicalization (9 digits, exactly structured as [Inst][Course][Shift]).
  - TFWS category suffix handling ('T' appended).
  - Normalization from raw dataset course codes (stripping leading zeros from 10-digit strings).
  - Integration with StructuredCollegeDiscoveryService and Orchestrator.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("."))

from scripts.branch_taxonomy import format_dte_choice_code, CANONICAL_DTE_COURSE_CODES
from scripts.agents.cutoff_agent import CutoffAgent
from scripts.college_discovery import StructuredCollegeDiscoveryService
from scripts.agents.orchestrator import Orchestrator


class TestDTEChoiceCodes(unittest.TestCase):

    def test_01_canonical_9_digit_from_10_digit_raw(self):
        """10-digit code with leading zero e.g. '0617524510' is normalized to '617524510'."""
        res = format_dte_choice_code(raw_course_code="0617524510", institute_code="06175", branch_name="Computer Engineering")
        self.assertEqual(res, "617524510")
        self.assertEqual(len(res), 9)

    def test_02_direct_9_digit_preserved(self):
        """Direct 9-digit code e.g. '627324510' is preserved as 9-digit code."""
        res = format_dte_choice_code(raw_course_code="627324510", institute_code="06273", branch_name="Computer Engineering")
        self.assertEqual(res, "627324510")
        self.assertEqual(len(res), 9)

    def test_03_tfws_category_appends_t(self):
        """TFWS category appends uppercase 'T' to the 9-digit choice code."""
        res = format_dte_choice_code(raw_course_code="617524510", institute_code="06175", branch_name="Computer Engineering", category="TFWS")
        self.assertEqual(res, "617524510T")
        self.assertTrue(res.endswith("T"))
        self.assertEqual(len(res), 10)

    def test_04_synthesizes_when_raw_code_missing(self):
        """When raw_course_code is absent, deterministically constructs 9-digit code."""
        res_ce = format_dte_choice_code(raw_course_code=None, institute_code="06004", branch_name="Civil Engineering")
        self.assertEqual(res_ce, "600419110")

        res_mech = format_dte_choice_code(raw_course_code=None, institute_code="6274", branch_name="Mechanical Engineering")
        self.assertEqual(res_mech, "627461210")

        res_it = format_dte_choice_code(raw_course_code=None, institute_code="6175", branch_name="Information Technology")
        self.assertEqual(res_it, "617524210")

    def test_05_discovery_service_populates_choice_code(self):
        """StructuredCollegeDiscoveryService assigns choice_code to discovered colleges."""
        ca = CutoffAgent("cutoffs/phase3_final_staging")
        discovery = StructuredCollegeDiscoveryService(ca)
        res = discovery.discover_colleges(
            location="Pune",
            preferred_branches=["Computer Engineering"],
            category="GOPENS",
            percentile=95.0,
            requested_unique_colleges=5
        )
        colleges = res.get("colleges", [])
        self.assertGreater(len(colleges), 0)
        for c in colleges:
            self.assertIsNotNone(c.choice_code, f"College {c.institute_name} ({c.institute_code}) has None choice_code")
            self.assertTrue(len(c.choice_code) in (9, 10), f"Invalid choice_code length: {c.choice_code}")
            # Ensure institute code forms the prefix
            inst_suffix = c.institute_code.lstrip("0")
            self.assertTrue(c.choice_code.startswith(inst_suffix), f"{c.choice_code} does not start with {inst_suffix}")

    def test_06_orchestrator_shortlist_contains_choice_codes(self):
        """Orchestrator._handle_multi_college_discovery contains choice_code in shortlist records."""
        ca = CutoffAgent("cutoffs/phase3_final_staging")
        orch = Orchestrator(cutoff_agent=ca)
        parsed = {
            "location": "Pune",
            "percentile": 93.0,
            "category": "GOPENS",
            "preferred_branches": ["Computer Engineering"],
            "requested_unique_colleges": 10,
        }
        res = orch._handle_multi_college_discovery("colleges in pune for 93 percentile", parsed)
        shortlist = res.get("shortlist", [])
        self.assertGreater(len(shortlist), 0)
        for item in shortlist[:5]:
            self.assertIn("choice_code", item)
            self.assertIsNotNone(item["choice_code"])
            self.assertTrue(len(item["choice_code"]) in (9, 10))


if __name__ == "__main__":
    unittest.main()
