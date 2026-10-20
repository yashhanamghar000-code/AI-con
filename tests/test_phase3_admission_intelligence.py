#!/usr/bin/env python3
"""
Unit tests for AI-con Phase 3: Admission Intelligence.
------------------------------------------------------
Verifies:
1. Data Ingestion & Validation (validate_cutoffs.py, adapt_cutoff_data.py)
2. Deterministic CAP Admission Rules & Quota Resolution (admission_rules.py)
3. Historical Cutoff Analysis Service (cutoff_analyzer.py)
4. College Comparison & Transparent Recommendation Engine (recommendation_engine.py)
5. CAP Option-Form Planner (option_planner.py)
6. Orchestrator Phase 3 Integration & Guardrails (orchestrator.py)

All tests run completely offline without downloading models or starting external servers.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
AGENTS = SCRIPTS / "agents"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(AGENTS))

from adapt_cutoff_data import CutoffAdapter, adapt_raw_file, canonical_list_type, clean_branch_name
from admission_rules import AdmissionRulesEngine, EligibilityResult, StudentProfile
from cutoff_agent import CutoffAgent
from cutoff_analyzer import CutoffAnalyzer
from option_planner import OptionFormPlanner
from orchestrator import CUTOFF_UNAVAILABLE, Orchestrator, normalize_citations
from recommendation_engine import RecommendationEngine
from reconcile_staging import CutoffReconciler
from validate_cutoffs import KNOWN_CATEGORY_PATTERN, CutoffValidator, validate_cutoff_file


class TestCutoffValidationAndAdapter(unittest.TestCase):
    """Test cutoff JSON validation and deterministic adaptation."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_sample_file(self, content: dict, filename: str = "sample.json") -> Path:
        p = self.temp_dir / filename
        p.write_text(json.dumps(content, indent=2), encoding="utf-8")
        return p

    def test_validator_valid_fixture(self):
        valid_data = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "course_code": "0100224210",
                    "branch": "Computer Science and Engineering",
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
                                    "source_file": "MHT-CET_CAP_Cutoffs_2024.pdf",
                                    "page": 42,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        fpath = self._create_sample_file(valid_data, "01002.json")
        res = validate_cutoff_file(fpath)
        self.assertTrue(res["is_valid"])
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["cutoffs_checked"], 1)

    def test_validator_catches_invalid_year(self):
        invalid_data = {
            "academic_year": "2024",  # Missing -YY format
            "institute_code": "01002",
            "institute_name": "Test College",
            "branches": [],
        }
        fpath = self._create_sample_file(invalid_data)
        res = validate_cutoff_file(fpath)
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("academic_year" in e for e in res["errors"]))

    def test_validator_catches_invalid_rank(self):
        invalid_data = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "branches": [
                {
                    "branch": "Mechanical",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "closing_rank": -5,  # Rank must be positive integer
                                    "closing_percentile": 85.0,
                                    "evidence_id": "EV-01",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        fpath = self._create_sample_file(invalid_data)
        res = validate_cutoff_file(fpath)
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("closing_rank" in e for e in res["errors"]))

    def test_validator_catches_invalid_percentile(self):
        invalid_data = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "branches": [
                {
                    "branch": "Civil",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "closing_rank": 1000,
                                    "closing_percentile": 105.5,  # Exceeds 100.0
                                    "evidence_id": "EV-02",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        fpath = self._create_sample_file(invalid_data)
        res = validate_cutoff_file(fpath)
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("closing_percentile" in e for e in res["errors"]))

    def test_validator_catches_duplicate_cutoff(self):
        invalid_data = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "branches": [
                {
                    "branch": "Electrical",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 2000,
                                    "closing_percentile": 90.0,
                                    "evidence_id": "EV-03",
                                },
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 2005,
                                    "closing_percentile": 89.9,
                                    "evidence_id": "EV-04",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        fpath = self._create_sample_file(invalid_data)
        res = validate_cutoff_file(fpath)
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("Duplicate cutoff" in e for e in res["errors"]))

    def test_validator_rejects_crawler_stub(self):
        stub_data = {
            "status": "needs_url",
            "institute_code": "01002",
            "branches": [],
        }
        fpath = self._create_sample_file(stub_data)
        res = validate_cutoff_file(fpath)
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("Unextracted scraper stub" in e for e in res["errors"]))

    def test_adapter_transforms_candidate_format(self):
        raw_candidate = {
            "academic_year": "2024-25",
            "institute_code": 1002,  # integer 4 digits
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "course_code": "100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": 1,
                                    "list_type": "CAP",
                                    "closing_rank": "1560",  # string to be cast to int
                                    "closing_percentile": "98.4231",  # string to be cast to float
                                    "source_file": "CAP_2024.pdf",
                                    "page": 10,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        raw_file = self._create_sample_file(raw_candidate, "raw_1002.json")
        adapted = adapt_raw_file(raw_file, canonical_names={"01002": "Government College of Engineering, Amravati"})

        self.assertIsNotNone(adapted)
        self.assertEqual(adapted["institute_code"], "01002")
        self.assertEqual(adapted["academic_year"], "2024-25")
        cutoffs = adapted["branches"][0]["categories"][0]["cutoffs"]
        self.assertEqual(len(cutoffs), 1)
        self.assertEqual(cutoffs[0]["closing_rank"], 1560)
        self.assertAlmostEqual(cutoffs[0]["closing_percentile"], 98.4231, places=4)
        self.assertTrue(cutoffs[0]["evidence_id"].startswith("EV-01002"))

    def test_branch_name_cleaning(self):
        self.assertEqual(clean_branch_name("Chemical Engineering Akola"), "Chemical Engineering")
        self.assertEqual(
            clean_branch_name("Computer Science and Institution(Integrated Campus), Amravati Engineering"),
            "Computer Science and Engineering",
        )
        self.assertEqual(clean_branch_name("Mechanical Engineering, Pusad"), "Mechanical Engineering")
        self.assertEqual(clean_branch_name("Civil Engineering College, Chikhali"), "Civil Engineering")
        self.assertEqual(clean_branch_name("Information Technology"), "Information Technology")

    def test_adapter_normalizes_4digit_evidence_ids(self):
        raw_candidate = {
            "academic_year": "2024-25",
            "institute_code": "1002",
            "institute_name": "Test College",
            "branches": [
                {
                    "course_code": "100224210",
                    "branch": "Computer Science and Institution(Integrated Campus), Amravati Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": 1,
                                    "list_type": "CAP",
                                    "closing_rank": 1000,
                                    "closing_percentile": 99.1,
                                    "evidence_id": "EV-1002-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        raw_file = self._create_sample_file(raw_candidate, "raw_1002_ev.json")
        adapted = adapt_raw_file(raw_file)
        self.assertIsNotNone(adapted)
        self.assertEqual(adapted["institute_code"], "01002")
        self.assertEqual(adapted["branches"][0]["branch"], "Computer Science and Engineering")
        self.assertEqual(adapted["branches"][0]["source_branch_name"], "Computer Science and Institution(Integrated Campus), Amravati Engineering")
        self.assertEqual(adapted["branches"][0]["categories"][0]["cutoffs"][0]["evidence_id"], "EV-01002-COMP-GOPENS-R1")

    def test_validator_allows_distinct_allocation_levels(self):
        data_distinct_levels = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "institute_name": "Test College",
            "branches": [
                {
                    "course_code": "0100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.0,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1-L1",
                                    "level_key": "other_than_home_university_seats_allotted_to_other_than_home",
                                },
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1700,
                                    "closing_percentile": 97.5,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1-L2",
                                    "level_key": "other_than_home_university_seats_allotted_to_home_university",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        fpath = self._create_sample_file(data_distinct_levels, "distinct_levels.json")
        res = validate_cutoff_file(fpath)
        self.assertTrue(res["is_valid"])
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["cutoffs_checked"], 2)

    def test_validator_catches_duplicate_evidence_id(self):
        invalid_data = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "institute_name": "Test College",
            "branches": [
                {
                    "branch": "Computer Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1000,
                                    "closing_percentile": 99.0,
                                    "evidence_id": "EV-DUPLICATE-KEY",
                                }
                            ],
                        }
                    ],
                },
                {
                    "branch": "Information Technology",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 2000,
                                    "closing_percentile": 97.0,
                                    "evidence_id": "EV-DUPLICATE-KEY",  # Duplicate across branches in same college
                                }
                            ],
                        }
                    ],
                },
            ],
        }
        fpath = self._create_sample_file(invalid_data)
        res = validate_cutoff_file(fpath)
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("DUPLICATE_EVIDENCE_ID" in e or "Duplicate evidence_id" in e for e in res["errors"]))

    def test_validator_directory_scan_ignores_auxiliary_and_report_files(self):
        from validate_cutoffs import CutoffValidator
        # Create staging dir with valid year dir and auxiliary files
        staging_dir = self.temp_dir / "staging"
        year_dir = staging_dir / "2024-25"
        year_dir.mkdir(parents=True)

        valid_college = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "branch": "Computer Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.0,
                                    "evidence_id": "EV-01002-COMP-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (year_dir / "01002.json").write_text(json.dumps(valid_college), encoding="utf-8")

        # Create auxiliary files and non-year directories in staging
        (staging_dir / "manifest.json").write_text(json.dumps({"manifest": "data"}), encoding="utf-8")
        (staging_dir / "schema.json").write_text(json.dumps({"schema": "data"}), encoding="utf-8")
        (staging_dir / "adaptation_report.json").write_text(json.dumps({"report": "data"}), encoding="utf-8")
        raw_dir = staging_dir / "raw_extracted"
        raw_dir.mkdir()
        (raw_dir / "raw.json").write_text(json.dumps({"raw": "unadapted"}), encoding="utf-8")

        validator = CutoffValidator()
        report = validator.validate_directory(staging_dir)

        # Must only inspect the 1 file inside 2024-25, ignoring manifest, schema, report, raw_extracted!
        self.assertEqual(report["total_files_inspected"], 1)
        self.assertEqual(report["valid_files"], 1)
        self.assertEqual(report["invalid_files"], 0)
        self.assertEqual(report["counts_by_year"]["2024-25"], 1)

    def test_validator_flags_offline_source_pdf(self):
        data_with_absent_pdf = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "branch": "Computer Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.0,
                                    "evidence_id": "EV-01002-COMP-R1",
                                    "source_file": "NonExistentAllotmentFile_2024.pdf",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        fpath = self._create_sample_file(data_with_absent_pdf)
        res = validate_cutoff_file(fpath)
        # Should be valid (since missing source PDF is an audit warning, not blocking fatal error)
        self.assertTrue(res["is_valid"])
        # Warning must be flagged
        self.assertTrue(any("SOURCE_PDF_UNVERIFIED_OFFLINE" in w or "not found in local workspace" in w for w in res["warnings"]))


