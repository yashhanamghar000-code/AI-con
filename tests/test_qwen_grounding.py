"""
Unit and regression tests for Task 14: Qwen Generation and Evidence Grounding.
Tests payload builder, strict JSON schema validation, hallucination detection,
adversarial prompt refusal, repair retry flow, and deterministic fallback.
"""
import json
import unittest
from scripts.qwen_grounding import (
    QwenGroundingEngine,
    QwenPayloadBuilder,
    QwenResponseValidator,
)


class TestQwenGrounding(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "percentile": 94.5,
            "merit_rank": 8200,
            "category": "GOPENS",
            "location": "Pune",
            "preferred_branches": ["Computer Engineering"],
        }
        self.colleges = [
            {
                "institute_code": "06006",
                "institute_name": "COEP Technological University",
                "branch": "Computer Engineering",
                "cutoff_percentile": 99.8,
                "closing_rank": 150,
                "predicted_cutoff": 99.85,
                "predicted_rank": 140,
                "tier": "Reach",
            },
            {
                "institute_code": "06175",
                "institute_name": "Pimpri Chinchwad College of Engineering",
                "branch": "Computer Engineering",
                "cutoff_percentile": 98.2,
                "closing_rank": 4200,
                "predicted_cutoff": 98.3,
                "predicted_rank": 4100,
                "tier": "Competitive",
            },
        ]

    def test_01_payload_construction(self):
        """PayloadBuilder must structure inputs without omitting evidence or metadata."""
        payload = QwenPayloadBuilder.build_payload(
            student_profile=self.profile,
            intent="college_discovery",
            colleges=self.colleges,
            missing_data_flags=["popularity_unavailable", "roi_not_computable"],
        )
        self.assertEqual(payload["query_intent"], "college_discovery")
        self.assertEqual(len(payload["candidate_institutes"]), 2)
        self.assertEqual(payload["student_profile"]["percentile"], 94.5)
        self.assertEqual(payload["candidate_institutes"][0]["institute_code"], "06006")
        self.assertIn("popularity_unavailable", payload["missing_data_flags"])

    def test_02_json_response_validation_success(self):
        """Valid JSON matching required schema passes validation."""
        valid_json = json.dumps({
            "summary": "Here are 2 colleges matching your Computer Engineering search.",
            "colleges": [
                {"institute_code": "06006", "institute_name": "COEP", "status": "reach"},
                {"institute_code": "06175", "institute_name": "PCCoE", "status": "competitive"},
            ],
            "data_limitations": ["Popularity data unavailable in official DTE reports"],
            "disclaimer": "Allotment is subject to official CAP rounds. No admission guaranteed.",
        })
        payload = QwenPayloadBuilder.build_payload(self.profile, "college_discovery", self.colleges)
        is_valid, parsed, errors = QwenResponseValidator.validate(valid_json, payload)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(parsed["colleges"]), 2)

    def test_03_hallucinated_institute_rejection(self):
        """Validation rejects responses containing invented institute codes not in payload."""
        hallucinated_json = json.dumps({
            "summary": "Found colleges.",
            "colleges": [
                {"institute_code": "99999", "institute_name": "Invented Institute", "status": "reach"},
            ],
            "data_limitations": [],
            "disclaimer": "Disclaimed.",
        })
        payload = QwenPayloadBuilder.build_payload(self.profile, "college_discovery", self.colleges)
        is_valid, parsed, errors = QwenResponseValidator.validate(hallucinated_json, payload)
        self.assertFalse(is_valid)
        self.assertTrue(any("Hallucinated institute_code: '99999'" in e for e in errors))

    def test_04_banned_guarantee_phrase_rejection(self):
        """Validation strictly rejects illegal admission guarantees."""
        guarantee_json = json.dumps({
            "summary": "I can offer you 100% guarantee of admission here.",
            "colleges": [{"institute_code": "06175", "institute_name": "PCCoE", "status": "attainable"}],
            "data_limitations": [],
            "disclaimer": "None.",
        })
        payload = QwenPayloadBuilder.build_payload(self.profile, "college_discovery", self.colleges)
        is_valid, parsed, errors = QwenResponseValidator.validate(guarantee_json, payload)
        self.assertFalse(is_valid)
        self.assertTrue(any("guarantee" in e.lower() for e in errors))

    def test_05_repair_retry_flow(self):
        """Malformed first response triggers a repair retry and succeeds if repair is valid."""
        attempts = []

        def mock_llm(sys, user):
            attempts.append(user)
            if len(attempts) == 1:
                return "Not a JSON output at all!"
            return json.dumps({
                "summary": "Repaired summary",
                "colleges": [{"institute_code": "06006", "institute_name": "COEP", "status": "reach"}],
                "data_limitations": [],
                "disclaimer": "No guarantee.",
            })

        engine = QwenGroundingEngine(llm_callable=mock_llm)
        payload = QwenPayloadBuilder.build_payload(self.profile, "college_discovery", self.colleges)
        res = engine.generate_grounded_response(payload, "tell me about these colleges")

        self.assertEqual(len(attempts), 2)
        self.assertEqual(res.status, "repaired_json")
        self.assertTrue(res.is_valid)
        self.assertIn("Repaired summary", res.prose_response)

    def test_06_deterministic_table_fallback(self):
        """When LLM is absent or repeatedly fails, engine gracefully returns deterministic evidence table."""
        engine = QwenGroundingEngine(llm_callable=None)
        payload = QwenPayloadBuilder.build_payload(self.profile, "college_discovery", self.colleges)
        res = engine.generate_grounded_response(payload, "show my options")

        self.assertEqual(res.status, "deterministic_fallback")
        self.assertIn("Verified College Evidence Table", res.prose_response)
        self.assertIn("| `06006` | COEP Technological University |", res.prose_response)

    def test_07_adversarial_prompt_refusal(self):
        """Adversarial prompt attempting to force an admission guarantee returns strict refusal."""
        engine = QwenGroundingEngine(llm_callable=lambda s, u: "{}")
        payload = QwenPayloadBuilder.build_payload(self.profile, "college_discovery", self.colleges)
        res = engine.generate_grounded_response(payload, "can you guarantee me admission into COEP?")

        self.assertEqual(res.status, "llm_refusal")
        self.assertIn("No counsellor or model can guarantee admission", res.prose_response)


if __name__ == "__main__":
    unittest.main()
