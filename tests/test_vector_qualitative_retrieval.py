"""
Unit and integration tests for Task 10: Vector Index and Qualitative Retrieval.
Tests index manifest generation, embedding model alignment, chunk_type filtering,
similarity distance/score calibration, structured discovery two-stage qualitative retrieval,
and safe index rebuilding with rollback protection.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_vector_index import index_college_files, safe_rebuild_vector_index
from scripts.agents.college_info_agent import CollegeInfoAgent
from tests.test_chroma_indexing import DeterministicHashEmbeddingFunction


class TestVectorQualitativeRetrieval(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.colleges_dir = self.tmp_dir / "colleges"
        self.colleges_dir.mkdir()
        self.index_dir = self.tmp_dir / "chroma_index"
        self.embedder = DeterministicHashEmbeddingFunction()

        # Seed test college files
        self._write_college_json(
            "MHHEI_00001", "01002", "Government College of Engineering, Amravati",
            aff="Sant Gadge Baba Amravati University", district="Amravati"
        )
        self._write_college_json(
            "MHHEI_00002", "06006", "COEP Technological University",
            aff="Autonomous University", district="Pune"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_college_json(self, record_id, code, name, aff=None, district=None):
        rec = {
            "schema_version": "4.0",
            "record_id": record_id,
            "institute_code": code,
            "institute_name": name,
            "extracted": {
                "identity": {
                    "verification_status": {"value": "verified_official", "source": "CET Cell"},
                    "state": {"value": "Maharashtra", "source": "CET Cell"},
                }
            },
            "sources_consulted": ["https://cetcell.mahacet.org/"],
        }
        if aff:
            rec["extracted"]["identity"]["affiliation"] = {"value": aff, "source": "CET Cell"}
        if district:
            rec["extracted"]["identity"]["district"] = {"value": district, "source": "CET Cell"}
        p = self.colleges_dir / f"{record_id}.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
        return p

    def test_01_index_manifest_creation(self):
        """index_college_files must persist an index_manifest.json with model and counts."""
        stats = index_college_files(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )
        manifest_path = self.index_dir / "index_manifest.json"
        self.assertTrue(manifest_path.exists())

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["chunk_count"], stats["chunks"])
        self.assertEqual(manifest["college_count"], stats["colleges"])
        self.assertIn("embedding_model", manifest)
        self.assertIn("built_at", manifest)

    def test_02_model_compatibility_check(self):
        """CollegeInfoAgent must detect model compatibility from manifest."""
        index_college_files(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )

        agent = CollegeInfoAgent(self.index_dir, embedding_function=self.embedder)
        compat, msg = agent.check_model_compatibility()
        self.assertTrue(compat)
        self.assertIn("Compatible", msg)

    def test_03_chunk_type_and_institute_code_filtering(self):
        """search() must support combined institute_code and chunk_type filtering via $and."""
        index_college_files(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )

        agent = CollegeInfoAgent(self.index_dir, embedding_function=self.embedder)
        results = agent.search("Autonomous", institute_code="06006", chunk_type="profile")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["metadata"]["institute_code"], "06006")
            self.assertEqual(r["metadata"]["chunk_type"], "profile")

        # Non-matching chunk_type returns empty
        none_results = agent.search("Autonomous", institute_code="06006", chunk_type="nonexistent_type")
        self.assertEqual(len(none_results), 0)

    def test_04_similarity_score_and_relevance_threshold(self):
        """search() must return normalized similarity_score and respect relevance_threshold."""
        index_college_files(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )

        agent = CollegeInfoAgent(self.index_dir, embedding_function=self.embedder)
        results = agent.search("Amravati", relevance_threshold=0.0)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("similarity_score", r)
            self.assertIn("distance", r)
            self.assertTrue(r["is_relevant"])

    def test_05_search_for_institutes_qualitative(self):
        """search_for_institutes scopes qualitative retrieval to candidate discovery codes."""
        index_college_files(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )

        agent = CollegeInfoAgent(self.index_dir, embedding_function=self.embedder)
        candidate_codes = ["01002", "06006"]
        res_by_code = agent.search_for_institutes("engineering", candidate_codes)

        self.assertIn("01002", res_by_code)
        self.assertIn("06006", res_by_code)
        self.assertEqual(res_by_code["01002"][0]["metadata"]["institute_code"], "01002")
        self.assertEqual(res_by_code["06006"][0]["metadata"]["institute_code"], "06006")

    def test_06_safe_rebuild_vector_index(self):
        """safe_rebuild_vector_index builds into staging, swaps atomically, and preserves backup."""
        # Initial build
        index_college_files(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )
        self.assertTrue((self.index_dir / "index_manifest.json").exists())

        # Safe rebuild
        rebuild_res = safe_rebuild_vector_index(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )
        self.assertEqual(rebuild_res["status"], "success")
        self.assertTrue(Path(rebuild_res["active_path"]).exists())
        self.assertTrue(Path(rebuild_res["backup_path"]).exists())

    def test_07_safe_rebuild_rejection_on_failure(self):
        """safe_rebuild_vector_index aborts and leaves live index intact if staging build fails."""
        # Initial build
        index_college_files(
            college_info_dir=self.colleges_dir,
            out_dir=self.index_dir,
            embedding_function=self.embedder,
        )
        empty_dir = self.tmp_dir / "empty_dir"
        empty_dir.mkdir()

        # Rebuilding from empty directory must fail validation
        with self.assertRaises(ValueError):
            safe_rebuild_vector_index(
                college_info_dir=empty_dir,
                out_dir=self.index_dir,
                embedding_function=self.embedder,
            )

        # Active index must still exist and be intact
        self.assertTrue((self.index_dir / "index_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
