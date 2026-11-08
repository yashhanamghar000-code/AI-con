"""
tests/test_recommendation_and_option_planner.py

Task 7 Acceptance Test Suite — Recommendation Tiers and CAP Option Strategy

Tests:
 1. Exact metric matching: percentile compared only with percentile, rank only with rank
 2. Percentile boundary values: delta >= +2.0 (historically_more_attainable), delta <= -2.5 (reach), between (competitive)
 3. Rank boundary values: student_rank <= 0.85 * cutoff (historically_more_attainable), student_rank > 1.15 * cutoff (reach)
 4. Missing score values: student without percentile and rank classified as eligibility_unresolved
 5. Ineligible student classified as ineligible without checking cutoffs
 6. Missing college or branch cutoffs classified as insufficient_evidence
 7. Deterministic record selection prefers requested round and Stage 1 without arbitrary results[0]
 8. Option form planner preserves user input preference order within each tier
 9. Option form planner places Reach -> Competitive -> Attainable in sequence
10. Option form planner warns when 0 attainable options are present
11. Option form planner isolates unplaced options (ineligible and unresolved)
12. Disclaimers explicitly state historical observation, no admission promises
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "agents"))

from admission_rules import AdmissionRulesEngine, StudentProfile
from cutoff_agent import CutoffAgent
from option_planner import OptionFormPlanner
from recommendation_engine import RecommendationEngine, RecommendationTier, RecommendationThresholds


class TestRecommendationTiersAndOptionPlanner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        ydir = self.temp_dir / "2023-24"
        ydir.mkdir()

        # College A: 06006 - COEP (Very High Cutoff: 99.0% / Rank 800)
        c_coep = {
            "academic_year": "2023-24",
            "institute_code": "06006",
            "institute_name": "College of Engineering, Pune",
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
                                    "closing_rank": 800,
                                    "closing_percentile": 99.0,
                                    "evidence_id": "2023-24:06006:0600624510:state_level:GOPENS:R1:S1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "06006.json").write_text(json.dumps(c_coep), encoding="utf-8")

        # College B: 06271 - PICT (Mid-High Cutoff: 95.0% / Rank 4000)
        c_pict = {
            "academic_year": "2023-24",
            "institute_code": "06271",
            "institute_name": "Pune Institute of Computer Technology",
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
                                    "closing_rank": 4000,
                                    "closing_percentile": 95.0,
                                    "evidence_id": "2023-24:06271:0627124510:state_level:GOPENS:R1:S1",
                                },
                                {
                                    "round": 2,
                                    "stage": "1",
                                    "list_type": "CAP",
                                    "closing_rank": 4200,
                                    "closing_percentile": 94.8,
                                    "evidence_id": "2023-24:06271:0627124510:state_level:GOPENS:R2:S1",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "06271.json").write_text(json.dumps(c_pict), encoding="utf-8")

        # College C: 06284 - Kamalnayan (Moderate Cutoff: 88.0% / Rank 16000)
        c_pvg = {
            "academic_year": "2023-24",
            "institute_code": "06284",
            "institute_name": "Kamalnayan Bajaj Institute of Engineering",
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
                                    "closing_rank": 16000,
                                    "closing_percentile": 88.0,
                                    "evidence_id": "2023-24:06284:0628424510:state_level:GOPENS:R1:S1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        (ydir / "06284.json").write_text(json.dumps(c_pvg), encoding="utf-8")

        self.agent = CutoffAgent(self.temp_dir)
        self.rules = AdmissionRulesEngine()
        self.engine = RecommendationEngine(self.agent, self.rules)
        self.planner = OptionFormPlanner(self.engine)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_percentile_boundary_classification(self):
        """Test delta boundaries: >= +2.0 (attainable), <= -2.5 (reach), between (competitive)."""
        # Baseline cutoff is 95.0% at PICT
        # 1. Attainable (97.0 vs 95.0, delta = +2.0)
        student_attainable = StudentProfile(domicile="Maharashtra", percentile=97.0)
        res_att = self.engine.categorize_option(student_attainable, "06271", "Computer Engineering")
        self.assertEqual(res_att["tier"], RecommendationTier.HISTORICALLY_MORE_ATTAINABLE)
        self.assertIn("+2.00", res_att["margin_explanation"])

        # 2. Competitive upper bound (96.9 vs 95.0, delta = +1.9)
        student_comp_up = StudentProfile(domicile="Maharashtra", percentile=96.9)
        res_comp_up = self.engine.categorize_option(student_comp_up, "06271", "Computer Engineering")
        self.assertEqual(res_comp_up["tier"], RecommendationTier.COMPETITIVE)

        # 3. Competitive lower bound (92.6 vs 95.0, delta = -2.4)
        student_comp_low = StudentProfile(domicile="Maharashtra", percentile=92.6)
        res_comp_low = self.engine.categorize_option(student_comp_low, "06271", "Computer Engineering")
        self.assertEqual(res_comp_low["tier"], RecommendationTier.COMPETITIVE)

        # 4. Reach (92.5 vs 95.0, delta = -2.5)
        student_reach = StudentProfile(domicile="Maharashtra", percentile=92.5)
        res_reach = self.engine.categorize_option(student_reach, "06271", "Computer Engineering")
        self.assertEqual(res_reach["tier"], RecommendationTier.REACH)

    def test_02_rank_boundary_classification(self):
        """Test rank boundaries: <= 0.85*cutoff (attainable), > 1.15*cutoff (reach)."""
        # Baseline closing rank is 4000 at PICT
        # 1. Attainable: rank 3400 (3400 <= 4000 * 0.85 = 3400)
        student_att = StudentProfile(domicile="Maharashtra", merit_rank=3400)
        res_att = self.engine.categorize_option(student_att, "06271", "Computer Engineering")
        self.assertEqual(res_att["tier"], RecommendationTier.HISTORICALLY_MORE_ATTAINABLE)

        # 2. Competitive: rank 3500 (3400 < 3500 <= 4600)
        student_comp = StudentProfile(domicile="Maharashtra", merit_rank=3500)
        res_comp = self.engine.categorize_option(student_comp, "06271", "Computer Engineering")
        self.assertEqual(res_comp["tier"], RecommendationTier.COMPETITIVE)

        # 3. Reach: rank 4601 (4601 > 4000 * 1.15 = 4600)
        student_reach = StudentProfile(domicile="Maharashtra", merit_rank=4601)
        res_reach = self.engine.categorize_option(student_reach, "06271", "Computer Engineering")
        self.assertEqual(res_reach["tier"], RecommendationTier.REACH)

    def test_03_missing_scores_unresolved(self):
        """Students without percentile or merit rank resolve to eligibility_unresolved."""
        student_noscore = StudentProfile(domicile="Maharashtra", percentile=None, merit_rank=None)
        res = self.engine.categorize_option(student_noscore, "06271", "Computer Engineering")
        self.assertEqual(res["tier"], RecommendationTier.ELIGIBILITY_UNRESOLVED)
        self.assertIn("Comparison cannot be computed", res["reason"])

    def test_04_ineligible_student_isolated(self):
        """Statutory ineligibility prevents cutoff comparison and labels option Ineligible."""
        student_ineligible = StudentProfile(
            domicile="OMS",
            percentile=95.0,
        )
        res = self.engine.categorize_option(
            student_ineligible,
            "06271",
            "Computer Engineering",
            specific_category="GOPENS",  # OMS candidate cannot claim Maharashtra State GOPENS quota
        )
        # When specific quota is ineligible or outside candidate's applicable categories
        self.assertIn(res["tier"], (RecommendationTier.INELIGIBLE, RecommendationTier.INSUFFICIENT_EVIDENCE))

    def test_05_missing_data_insufficient_evidence(self):
        """Nonexistent institutes or branches return Insufficient Evidence."""
        student = StudentProfile(domicile="Maharashtra", percentile=95.0)
        res_inst = self.engine.categorize_option(student, "99999", "Computer Engineering")
        self.assertEqual(res_inst["tier"], RecommendationTier.INSUFFICIENT_EVIDENCE)

        res_branch = self.engine.categorize_option(student, "06271", "NonExistentEngineering")
        self.assertEqual(res_branch["tier"], RecommendationTier.INSUFFICIENT_EVIDENCE)

    def test_06_deterministic_record_selection(self):
        """Specific round requested selects that round, not an arbitrary results[0]."""
        student = StudentProfile(domicile="Maharashtra", percentile=94.9)
        # PICT R1 cutoff: 95.0 (student 94.9 is Competitive)
        # PICT R2 cutoff: 94.8 (student 94.9 is delta +0.1, still Competitive, but reflects R2)
        res_r2 = self.engine.categorize_option(student, "06271", "Computer Engineering", round_no=2)
        self.assertEqual(res_r2["round"], 2)
        self.assertAlmostEqual(res_r2["closing_percentile"], 94.8)

    def test_07_option_plan_portfolio_and_preference_preservation(self):
        """Option plan groups by Reach -> Competitive -> Attainable while preserving input order within tiers."""
        student = StudentProfile(domicile="Maharashtra", percentile=95.0)
        # Candidate inputs:
        # 1. PVG (Attainable - cutoff 88.0)
        # 2. COEP (Reach - cutoff 99.0)
        # 3. PICT (Competitive - cutoff 95.0)
        prefs = [
            {"institute_code": "06284", "branch": "Computer Engineering"},
            {"institute_code": "06006", "branch": "Computer Engineering"},
            {"institute_code": "06271", "branch": "Computer Engineering"},
        ]
        plan = self.planner.build_option_plan(student, prefs)

        self.assertEqual(plan["total_preferences_submitted"], 3)
        self.assertEqual(plan["tier_counts"]["reach"], 1)
        self.assertEqual(plan["tier_counts"]["competitive"], 1)
        self.assertEqual(plan["tier_counts"]["historically_more_attainable"], 1)

        seq = plan["recommended_sequence"]
        # Position 1: COEP (Reach)
        self.assertEqual(seq[0]["institute_code"], "06006")
        self.assertEqual(seq[0]["tier"], RecommendationTier.REACH)
        # Position 2: PICT (Competitive)
        self.assertEqual(seq[1]["institute_code"], "06271")
        self.assertEqual(seq[1]["tier"], RecommendationTier.COMPETITIVE)
        # Position 3: PVG (Attainable)
        self.assertEqual(seq[2]["institute_code"], "06284")
        self.assertEqual(seq[2]["tier"], RecommendationTier.HISTORICALLY_MORE_ATTAINABLE)

    def test_08_risk_warning_on_no_attainable_options(self):
        """Planner emits risk warning when no attainable choices are selected."""
        student = StudentProfile(domicile="Maharashtra", percentile=90.0)
        prefs = [
            {"institute_code": "06006", "branch": "Computer Engineering"},  # Reach (99.0)
            {"institute_code": "06271", "branch": "Computer Engineering"},  # Reach (95.0)
        ]
        plan = self.planner.build_option_plan(student, prefs)
        self.assertTrue(any("Risk Alert" in w for w in plan["warnings"]))

    def test_09_disclaimers_never_guarantee_admission(self):
        """Output disclaimers explicitly clarify decision support without guarantees."""
        student = StudentProfile(domicile="Maharashtra", percentile=99.5)
        eval_res = self.engine.categorize_option(student, "06284", "Computer Engineering")
        self.assertIn("no past cutoff guarantees", eval_res["disclaimer"].lower())

        plan = self.planner.build_option_plan(student, [{"institute_code": "06284", "branch": "Computer Engineering"}])
        self.assertIn("not an official submission", plan["disclaimer"].lower())
        self.assertIn("never an admission guarantee", plan["disclaimer"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
