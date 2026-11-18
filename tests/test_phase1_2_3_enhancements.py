"""
Unit & Integration Tests for Phase 1, Phase 2, and Phase 3 Enhancements.
Tests:
1. Profile Intake & Syncing
2. Option Form Risk Meter & DTE CSV Export
3. College Duel / Side-by-Side Comparison Matrix
4. Freeze vs Float Decision Assistant (Statutory Rules)
5. Statutory Document Verification Checklist
6. Marathi Language Comprehension (Devanagari Entities)
7. Cache Service (In-Memory + Redis fallback)
8. FastAPI UI Endpoints
"""
import unittest
from pathlib import Path

from scripts.cache_service import CacheService
from scripts.cap_strategy_service import CAPStrategyService
from scripts.college_comparison_service import CollegeComparisonService
from scripts.query_intelligence import QueryIntelligenceParser
from aicon_ui.app import (
    save_profile,
    get_profile,
    validate_option_form_endpoint,
    export_option_form_csv,
    freeze_float_endpoint,
    document_checklist_endpoint,
    whatsapp_verify,
    ProfileRequest,
    OptionFormValidateRequest,
    FreezeFloatRequest,
)


class TestPhase123Enhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = QueryIntelligenceParser()
        cls.comp_service = CollegeComparisonService()

    def test_marathi_query_comprehension(self):
        """Phase 2: Marathi Devanagari query extraction."""
        q = "मला ९४ पर्सेंटाईल आहेत, पुण्यात ओपन कॅटेगरीसाठी कॉम्प्युटर इंजिनिअरिंगची ३० कॉलेजेस सांगा"
        parsed = self.parser.parse_query(q)
        self.assertEqual(parsed.get("percentile"), 94.0)
        self.assertEqual(parsed.get("location"), "Pune")
        self.assertEqual(parsed.get("category"), "GOPENS")
        self.assertIn("Computer Engineering", parsed.get("preferred_branches", []))
        self.assertEqual(parsed.get("detected_language"), "mr")

    def test_marathi_location_variations(self):
        """Phase 2: Marathi inflected location names."""
        for q, expected_loc in [
            ("मुंबईत चांगल्या कॉलेजची माहिती द्या", "Mumbai"),
            ("नागपुरात आयटीसाठी कोणते कॉलेज आहे", "Nagpur"),
            ("नाशिकमध्ये मेकॅनिकल इंजिनिअरिंग", "Nashik"),
            ("संभाजीनगरात गव्हर्नमेंट कॉलेज", "Aurangabad"),
        ]:
            res = self.parser.parse_query(q)
            self.assertEqual(res.get("location"), expected_loc, f"Failed for {q}")

    def test_option_form_validation_and_risk(self):
        """Phase 1: Option form balance & risk evaluation."""
        # Scenario 1: Empty list
        empty_res = CAPStrategyService.validate_option_form([])
        self.assertFalse(empty_res["valid"])
        self.assertEqual(empty_res["risk_level"], "empty")

        # Scenario 2: High risk (no safe attainable colleges, < 5 choices)
        risky_choices = [
            {"institute_name": "COEP Pune", "tier": "reach", "cutoff_percentile": 99.8, "branch": "Computer Engineering"},
            {"institute_name": "VJTI Mumbai", "tier": "reach", "cutoff_percentile": 99.7, "branch": "Computer Engineering"},
        ]
        risky_res = CAPStrategyService.validate_option_form(risky_choices)
        self.assertTrue(risky_res["valid"])
        self.assertEqual(risky_res["risk_level"], "high_risk")
        self.assertTrue(any("Attainable" in r for r in risky_res["recommendations"]))

        # Scenario 3: Balanced list
        balanced_choices = [
            {"institute_name": "COEP", "tier": "reach", "cutoff_percentile": 99.8, "branch": "CS"},
            {"institute_name": "VJTI", "tier": "reach", "cutoff_percentile": 99.7, "branch": "CS"},
            {"institute_name": "PICT", "tier": "competitive", "cutoff_percentile": 99.2, "branch": "CS"},
            {"institute_name": "PCCOE", "tier": "competitive", "cutoff_percentile": 98.2, "branch": "CS"},
            {"institute_name": "VIIT", "tier": "competitive", "cutoff_percentile": 96.5, "branch": "CS"},
            {"institute_name": "DY Patil", "tier": "attainable", "cutoff_percentile": 92.0, "branch": "CS"},
            {"institute_name": "MIT AOE", "tier": "attainable", "cutoff_percentile": 91.0, "branch": "CS"},
            {"institute_name": "PVPIT", "tier": "attainable", "cutoff_percentile": 88.0, "branch": "CS"},
        ]
        bal_res = CAPStrategyService.validate_option_form(balanced_choices)
        self.assertEqual(bal_res["risk_level"], "balanced")
        self.assertTrue(bal_res["is_balanced"])
        self.assertGreater(bal_res["tier_breakdown"]["attainable_pct"], 20.0)

    def test_dte_csv_export(self):
        """Phase 1: DTE-compliant CSV export."""
        sample_choices = [
            {
                "preference_no": 1,
                "choice_code": "600624510",
                "institute_code": "6006",
                "institute_name": "COEP Technological University",
                "branch": "Computer Engineering",
                "category": "GOPENS",
                "cutoff_percentile": 99.85,
                "tier": "Reach",
            },
            {
                "preference_no": 2,
                "choice_code": "617524510",
                "institute_code": "6175",
                "institute_name": "PCCOE",
                "branch": "Computer Engineering",
                "category": "GOPENS",
                "cutoff_percentile": 98.15,
                "tier": "Competitive",
            },
        ]
        csv_out = CAPStrategyService.export_dte_csv(sample_choices)
        self.assertIn("Preference_Number,Choice_Code,Institute_Code", csv_out)
        self.assertIn("600624510", csv_out)
        self.assertIn("PCCOE", csv_out)

    def test_college_comparison_duel(self):
        """Phase 1: Head-to-head college comparison matrix."""
        res = self.comp_service.compare(
            institute_codes=["06006", "06175"],
            branch="Computer Engineering",
            category="GOPENS",
            student_percentile=98.5,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["colleges"]), 2)

        c1, c2 = res["colleges"][0], res["colleges"][1]
        self.assertIn("COEP", c1["institute_name"])
        self.assertIn("Pimpri", c2["institute_name"])
        self.assertGreater(len(res["takeaways"]), 0)

    def test_freeze_vs_float_statutory_logic(self):
        """Phase 2: Freeze vs Float decision rules."""
        # Case 1: Allotted Choice #1 -> Mandatory Auto-Freeze
        res_ch1 = CAPStrategyService.analyze_freeze_float(
            allotted_choice_no=1,
            allotted_choice_code="600624510",
            allotted_institute_name="COEP",
            cap_round=1,
            student_percentile=99.9,
        )
        self.assertEqual(res_ch1["decision"], "AUTO_FREEZE")
        self.assertIn("automatically frozen", res_ch1["explanation"].lower())

        # Case 2: Allotted Choice #5 with realistic higher choices -> Float for Betterment
        higher = [
            {"preference_no": 1, "institute_name": "COEP", "cutoff_percentile": 99.8},
            {"preference_no": 2, "institute_name": "VJTI", "cutoff_percentile": 99.7},
            {"preference_no": 3, "institute_name": "PICT", "cutoff_percentile": 99.1},
            {"preference_no": 4, "institute_name": "PCCOE", "cutoff_percentile": 98.5},
        ]
        res_float = CAPStrategyService.analyze_freeze_float(
            allotted_choice_no=5,
            allotted_choice_code="628924510",
            allotted_institute_name="VIIT Pune",
            cap_round=1,
            student_percentile=98.0,
            higher_choices=higher,
        )
        self.assertEqual(res_float["decision"], "FLOAT_FOR_BETTERMENT")
        self.assertGreater(len(res_float["viable_betterment_options"]), 0)

    def test_document_verification_checklist(self):
        """Phase 2: Statutory document checklist for reserved categories."""
        # OBC candidate requires Caste Certificate, CVC, and NCL
        res_obc = CAPStrategyService.get_document_checklist(category="OBC", has_tfws=True)
        doc_titles = [d["title"] for d in res_obc["common_documents"] + res_obc["category_specific_documents"]]
        self.assertTrue(any("Caste Certificate" in t for t in doc_titles))
        self.assertTrue(any("Caste Validity" in t for t in doc_titles))
        self.assertTrue(any("Non-Creamy Layer" in t for t in doc_titles))
        self.assertTrue(any("Income Certificate" in t for t in doc_titles))

    def test_cache_service(self):
        """Phase 3: Cache Service (In-Memory + TTL)."""
        cache = CacheService()
        cache.set("test_key", {"foo": "bar"}, ttl_seconds=60)
        self.assertEqual(cache.get("test_key"), {"foo": "bar"})
        cache.delete("test_key")
        self.assertIsNone(cache.get("test_key"))

    def test_api_endpoints_integration(self):
        """Integration tests for all newly registered FastAPI handler functions."""
        # 1. Profile API
        save_resp = save_profile(ProfileRequest(
            session_id="test_s1",
            percentile=95.5,
            category="GOPENS",
            preferred_location="Pune",
        ))
        self.assertEqual(save_resp["status"], "ok")
        self.assertEqual(save_resp["profile"]["percentile"], 95.5)

        get_resp = get_profile(session_id="test_s1")
        self.assertEqual(get_resp["status"], "ok")
        self.assertEqual(get_resp["profile"]["percentile"], 95.5)

        # 2. Option Form Validate API
        val_resp = validate_option_form_endpoint(OptionFormValidateRequest(
            choices=[{"institute_name": "COEP", "tier": "reach", "cutoff_percentile": 99.8}]
        ))
        self.assertIn("risk_level", val_resp)

        # 3. Option Form Export CSV API
        csv_resp = export_option_form_csv(OptionFormValidateRequest(
            choices=[{"institute_name": "COEP", "tier": "reach", "cutoff_percentile": 99.8}]
        ))
        self.assertIn("Preference_Number", csv_resp.body.decode("utf-8"))

        # 4. Strategy Freeze vs Float API
        strat_resp = freeze_float_endpoint(FreezeFloatRequest(
            allotted_choice_no=1,
            allotted_institute_name="COEP",
            cap_round=1,
            student_percentile=99.9,
        ))
        self.assertEqual(strat_resp["decision"], "AUTO_FREEZE")

        # 5. Document Checklist API
        doc_resp = document_checklist_endpoint(category="SC")
        self.assertGreater(doc_resp["total_documents"], 4)

        # 6. WhatsApp Webhook Verification
        wa_ver = whatsapp_verify(
            hub_mode="subscribe",
            hub_token="aicon_secret_token_2026",
            hub_challenge="VERIFIED_CHALLENGE",
        )
        self.assertEqual(wa_ver.body.decode("utf-8"), "VERIFIED_CHALLENGE")


if __name__ == "__main__":
    unittest.main()