class TestAdmissionRulesEngine(unittest.TestCase):
    """Test deterministic CAP admission rules and quota evaluation."""

    def setUp(self):
        self.engine = AdmissionRulesEngine(rule_year="2025-26")

    def test_oms_domicile_gets_all_india_only(self):
        student = StudentProfile(
            domicile="OMS",
            entrance_exam="JEE-Main",
            percentile=94.5,
            caste_category="OPEN",
        )
        res = self.engine.evaluate_student(student)
        self.assertEqual(res.status, "eligible")
        self.assertIn("All India Candidature (OMS)", res.candidature_type)
        self.assertEqual(res.applicable_categories, ["AI"])

    def test_home_university_match_gets_gopenh(self):
        student = StudentProfile(
            domicile="Maharashtra",
            home_university="Amravati",
            percentile=95.0,
            gender="Male",
        )
        res = self.engine.evaluate_student(student, target_college_university="Sant Gadge Baba Amravati University")
        self.assertEqual(res.status, "eligible")
        self.assertIn("GOPENH", res.applicable_categories)
        self.assertIn("GOPENS", res.applicable_categories)
        self.assertNotIn("GOPENO", res.applicable_categories)

    def test_other_university_gets_gopeno(self):
        student = StudentProfile(
            domicile="Maharashtra",
            home_university="Pune",
            percentile=95.0,
            gender="Male",
        )
        res = self.engine.evaluate_student(student, target_college_university="Sant Gadge Baba Amravati University")
        self.assertEqual(res.status, "eligible")
        self.assertIn("GOPENO", res.applicable_categories)
        self.assertIn("GOPENS", res.applicable_categories)
        self.assertNotIn("GOPENH", res.applicable_categories)

    def test_autonomous_or_state_level_gets_gopens(self):
        student = StudentProfile(
            domicile="Maharashtra",
            home_university="Pune",
            percentile=95.0,
            gender="Female",
        )
        res = self.engine.evaluate_student(
            student,
            target_college_university="COEP Technological University",
            is_autonomous_or_state_level=True,
        )
        self.assertEqual(res.status, "eligible")
        self.assertIn("GOPENS", res.applicable_categories)
        self.assertIn("LOPENS", res.applicable_categories)
        self.assertNotIn("GOPENH", res.applicable_categories)
        self.assertNotIn("GOPENO", res.applicable_categories)

    def test_obc_valid_certificates_gets_reserved_quota(self):
        student = StudentProfile(
            domicile="Maharashtra",
            caste_category="OBC",
            has_caste_validity=True,
            has_non_creamy_layer=True,
            percentile=92.0,
            home_university="Amravati",
        )
        res = self.engine.evaluate_student(student, target_college_university="Amravati")
        self.assertEqual(res.status, "eligible")
        self.assertIn("GOBCH", res.applicable_categories)
        self.assertIn("GOBCS", res.applicable_categories)

    def test_obc_missing_validity_falls_back_to_open(self):
        student = StudentProfile(
            domicile="Maharashtra",
            caste_category="OBC",
            has_caste_validity=False,  # Explicitly missing
            has_non_creamy_layer=True,
            percentile=92.0,
            home_university="Amravati",
        )
        res = self.engine.evaluate_student(student, target_college_university="Amravati")
        self.assertEqual(res.status, "eligible")
        self.assertNotIn("GOBCH", res.applicable_categories)
        self.assertIn("GOPENH", res.applicable_categories)
        self.assertTrue(any("Caste Validity Certificate" in exp for exp in res.explanations))

    def test_obc_missing_ncl_falls_back_to_open(self):
        student = StudentProfile(
            domicile="Maharashtra",
            caste_category="OBC",
            has_caste_validity=True,
            has_non_creamy_layer=False,  # Explicitly missing
            percentile=92.0,
            home_university="Amravati",
        )
        res = self.engine.evaluate_student(student, target_college_university="Amravati")
        self.assertEqual(res.status, "eligible")
        self.assertNotIn("GOBCH", res.applicable_categories)
        self.assertIn("GOPENH", res.applicable_categories)
        self.assertTrue(any("Non-Creamy Layer" in exp for exp in res.explanations))

    def test_pending_certificates_needs_verification(self):
        student = StudentProfile(
            domicile="Maharashtra",
            caste_category="OBC",
            has_caste_validity=None,  # Unverified
            has_non_creamy_layer=None,
            percentile=92.0,
            home_university="Amravati",
        )
        res = self.engine.evaluate_student(student, target_college_university="Amravati")
        self.assertEqual(res.status, "needs_verification")
        self.assertIn("has_caste_validity", res.missing_fields)
        self.assertIn("has_non_creamy_layer", res.missing_fields)

    def test_tfws_income_threshold(self):
        # Under 8 LPA
        eligible_tfws = StudentProfile(
            domicile="Maharashtra",
            percentile=98.0,
            tfws_opted=True,
            annual_income=450000.0,
        )
        res_ok = self.engine.evaluate_student(eligible_tfws)
        self.assertIn("TFWS", res_ok.applicable_categories)

        # Over 8 LPA
        ineligible_tfws = StudentProfile(
            domicile="Maharashtra",
            percentile=98.0,
            tfws_opted=True,
            annual_income=900000.0,
        )
        res_no = self.engine.evaluate_student(ineligible_tfws)
        self.assertNotIn("TFWS", res_no.applicable_categories)
        self.assertTrue(any("exceeds Rs. 8,00,000" in exp for exp in res_no.explanations))

    def test_ews_with_certificate(self):
        student = StudentProfile(
            domicile="Maharashtra",
            percentile=96.0,
            caste_category="EWS",
            has_ews_certificate=True,
        )
        res = self.engine.evaluate_student(student)
        self.assertIn("EWS", res.applicable_categories)

    def test_unspecified_home_university_does_not_assume_gopeno(self):
        student = StudentProfile(
            domicile="Maharashtra",
            home_university=None,
            percentile=95.0,
            gender="Male",
        )
        res = self.engine.evaluate_student(
            student,
            target_college_university="Sant Gadge Baba Amravati University",
            is_autonomous_or_state_level=False,
        )
        self.assertEqual(res.status, "needs_verification")
        self.assertIn("home_university", res.missing_fields)
        self.assertNotIn("GOPENO", res.applicable_categories)
        self.assertNotIn("GOPENH", res.applicable_categories)
        self.assertIn("GOPENS", res.applicable_categories)


