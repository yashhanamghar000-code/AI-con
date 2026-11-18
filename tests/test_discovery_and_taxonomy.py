"""
Unit tests for Structured College Discovery & Branch Taxonomy (Tasks 4 & 5).
Verifies:
1. Canonical branch resolution and repair of truncated strings.
2. Separation of Electronics & Computer Engineering from pure Computer Engineering.
3. Master dataset structured enumeration across locations (Pune district, Alandi, Wagholi).
4. Request for 30 colleges returns up to 30 unique institutes (no duplicate colleges across branches).
5. Accurate shortfall reporting when matching colleges < requested count.
6. Diagnostic reporting for total colleges and valid codes.
"""
import unittest
from pathlib import Path
from scripts.branch_taxonomy import BranchTaxonomyService
from scripts.college_discovery import StructuredCollegeDiscoveryService
from scripts.agents.cutoff_agent import CutoffAgent

CUTOFFS_DIR = Path(__file__).resolve().parent.parent / "cutoffs" / "phase3_final_staging"


class TestDiscoveryAndTaxonomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.branch_service = BranchTaxonomyService()
        cls.cutoff_agent = CutoffAgent(str(CUTOFFS_DIR))
        cls.disco = StructuredCollegeDiscoveryService(cls.cutoff_agent)

    def test_01_canonical_branch_truncation_repair(self):
        """Truncated branch strings from CET Cell PDFs are accurately repaired."""
        raw = "Computer Science and Engineering(Artificial"
        res = self.branch_service.resolve_branch(raw)
        self.assertEqual(
            res.canonical_name,
            "Computer Science and Engineering(Artificial Intelligence and Machine Learning)",
        )
        self.assertTrue(res.is_truncated_repaired)
        self.assertEqual(res.canonical_group, "AI, Data Science & Machine Learning")

    def test_02_electronics_and_computer_separation(self):
        """Electronics and Computer Engineering must NOT be conflated with Computer Engineering."""
        raw = "Electronics and Computer Engineering"
        res = self.branch_service.resolve_branch(raw)
        self.assertEqual(res.canonical_name, "Electronics and Computer Engineering")
        self.assertNotEqual(res.canonical_group, "Computer & IT Engineering")
        self.assertEqual(res.canonical_group, "Specialized / Multidisciplinary")

    def test_03_discovery_diagnostics(self):
        """Discovery diagnostic reports total master colleges, valid codes, and location count."""
        diag = self.disco.get_discovery_diagnostics("Pune")
        self.assertEqual(diag["total_master_colleges"], 389)
        self.assertEqual(diag["total_valid_codes"], 389)
        self.assertGreaterEqual(diag["total_location_colleges"], 50)

    def test_04_30_unique_institutes_returned(self):
        """Request for 30 colleges returns 30 unique institutes without duplicate rows."""
        res = self.disco.discover_colleges(
            location="Pune",
            preferred_branches=["Computer Engineering", "Information Technology"],
            percentile=94.0,
            requested_unique_colleges=30,
        )
        self.assertEqual(res["returned_count"], 30)
        codes = [c.institute_code for c in res["colleges"]]
        self.assertEqual(len(codes), len(set(codes)), "Duplicate institute codes found in shortlist!")

    def test_05_location_scope_alandi_and_wagholi(self):
        """Colleges in Alandi and Wagholi must match the Pune geographic scope."""
        # MIT AOE Alandi is 06146
        self.assertTrue(self.disco.is_in_location_scope("06146", "MIT Academy of Engineering,Alandi, Pune", "Pune"))
        # Raisoni Wagholi is 06155
        self.assertTrue(self.disco.is_in_location_scope("06155", "G.H.Raisoni College of Engineering & Management, Wagholi, Pune", "Pune"))

    def test_06_shortfall_explanation(self):
        """When requested limit exceeds available unique institutes, accurate shortfall explanation is returned."""
        res = self.disco.discover_colleges(
            location="Pune",
            preferred_branches=["Computer Engineering"],
            percentile=99.9, # Very high percentile where fewer match
            requested_unique_colleges=50,
        )
        if res["returned_count"] < 50:
            self.assertIsNotNone(res["shortfall_explanation"])
            self.assertIn("only", res["shortfall_explanation"])


if __name__ == "__main__":
    unittest.main()

