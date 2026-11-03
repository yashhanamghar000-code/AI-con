# -*- coding: utf-8 -*-
"""
Tests for AI-CON API Server, Authentication, Onboarding, Stream Engine, and Chat API.
Executes directly against application handlers for 100% deterministic, offline execution.
"""

import sys
import unittest
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
AGENTS_DIR = SCRIPTS_DIR / "agents"

for p in (str(ROOT), str(SCRIPTS_DIR), str(AGENTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.api_server import (
    health,
    register,
    login,
    get_current_user,
    save_onboarding,
    get_profile,
    calculate_stream_recommendation,
    chat,
    search_colleges,
    RegisterRequest,
    LoginRequest,
    OnboardingSaveRequest,
    StreamRecommendRequest,
    ChatRequest,
    hash_password,
    FRONTEND_DIR
)


class TestFrontendAPIServer(unittest.TestCase):

    def test_health_endpoint(self):
        data = health()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "AI-CON College Consultant")
        self.assertIn("cutoffs_indexed_institutes", data)
        self.assertIn("vector_profiles_indexed", data)

    def test_auth_registration_and_login_lifecycle(self):
        unique_email = f"student_test_{int(time.time() * 1000)}@example.com"
        reg_req = RegisterRequest(
            name="Pooja Patil",
            email=unique_email,
            password="SecurePassword123"
        )
        res_reg = register(reg_req)
        self.assertTrue(res_reg["success"])
        self.assertIn("token", res_reg)
        self.assertEqual(res_reg["user"]["name"], "Pooja Patil")
        self.assertEqual(res_reg["user"]["email"], unique_email)

        # Test duplicate registration rejection
        with self.assertRaises(Exception):
            register(reg_req)

        # Test valid login
        login_req = LoginRequest(email=unique_email, password="SecurePassword123")
        res_login = login(login_req)
        self.assertTrue(res_login["success"])
        self.assertEqual(res_login["user"]["email"], unique_email)

        # Test invalid password rejection
        bad_req = LoginRequest(email=unique_email, password="WrongPassword")
        with self.assertRaises(Exception):
            login(bad_req)

        # Test get_current_user with token
        user_info = get_current_user(token=res_login["token"])
        self.assertTrue(user_info["is_authenticated"])
        self.assertEqual(user_info["user"]["name"], "Pooja Patil")

    def test_onboarding_persistence_lifecycle(self):
        test_uid = f"uid_test_{int(time.time() * 1000)}"
        save_req = OnboardingSaveRequest(
            user_id=test_uid,
            current_step=4,
            personal_info={
                "fullName": "Siddharth Deshmukh",
                "district": "Pune",
                "state": "Maharashtra"
            },
            academic_info={
                "level": "Class 10 (Secondary School)",
                "board": "Maharashtra State Board",
                "school": "Ferguson High School"
            },
            marks_info={
                "maths": 92,
                "science": 90,
                "english": 85,
                "social_science": 80,
                "percentage": 86.8
            },
            interests_info={
                "tags": ["technology", "engineering", "maths_puzzles"],
                "ambitions": "Pursue Computer Engineering at COEP Pune"
            },
            selected_stream="science_pcm",
            is_confirmed=False
        )
        save_res = save_onboarding(save_req)
        self.assertTrue(save_res["success"])

        # Fetch profile and verify fields
        prof = get_profile(test_uid)
        self.assertEqual(prof["user_id"], test_uid)
        self.assertEqual(prof["current_step"], 4)
        self.assertEqual(prof["personal_info"]["fullName"], "Siddharth Deshmukh")
        self.assertEqual(prof["marks_info"]["maths"], 92)
        self.assertEqual(prof["selected_stream"], "science_pcm")
        self.assertFalse(prof["is_confirmed"])

        # Update profile to confirmed
        confirm_req = OnboardingSaveRequest(user_id=test_uid, current_step=7, is_confirmed=True)
        save_onboarding(confirm_req)
        prof_updated = get_profile(test_uid)
        self.assertTrue(prof_updated["is_confirmed"])
        self.assertEqual(prof_updated["current_step"], 7)

    def test_stream_recommendation_engine(self):
        # Scenario: Student with high Maths & Science + Technical interests
        req_pcm = StreamRecommendRequest(
            marks={
                "maths": 95,
                "science": 92,
                "english": 80,
                "social_science": 75,
                "overall_percentage": 88.5
            },
            interests={
                "tags": ["technology", "engineering", "maths_puzzles"],
                "text": "I want to build software and study Computer Engineering."
            },
            aptitude_scores={
                "category_percentages": {
                    "logical": 100,
                    "numerical": 100,
                    "scientific": 85,
                    "business": 60,
                    "creative": 70,
                    "communication": 75,
                    "analytical": 90
                }
            }
        )
        rec = calculate_stream_recommendation(req_pcm)
        self.assertTrue(rec["success"])
        self.assertEqual(rec["recommended_stream"]["id"], "science_pcm")
        self.assertGreaterEqual(rec["recommended_stream"]["score"], 88.0)
        self.assertIn("alternatives", rec)
        self.assertGreaterEqual(len(rec["all_streams"]), 4)

        # Verify key subjects & career pathways are provided
        self.assertIn("Physics", rec["recommended_stream"]["key_subjects"])
        self.assertTrue(len(rec["recommended_stream"]["career_pathways"]) > 0)
        self.assertTrue(len(rec["recommended_stream"]["reasons"]) > 0)

    def test_chat_rag_query_handling(self):
        # Test chat query dispatch
        chat_req = ChatRequest(
            query="What is the affiliation and autonomy of Government College of Engineering, Amravati?",
            user_id="test_student_chat"
        )
        res = chat(chat_req)
        self.assertTrue(res["success"])
        self.assertIn(res["status"], ("answered", "evidence_only", "needs_clarification", "fallback"))
        self.assertTrue(len(res["message"]) > 0)

    def test_colleges_search_endpoint(self):
        # Test cutoff search mode
        search_res = search_colleges(branch="Computer", min_percentile=90.0, max_percentile=95.0, limit=5)
        self.assertIn("results", search_res)
        self.assertIn("total", search_res)
        self.assertIn(search_res["mode"], ("cutoffs", "directory", "empty"))

    def test_frontend_assets_integrity(self):
        # Verify all frontend files exist on disk with valid content
        index_file = FRONTEND_DIR / "index.html"
        styles_file = FRONTEND_DIR / "styles.css"
        app_file = FRONTEND_DIR / "app.js"
        questions_file = FRONTEND_DIR / "questions.js"

        self.assertTrue(index_file.is_file(), "index.html must exist")
        self.assertTrue(styles_file.is_file(), "styles.css must exist")
        self.assertTrue(app_file.is_file(), "app.js must exist")
        self.assertTrue(questions_file.is_file(), "questions.js must exist")

        index_text = index_file.read_text(encoding="utf-8")
        self.assertIn("AI-CON", index_text)
        self.assertIn("Smart Stream Discovery", index_text)
        self.assertIn("Aptitude Assessment", index_text)

        styles_text = styles_file.read_text(encoding="utf-8")
        self.assertIn("#2563EB", styles_text)
        self.assertIn("#0F172A", styles_text)

        q_text = questions_file.read_text(encoding="utf-8")
        self.assertIn("APTITUDE_QUESTIONS", q_text)
        self.assertIn("Logical Reasoning", q_text)


if __name__ == "__main__":
    unittest.main()
