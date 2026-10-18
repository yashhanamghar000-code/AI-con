#!/usr/bin/env python3
"""Unit tests for Orchestrator and Pipeline Routing (Phase 1)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "agents"))

from cutoff_agent import CutoffAgent
from orchestrator import CUTOFF_UNAVAILABLE, Orchestrator
from rag_pipeline import answer_question, build_pipeline


class MockCollegeInfoAgent:
    def __init__(self):
        self._index = {
            "Government College of Engineering, Amravati": {
                "institute_code": "01002",
                "record_id": "MHHEI_00001",
            },
            "KDM College of Arts": {
                "record_id": "MHHEI_00552",
            },
            "Government College of Engineering, Karad": {
                "institute_code": "06005",
                "record_id": "MHHEI_00050",
            },
        }

    def list_name_index(self):
        return self._index

    def search(self, query, institute_code=None, record_id=None, n_results=5):
        if record_id == "MHHEI_00001" or institute_code == "01002":
            return [
                {
                    "chunk_id": "MHHEI_00001_profile",
                    "text": "College: Government College of Engineering, Amravati\naffiliation: Sant Gadge Baba Amravati University\nstate: Maharashtra",
                    "metadata": {
                        "record_id": "MHHEI_00001",
                        "institute_code": "01002",
                        "source_page": "https://www.gcoea.ac.in/",
                        "chunk_type": "profile",
                    },
                    "distance": 0.1,
                }
            ]
        elif record_id == "MHHEI_00552":
            return [
                {
                    "chunk_id": "MHHEI_00552_profile",
                    "text": "College: KDM College of Arts\nstate: Maharashtra",
                    "metadata": {
                        "record_id": "MHHEI_00552",
                        "source_page": "college profile",
                        "chunk_type": "profile",
                    },
                    "distance": 0.1,
                }
            ]
        return []

    def as_evidence_text(self, results):
        if not results:
            return "No relevant information found in the college dataset."
        return "\n".join(f"[{r['metadata'].get('record_id')}:{r['chunk_id']}] {r['text']}" for r in results)


class TestOrchestratorPipeline(unittest.TestCase):
    def setUp(self):
        self.mock_info = MockCollegeInfoAgent()
        self.orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info)

    def test_info_query_returns_evidence_only(self):
        res = self.orch.answer("What is the affiliation of Government College of Engineering, Amravati?")
        self.assertEqual(res["status"], "evidence_only")
        self.assertEqual(res["intent"], "info")
        self.assertEqual(res["institute_code"], "01002")
        self.assertEqual(res["record_id"], "MHHEI_00001")
        self.assertIn("Sant Gadge Baba Amravati University", res["evidence"])

    def test_info_query_without_institute_code_resolves_record_id(self):
        res = self.orch.answer("Tell me about KDM College of Arts")
        self.assertEqual(res["status"], "evidence_only")
        self.assertEqual(res["intent"], "info")
        self.assertIsNone(res["institute_code"])
        self.assertEqual(res["record_id"], "MHHEI_00552")
        self.assertIn("KDM College of Arts", res["evidence"])

    def test_cutoff_query_without_cutoff_agent_returns_unavailable(self):
        res = self.orch.answer(
            "What was the GOPENS cutoff for Computer Engineering at Government College of Engineering, Amravati?"
        )
        self.assertEqual(res["status"], "unavailable")
        self.assertEqual(res["intent"], "cutoff")
        self.assertEqual(res["message"], CUTOFF_UNAVAILABLE)
        # Verify no rank numbers or percentages hallucinated
        self.assertNotIn("closing rank", res["message"])
        self.assertNotIn("percentile", res["message"])

    def test_ambiguous_college_query_requests_clarification(self):
        # "Government College of Engineering" matches both Amravati and Karad in mock_info
        res = self.orch.answer("What is the affiliation of Government College of Engineering?")
        self.assertEqual(res["status"], "needs_clarification")
        self.assertIn("candidates", res)
        self.assertTrue(len(res["candidates"]) >= 2)

    def test_unknown_college_requests_clarification(self):
        res = self.orch.answer("What is the cutoff for Harvard University?")
        self.assertEqual(res["status"], "needs_clarification")

    def test_valid_cutoff_fixture_integration(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            year_dir = tmp / "2025-26"
            year_dir.mkdir()
            college_cutoff = {
                "institute_code": "01002",
                "institute_name": "Government College of Engineering, Amravati",
                "academic_year": "2025-26",
                "branches": [
                    {
                        "branch": "Computer Engineering",
                        "categories": [
                            {
                                "category": "GOPENS",
                                "category_meaning": "General Open State-level",
                                "cutoffs": [
                                    {
                                        "round": 1,
                                        "stage": "1",
                                        "list_type": "CAP",
                                        "closing_rank": 1560,
                                        "closing_percentile": 98.42,
                                        "evidence_id": "EV-01002-COMP-GOPENS-R1",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
            (year_dir / "01002.json").write_text(json.dumps(college_cutoff), encoding="utf-8")

            cutoff_agent = CutoffAgent(tmp)
            orch_with_cutoffs = Orchestrator(cutoff_agent=cutoff_agent, college_info_agent=self.mock_info)

            res = orch_with_cutoffs.answer(
                "What was the GOPENS cutoff for Computer Engineering at Government College of Engineering, Amravati?"
            )
            self.assertEqual(res["status"], "evidence_only")
            self.assertEqual(res["intent"], "cutoff")
            self.assertIn("closing rank 1560", res["evidence"])
            self.assertIn("percentile 98.42", res["evidence"])
            self.assertIn("EV-01002-COMP-GOPENS-R1", res["evidence"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
