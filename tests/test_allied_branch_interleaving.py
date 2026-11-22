"""
Unit tests for Allied Branch Interleaving (Step 3).
Verifies:
  - Discovery across multiple requested branch disciplines (Computer, IT, AI&DS).
  - Generation of interleaved options list sorted strictly by cutoff competitiveness.
  - Distinct DTE Choice Codes for each branch at the same college (e.g., 617524510 vs 617524210).
  - Orchestrator integration passing interleaved_options.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("."))

from scripts.agents.cutoff_agent import CutoffAgent
from scripts.college_discovery import StructuredCollegeDiscoveryService
from scripts.agents.orchestrator import Orchestrator


class TestAlliedBranchInterleaving(unittest.TestCase):

    def setUp(self):
        self.ca = CutoffAgent("cutoffs/phase3_final_staging")
        self.discovery = StructuredCollegeDiscoveryService(self.ca)

    def test_01_multi_branch_array_retrieves_multiple_disciplines(self):
        """Requesting Computer and IT retrieves colleges offering both branches."""
        res = self.discovery.discover_colleges(
            location="Pune",
            preferred_branches=["Computer Engineering", "Information Technology"],
            category="GOPENS",
            percentile=95.0,
            requested_unique_colleges=10
        )
        colleges = res.get("colleges", [])
        self.assertGreater(len(colleges), 0)
        # Check that top colleges have multiple matching branches
        multi_branch_cols = [c for c in colleges if len(c.matching_branches) > 1]
        self.assertGreater(len(multi_branch_cols), 0)

    def test_02_interleaved_options_generated_and_sorted(self):
        """Interleaved options are produced and sorted by cutoff descending."""
        res = self.discovery.discover_colleges(
            location="Pune",
            preferred_branches=["Computer Engineering", "Information Technology"],
            category="GOPENS",
            percentile=95.0,
            requested_unique_colleges=10
        )
        opts = res.get("interleaved_options", [])
        self.assertGreater(len(opts), 0)
        
        # Verify strict cutoff descending order
        cutoffs = [o["cutoff_percentile"] for o in opts if o["cutoff_percentile"] is not None]
        for i in range(len(cutoffs) - 1):
            self.assertGreaterEqual(cutoffs[i], cutoffs[i+1], f"Cutoffs not sorted at idx {i}: {cutoffs[i]} < {cutoffs[i+1]}")

    def test_03_distinct_choice_codes_per_branch_at_same_college(self):
        """Different branches at the same institute must receive distinct DTE choice codes."""
        res = self.discovery.discover_colleges(
            location="Pune",
            preferred_branches=["Computer Engineering", "Information Technology"],
            category="GOPENS",
            percentile=98.0,
            requested_unique_colleges=5
        )
        opts = res.get("interleaved_options", [])
        
        # Find PCCOE options (06175)
        pccoe_opts = [o for o in opts if "6175" in o["institute_code"]]
        if len(pccoe_opts) > 1:
            choice_codes = [o["choice_code"] for o in pccoe_opts]
            # Ensure choice codes are distinct
            self.assertEqual(len(choice_codes), len(set(choice_codes)), f"Duplicate choice codes found: {choice_codes}")

    def test_04_orchestrator_returns_interleaved_options(self):
        """Orchestrator discovery query exposes interleaved_options in result dict."""
        orch = Orchestrator(cutoff_agent=self.ca)
        parsed = {
            "location": "Pune",
            "percentile": 93.0,
            "category": "GOPENS",
            "preferred_branches": ["Computer Engineering", "Information Technology"],
            "requested_unique_colleges": 10,
        }
        res = orch._handle_multi_college_discovery("computer and IT colleges in pune", parsed)
        self.assertIn("interleaved_options", res)
        self.assertIsInstance(res["interleaved_options"], list)
        self.assertGreater(len(res["interleaved_options"]), 0)


if __name__ == "__main__":
    unittest.main()
