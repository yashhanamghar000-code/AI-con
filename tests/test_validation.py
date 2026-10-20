#!/usr/bin/env python3
"""Unit tests for Dataset Validation Module (Phase 1)."""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_dataset import (
    ValidationSummary,
    format_validation_report,
    validate_dataset,
)


class TestDatasetValidation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_record(self, record_id, name, code=None, website=None, affiliation=None):
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
        }
        if code:
            rec["institute_code"] = code
        if website:
            rec["official_website"] = website
        if affiliation:
            rec["extracted"]["identity"]["affiliation"] = {
                "value": affiliation,
                "source": "CET Cell",
            }
        p = self.tmp_dir / f"{record_id}.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
        return p

    def test_clean_records_pass_validation(self):
        self._create_record("MHHEI_00001", "College One", code="01001", website="https://c1.edu")
        self._create_record("MHHEI_00002", "College Two", code="01002", website="https://c2.edu")

        summary = validate_dataset(self.tmp_dir)
        self.assertEqual(summary.college_records_count, 2)
        self.assertEqual(summary.valid_json_count, 2)
        self.assertEqual(summary.invalid_json_count, 0)
        self.assertEqual(summary.unique_record_ids, 2)
        self.assertEqual(len(summary.duplicate_record_ids), 0)
        self.assertEqual(summary.records_with_institute_code, 2)
        self.assertEqual(summary.records_without_institute_code, 0)
        self.assertEqual(len(summary.errors), 0)

    def test_invalid_json_detected(self):
        self._create_record("MHHEI_00001", "College One", code="01001")
        bad_file = self.tmp_dir / "MHHEI_00002.json"
        bad_file.write_text("{this is not valid json:", encoding="utf-8")

        summary = validate_dataset(self.tmp_dir)
        self.assertEqual(summary.invalid_json_count, 1)
        self.assertEqual(summary.valid_json_count, 1)
        self.assertTrue(any("Invalid JSON" in err for err in summary.errors))

    def test_duplicate_record_id_detected(self):
        self._create_record("MHHEI_00001", "College One", code="01001")
        # Write another file with the same record_id
        dupe_file = self.tmp_dir / "duplicate_record.json"
        dupe_file.write_text(json.dumps({
            "schema_version": "4.0",
            "record_id": "MHHEI_00001",
            "institute_name": "College Dupe",
        }), encoding="utf-8")

        summary = validate_dataset(self.tmp_dir)
        self.assertEqual(len(summary.duplicate_record_ids), 1)
        self.assertTrue(any("Duplicate record_id" in err for err in summary.errors))

    def test_missing_institute_name_detected(self):
        rec_file = self.tmp_dir / "MHHEI_00001.json"
        rec_file.write_text(json.dumps({
            "schema_version": "4.0",
            "record_id": "MHHEI_00001",
            "institute_name": "",
        }), encoding="utf-8")

        summary = validate_dataset(self.tmp_dir)
        self.assertEqual(len(summary.missing_institute_names), 1)
        self.assertTrue(any("empty institute_name" in err for err in summary.errors))

    def test_manifest_and_csv_consistency_check(self):
        self._create_record("MHHEI_00001", "College One", code="01001")

        # Manifest expecting 2 records, but only 1 present
        manifest_path = self.tmp_dir / "dataset_manifest.json"
        manifest_path.write_text(json.dumps({
            "dataset_version": "4.0_sparse_verified_fields",
            "json_records_written": 2,
            "record_ids_unique": True,
        }), encoding="utf-8")

        # CSV with 1 row matching
        csv_path = self.tmp_dir / "college_dataset_index.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["record_id", "institute_code", "institute_name", "official_website_present", "source_count", "retained_extracted_sections", "json_file"])
            writer.writerow(["MHHEI_00001", "01001", "College One", "False", "0", "identity", "MHHEI_00001.json"])

        summary = validate_dataset(self.tmp_dir, csv_index_path=csv_path, manifest_path=manifest_path)
        self.assertTrue(summary.manifest_checked)
        self.assertFalse(summary.manifest_matches)  # expected 2, got 1
        self.assertTrue(summary.csv_index_checked)
        # CSV has 1 row and 1 record, so CSV matches
        self.assertTrue(summary.csv_index_matches)

        report = format_validation_report(summary)
        self.assertIn("AI-CON DATASET VALIDATION REPORT", report)


if __name__ == "__main__":
    unittest.main()
