#!/usr/bin/env python3
"""Phase 1A tests: v4 college JSON parsing and information-only retrieval."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DATASET = ROOT.parent / "college_ai_consultant_sparse_enriched_v4_no_cutoffs"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "agents"))

from build_vector_index import (  # noqa: E402
    build_college_documents,
    extract_profile_facts,
    factual_value,
    index_college_files,
    is_college_record,
)
from orchestrator import CUTOFF_UNAVAILABLE, Orchestrator  # noqa: E402
from rag_pipeline import answer_question  # noqa: E402


SAMPLE_IDS = ("MHHEI_00001", "MHHEI_00552", "MHHEI_01039")


try:
    from chromadb.api.types import EmbeddingFunction, Documents
    from chromadb.utils.embedding_functions import register_embedding_function
    BaseEF = EmbeddingFunction[Documents]
except Exception:
    BaseEF = object
    def register_embedding_function(cls):
        return cls


@register_embedding_function
class HashEmbeddingFunction(BaseEF):
    """Deterministic local embedder so tests do not download a model."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, input):
        vectors = []
        for text in input:
            vec = [0.0] * 16
            data = (text or "").encode("utf-8")
            for i, byte in enumerate(data):
                vec[i % 16] += (byte % 17) / 17.0
            length = sum(x * x for x in vec) ** 0.5 or 1.0
            vectors.append([x / length for x in vec])
        return vectors

    @staticmethod
    def name() -> str:
        return "hash_embedding_function"

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list:
        return ["cosine", "l2", "ip"]

    def embed_query(self, input):
        return self.__call__(input)

    def embed_with_retries(self, input, **kwargs):
        return self.__call__(input)

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict):
        return HashEmbeddingFunction()

    def is_legacy(self) -> bool:
        return False


def load_sample(record_id):
    path = DATASET / f"{record_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class FactualValueTests(unittest.TestCase):
    def test_nested_value_used_not_source_or_confidence(self):
        obj = {
            "value": "Sant Gadge Baba Amravati University",
            "source": "Maharashtra State CET Cell",
            "confidence": "provided_master_list",
        }
        self.assertEqual(factual_value(obj), "Sant Gadge Baba Amravati University")

    def test_confidence_only_field_is_missing(self):
        obj = {
            "confidence": "provided_master_list",
            "source": "Maharashtra State CET Cell",
        }
        self.assertIsNone(factual_value(obj))

    def test_plain_string_and_empty(self):
        self.assertEqual(factual_value("  Parbhani  "), "Parbhani")
        self.assertIsNone(factual_value(""))
        self.assertIsNone(factual_value(None))
        self.assertIsNone(factual_value({"conflict": [{"value": "A"}, {"value": "B"}]}))


