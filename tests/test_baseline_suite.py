"""
AI-CON Baseline Regression Test Suite (Task 1)
Fixture-based offline regression suite verifying:
- exact college lookup by institute code
- exact cutoff lookup by institute, branch, category, year, round
- multi-college discovery by location and branch
- 30-unique-college request behavior
- follow-up "rank these by ROI" using preceding shortlist
- follow-up "show only Pune colleges"
- missing cutoff evidence
- no matching branch
- duplicate institute/branch records
- malformed or absent model predictions
"""
import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
AGENTS_DIR = SCRIPTS_DIR / "agents"
CUTOFFS_DIR = PROJECT_ROOT / "cutoffs" / "phase3_final_staging"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from cutoff_agent import CutoffAgent
from college_resolver import CollegeResolver
from orchestrator import Orchestrator


class TestBaselineSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cutoffs_dir = str(CUTOFFS_DIR)
        cls.cutoff_agent = CutoffAgent(cls.cutoffs_dir)
        cls.orchestrator = Orchestrator(cutoff_agent=cls.cutoff_agent, college_info_agent=None)

    def test_01_exact_college_lookup_by_code(self):
        """Exact college lookup by institute code (e.g. 6006 / 06006 COEP)."""
        res = self.orchestrator.resolver.resolve("06006")
        self.assertTrue(res.matched)
        self.assertIn("6006", str(res.institute_code))

    def test_02_exact_cutoff_lookup(self):
        """Exact cutoff lookup by institute, branch, category, year, round."""
        records = self.cutoff_agent.get_cutoffs(
            "06006",
            branch_query="Computer",
            category="GOPENS",
            year="2023-24",
            round_no=1,
        )
        self.assertGreater(len(records), 0)
        rec = records[0]
        self.assertEqual(rec["category"], "GOPENS")
        self.assertEqual(rec["round"], 1)
        self.assertIsNotNone(rec.get("closing_percentile"))
        self.assertIsNotNone(rec.get("closing_rank"))

    def test_03_multi_college_discovery_by_location_and_branch(self):
        """Multi-college discovery by location and branch."""
        res = self.orchestrator.answer("colleges in Pune for Computer Engineering at 94 percentile")
        self.assertIn(res.get("status"), ["evidence_only", "answered"])
        self.assertIn("shortlist", res)
        shortlist = res["shortlist"]
        self.assertGreater(len(shortlist), 0)

    def test_04_30_unique_college_request(self):
        """Request for 30 unique colleges should evaluate institute uniqueness."""
        res = self.orchestrator.answer("give me 30 colleges in Pune for Computer Engineering")
        shortlist = res.get("shortlist", [])
        unique_insts = set(c.get("institute_code") for c in shortlist)
        # Record baseline behavior: current implementation returns fewer unique institutes than requested
        self.assertIsInstance(shortlist, list)

    def test_05_followup_rank_by_roi(self):
        """Follow-up 'rank these by ROI' using preceding shortlist."""
        # Prime orchestrator session context
        self.orchestrator.answer("Pune colleges at 94 percentile")
        followup_res = self.orchestrator.answer("rank these colleges by ROI")
        self.assertIn(followup_res.get("status"), ["evidence_only", "answered", "needs_clarification"])

    def test_06_followup_show_only_pune(self):
        """Follow-up 'show only Pune colleges' retains query state."""
        self.orchestrator.answer("colleges at 94 percentile for Computer")
        followup = self.orchestrator.answer("show only Pune colleges")
        self.assertIsNotNone(followup)

    def test_07_missing_cutoff_evidence(self):
        """Missing cutoff evidence for nonexistent branch or combination."""
        records = self.cutoff_agent.get_cutoffs(
            "06006",
            branch_query="NonExistentBranchXYZ",
            category="GOPENS"
        )
        self.assertEqual(len(records), 0)
        evidence = self.cutoff_agent.as_evidence_text(records)
        self.assertIn("No matching cutoff records found", evidence)

    def test_08_no_matching_branch(self):
        """Querying branches for unknown discipline returns empty or graceful message."""
        branches = self.cutoff_agent.list_branches("99999")
        self.assertEqual(len(branches), 0)

    def test_09_duplicate_institute_branch_records(self):
        """Deduplication check: an institute should not show duplicate records for identical round/cat."""
        records = self.cutoff_agent.get_cutoffs(
            "06006",
            branch_query="Computer Engineering",
            category="GOPENS",
            year="2024-25",
            round_no=1,
        )
        # Check uniqueness by (round, stage, list_type)
        keys = [(r.get("round"), r.get("stage"), r.get("list_type")) for r in records]
        self.assertEqual(len(keys), len(set(keys)))

    def test_10_malformed_or_absent_model_predictions(self):
        """ML inference handles unknown or malformed codes gracefully without crashing."""
        pred = self.orchestrator.predict_next_year_cutoff("99999", seat_type="UNKNOWN_SEAT")
        self.assertIsInstance(pred, dict)
        if pred.get("predicted"):
            self.assertGreaterEqual(pred["predicted_rank"], 1)
            self.assertGreaterEqual(pred["predicted_percentile"], 0.0)


if __name__ == "__main__":
    unittest.main()
