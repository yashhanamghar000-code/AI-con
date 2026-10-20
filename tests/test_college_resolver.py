#!/usr/bin/env python3
"""Unit tests for College Name & Code Resolver (Phase 1)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS / "agents"))

from college_resolver import (
    CollegeResolution,
    CollegeResolver,
    extract_significant_tokens,
    normalize_text,
)


class TestTextNormalization(unittest.TestCase):
    def test_strip_punctuation_and_trailing_commas(self):
        self.assertEqual(
            normalize_text("P. R. Pote (Patil) Education & Welfare Trust's Group of,"),
            "p r pote patil education welfare trust s group of",
        )
        self.assertEqual(
            normalize_text("College of Engineering & Technology,"),
            "college of engineering technology",
        )

    def test_extract_tokens(self):
        tokens = extract_significant_tokens("What is the affiliation of Amravati College?")
        self.assertIn("amravati", tokens)
        self.assertNotIn("what", tokens)
        self.assertNotIn("the", tokens)


class TestCollegeResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = CollegeResolver()
        self.resolver.register(
            "Government College of Engineering, Amravati",
            institute_code="01002",
            record_id="MHHEI_00001",
        )
        self.resolver.register(
            "Government College of Engineering, Aurangabad",
            institute_code="02008",
            record_id="MHHEI_00002",
        )
        self.resolver.register(
            "Shri Sant Gajanan Maharaj College of Engineering, Shegaon",
            institute_code="01101",
            record_id="MHHEI_00004",
        )
        self.resolver.register(
            "KDM College of Arts",
            institute_code=None,
            record_id="MHHEI_00552",
        )
        self.resolver.register(
            "Prof. Ram Meghe Institute of Technology & Research, Amravati",
            institute_code="01105",
            record_id="MHHEI_00005",
        )
        self.resolver.register(
            "Prof Ram Meghe College of Engineering and Management, Badnera",
            institute_code="01128",
            record_id="MHHEI_00017",
        )

    def test_exact_institute_code_match(self):
        res = self.resolver.resolve("What is the affiliation of college 01002?")
        self.assertTrue(res.matched)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.institute_name, "Government College of Engineering, Amravati")
        self.assertEqual(res.institute_code, "01002")
        self.assertEqual(res.record_id, "MHHEI_00001")
        self.assertEqual(res.match_type, "code")

    def test_exact_record_id_match(self):
        res = self.resolver.resolve("Tell me about MHHEI_00552")
        self.assertTrue(res.matched)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.institute_name, "KDM College of Arts")
        self.assertIsNone(res.institute_code)
        self.assertEqual(res.record_id, "MHHEI_00552")
        self.assertEqual(res.match_type, "record_id")

    def test_exact_name_match_with_punctuation(self):
        res = self.resolver.resolve("Government College of Engineering, Amravati")
        self.assertTrue(res.matched)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.institute_code, "01002")

    def test_contained_full_name_in_query(self):
        res = self.resolver.resolve("Can you tell me the address of Shri Sant Gajanan Maharaj College of Engineering, Shegaon please?")
        self.assertTrue(res.matched)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.institute_code, "01101")
        self.assertEqual(res.record_id, "MHHEI_00004")

    def test_ambiguity_returns_needs_clarification(self):
        # Query mentioning only "Government College of Engineering" without specifying Amravati vs Aurangabad
        res = self.resolver.resolve("What is the cutoff for Government College of Engineering?")
        self.assertFalse(res.matched)
        self.assertEqual(res.status, "needs_clarification")
        self.assertIsNotNone(res.message)
        self.assertTrue(len(res.candidates) >= 2)

    def test_ambiguous_ram_meghe_colleges(self):
        # Query mentioning Ram Meghe without distinguishing between Institute vs College of Engineering
        res = self.resolver.resolve("Tell me about Ram Meghe")
        self.assertFalse(res.matched)
        self.assertEqual(res.status, "needs_clarification")

    def test_no_match_returns_not_found(self):
        res = self.resolver.resolve("Tell me about Massachusetts Institute of Technology")
        self.assertFalse(res.matched)
        self.assertEqual(res.status, "not_found")


if __name__ == "__main__":
    unittest.main()