class V4ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DATASET.is_dir():
            raise unittest.SkipTest(f"Dataset folder not found: {DATASET}")
        for record_id in SAMPLE_IDS:
            if not (DATASET / f"{record_id}.json").is_file():
                raise unittest.SkipTest(f"Missing sample {record_id}.json")

    def test_nested_affiliation_from_real_record(self):
        record = load_sample("MHHEI_00001")
        facts = dict(extract_profile_facts(record))
        self.assertEqual(facts["affiliation"], "Sant Gadge Baba Amravati University")
        self.assertEqual(facts["institute_code"], "01002")
        self.assertEqual(facts["record_id"], "MHHEI_00001")
        self.assertEqual(facts["official_website"], "https://www.gcoea.ac.in/")
        self.assertIn("gcoea.ac.in", facts["sources_consulted"])
        self.assertNotIn("provided_master_list", " ".join(facts.values()))
        self.assertNotIn("placement", facts)
        self.assertNotIn("naac_grade", facts)

    def test_missing_institute_code_uses_record_id(self):
        record = load_sample("MHHEI_00552")
        self.assertIsNone(factual_value(record.get("institute_code")))
        docs = build_college_documents(record)
        self.assertTrue(docs)
        doc_id, text, meta = docs[0]
        self.assertTrue(doc_id.startswith("MHHEI_00552"))
        self.assertEqual(meta["record_id"], "MHHEI_00552")
        self.assertNotIn("institute_code", meta)
        self.assertIn("KDM College of Arts", text)
        self.assertNotIn("affiliation:", text.lower())

    def test_empty_city_not_indexed_district_value_is(self):
        record = load_sample("MHHEI_01039")
        facts = dict(extract_profile_facts(record))
        self.assertNotIn("city", facts)
        self.assertEqual(facts["district"], "Parbhani")
        self.assertNotIn("closing_rank", facts)
        text = "\n".join(d[1] for d in build_college_documents(record))
        self.assertNotIn("provided_master_list", text)

    def test_manifest_is_not_a_college_record(self):
        manifest = json.loads((DATASET / "dataset_manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(is_college_record(manifest))
        self.assertEqual(build_college_documents(manifest), [])

    def test_chroma_metadata_has_no_none(self):
        for record_id in SAMPLE_IDS:
            for _, _, meta in build_college_documents(load_sample(record_id)):
                for key, value in meta.items():
                    self.assertIsNotNone(value, key)
                    self.assertIsInstance(value, (str, int, float, bool))


class MissingCutoffTests(unittest.TestCase):
    def test_cutoff_question_does_not_invent_numbers(self):
        class FakeInfo:
            def list_name_index(self):
                return {"Government College of Engineering, Amravati": {
                    "institute_code": "01002", "record_id": "MHHEI_00001"}}

            def search(self, query, institute_code=None, record_id=None, n_results=5):
                return []

            def as_evidence_text(self, results):
                return "No relevant information found in the college dataset."

        orch = Orchestrator(cutoff_agent=None, college_info_agent=FakeInfo())
        result = orch.answer(
            "What was the GOPENS cutoff for Computer Engineering at "
            "Government College of Engineering, Amravati?"
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("not available", result["message"].lower())
        blob = json.dumps(result).lower()
        self.assertNotRegex(blob, r"closing rank \d+")
        self.assertIn("no cutoff values were generated", blob)

    def test_info_question_does_not_require_cutoff_agent(self):
        class FakeInfo:
            def list_name_index(self):
                return {"KDM College of Arts": {"record_id": "MHHEI_00552"}}

            def search(self, query, institute_code=None, record_id=None, n_results=5):
                self.seen = {"query": query, "institute_code": institute_code, "record_id": record_id}
                return [{"chunk_id": "MHHEI_00552_profile", "text": "College: KDM College of Arts",
                         "metadata": {"record_id": "MHHEI_00552", "chunk_type": "profile",
                                      "institute_name": "KDM College of Arts"}}]

            def as_evidence_text(self, results):
                from college_info_agent import CollegeInfoAgent
                return CollegeInfoAgent.as_evidence_text(CollegeInfoAgent, results)

        fake = FakeInfo()
        orch = Orchestrator(cutoff_agent=None, college_info_agent=fake)
        result = orch.answer("Tell me about KDM College of Arts")
        self.assertEqual(result["status"], "evidence_only")
        self.assertEqual(result["intent"], "info")
        self.assertIsNone(result["institute_code"])
        self.assertEqual(result["record_id"], "MHHEI_00552")
        self.assertEqual(fake.seen["record_id"], "MHHEI_00552")
        self.assertIn("KDM College of Arts", result["evidence"])


class CutoffAgentPreservedTests(unittest.TestCase):
    def test_valid_cutoff_folder_still_looks_up_exactly(self):
        from cutoff_agent import CutoffAgent

        tmp = Path(tempfile.mkdtemp())
        try:
            year = tmp / "2025-26"
            year.mkdir()
            payload = {
                "institute_code": "01002",
                "institute_name": "Government College of Engineering, Amravati",
                "academic_year": "2025-26",
                "branches": [{
                    "branch": "Computer Engineering",
                    "categories": [{
                        "category": "GOPENS",
                        "cutoffs": [{
                            "round": 1,
                            "stage": "1",
                            "list_type": "CAP",
                            "closing_rank": 1234,
                            "closing_percentile": 98.1,
                            "evidence_id": "EV-TEST-1",
                        }],
                    }],
                }],
            }
            (year / "01002.json").write_text(json.dumps(payload), encoding="utf-8")
            agent = CutoffAgent(tmp)
            rows = agent.get_cutoffs("01002", branch_query="Computer", category="GOPENS")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["closing_rank"], 1234)
            self.assertIn("EV-TEST-1", agent.as_evidence_text(rows))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RetrievalIntegrationTests(unittest.TestCase):
    def test_sample_index_and_info_query(self):
        try:
            import chromadb  # noqa: F401
        except ImportError:
            raise unittest.SkipTest(
                "chromadb is not installed. In PowerShell run:\n"
                "  cd model_rag_agent_plan\n"
                "  pip install -r requirements.txt"
            )
        if not DATASET.is_dir():
            raise unittest.SkipTest(f"Dataset folder not found: {DATASET}")

        tmp = Path(tempfile.mkdtemp())
        sample_dir = tmp / "colleges"
        index_dir = tmp / "index"
        sample_dir.mkdir()
        try:
            for record_id in SAMPLE_IDS:
                src = DATASET / f"{record_id}.json"
                shutil.copy(src, sample_dir / src.name)
            stats = index_college_files(
                sample_dir, index_dir, embedding_function=HashEmbeddingFunction())
            self.assertEqual(stats["colleges"], 3)
            self.assertGreaterEqual(stats["chunks"], 3)

            from college_info_agent import CollegeInfoAgent
            agent = CollegeInfoAgent(index_dir, embedding_function=HashEmbeddingFunction())
            result = answer_question(
                "What is the affiliation of Government College of Engineering, Amravati?",
                cutoffs_dir=None,
                vector_index_dir=index_dir,
                embedding_function=HashEmbeddingFunction(),
            )
            self.assertEqual(result["status"], "evidence_only")
            self.assertEqual(result["intent"], "info")
            self.assertEqual(result["institute_code"], "01002")
            self.assertEqual(result["record_id"], "MHHEI_00001")
            self.assertIn("Sant Gadge Baba Amravati University", result["evidence"])
            self.assertIn("source:", result["evidence"].lower())
            self.assertNotIn("provided_master_list", result["evidence"])

            hits = agent.search("affiliation", record_id="MHHEI_00001")
            self.assertTrue(hits)
            self.assertEqual(hits[0]["metadata"]["record_id"], "MHHEI_00001")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
