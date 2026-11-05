#!/usr/bin/env python3
"""
Regression test for Cross-College Cutoff Search & Multi-College Query Routing.
Tests:
1. CutoffAgent.find_colleges() filters by percentile range.
2. CutoffAgent.find_colleges() filters by closing rank threshold.
3. Orchestrator.answer() handles question A1 (percentile range 90-95).
4. Orchestrator.answer() handles question A2 (closing rank above 50,000).
5. Orchestrator.answer() provides helpful guidance on general shortlist query.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
AGENTS = SCRIPTS / "agents"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(AGENTS))

from cutoff_agent import CutoffAgent
from orchestrator import Orchestrator


class TestCrossCollegeCutoffSearch(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        ydir = self.temp_dir / "2025-26"
        ydir.mkdir()

        # College 1: 01002 - Cutoff: 98.2 percentile / Rank 1200
        c1 = {
            "academic_year": "2025-26",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1200,
                                    "closing_percentile": 98.2,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "01002.json").write_text(json.dumps(c1), encoding="utf-8")

        # College 2: 06005 - Cutoff: 92.5 percentile / Rank 7500
        c2 = {
            "academic_year": "2025-26",
            "institute_code": "06005",
            "institute_name": "Government College of Engineering, Karad",
            "branches": [
                {
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 7500,
                                    "closing_percentile": 92.5,
                                    "evidence_id": "EV-06005-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                },
                {
                    "branch": "Civil Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 58000,
                                    "closing_percentile": 52.1,
                                    "evidence_id": "EV-06005-CIVIL-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "06005.json").write_text(json.dumps(c2), encoding="utf-8")

        self.agent = CutoffAgent(self.temp_dir)
        self.orch = Orchestrator(cutoff_agent=self.agent, college_info_agent=None)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_colleges_by_percentile_range(self):
        # Search for cutoffs between 90 and 95 percentile
        matches = self.agent.find_colleges(
            min_percentile=90.0,
            max_percentile=95.0,
            branch_query="Computer",
            category="GOPENS",
            year="2025-26",
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["institute_code"], "06005")
        self.assertEqual(matches[0]["closing_percentile"], 92.5)

    def test_find_colleges_by_rank_threshold(self):
        # Search for Civil Engineering closing rank above 50,000
        matches = self.agent.find_colleges(
            min_rank=50000,
            branch_query="Civil",
            category="GOPENS",
            round_no=1,
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["institute_code"], "06005")
        self.assertEqual(matches[0]["closing_rank"], 58000)

    def test_orchestrator_answers_a1_percentile_range(self):
        q = "List colleges where the GOPENS cutoff for Computer Engineering was between 90 and 95 percentile in 2025-26."
        res = self.orch.answer(q)
        self.assertEqual(res.get("status"), "evidence_only")
        self.assertIn("06005", res.get("evidence", ""))
        self.assertIn("92.5", res.get("evidence", ""))

    def test_orchestrator_answers_a2_closing_rank(self):
        q = "Which colleges had a Civil Engineering closing rank above 50,000 for GOPENS in round 1?"
        res = self.orch.answer(q)
        self.assertEqual(res.get("status"), "evidence_only")
        self.assertIn("06005", res.get("evidence", ""))
        self.assertIn("58000", res.get("evidence", ""))

    def test_orchestrator_shortlist_guidance(self):
        q = "Can you give me a personalized college shortlist for Computer Engineering?"
        res = self.orch.answer(q)
        self.assertEqual(res.get("status"), "needs_clarification")
        self.assertIn("MHT-CET percentile or merit rank", res.get("message", ""))


if __name__ == "__main__":
    unittest.main()
