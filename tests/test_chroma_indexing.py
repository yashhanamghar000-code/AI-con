#!/usr/bin/env python3
"""Integration tests for Persistent Chroma Vector Indexing (Phase 1)."""
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

from build_vector_index import (
    build_college_documents,
    index_college_files,
)


try:
    from chromadb.api.types import EmbeddingFunction, Documents
    from chromadb.utils.embedding_functions import register_embedding_function
    BaseEF = EmbeddingFunction[Documents]
except Exception:
    BaseEF = object
    def register_embedding_function(cls):
        return cls


@register_embedding_function
class DeterministicHashEmbeddingFunction(BaseEF):
    """Local, offline embedding function for testing without internet or PyTorch models."""

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
        return "deterministic_hash"

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
        return DeterministicHashEmbeddingFunction()

    def is_legacy(self) -> bool:
        return False


class TestChromaIndexing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import chromadb  # noqa: F401
        except ImportError:
            raise unittest.SkipTest(
                "chromadb is not installed. To run Chroma integration tests:\n"
                "  cd model_rag_agent_plan\n"
                "  pip install -r requirements.txt"
            )

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.sample_colleges = self.tmp_dir / "colleges"
        self.sample_colleges.mkdir()
        self.index_dir = self.tmp_dir / "chroma_index"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_sample(self, record_id, name, code=None, aff=None, district=None):
        rec = {
            "schema_version": "4.0",
            "record_id": record_id,
            "institute_name": name,
            "extracted": {
                "identity": {
                    "verification_status": {"value": "verified", "source": "CET Cell"},
                    "state": {"value": "Maharashtra", "source": "CET Cell"},
                }
            },
            "sources_consulted": ["https://cetcell.mahacet.org/"],
        }
        if code:
            rec["institute_code"] = code
        if aff:
            rec["extracted"]["identity"]["affiliation"] = {"value": aff, "source": "CET Cell"}
        if district:
            rec["extracted"]["identity"]["district"] = {"value": district, "source": "CET Cell"}

        p = self.sample_colleges / f"{record_id}.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
        return p

    def test_sample_indexing_and_retrieval(self):
        self._write_sample("MHHEI_00001", "Government College of Engineering, Amravati", code="01002", aff="Sant Gadge Baba Amravati University", district="Amravati")
        self._write_sample("MHHEI_00004", "Shri Sant Gajanan Maharaj College of Engineering, Shegaon", code="01101", aff="Amravati University", district="Buldhana")
        self._write_sample("MHHEI_00552", "KDM College of Arts", code=None, district="Nagpur")

        embedder = DeterministicHashEmbeddingFunction()
        stats = index_college_files(
            college_info_dir=self.sample_colleges,
            out_dir=self.index_dir,
            limit=0,
            embedding_function=embedder,
        )

        self.assertEqual(stats["colleges"], 3)
        self.assertEqual(stats["chunks"], 3)
        self.assertEqual(stats["skipped"], 0)

        from college_info_agent import CollegeInfoAgent

        agent = CollegeInfoAgent(self.index_dir, embedding_function=embedder)
        name_idx = agent.list_name_index()
        self.assertIn("Government College of Engineering, Amravati", name_idx)
        self.assertIn("KDM College of Arts", name_idx)

        # Retrieval with metadata filter
        results = agent.search("affiliation", institute_code="01002")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["metadata"]["institute_code"], "01002")
        self.assertIn("Sant Gadge Baba Amravati University", results[0]["text"])

        # Retrieval by record_id (college without institute_code)
        kdm_results = agent.search("arts", record_id="MHHEI_00552")
        self.assertTrue(len(kdm_results) > 0)
        self.assertEqual(kdm_results[0]["metadata"]["record_id"], "MHHEI_00552")
        self.assertIn("KDM College of Arts", kdm_results[0]["text"])


if __name__ == "__main__":
    unittest.main()
