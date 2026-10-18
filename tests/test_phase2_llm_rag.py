#!/usr/bin/env python3
"""Unit tests for Phase 2: Local LLM + RAG Integration.

Tests:
1. Ollama client request building, temperature=0, and JSON response parsing.
2. Ollama error handling (ConnectionError, ModelError, TimeoutError, generic OllamaError).
3. Grounded answer generation via Orchestrator with anti-hallucination prompt.
4. Abstention on missing facts without hallucination.
5. Structured error response (status='llm_error') when Ollama fails, retaining retrieved evidence.
6. Ambiguity safety: ambiguous college queries return 'needs_clarification' WITHOUT invoking LLM.
7. Cutoff safety: cutoff queries without cutoff dataset return 'unavailable' WITHOUT invoking LLM.
8. Backward compatibility: when use_llm=False, pipeline retains status='evidence_only'.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
AGENTS = SCRIPTS / "agents"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(AGENTS))

from cutoff_agent import CutoffAgent
from ollama_client import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelError,
    call_ollama,
)
from orchestrator import (
    CUTOFF_UNAVAILABLE,
    Orchestrator,
    extract_evidence_identifiers,
    normalize_citations,
)
from rag_pipeline import answer_question, build_pipeline


class MockCollegeInfoAgent:
    """Mock college info agent providing deterministic college profile chunks."""

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
                    "text": (
                        "College: Government College of Engineering, Amravati\n"
                        "affiliation: Sant Gadge Baba Amravati University\n"
                        "district: Amravati\n"
                        "state: Maharashtra"
                    ),
                    "metadata": {
                        "record_id": "MHHEI_00001",
                        "institute_code": "01002",
                        "source_page": "https://www.gcoea.ac.in/",
                        "chunk_type": "profile",
                    },
                    "distance": 0.05,
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
        return "\n".join(
            f"[{r['metadata'].get('record_id')}:{r['chunk_id']}] {r['text']}"
            for r in results
        )


class TestOllamaClient(unittest.TestCase):
    """Test the local Ollama HTTP client implementation."""

    @patch("urllib.request.urlopen")
    def test_call_ollama_success(self, mock_urlopen):
        # Prepare mock Ollama response
        response_payload = {
            "model": "qwen2.5:7b",
            "message": {
                "role": "assistant",
                "content": (
                    "Government College of Engineering, Amravati is affiliated with "
                    "Sant Gadge Baba Amravati University [MHHEI_00001:MHHEI_00001_profile]."
                ),
            },
            "done": True,
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        ans = call_ollama(
            system="Answer strictly from evidence.",
            user="EVIDENCE: Affiliation is Sant Gadge Baba\nQUESTION: What is affiliation?",
            model="qwen2.5:7b",
            host="http://localhost:11434",
        )

        self.assertIn("Sant Gadge Baba Amravati University", ans)
        self.assertIn("[MHHEI_00001:MHHEI_00001_profile]", ans)

        # Verify request parameters
        call_args, _ = mock_urlopen.call_args
        req = call_args[0]
        self.assertEqual(req.full_url, "http://localhost:11434/api/chat")
        sent_body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(sent_body["model"], "qwen2.5:7b")
        self.assertFalse(sent_body["stream"])
        self.assertEqual(sent_body["options"]["temperature"], 0.0)

    @patch("urllib.request.urlopen")
    def test_call_ollama_http_404_model_not_found(self, mock_urlopen):
        err_body = io.BytesIO(b'{"error": "model \'qwen2.5:7b\' not found, try pulling it first"}')
        http_err = urllib.error.HTTPError(
            url="http://localhost:11434/api/chat",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=err_body,
        )
        mock_urlopen.side_effect = http_err

        with self.assertRaises(OllamaModelError) as ctx:
            call_ollama("sys", "usr", model="qwen2.5:7b")
        self.assertIn("qwen2.5:7b", str(ctx.exception))
        self.assertIn("not found", str(ctx.exception).lower())

    @patch("urllib.request.urlopen")
    def test_call_ollama_connection_error_daemon_down(self, mock_urlopen):
        url_err = urllib.error.URLError(reason="Connection refused")
        mock_urlopen.side_effect = url_err

        with self.assertRaises(OllamaConnectionError) as ctx:
            call_ollama("sys", "usr", host="http://localhost:11434")
        self.assertIn("Failed to connect to local Ollama daemon", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_call_ollama_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Timed out")

        with self.assertRaises(OllamaConnectionError) as ctx:
            call_ollama("sys", "usr", timeout=5.0)
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch("urllib.request.urlopen")
    def test_call_ollama_malformed_response(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"Not JSON at all"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaises(OllamaError):
            call_ollama("sys", "usr")


class TestOrchestratorLLMIntegration(unittest.TestCase):
    """Test Orchestrator routing, prompting, and structured response with LLM attached."""

    def setUp(self):
        self.mock_info = MockCollegeInfoAgent()

    def test_grounded_answer_generation(self):
        recorded_calls = []

        def mock_llm(system: str, user: str) -> str:
            recorded_calls.append({"system": system, "user": user})
            return (
                "According to the records, Government College of Engineering, Amravati "
                "is affiliated with Sant Gadge Baba Amravati University "
                "[MHHEI_00001:MHHEI_00001_profile]."
            )

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=mock_llm)
        res = orch.answer("What is the affiliation of Government College of Engineering, Amravati?")

        self.assertEqual(res["status"], "answered")
        self.assertEqual(res["matched_college"], "Government College of Engineering, Amravati")
        self.assertEqual(res["institute_code"], "01002")
        self.assertEqual(res["record_id"], "MHHEI_00001")
        self.assertEqual(res["intent"], "info")
        self.assertIn("Sant Gadge Baba Amravati University", res["answer"])
        self.assertIn("[MHHEI_00001:MHHEI_00001_profile]", res["answer"])
        self.assertIn("Sant Gadge Baba Amravati University", res["evidence"])

        # Verify strict prompt requirements
        self.assertEqual(len(recorded_calls), 1)
        sys_prompt = recorded_calls[0]["system"]
        self.assertIn("ONLY using the facts present in the EVIDENCE", sys_prompt)
        self.assertIn("EXACT bracketed identifier tag", sys_prompt)
        self.assertIn("Never invent, shorten, modify, or rewrite citation identifiers", sys_prompt)
        self.assertIn("Preserve the complete bracketed format exactly as provided in the evidence", sys_prompt)
        self.assertNotIn("[record_id:chunk_id]", sys_prompt)
        self.assertIn("NEVER invent", sys_prompt)
        self.assertIn("Never guarantee or promise admission", sys_prompt)

        user_prompt = recorded_calls[0]["user"]
        self.assertIn("EVIDENCE:", user_prompt)
        self.assertIn("QUESTION:", user_prompt)
        self.assertIn("Sant Gadge Baba", user_prompt)
        self.assertIn("[MHHEI_00001:MHHEI_00001_profile]", user_prompt)

    def test_citation_fixes_accidental_record_id_placeholder(self):
        """Simulates Qwen emitting '[record_id:MHHEI_00001_profile]' and verifies orchestrator normalizes it."""
        def mock_buggy_llm(system: str, user: str) -> str:
            return (
                "Government College of Engineering, Amravati is affiliated with "
                "Sant Gadge Baba Amravati University [record_id:MHHEI_00001_profile]."
            )

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=mock_buggy_llm)
        res = orch.answer("What is the affiliation of Government College of Engineering, Amravati?")

        self.assertEqual(res["status"], "answered")
        # Citation must be normalized to exact chunk identifier from evidence
        self.assertIn("[MHHEI_00001:MHHEI_00001_profile]", res["answer"])
        self.assertNotIn("[record_id:", res["answer"])
        # Verify that the normalized citation exists in the evidence text
        evidence_ids = extract_evidence_identifiers(res["evidence"])
        self.assertIn("MHHEI_00001:MHHEI_00001_profile", evidence_ids)

    def test_citation_fixes_shortened_chunk_identifier(self):
        """Simulates LLM emitting '[MHHEI_00001_profile]' without record prefix and verifies normalization."""
        def mock_shortened_llm(system: str, user: str) -> str:
            return (
                "The college is located in Amravati [MHHEI_00001_profile]."
            )

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=mock_shortened_llm)
        res = orch.answer("Where is Government College of Engineering, Amravati?")

        self.assertEqual(res["status"], "answered")
        self.assertIn("[MHHEI_00001:MHHEI_00001_profile]", res["answer"])
        self.assertNotIn("[MHHEI_00001_profile]", res["answer"])

    def test_citations_refer_to_supplied_evidence_identifiers(self):
        """Verifies that all citations in the answer correspond directly to identifiers in the evidence."""
        def mock_llm(system: str, user: str) -> str:
            return (
                "Affiliated with Sant Gadge Baba University [MHHEI_00001:MHHEI_00001_profile]."
            )

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=mock_llm)
        res = orch.answer("What is the affiliation of Government College of Engineering, Amravati?")

        evidence_ids = extract_evidence_identifiers(res["evidence"])
        self.assertTrue(len(evidence_ids) > 0)
        self.assertIn("MHHEI_00001:MHHEI_00001_profile", evidence_ids)

        import re
        answer_citations = re.findall(r"\[([A-Za-z0-9_:\-]+)\]", res["answer"])
        for cite in answer_citations:
            self.assertIn(cite, evidence_ids)

    def test_extract_and_normalize_utility(self):
        evidence_sample = (
            "COLLEGE INFO EVIDENCE:\n"
            "[MHHEI_00001:MHHEI_00001_profile] (profile): College: GCOE Amravati\n\n"
            "[MHHEI_00001:MHHEI_00001_placement_0] (placement): Placement: 10 LPA\n\n"
            "CUTOFF EVIDENCE:\n"
            "[EV-01002-COMP-GOPENS-R1] 2025-26 GCOE Amravati - Computer - GOPENS: round 1"
        )
        ids = extract_evidence_identifiers(evidence_sample)
        self.assertEqual(ids, [
            "MHHEI_00001:MHHEI_00001_profile",
            "MHHEI_00001:MHHEI_00001_placement_0",
            "EV-01002-COMP-GOPENS-R1",
        ])

        # Test normalization of buggy citations
        ans_raw = (
            "GCOE is in Amravati [record_id:MHHEI_00001_profile] with high package "
            "[MHHEI_00001_placement_0] and cutoff [EV-01002-COMP-GOPENS-R1]."
        )
        cleaned = normalize_citations(ans_raw, evidence_sample)
        self.assertIn("[MHHEI_00001:MHHEI_00001_profile]", cleaned)
        self.assertIn("[MHHEI_00001:MHHEI_00001_placement_0]", cleaned)
        self.assertIn("[EV-01002-COMP-GOPENS-R1]", cleaned)
        self.assertNotIn("record_id:", cleaned)

    def test_missing_evidence_honesty(self):
        def mock_llm(system: str, user: str) -> str:
            return (
                "The college records for Government College of Engineering, Amravati "
                "do not mention the annual tuition fee [MHHEI_00001:MHHEI_00001_profile]."
            )

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=mock_llm)
        res = orch.answer("What is the annual tuition fee of Government College of Engineering, Amravati?")

        self.assertEqual(res["status"], "answered")
        self.assertIn("do not mention", res["answer"].lower())
        self.assertNotIn("₹", res["answer"])
        self.assertNotIn("Rs", res["answer"])

    def test_ollama_connection_failure_returns_structured_error(self):
        def mock_llm_fail(system: str, user: str) -> str:
            raise OllamaConnectionError(
                "Failed to connect to local Ollama daemon at http://localhost:11434 (Connection refused)."
            )

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=mock_llm_fail)
        res = orch.answer("What is the affiliation of Government College of Engineering, Amravati?")

        self.assertEqual(res["status"], "llm_error")
        self.assertIn("Failed to connect to local Ollama daemon", res["error"])
        self.assertIn("Local LLM generation failed", res["message"])
        # Crucial: evidence is still preserved for the user/system!
        self.assertIn("Sant Gadge Baba Amravati University", res["evidence"])
        self.assertEqual(res["matched_college"], "Government College of Engineering, Amravati")
        self.assertEqual(res["institute_code"], "01002")

    def test_ollama_model_missing_error_handling(self):
        def mock_llm_model_error(system: str, user: str) -> str:
            raise OllamaModelError("Ollama model 'qwen2.5:7b' not found on http://localhost:11434.")

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=mock_llm_model_error)
        res = orch.answer("What is the affiliation of Government College of Engineering, Amravati?")

        self.assertEqual(res["status"], "llm_error")
        self.assertIn("not found", res["error"].lower())
        self.assertIn("qwen2.5:7b", res["error"])
        self.assertIn("Sant Gadge Baba Amravati University", res["evidence"])

    def test_ambiguity_safety_never_invokes_llm(self):
        """Ambiguous query must return needs_clarification immediately without touching LLM."""
        call_count = [0]

        def forbidden_llm(system: str, user: str) -> str:
            call_count[0] += 1
            raise AssertionError("LLM should NEVER be called for ambiguous queries!")

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=forbidden_llm)
        # "Government College of Engineering" matches Amravati and Karad
        res = orch.answer("What is the affiliation of Government College of Engineering?")

        self.assertEqual(res["status"], "needs_clarification")
        self.assertEqual(call_count[0], 0)
        self.assertIn("candidates", res)
        self.assertTrue(len(res["candidates"]) >= 2)

    def test_cutoff_safety_without_cutoff_dataset_never_invokes_llm(self):
        """Cutoff query with no cutoff dataset must return unavailable immediately without touching LLM."""
        call_count = [0]

        def forbidden_llm(system: str, user: str) -> str:
            call_count[0] += 1
            raise AssertionError("LLM should NEVER be called for cutoffs when cutoff dataset is missing!")

        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=forbidden_llm)
        res = orch.answer(
            "What was the GOPENS cutoff for Computer Engineering at Government College of Engineering, Amravati?"
        )

        self.assertEqual(res["status"], "unavailable")
        self.assertEqual(call_count[0], 0)
        self.assertEqual(res["message"], CUTOFF_UNAVAILABLE)
        self.assertEqual(res["intent"], "cutoff")
        # Ensure no ranks or cutoffs were fabricated
        self.assertNotIn("closing rank", res["message"])
        self.assertNotIn("percentile", res["message"])

    def test_evidence_only_when_no_llm_configured(self):
        """Backward compatibility: without llm_call, status must remain 'evidence_only'."""
        orch = Orchestrator(cutoff_agent=None, college_info_agent=self.mock_info, llm_call=None)
        res = orch.answer("What is the affiliation of Government College of Engineering, Amravati?")
        self.assertEqual(res["status"], "evidence_only")
        self.assertNotIn("answer", res)
        self.assertIn("Sant Gadge Baba Amravati University", res["evidence"])

    def test_fabricated_profile_citation_removed_from_cutoff_response(self):
        """Unsupported [MHHEI_...] citations in cutoff answers must be stripped."""
        class MockCutoffForCitationTest(CutoffAgent):
            def __init__(self):
                self.cutoffs_dir = Path(".")
                self._by_code = {}

            def list_branches(self, code, year=None):
                return ["Computer Science and Engineering"]

            def years_available(self, code):
                return ["2024-25"]

            def get_cutoffs(self, code, **kwargs):
                return [{
                    "academic_year": "2024-25",
                    "institute_code": "01002",
                    "branch": "Computer Science and Engineering",
                    "category": "GOPENS",
                    "round": 1,
                    "closing_rank": 1500,
                    "closing_percentile": 98.25,
                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                }]

            def as_evidence_text(self, results):
                return "[EV-01002-COMP-GOPENS-R1] 2024-25 GCOE Amravati - Computer - GOPENS: round 1 rank 1500 (98.25%)"

        def mock_hallucinating_llm(system: str, user: str) -> str:
            return (
                "The closing rank was 1500 [MHHEI_00001:MHHEI_00001_profile] and "
                "percentile was 98.25 [EV-01002-COMP-GOPENS-R1]."
            )

        orch = Orchestrator(
            cutoff_agent=MockCutoffForCitationTest(),
            college_info_agent=self.mock_info,
            llm_call=mock_hallucinating_llm,
        )
        res = orch.answer(
            "What is the cutoff for Computer Science and Engineering at Government College of Engineering, Amravati?"
        )
        self.assertEqual(res["status"], "answered")
        self.assertNotIn("MHHEI_00001", res["answer"])
        self.assertIn("[EV-01002-COMP-GOPENS-R1]", res["answer"])

    def test_missing_cutoff_unoffered_branch_never_invokes_llm(self):
        """Cutoff query for an unoffered branch must return unavailable without calling LLM or leaking unrelated evidence."""
        call_count = [0]

        def forbidden_llm(system: str, user: str) -> str:
            call_count[0] += 1
            raise AssertionError("LLM should NEVER be called for unoffered cutoff branch!")

        class MockCutoffCivilOnly(CutoffAgent):
            def __init__(self):
                self.cutoffs_dir = Path(".")
                self._by_code = {}

            def list_branches(self, code, year=None):
                return ["Civil Engineering"]

            def years_available(self, code):
                return ["2024-25"]

            def get_cutoffs(self, code, **kwargs):
                return []

            def as_evidence_text(self, results):
                return "No matching cutoff records found."

        orch = Orchestrator(
            cutoff_agent=MockCutoffCivilOnly(),
            college_info_agent=self.mock_info,
            llm_call=forbidden_llm,
        )
        res = orch.answer(
            "What is the cutoff for Aerospace Engineering at Government College of Engineering, Amravati?"
        )
        self.assertEqual(res["status"], "unavailable")
        self.assertEqual(call_count[0], 0)
        self.assertIn("The requested branch 'Aerospace Engineering' is not offered", res["message"])
        self.assertNotIn("Civil Engineering", res["evidence"])

        # Test exact query from smoke test
        res_exact = orch.answer(
            "What was the Aerospace Engineering cutoff at Government College of Engineering, Amravati in 2024-25?"
        )
        self.assertEqual(res_exact["status"], "unavailable")
        self.assertEqual(call_count[0], 0)
        self.assertIn("The requested branch 'Aerospace Engineering' is not offered", res_exact["message"])
        self.assertNotIn("the Aerospace", res_exact["message"])
        self.assertNotIn("Civil Engineering", res_exact["evidence"])

        # Test leading article variation ("the Aerospace Engineering")
        res_article = orch.answer(
            "What was the cutoff for the Aerospace Engineering branch at Government College of Engineering, Amravati in 2024-25?"
        )
        self.assertEqual(res_article["status"], "unavailable")
        self.assertEqual(call_count[0], 0)
        self.assertIn("The requested branch 'Aerospace Engineering' is not offered", res_article["message"])
        self.assertNotIn("the Aerospace", res_article["message"])
        self.assertNotIn("the Aerospace Engineering", res_article["message"])

    def test_positive_cse_query_answers_normally(self):
        """Positive query for an offered branch (CSE) succeeds with answered status and invokes LLM."""
        llm_invocations = [0]

        def normal_llm(system: str, user: str) -> str:
            llm_invocations[0] += 1
            return "The closing rank for Computer Science and Engineering was 1500 [EV-01002-COMP-GOPENS-R1]."

        class MockCutoffCSE(CutoffAgent):
            def __init__(self):
                self.cutoffs_dir = Path(".")
                self._by_code = {}

            def list_branches(self, code, year=None):
                return ["Civil Engineering", "Computer Science and Engineering"]

            def years_available(self, code):
                return ["2024-25"]

            def get_cutoffs(self, code, **kwargs):
                return [{
                    "academic_year": "2024-25",
                    "institute_code": "01002",
                    "institute_name": "Government College of Engineering, Amravati",
                    "branch": "Computer Science and Engineering",
                    "category": "GOPENS",
                    "round": 1,
                    "stage": "1",
                    "list_type": "CAP",
                    "closing_rank": 1500,
                    "closing_percentile": 98.25,
                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                }]

            def as_evidence_text(self, results):
                return "[EV-01002-COMP-GOPENS-R1] 2024-25 GCOE Amravati - Computer Science and Engineering - GOPENS: round 1 rank 1500 (98.25%)"

        orch = Orchestrator(
            cutoff_agent=MockCutoffCSE(),
            college_info_agent=self.mock_info,
            llm_call=normal_llm,
        )
        res = orch.answer(
            "What was the Computer Science and Engineering cutoff at Government College of Engineering, Amravati in 2024-25?"
        )
        self.assertEqual(res["status"], "answered")
        self.assertEqual(llm_invocations[0], 1)
        self.assertIn("1500", res["answer"])
        self.assertIn("[EV-01002-COMP-GOPENS-R1]", res["answer"])


class TestRAGPipelinePhase2(unittest.TestCase):
    """Test rag_pipeline build_pipeline and answer_question Phase 2 integration."""

    @patch("rag_pipeline.CollegeInfoAgent")
    def test_answer_question_with_mock_llm(self, mock_info_cls):
        mock_info = MockCollegeInfoAgent()
        mock_info_cls.return_value = mock_info

        def mock_llm(system: str, user: str) -> str:
            return "Government College of Engineering, Amravati is located in Amravati [MHHEI_00001:MHHEI_00001_profile]."

        res = answer_question(
            question="Tell me about Government College of Engineering, Amravati",
            vector_index_dir="./dummy_index",
            use_llm=True,
            llm_call=mock_llm,
        )
        self.assertEqual(res["status"], "answered")
        self.assertEqual(res["matched_college"], "Government College of Engineering, Amravati")
        self.assertIn("located in Amravati", res["answer"])


if __name__ == "__main__":
    unittest.main()