class TestCutoffAnalyzer(unittest.TestCase):
    """Test deterministic historical cutoff analysis and metric independence."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        # Build 2 years of cutoffs: 2023-24 and 2024-25
        for year in ["2023-24", "2024-25"]:
            ydir = self.temp_dir / year
            ydir.mkdir()
            closing_rank = 1600 if year == "2023-24" else 1500
            closing_perc = 97.5 if year == "2023-24" else 98.1
            college = {
                "academic_year": year,
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
                                        "closing_rank": closing_rank,
                                        "closing_percentile": closing_perc,
                                        "evidence_id": f"EV-01002-COMP-GOPENS-{year}-R1",
                                    },
                                    {
                                        "round": 2,
                                        "stage": "1",
                                        "list_type": "CAP",
                                        "closing_rank": closing_rank + 150,
                                        "closing_percentile": closing_perc - 0.4,
                                        "evidence_id": f"EV-01002-COMP-GOPENS-{year}-R2",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
            (ydir / "01002.json").write_text(json.dumps(college), encoding="utf-8")

        self.agent = CutoffAgent(self.temp_dir)
        self.analyzer = CutoffAnalyzer(self.agent)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_compare_across_years_rank_and_percentile_deltas(self):
        trend = self.analyzer.compare_across_years(
            institute_code="01002",
            branch="Computer Science and Engineering",
            category="GOPENS",
            round_no=1,
        )
        self.assertEqual(trend["status"], "available")
        self.assertTrue(trend["comparable"])
        self.assertEqual(trend["years_tracked"], ["2023-24", "2024-25"])
        # Rank shift: 1500 - 1600 = -100 (supports both readable 'YEAR -> YEAR' and legacy 'YEAR->YEAR')
        self.assertEqual(trend["rank_deltas"]["2023-24 -> 2024-25"], -100)
        self.assertEqual(trend["rank_deltas"]["2023-24->2024-25"], -100)
        # Percentile shift: 98.1 - 97.5 = +0.6
        self.assertAlmostEqual(trend["percentile_deltas"]["2023-24 -> 2024-25"], 0.6, places=4)
        self.assertAlmostEqual(trend["percentile_deltas"]["2023-24->2024-25"], 0.6, places=4)
        self.assertIn("Historical observations describe past CAP rounds only", trend["disclaimer"])

    def test_metric_independence(self):
        trend = self.analyzer.compare_across_years(
            institute_code="01002",
            branch="Computer Science and Engineering",
            category="GOPENS",
            round_no=1,
        )
        # Ranks must be pure integers
        for val in trend["rank_history"].values():
            self.assertIsInstance(val, int)
        # Percentiles must be floats
        for val in trend["percentile_history"].values():
            self.assertIsInstance(val, float)
        # Deltas are kept completely separate
        self.assertIn("rank_deltas", trend)
        self.assertIn("percentile_deltas", trend)

    def test_comparability_guardrail_different_branches(self):
        rec_a = {"institute_code": "01002", "branch": "Computer Engineering", "category": "GOPENS", "list_type": "CAP", "stage": "1"}
        rec_b = {"institute_code": "01002", "branch": "Mechanical Engineering", "category": "GOPENS", "list_type": "CAP", "stage": "1"}
        comp, reason = self.analyzer.check_comparability(rec_a, rec_b)
        self.assertFalse(comp)
        self.assertIn("Branches differ", reason)

    def test_comparability_guardrail_different_categories(self):
        rec_a = {"institute_code": "01002", "branch": "Computer Engineering", "category": "GOPENS", "list_type": "CAP", "stage": "1"}
        rec_b = {"institute_code": "01002", "branch": "Computer Engineering", "category": "TFWS", "list_type": "CAP", "stage": "1"}
        comp, reason = self.analyzer.check_comparability(rec_a, rec_b)
        self.assertFalse(comp)
        self.assertIn("Categories differ", reason)

    def test_compare_rounds_progression(self):
        rounds = self.analyzer.compare_rounds(
            institute_code="01002",
            branch="Computer Science and Engineering",
            category="GOPENS",
            year="2024-25",
        )
        self.assertEqual(rounds["status"], "available")
        self.assertEqual(rounds["rounds_available"], [1, 2])
        self.assertEqual(rounds["round_ranks"][1], 1500)
        self.assertEqual(rounds["round_ranks"][2], 1650)


class TestRecommendationEngineAndPlanner(unittest.TestCase):
    """Test transparent classification tiers and CAP option-form sequencing."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        ydir = self.temp_dir / "2024-25"
        ydir.mkdir()

        # College 1: 01002 - Cutoff: 98.0 percentile / Rank 1500
        c1 = {
            "academic_year": "2024-25",
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
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.0,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "01002.json").write_text(json.dumps(c1), encoding="utf-8")

        # College 2: 06005 - Cutoff: 93.0 percentile / Rank 6000
        c2 = {
            "academic_year": "2024-25",
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
                                    "closing_rank": 6000,
                                    "closing_percentile": 93.0,
                                    "evidence_id": "EV-06005-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "06005.json").write_text(json.dumps(c2), encoding="utf-8")

        self.agent = CutoffAgent(self.temp_dir)
        self.rules = AdmissionRulesEngine()
        self.rec_engine = RecommendationEngine(self.agent, self.rules)
        self.planner = OptionFormPlanner(self.rec_engine)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_categorize_option_tiers(self):
        # High score student (99.0%): 06005 should be attainable, 01002 should be attainable/competitive
        student_high = StudentProfile(domicile="Maharashtra", percentile=99.0, home_university="Amravati")
        eval_attainable = self.rec_engine.categorize_option(
            student_high, institute_code="06005", branch="Computer Science and Engineering"
        )
        self.assertEqual(eval_attainable["tier"], "Historically more attainable")

        # Competitive student (98.2% vs 98.0% cutoff)
        student_mid = StudentProfile(domicile="Maharashtra", percentile=98.2, home_university="Amravati")
        eval_comp = self.rec_engine.categorize_option(
            student_mid, institute_code="01002", branch="Computer Science and Engineering"
        )
        self.assertEqual(eval_comp["tier"], "Competitive")

        # Reach student (94.0% vs 98.0% cutoff)
        student_low = StudentProfile(domicile="Maharashtra", percentile=94.0, home_university="Amravati")
        eval_reach = self.rec_engine.categorize_option(
            student_low, institute_code="01002", branch="Computer Science and Engineering"
        )
        self.assertEqual(eval_reach["tier"], "Reach")

    def test_categorize_option_ineligible(self):
        student_ineligible = StudentProfile(
            domicile="Maharashtra",
            percentile=95.0,
            caste_category="OBC",
            has_caste_validity=False,  # Can't claim OBC, falls back to OPEN, but if we query non-existent quota
        )
        # Student with 0 percentile/rank
        student_noscore = StudentProfile(domicile="Maharashtra", percentile=None, merit_rank=None)
        eval_unres = self.rec_engine.categorize_option(
            student_noscore, institute_code="01002", branch="Computer Science and Engineering"
        )
        self.assertEqual(eval_unres["tier"], "Eligibility Unresolved")

    def test_categorize_option_insufficient_evidence_tier(self):
        student = StudentProfile(domicile="Maharashtra", percentile=95.0, home_university="Amravati")
        # College with no cutoffs in agent
        eval_missing_college = self.rec_engine.categorize_option(
            student, institute_code="99999", branch="Computer Science and Engineering"
        )
        self.assertEqual(eval_missing_college["tier"], "Insufficient evidence")
        self.assertIn("No historical cutoff records available", eval_missing_college["reason"])

        # College with cutoffs, but queried branch not found
        eval_missing_branch = self.rec_engine.categorize_option(
            student, institute_code="01002", branch="NonExistentBranch"
        )
        self.assertEqual(eval_missing_branch["tier"], "Insufficient evidence")
        self.assertIn("No historical cutoffs found", eval_missing_branch["reason"])

    def test_build_option_plan_balanced_ordering(self):
        student = StudentProfile(domicile="Maharashtra", percentile=97.0, home_university="Amravati")
        preferences = [
            {"institute_code": "06005", "branch": "Computer Science and Engineering"},  # Attainable (cutoff 93.0)
            {"institute_code": "01002", "branch": "Computer Science and Engineering"},  # Competitive / Reach (cutoff 98.0)
        ]
        plan = self.planner.build_option_plan(student, preferences, academic_year="2024-25")

        self.assertEqual(plan["total_preferences_submitted"], 2)
        # Strategic order: Reach -> Competitive -> Attainable
        seq = plan["recommended_sequence"]
        self.assertEqual(len(seq), 2)
        # 01002 (Reach/Competitive) placed before 06005 (Attainable)
        self.assertEqual(seq[0]["institute_code"], "01002")
        self.assertEqual(seq[1]["institute_code"], "06005")
        self.assertIn("This advisory option form plan", plan["disclaimer"])

    def test_option_plan_warning_on_no_attainable_options(self):
        student = StudentProfile(domicile="Maharashtra", percentile=94.0, home_university="Amravati")
        # Only ambitious option
        preferences = [
            {"institute_code": "01002", "branch": "Computer Science and Engineering"},
        ]
        plan = self.planner.build_option_plan(student, preferences, academic_year="2024-25")
        self.assertTrue(any("Risk Alert" in w for w in plan["warnings"]))


class TestOrchestratorPhase3Integration(unittest.TestCase):
    """Test Orchestrator routing with Admission Intelligence services."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        ydir = self.temp_dir / "2024-25"
        ydir.mkdir()
        college = {
            "academic_year": "2024-25",
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
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.25,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "01002.json").write_text(json.dumps(college), encoding="utf-8")

        college_safe = {
            "academic_year": "2024-25",
            "institute_code": "06005",
            "institute_name": "Government College of Engineering, Karad",
            "branches": [
                {
                    "course_code": "0600524210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 3500,
                                    "closing_percentile": 93.0,
                                    "evidence_id": "EV-06005-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "06005.json").write_text(json.dumps(college_safe), encoding="utf-8")

        self.cutoff_agent = CutoffAgent(self.temp_dir)
        self.orch = Orchestrator(cutoff_agent=self.cutoff_agent, college_info_agent=None)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cutoff_trend_query_with_cutoff_agent(self):
        res = self.orch.answer(
            "What is the historical trend for Computer Science and Engineering at Government College of Engineering, Amravati?"
        )
        self.assertEqual(res["intent"], "trend")
        self.assertIn("HISTORICAL CUTOFF TREND", res["evidence"])
        self.assertIn("EV-01002-COMP-GOPENS-R1", res["evidence"])

    def test_cutoff_trend_query_without_cutoff_agent_returns_unavailable(self):
        # Create dummy info agent to instantiate Orchestrator without cutoffs
        class DummyInfo:
            def list_name_index(self):
                return {"Government College of Engineering, Amravati": {"institute_code": "01002"}}
            def search(self, *args, **kwargs):
                return []
            def as_evidence_text(self, *args, **kwargs):
                return ""

        orch_no_cutoffs = Orchestrator(cutoff_agent=None, college_info_agent=DummyInfo())
        res = orch_no_cutoffs.answer(
            "What is the cutoff trend for Government College of Engineering, Amravati?"
        )
        self.assertEqual(res["status"], "unavailable")
        self.assertEqual(res["message"], CUTOFF_UNAVAILABLE)

    def test_evaluate_student_method(self):
        student = StudentProfile(domicile="Maharashtra", percentile=95.0, caste_category="OPEN", home_university="Amravati")
        elig = self.orch.evaluate_student(student, college_university="Sant Gadge Baba Amravati University")
        self.assertIsInstance(elig, EligibilityResult)
        self.assertEqual(elig.status, "eligible")
        self.assertIn("GOPENH", elig.applicable_categories)

    def test_compare_colleges_method(self):
        comp = self.orch.compare_colleges(
            institute_queries=["01002"],
            branch="Computer Science and Engineering",
            category="GOPENS",
            academic_year="2024-25",
        )
        self.assertEqual(comp["academic_year"], "2024-25")
        self.assertEqual(len(comp["comparison"]), 1)
        self.assertEqual(comp["comparison"][0]["closing_rank"], 1500)

    def test_plan_options_method(self):
        student = StudentProfile(domicile="Maharashtra", percentile=98.5, home_university="Amravati")
        prefs = [
            {"institute_code": "01002", "branch": "Computer Science and Engineering"},
            {"institute_code": "06005", "branch": "Computer Science and Engineering"},
        ]
        plan = self.orch.plan_options(student, prefs, academic_year="2024-25")
        self.assertEqual(plan["total_preferences_submitted"], 2)
        self.assertEqual(plan["tier_counts"]["competitive"], 1)
        self.assertEqual(plan["tier_counts"]["attainable"], 1)

    def test_backward_compatible_info_query_returns_evidence_only(self):
        class DummyInfoAgent:
            def list_name_index(self):
                return {
                    "Government College of Engineering, Amravati": {
                        "institute_code": "01002",
                        "record_id": "MHHEI_00001",
                    }
                }

            def search(self, question, institute_code=None, record_id=None):
                return [
                    {
                        "chunk_id": "MHHEI_00001:MHHEI_00001_profile",
                        "text": "Established in 1964, affiliated to Sant Gadge Baba Amravati University.",
                    }
                ]

            def as_evidence_text(self, results):
                return "[MHHEI_00001:MHHEI_00001_profile]\nEstablished in 1964, affiliated to Sant Gadge Baba Amravati University."

        orch = Orchestrator(
            cutoff_agent=self.cutoff_agent,
            college_info_agent=DummyInfoAgent(),
            llm_call=None,
        )
        res = orch.answer("What is the history and affiliation of Government College of Engineering, Amravati?")
        self.assertEqual(res["status"], "evidence_only")
        self.assertEqual(res["intent"], "info")
        self.assertIn("Established in 1964", res["evidence"])
        self.assertIn("[MHHEI_00001:MHHEI_00001_profile]", res["evidence"])
        self.assertNotIn("answer", res)


class TestPhase3HistoricalReconciliationAndAudit(unittest.TestCase):
    """Verifies historical PDF inventory, special category patterns, and multi-year reconciliation."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_category_token_pattern_recognizes_special_reservations(self):
        """DEFOPENS, PWDOPENS, DEFROBCS, etc. must match without warning."""
        valid_special_tokens = [
            "DEFOPENS",
            "PWDOPENS",
            "DEFROBCS",
            "DEF1OPENS",
            "DEF2OPENH",
            "DEF3OPENO",
            "PWDRSCS",
            "PWDROBCS",
            "PWDRSTH",
            "GOPENH",
            "GOPENO",
            "GOPENS",
            "LOPENH",
            "LOPENO",
            "LOPENS",
            "GSCS",
            "GSTS",
            "GOBCS",
            "LOBCS",
            "TFWS",
            "EWS",
            "ORPHAN",
            "AI",
        ]
        for tok in valid_special_tokens:
            self.assertIsNotNone(
                KNOWN_CATEGORY_PATTERN.match(tok),
                f"Valid MHT-CET quota category token '{tok}' failed to match KNOWN_CATEGORY_PATTERN",
            )

    def test_category_token_pattern_rejects_arbitrary_tokens(self):
        """Arbitrary invalid strings must not match."""
        invalid_tokens = ["UNKNOWN_XYZ", "ABC_12345", "INVALID_TOKEN", "RANDOM999"]
        for tok in invalid_tokens:
            self.assertIsNone(
                KNOWN_CATEGORY_PATTERN.match(tok),
                f"Invalid token '{tok}' unexpectedly matched KNOWN_CATEGORY_PATTERN",
            )

    def test_historical_pdf_inventory_mapping(self):
        """Verifies explicit mapping and disposition for all seven historical PDFs."""
        inventory_file = Path("cutoffs/reports/historical_pdf_inventory.json")
        if inventory_file.is_file():
            data = json.loads(inventory_file.read_text(encoding="utf-8"))
            pdfs = {p["filename"]: p for p in data.get("pdfs", [])}
            self.assertEqual(len(pdfs), 7)
            # Confirm 2020 complementary rounds
            self.assertEqual(pdfs["round-1-mht-cet-2020-mh.pdf"]["academic_year"], "2020-21")
            self.assertEqual(pdfs["round-1-mht-cet-2020-mh.pdf"]["cap_round"], 1)
            self.assertEqual(pdfs["2020ENGG_CAP2_CutOff.pdf"]["academic_year"], "2020-21")
            self.assertEqual(pdfs["2020ENGG_CAP2_CutOff.pdf"]["cap_round"], 2)
            # Confirm 2021 rounds
            self.assertEqual(pdfs["2021ENGG_CAP1_CutOff.pdf"]["academic_year"], "2021-22")
            self.assertEqual(pdfs["2021ENGG_CAP1_CutOff.pdf"]["cap_round"], 1)
            self.assertEqual(pdfs["2021ENGG_CAP2_CutOff.pdf"]["academic_year"], "2021-22")
            self.assertEqual(pdfs["2021ENGG_CAP2_CutOff.pdf"]["cap_round"], 2)
            # Confirm 2022 rounds
            self.assertEqual(pdfs["2022ENGG_CAP1_CutOff.pdf"]["academic_year"], "2022-23")
            self.assertEqual(pdfs["2022ENGG_CAP1_CutOff.pdf"]["cap_round"], 1)
            self.assertEqual(pdfs["2022ENGG_CAP2_CutOff.pdf"]["academic_year"], "2022-23")
            self.assertEqual(pdfs["2022ENGG_CAP2_CutOff.pdf"]["cap_round"], 2)
            self.assertEqual(pdfs["2022ENGG_CAP3_CutOff.pdf"]["academic_year"], "2022-23")
            self.assertEqual(pdfs["2022ENGG_CAP3_CutOff.pdf"]["cap_round"], 3)

    def test_validator_pdf_offline_verification(self):
        """Validator marks present local PDFs as verified and absent ones as unverified."""
        pdf_dir = self.temp_dir / "test_pdfs"
        pdf_dir.mkdir()
        present_pdf = "2021ENGG_CAP1_CutOff.pdf"
        (pdf_dir / present_pdf).write_text("Dummy PDF content", encoding="utf-8")

        college_data = {
            "academic_year": "2021-22",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "course_code": "0100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.5,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                                    "source_file": present_pdf,
                                    "page": 12,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        json_file = self.temp_dir / "01002.json"
        json_file.write_text(json.dumps(college_data), encoding="utf-8")

        # 1. Validation with pdf_dir where PDF exists -> No SOURCE_PDF_UNVERIFIED_OFFLINE
        res_present = validate_cutoff_file(json_file, pdf_dir=pdf_dir)
        self.assertTrue(res_present["is_valid"])
        self.assertFalse(any("SOURCE_PDF_UNVERIFIED_OFFLINE" in str(f) for f in res_present["findings"]))

        # 2. Validation pointing to empty dir -> Flags SOURCE_PDF_UNVERIFIED_OFFLINE
        empty_dir = self.temp_dir / "empty_dir"
        empty_dir.mkdir()
        college_data["branches"][0]["categories"][0]["cutoffs"][0]["source_file"] = "missing_doc.pdf"
        json_file.write_text(json.dumps(college_data), encoding="utf-8")
        res_missing = validate_cutoff_file(json_file, pdf_dir=empty_dir)
        self.assertTrue(res_missing["is_valid"])  # Non-blocking warning
        self.assertTrue(any("SOURCE_PDF_UNVERIFIED_OFFLINE" in str(f) for f in res_missing["findings"]))

    def test_reconciler_exact_duplicate_collapse(self):
        """Reconciler collapses identical cutoffs and preserves corroborating source files."""
        base = {
            "academic_year": "2022-23",
            "institute_code": "01002",
            "branches": [
                {
                    "course_code": "0100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "level_key": "state_level",
                                    "closing_rank": 1400,
                                    "closing_percentile": 98.7,
                                    "source_file": "Source_A.pdf",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        duplicate = {
            "academic_year": "2022-23",
            "institute_code": "01002",
            "branches": [
                {
                    "course_code": "0100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "level_key": "state_level",
                                    "closing_rank": 1400,
                                    "closing_percentile": 98.7,
                                    "source_file": "Source_B.pdf",  # Corroborating source
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        reconciler = CutoffReconciler(out_dir=self.temp_dir / "out", reports_dir=self.temp_dir / "reports")
        merged = reconciler.reconcile_college_records(base, duplicate)
        self.assertEqual(reconciler.exact_duplicates_collapsed, 1)
        cutoffs = merged["branches"][0]["categories"][0]["cutoffs"]
        self.assertEqual(len(cutoffs), 1)
        self.assertIn("Source_B.pdf", cutoffs[0].get("corroborating_sources", []))

    def test_reconciler_conflict_detection(self):
        """Reconciler detects differing cutoffs on identical dimension key."""
        base = {
            "academic_year": "2022-23",
            "institute_code": "01002",
            "branches": [
                {
                    "course_code": "0100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "level_key": "state_level",
                                    "closing_rank": 1400,
                                    "closing_percentile": 98.7,
                                    "source_file": "Source_A.pdf",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        conflicting = {
            "academic_year": "2022-23",
            "institute_code": "01002",
            "branches": [
                {
                    "course_code": "0100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "level_key": "state_level",
                                    "closing_rank": 1550,  # Conflicting closing rank
                                    "closing_percentile": 98.1,
                                    "source_file": "Source_C.pdf",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        reconciler = CutoffReconciler(out_dir=self.temp_dir / "out", reports_dir=self.temp_dir / "reports")
        reconciler.reconcile_college_records(base, conflicting)
        self.assertEqual(len(reconciler.conflicts), 1)
        c = reconciler.conflicts[0]
        self.assertEqual(c["category"], "GOPENS")
        self.assertEqual(c["existing_cutoff"]["rank"], 1400)
        self.assertEqual(c["incoming_cutoff"]["rank"], 1550)

    def test_multi_year_historical_trend_analysis(self):
        """CutoffAnalyzer calculates independent multi-year metric shifts across continuous years."""
        staging_dir = self.temp_dir / "cutoffs"
        years_ranks = {
            "2020-21": (1200, 98.9),
            "2021-22": (1300, 98.8),
            "2022-23": (1400, 98.6),
            "2023-24": (1450, 98.5),
            "2024-25": (1500, 98.4),
            "2025-26": (1550, 98.2),
        }
        for ay, (rank, perc) in years_ranks.items():
            ydir = staging_dir / ay
            ydir.mkdir(parents=True)
            college = {
                "academic_year": ay,
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
                                        "closing_rank": rank,
                                        "closing_percentile": perc,
                                        "evidence_id": f"EV-01002-{ay}-R1",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
            (ydir / "01002.json").write_text(json.dumps(college), encoding="utf-8")

        agent = CutoffAgent(staging_dir)
        analyzer = CutoffAnalyzer(agent)
        trend = analyzer.compare_across_years(
            "01002",
            branch="Computer Science and Engineering",
            category="GOPENS",
            round_no=1,
        )
        self.assertEqual(trend["status"], "available")
        self.assertEqual(len(trend["years_tracked"]), 6)
        self.assertEqual(trend["rank_history"]["2020-21"], 1200)
        self.assertEqual(trend["rank_history"]["2024-25"], 1500)
        self.assertEqual(trend["rank_history"]["2025-26"], 1550)

        # Metric independence: verify all rank deltas are ints and percentile deltas are floats
        for k, v in trend["rank_deltas"].items():
            self.assertIsInstance(v, int, f"Rank delta for {k} must be an integer")
        for k, v in trend["percentile_deltas"].items():
            self.assertIsInstance(v, float, f"Percentile delta for {k} must be a float")

        # 6 continuous years yield exactly 5 adjacent pairs
        self.assertEqual(len(trend["rank_deltas"]), 5)
        self.assertEqual(len(trend["percentile_deltas"]), 5)

        # Initial pair: 2020-21 -> 2021-22
        self.assertIn("2020-21 -> 2021-22", trend["rank_deltas"])
        self.assertEqual(trend["rank_deltas"]["2020-21 -> 2021-22"], 100)
        self.assertAlmostEqual(trend["percentile_deltas"]["2020-21 -> 2021-22"], -0.1, places=3)

        # Final adjacent pair: 2024-25 -> 2025-26
        self.assertIn("2024-25 -> 2025-26", trend["rank_deltas"])
        self.assertEqual(trend["rank_deltas"]["2024-25 -> 2025-26"], 50)
        self.assertAlmostEqual(trend["percentile_deltas"]["2024-25 -> 2025-26"], -0.2, places=3)


class TestLiveSmokeDefectFixes(unittest.TestCase):
    """Targeted regression tests for Phase 3 smoke defect fixes."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_year_trend_with_mixed_cap_and_maharashtra_minority(self):
        """Verify 6-year trend comparison succeeds when historical uses 'CAP' and recent uses 'maharashtra_minority'."""
        staging = self.temp_dir / "staging"
        staging.mkdir()

        years_data = {
            "2020-21": (1200, 99.0, "CAP"),
            "2021-22": (1300, 98.9, "CAP"),
            "2022-23": (1400, 98.6, "CAP"),
            "2023-24": (1450, 98.5, "maharashtra_minority"),
            "2024-25": (1500, 98.4, "maharashtra_minority"),
            "2025-26": (1550, 98.2, "maharashtra_minority"),
        }
        for ay, (rank, perc, ltype) in years_data.items():
            ydir = staging / ay
            ydir.mkdir(parents=True)
            college = {
                "academic_year": ay,
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
                                        "list_type": ltype,
                                        "closing_rank": rank,
                                        "closing_percentile": perc,
                                        "evidence_id": f"EV-01002-{ay}-R1",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
            (ydir / "01002.json").write_text(json.dumps(college), encoding="utf-8")

        agent = CutoffAgent(staging)
        analyzer = CutoffAnalyzer(agent)
        trend = analyzer.compare_across_years(
            "01002",
            branch="Computer Science and Engineering",
            category="GOPENS",
            round_no=1,
            list_type="CAP",
        )
        self.assertEqual(trend["status"], "available")
        self.assertEqual(len(trend["years_tracked"]), 6)
        self.assertEqual(trend["years_tracked"], ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"])
        self.assertEqual(len(trend["rank_deltas"]), 5)
        self.assertEqual(len(trend["percentile_deltas"]), 5)
        # Check transition between 2022-23 (CAP) and 2023-24 (maharashtra_minority)
        self.assertEqual(trend["rank_deltas"]["2022-23 -> 2023-24"], 50)
        self.assertAlmostEqual(trend["percentile_deltas"]["2022-23 -> 2023-24"], -0.1, places=3)

    def test_comparability_guardrail_cap_vs_all_india(self):
        """Verify State CAP and All India quotas cannot be compared."""
        # 1. Isolate list-type guardrail: identical category ("AI"), branch, code, stage
        rec_cap = {
            "institute_code": "01002",
            "branch": "Computer Science and Engineering",
            "category": "AI",
            "list_type": "CAP",
            "stage": "1",
        }
        rec_ai = {
            "institute_code": "01002",
            "branch": "Computer Science and Engineering",
            "category": "AI",
            "list_type": "All India",
            "stage": "1",
        }
        comp, reason = CutoffAnalyzer.check_comparability(rec_cap, rec_ai)
        self.assertFalse(comp)
        self.assertIn("List types differ", reason)

        # 2. Verify State CAP variants (CAP vs maharashtra_minority) ARE canonical and comparable
        rec_cap_minority = {
            "institute_code": "01002",
            "branch": "Computer Science and Engineering",
            "category": "AI",
            "list_type": "maharashtra_minority",
            "stage": "1",
        }
        comp_cap, reason_cap = CutoffAnalyzer.check_comparability(rec_cap, rec_cap_minority)
        self.assertTrue(comp_cap)
        self.assertIsNone(reason_cap)

        # 3. Preserve separate rule that differing categories cannot be compared
        rec_gopens = {
            "institute_code": "01002",
            "branch": "Computer Science and Engineering",
            "category": "GOPENS",
            "list_type": "CAP",
            "stage": "1",
        }
        comp_diff_cat, reason_diff_cat = CutoffAnalyzer.check_comparability(rec_gopens, rec_ai)
        self.assertFalse(comp_diff_cat)
        self.assertIn("Categories differ", reason_diff_cat)

    def test_nonexistent_branch_query_returns_unavailable_without_leaking_evidence(self):
        """Verify querying a nonexistent branch returns status: unavailable without leaking other branches."""
        staging = self.temp_dir / "staging_branch"
        staging.mkdir()
        ydir = staging / "2024-25"
        ydir.mkdir()
        college = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
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
                                    "closing_rank": 8000,
                                    "closing_percentile": 88.5,
                                    "evidence_id": "EV-01002-CIVIL-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                },
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
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.25,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                },
            ],
        }
        (ydir / "01002.json").write_text(json.dumps(college), encoding="utf-8")

        agent = CutoffAgent(staging)
        orch = Orchestrator(cutoff_agent=agent, college_info_agent=None)

        # Query nonexistent Aerospace Engineering
        res = orch.answer(
            "What is the cutoff for Aerospace Engineering at Government College of Engineering, Amravati?"
        )
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("not offered", res["message"])
        # Ensure Civil Engineering and Computer Science are NOT leaked
        self.assertNotIn("Civil Engineering", res["evidence"])
        self.assertNotIn("EV-01002-CIVIL-GOPENS-R1", res["evidence"])

    def test_nonexistent_branch_trend_query_returns_unavailable(self):
        """Verify historical trend query for nonexistent branch does not fallback to an unrelated branch."""
        staging = self.temp_dir / "staging_trend"
        staging.mkdir()
        ydir = staging / "2024-25"
        ydir.mkdir()
        college = {
            "academic_year": "2024-25",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
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
                                    "closing_rank": 8000,
                                    "closing_percentile": 88.5,
                                    "evidence_id": "EV-01002-CIVIL-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "01002.json").write_text(json.dumps(college), encoding="utf-8")

        agent = CutoffAgent(staging)
        orch = Orchestrator(cutoff_agent=agent, college_info_agent=None)

        res = orch.answer(
            "What is the historical trend for Aerospace Engineering at Government College of Engineering, Amravati?"
        )
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("not offered", res["message"])
        self.assertNotIn("Civil Engineering", res["evidence"])

    def test_evidence_id_normalization_and_provenance(self):
        """Verify evidence ID normalization to 5-digit code while preserving source_evidence_id."""
        adapter = CutoffAdapter()
        raw_file = self.temp_dir / "raw_1002.json"
        raw_data = {
            "institute_code": "1002",
            "academic_year": "2020-21",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "branch": "Computer Science and Engineering",
                    "course_code": "100224210",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "maharashtra_minority",
                                    "closing_rank": 1200,
                                    "closing_percentile": 99.0,
                                    "evidence_id": "2020-21:1002:100224210:na:GOPENS:R1:S1",
                                },
                                {
                                    "round": 2,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 1350,
                                    "closing_percentile": 98.7,
                                    "evidence_id": "EV-1002-COMP-GOPENS-R2",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        raw_file.write_text(json.dumps(raw_data), encoding="utf-8")

        adapted, warnings = adapter.adapt_file(raw_file)
        self.assertIsNotNone(adapted)
        self.assertEqual(adapted["institute_code"], "01002")

        c1 = adapted["branches"][0]["categories"][0]["cutoffs"][0]
        # Colon format normalized to 5-digit code and 10-digit course code
        self.assertEqual(c1["evidence_id"], "2020-21:01002:0100224210:na:GOPENS:R1:S1")
        self.assertEqual(c1["source_evidence_id"], "2020-21:1002:100224210:na:GOPENS:R1:S1")
        self.assertEqual(c1["list_type"], "CAP")
        self.assertEqual(c1["source_list_type"], "maharashtra_minority")

        c2 = adapted["branches"][0]["categories"][0]["cutoffs"][1]
        # EV format normalized to 5-digit code
        self.assertEqual(c2["evidence_id"], "EV-01002-COMP-GOPENS-R2")
        self.assertEqual(c2["source_evidence_id"], "EV-1002-COMP-GOPENS-R2")

    def test_hallucinated_profile_citation_stripped_from_cutoff_answer(self):
        """Verify that fabricated college profile citations are stripped from cutoff answers."""
        staging = self.temp_dir / "staging_halluc"
        staging.mkdir()
        ydir = staging / "2024-25"
        ydir.mkdir()
        college = {
            "academic_year": "2024-25",
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
                                    "closing_rank": 1500,
                                    "closing_percentile": 98.25,
                                    "evidence_id": "EV-01002-COMP-GOPENS-R1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "01002.json").write_text(json.dumps(college), encoding="utf-8")

        agent = CutoffAgent(staging)

        # Mock LLM that hallucinates an MHHEI citation on cutoff facts
        def mock_hallucinating_llm(sys_prompt, user_prompt):
            return "The closing rank was 1500 [MHHEI_00001:MHHEI_00001_profile] and closing percentile was 98.25 [EV-01002-COMP-GOPENS-R1]."

        orch = Orchestrator(cutoff_agent=agent, college_info_agent=None, llm_call=mock_hallucinating_llm)
        res = orch.answer("What is the cutoff for Computer Science and Engineering at Government College of Engineering, Amravati?")

        self.assertEqual(res["status"], "answered")
        self.assertNotIn("MHHEI_00001", res["answer"])
        self.assertIn("[EV-01002-COMP-GOPENS-R1]", res["answer"])

    def test_cutoff_agent_canonicalizes_evidence_id_on_the_fly(self):
        """Verify that CutoffAgent normalizes legacy 4-digit colon/EV IDs on the fly with source provenance."""
        staging = self.temp_dir / "staging_legacy_ev"
        staging.mkdir()
        ydir = staging / "2020-21"
        ydir.mkdir()
        legacy_data = {
            "academic_year": "2020-21",
            "institute_code": "1002",
            "institute_name": "Government College of Engineering, Amravati",
            "branches": [
                {
                    "course_code": "100224210",
                    "branch": "Computer Science and Engineering",
                    "categories": [
                        {
                            "category": "GOPENS",
                            "cutoffs": [
                                {
                                    "round": 1,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 2000,
                                    "closing_percentile": 97.5,
                                    "evidence_id": "2020-21:1002:100224210:state_level:GOPENS:R1:S1",
                                },
                                {
                                    "round": 2,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 2500,
                                    "closing_percentile": 96.5,
                                    "evidence_id": "EV-1002-COMP-GOPENS-R2",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "1002.json").write_text(json.dumps(legacy_data), encoding="utf-8")

        agent = CutoffAgent(staging)
        records = agent.get_cutoffs("01002", year="2020-21")
        self.assertEqual(len(records), 2)
        # Check canonicalization of colon format
        self.assertEqual(records[0]["evidence_id"], "2020-21:01002:0100224210:state_level:GOPENS:R1:S1")
        self.assertEqual(records[0]["source_evidence_id"], "2020-21:1002:100224210:state_level:GOPENS:R1:S1")
        self.assertEqual(records[0]["institute_code"], "01002")

        # Check canonicalization of EV format
        self.assertEqual(records[1]["evidence_id"], "EV-01002-COMP-GOPENS-R2")
        self.assertEqual(records[1]["source_evidence_id"], "EV-1002-COMP-GOPENS-R2")

    def test_orchestrator_requested_branch_parser(self):
        """Verify _requested_branch_in_query correctly extracts clean disciplines and strips query grammar/articles."""
        orch = Orchestrator(cutoff_agent=None, college_info_agent=None)

        q1 = "What was the Aerospace Engineering cutoff at Government College of Engineering, Amravati in 2024-25?"
        self.assertEqual(orch._requested_branch_in_query(q1), "Aerospace Engineering")

        q2 = "What was the cutoff for the Aerospace Engineering branch at Government College of Engineering, Amravati in 2024-25?"
        self.assertEqual(orch._requested_branch_in_query(q2), "Aerospace Engineering")

        q3 = "What is the cutoff for the Aerospace Engineering at Government College of Engineering, Amravati?"
        self.assertEqual(orch._requested_branch_in_query(q3), "Aerospace Engineering")

        q4 = "What was the Computer Science and Engineering cutoff at Government College of Engineering, Amravati in 2024-25?"
        self.assertEqual(orch._requested_branch_in_query(q4), "Computer Science and Engineering")

        q5 = "Tell me about Government College of Engineering, Amravati"
        self.assertIsNone(orch._requested_branch_in_query(q5))


if __name__ == "__main__":
    unittest.main()
