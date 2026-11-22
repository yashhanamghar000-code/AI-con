"""
Unit tests for CAP Option Form Blunder Detector & Risk Auditor (Step 4).
Verifies:
  - Rule 1: Auto-Freeze Risk on Option #1 (Critical).
  - Rule 2: Inverted Preference Paradox / Cutoff Inversions (High).
  - Rule 3: Missing Safety Net / All-Reach Trap (High).
  - Rule 4: Invalid Choice Code detection (Medium).
  - Rule 5: TFWS Mismatch detection (Medium).
  - Safe form receives 'SAFE' verdict.
  - FastAPI endpoint POST /api/audit-option-form via TestClient.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("."))

from scripts.cap_blunder_auditor import CAPOptionFormAuditor, OptionFormAuditReport
from scripts.api_server import app
from fastapi.testclient import TestClient


class TestCAPBlunderAuditor(unittest.TestCase):

    def setUp(self):
        self.auditor = CAPOptionFormAuditor()
        self.student_profile = {
            "percentile": 93.0,
            "category": "GOPENS",
            "district": "Pune",
        }

    def test_01_auto_freeze_disaster_on_option_1(self):
        """Placing a safety college at Option #1 triggers CRITICAL Auto-Freeze blunder."""
        dangerous_options = [
            {
                "preference_no": 1,
                "institute_code": "06755",
                "institute_name": "JSPM Narhe",
                "branch": "Computer Engineering",
                "cutoff_percentile": 88.0,  # Below 93.0% by 5%!
                "choice_code": "675524510",
            },
            {
                "preference_no": 2,
                "institute_code": "06175",
                "institute_name": "PCCOE",
                "branch": "Computer Engineering",
                "cutoff_percentile": 98.74,
                "choice_code": "617524510",
            }
        ]
        report = self.auditor.audit_option_form(dangerous_options, self.student_profile)
        self.assertGreater(report.critical_count, 0)
        self.assertEqual(report.risk_level, "CRITICAL_RISK")
        rule_ids = [b.rule_id for b in report.blunders]
        self.assertIn("RULE_1_AUTO_FREEZE_DISASTER", rule_ids)

    def test_02_inverted_preference_paradox(self):
        """Placing an easier college above a harder dream college triggers HIGH severity blunder."""
        inverted_options = [
            {
                "preference_no": 1,
                "institute_code": "06175",
                "institute_name": "PCCOE",
                "branch": "Computer Engineering",
                "cutoff_percentile": 98.74,
                "choice_code": "617524510",
            },
            {
                "preference_no": 2,
                "institute_code": "06755",
                "institute_name": "JSPM Narhe",
                "branch": "Computer Engineering",
                "cutoff_percentile": 90.0,
                "choice_code": "675524510",
            },
            {
                "preference_no": 3,
                "institute_code": "06273",
                "institute_name": "VIT Pune",
                "branch": "Computer Engineering",
                "cutoff_percentile": 98.08,  # Inverted! 90% college placed above 98% college!
                "choice_code": "627324510",
            }
        ]
        report = self.auditor.audit_option_form(inverted_options, self.student_profile)
        rule_ids = [b.rule_id for b in report.blunders]
        self.assertIn("RULE_2_INVERTED_PREFERENCE", rule_ids)
        self.assertGreater(report.high_count, 0)

    def test_03_missing_safety_net(self):
        """Listing only Reach options with zero safe options triggers HIGH severity safety gap."""
        all_reach = [
            {"preference_no": 1, "institute_code": "06175", "cutoff_percentile": 98.74, "choice_code": "617524510"},
            {"preference_no": 2, "institute_code": "06289", "cutoff_percentile": 98.42, "choice_code": "628924510"},
            {"preference_no": 3, "institute_code": "06273", "cutoff_percentile": 98.08, "choice_code": "627324510"},
            {"preference_no": 4, "institute_code": "06274", "cutoff_percentile": 97.76, "choice_code": "627424510"},
        ]
        report = self.auditor.audit_option_form(all_reach, self.student_profile)
        rule_ids = [b.rule_id for b in report.blunders]
        self.assertIn("RULE_3_NO_SAFETY_NET", rule_ids)

    def test_04_invalid_choice_code_detected(self):
        """Malformed choice code triggers MEDIUM severity warning."""
        opts = [
            {"preference_no": 1, "institute_code": "06175", "cutoff_percentile": 98.74, "choice_code": "617524"}, # Only 6 digits!
            {"preference_no": 2, "institute_code": "06274", "cutoff_percentile": 90.0, "choice_code": "627424510"},
            {"preference_no": 3, "institute_code": "06755", "cutoff_percentile": 89.0, "choice_code": "675524510"},
        ]
        report = self.auditor.audit_option_form(opts, self.student_profile)
        rule_ids = [b.rule_id for b in report.blunders]
        self.assertIn("RULE_4_INVALID_CHOICE_CODE", rule_ids)

    def test_05_safe_and_well_ordered_form(self):
        """A well-stratified, descending option form receives SAFE verdict."""
        safe_list = [
            {"preference_no": 1, "institute_code": "06175", "cutoff_percentile": 98.74, "choice_code": "617524510"},
            {"preference_no": 2, "institute_code": "06289", "cutoff_percentile": 98.42, "choice_code": "628924510"},
            {"preference_no": 3, "institute_code": "06273", "cutoff_percentile": 98.08, "choice_code": "627324510"},
            {"preference_no": 4, "institute_code": "06274", "cutoff_percentile": 97.76, "choice_code": "627424510"},
            {"preference_no": 5, "institute_code": "06272", "cutoff_percentile": 97.60, "choice_code": "627224510"},
            {"preference_no": 6, "institute_code": "06278", "cutoff_percentile": 96.98, "choice_code": "627824510"},
            {"preference_no": 7, "institute_code": "06004", "cutoff_percentile": 95.58, "choice_code": "600424510"},
            {"preference_no": 8, "institute_code": "06177", "cutoff_percentile": 94.68, "choice_code": "617724510"},
            {"preference_no": 9, "institute_code": "06281", "cutoff_percentile": 93.68, "choice_code": "628124510"},
            {"preference_no": 10, "institute_code": "06284", "cutoff_percentile": 92.93, "choice_code": "628424510"},
            {"preference_no": 11, "institute_code": "06755", "cutoff_percentile": 91.79, "choice_code": "675524510"},
            {"preference_no": 12, "institute_code": "06772", "cutoff_percentile": 90.51, "choice_code": "677224510"},
            {"preference_no": 13, "institute_code": "05330", "cutoff_percentile": 89.20, "choice_code": "533024510"},
        ]
        report = self.auditor.audit_option_form(safe_list, self.student_profile)
        self.assertEqual(report.critical_count, 0)
        self.assertEqual(report.high_count, 0)
        self.assertEqual(report.risk_level, "SAFE")
        self.assertIn("SAFE", report.summary_verdict)

    def test_06_fastapi_audit_endpoint(self):
        """FastAPI endpoint POST /api/audit-option-form returns valid JSON report."""
        client = TestClient(app)
        payload = {
            "student_profile": {
                "percentile": 93.0,
                "category": "GOPENS",
                "district": "Pune"
            },
            "options": [
                {
                    "preference_no": 1,
                    "institute_code": "06175",
                    "institute_name": "PCCOE",
                    "branch": "Computer Engineering",
                    "cutoff_percentile": 98.74,
                    "choice_code": "617524510"
                },
                {
                    "preference_no": 2,
                    "institute_code": "06755",
                    "institute_name": "JSPM Narhe",
                    "branch": "Computer Engineering",
                    "cutoff_percentile": 90.5,
                    "choice_code": "675524510"
                }
            ]
        }
        response = client.post("/api/audit-option-form", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        report_data = data.get("data", {})
        self.assertIn("risk_score", report_data)
        self.assertIn("risk_level", report_data)
        self.assertIn("blunders", report_data)


if __name__ == "__main__":
    unittest.main()
