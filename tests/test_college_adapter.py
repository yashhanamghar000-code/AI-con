#!/usr/bin/env python3
"""Unit tests for Reusable College Data Adapter (Phase 1)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from college_adapter import (
    CollegeRecord,
    adapt_college_record,
    extract_source_attribution,
    factual_value,
    is_college_record,
    sanitize_chroma_metadata,
)


class TestFactualValue(unittest.TestCase):
    def test_extract_from_nested_dict(self):
        obj = {
            "value": "Government College of Engineering, Amravati",
            "source": "Maharashtra State CET Cell",
            "confidence": "provided_master_list",
        }
        self.assertEqual(factual_value(obj), "Government College of Engineering, Amravati")

    def test_confidence_only_object_yields_none(self):
        obj = {
            "confidence": "provided_master_list",
            "source": "Maharashtra State CET Cell",
        }
        self.assertIsNone(factual_value(obj))

    def test_conflict_object_yields_none(self):
        obj = {
            "conflict": [
                {"value": "1960", "source": "official"},
                {"value": "2008", "source": "forum"},
            ]
        }
        self.assertIsNone(factual_value(obj))

    def test_scalar_types(self):
        self.assertEqual(factual_value("  Amravati  "), "Amravati")
        self.assertEqual(factual_value(""), None)
        self.assertEqual(factual_value(1002), 1002)
        self.assertEqual(factual_value(98.5), 98.5)
        self.assertEqual(factual_value(True), True)
        self.assertEqual(factual_value(False), False)
        self.assertIsNone(factual_value(None))


class TestMetadataSanitization(unittest.TestCase):
    def test_none_and_empty_values_omitted(self):
        meta = {
            "record_id": "MHHEI_00001",
            "institute_code": None,
            "district": "",
            "state": "Maharashtra",
            "count": 5,
            "score": 0.95,
            "active": True,
        }
        sanitized = sanitize_chroma_metadata(meta)
        self.assertIn("record_id", sanitized)
        self.assertNotIn("institute_code", sanitized)
        self.assertNotIn("district", sanitized)
        self.assertEqual(sanitized["state"], "Maharashtra")
        self.assertEqual(sanitized["count"], 5)
        self.assertEqual(sanitized["score"], 0.95)
        self.assertEqual(sanitized["active"], True)
        for k, v in sanitized.items():
            self.assertIsInstance(v, (str, int, float, bool))


class TestCollegeRecordAdapter(unittest.TestCase):
    def test_manifest_is_not_college_record(self):
        manifest = {
            "dataset_version": "4.0_sparse_verified_fields",
            "json_records_written": 1041,
        }
        self.assertFalse(is_college_record(manifest))
        self.assertIsNone(adapt_college_record(manifest))

    def test_v4_sparse_record_with_all_identity_fields(self):
        raw = {
            "schema_version": "4.0",
            "record_id": "MHHEI_00001",
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "official_website": "https://www.gcoea.ac.in/",
            "institution_type": "Government Autonomous",
            "extracted": {
                "identity": {
                    "verification_status": {
                        "value": "verified_government",
                        "source": "Maharashtra State CET Cell",
                    },
                    "district": {
                        "confidence": "provided_master_list",
                        "source": "Maharashtra State CET Cell",
                    },
                    "state": {
                        "value": "Maharashtra",
                        "source": "scope of supplied college dataset",
                    },
                    "affiliation": {
                        "value": "Sant Gadge Baba Amravati University",
                        "source": "Maharashtra State CET Cell",
                    },
                    "ownership": {
                        "value": "Government Autonomous",
                        "source": "Maharashtra State CET Cell",
                    },
                },
                "location": {
                    "state": "Maharashtra",
                },
            },
            "sources_consulted": ["https://www.gcoea.ac.in/"],
        }
        record = adapt_college_record(raw)
        self.assertIsNotNone(record)
        self.assertEqual(record.record_id, "MHHEI_00001")
        self.assertEqual(record.institute_code, "01002")
        self.assertEqual(record.institute_name, "Government College of Engineering, Amravati")
        self.assertEqual(record.affiliation, "Sant Gadge Baba Amravati University")
        self.assertEqual(record.state, "Maharashtra")
        # District had only confidence rating - must be None
        self.assertIsNone(record.district)
        self.assertIsNone(record.city)
        self.assertEqual(record.stable_id, "MHHEI_00001")

        # Profile text must omit missing fields
        profile_text = record.get_profile_text()
        self.assertIn("College: Government College of Engineering, Amravati", profile_text)
        self.assertIn("affiliation: Sant Gadge Baba Amravati University", profile_text)
        self.assertNotIn("district:", profile_text)
        self.assertNotIn("provided_master_list", profile_text)

    def test_record_without_institute_code(self):
        raw = {
            "schema_version": "4.0",
            "record_id": "MHHEI_00552",
            "institute_name": "KDM College of Arts",
            "institution_type": "Affiliated higher-education institution",
            "extracted": {
                "identity": {
                    "state": {"value": "Maharashtra"},
                    "affiliation": {"confidence": "provided_master_list"},
                }
            },
        }
        record = adapt_college_record(raw)
        self.assertIsNotNone(record)
        self.assertIsNone(record.institute_code)
        self.assertEqual(record.stable_id, "MHHEI_00552")
        self.assertIsNone(record.affiliation)
        self.assertEqual(record.state, "Maharashtra")

        meta = record.get_chroma_metadata()
        self.assertNotIn("institute_code", meta)
        self.assertEqual(meta["record_id"], "MHHEI_00552")


if __name__ == "__main__":
    unittest.main()
