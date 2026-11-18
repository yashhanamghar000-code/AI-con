"""
Unit tests for Query Intelligence and Intent Routing (Task 2).
Tests parsing, validation, spelling variations, short follow-ups,
ambiguities, and entity extraction.
"""
import unittest
from scripts.query_intelligence import (
    QueryIntelligenceParser,
    AdmissionIntent,
    RankingObjective,
    ParsedAdmissionQuery,
)


class TestQueryIntelligence(unittest.TestCase):
    def setUp(self):
        self.parser = QueryIntelligenceParser()

    def test_01_full_discovery_query(self):
        query = (
            "I have 94 percentile in CET and want colleges in Pune, category OPEN, "
            "give me a list of the most popular 30 colleges for Computer Engineering and related branches."
        )
        res = self.parser.parse_admission_query(query)
        self.assertEqual(res.intent, AdmissionIntent.COLLEGE_DISCOVERY)
        self.assertEqual(res.exam, "MHT-CET")
        self.assertEqual(res.percentile, 94.0)
        self.assertEqual(res.category_raw, "OPEN")
        self.assertEqual(res.normalized_seat_code, "GOPENS")
        self.assertEqual(res.location, "Pune")
        self.assertEqual(res.requested_unique_colleges, 30)
        self.assertEqual(res.ranking_objective, RankingObjective.POPULARITY)
        self.assertTrue(res.is_multi_college)
        self.assertFalse(res.is_follow_up)
        self.assertIn("Computer Engineering", res.preferred_branches)
        self.assertIn("Information Technology", res.preferred_branches)

    def test_02_followup_count_update(self):
        """Follow-up 'give me list of 30 colleges' inherits active session context."""
        ctx = {
            "last_shortlist": [{"code": "06006", "name": "COEP"}],
            "location": "Pune",
            "percentile": 94.0,
            "category": "GOPENS",
            "preferred_branches": ["Computer Engineering"],
        }
        res = self.parser.parse_admission_query("give me list of 30 colleges", conversation_context=ctx)
        self.assertTrue(res.is_follow_up)
        self.assertEqual(res.intent, AdmissionIntent.COLLEGE_DISCOVERY)
        self.assertEqual(res.requested_unique_colleges, 30)
        self.assertEqual(res.location, "Pune")
        self.assertEqual(res.percentile, 94.0)

    def test_03_followup_rank_by_roi(self):
        """Follow-up 'now rank these by ROI' classifies as ROI_RANKING."""
        ctx = {"last_shortlist": [{"code": "06006"}], "location": "Pune"}
        res = self.parser.parse_admission_query("now rank these by ROI", conversation_context=ctx)
        self.assertTrue(res.is_follow_up)
        self.assertEqual(res.intent, AdmissionIntent.ROI_RANKING)
        self.assertEqual(res.ranking_objective, RankingObjective.ROI)

    def test_04_locality_scope_alandi_wagholi(self):
        """Alandi and Wagholi resolve into Pune district geographic scope."""
        res1 = self.parser.parse_admission_query("colleges in Alandi for Computer Engineering")
        self.assertEqual(res1.location, "Pune")
        self.assertIn("Alandi", res1.location_scope_notes)

        res2 = self.parser.parse_admission_query("colleges in Wagholi for IT")
        self.assertEqual(res2.location, "Pune")
        self.assertIn("Wagholi", res2.location_scope_notes)

    def test_05_percentile_validation_and_rejection(self):
        """Percentile validator bounds checks."""
        # Valid percentile
        res = self.parser.parse_admission_query("colleges at 98.75 percentile")
        self.assertEqual(res.percentile, 98.75)

        # Invalid percentiles (> 100 or < 0) are rejected / omitted
        res_invalid = self.parser.parse_admission_query("colleges at 105 percentile")
        self.assertIsNone(res_invalid.percentile)

    def test_06_exact_college_info_lookup(self):
        """Queries for fees/affiliation of a single college classify as college_information."""
        res = self.parser.parse_admission_query("What is the fee and affiliation of VJTI Mumbai?")
        self.assertEqual(res.intent, AdmissionIntent.COLLEGE_INFORMATION)
        self.assertFalse(res.is_multi_college)

    def test_07_ml_prediction_intent(self):
        """Queries asking for ML regression or closing rank prediction classify as ml_cutoff_prediction."""
        res = self.parser.parse_admission_query("predict next year closing rank with histgradientboosting")
        self.assertEqual(res.intent, AdmissionIntent.ML_CUTOFF_PREDICTION)


if __name__ == "__main__":
    unittest.main()

