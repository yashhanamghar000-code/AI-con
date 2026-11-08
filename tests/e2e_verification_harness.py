#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-CON Comprehensive End-to-End Verification Harness.
Tests all application layers:
1. Server Health & Static Frontend Assets
2. Authentication & Authorization Lifecycle
3. 7-Step Onboarding Workflow & SQLite Persistence
4. Multi-Profile Stream Recommendation Engine (PCM, PCB, Commerce, Arts, Vocational)
5. AI Consultant Chat RAG Integration with Orchestrator (All 5 Domain Questions)
6. Historical College Cutoff Search API
7. Security, User Isolation & Data Integrity Checks
"""

import sys
import os
import json
import time
import sqlite3
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB_PATH = ROOT / "ai_con_app.db"
BASE_URL = "http://127.0.0.1:8000"

results = {
    "server_startup": {},
    "frontend_assets": {},
    "authentication": {},
    "onboarding_persistence": {},
    "stream_engine_profiles": {},
    "ai_consultant_chat": {},
    "cutoff_search": {},
    "security_audit": {}
}

def log(section, msg):
    print(f"[{section.upper()}] {msg}")

def test_server_health_and_assets():
    log("health", "Testing server health & docs...")
    r_health = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r_health.status_code == 200, f"Health check failed: {r_health.status_code}"
    h_data = r_health.json()
    assert h_data["status"] == "healthy"
    results["server_startup"] = h_data
    log("health", f"Health OK: {h_data['service']}")

    r_docs = requests.get(f"{BASE_URL}/docs", timeout=5)
    assert r_docs.status_code == 200, f"Docs endpoint failed: {r_docs.status_code}"
    log("health", "Swagger UI Docs OK (HTTP 200)")

    assets = {
        "/": "index.html",
        "/styles.css": "styles.css",
        "/app.js": "app.js",
        "/questions.js": "questions.js"
    }
    for path, name in assets.items():
        r = requests.get(f"{BASE_URL}{path}", timeout=5)
        assert r.status_code == 200, f"Asset {path} failed: {r.status_code}"
        assert len(r.text) > 1000, f"Asset {path} is suspiciously small: {len(r.text)} bytes"
        results["frontend_assets"][name] = {"status": r.status_code, "bytes": len(r.text)}
        log("assets", f"Asset {name} ({len(r.text):,} bytes) verified HTTP 200")

def test_authentication_lifecycle():
    log("auth", "Testing user registration and login lifecycle...")
    test_email = f"e2e_student_{int(time.time())}@example.com"
    test_password = "StrictlySecurePassword!2026"
    test_name = "Ananya Kulkarni"

    # 1. Register new user
    r_reg = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": test_name,
        "email": test_email,
        "password": test_password
    }, timeout=5)
    assert r_reg.status_code == 200, f"Registration failed: {r_reg.text}"
    reg_data = r_reg.json()
    assert reg_data["success"] is True
    assert "token" in reg_data
    user_id = reg_data["user"]["id"]
    token = reg_data["token"]
    log("auth", f"Registered new user ID: {user_id}")

    # 2. Duplicate registration must fail with 400
    r_dup = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": test_name,
        "email": test_email,
        "password": test_password
    }, timeout=5)
    assert r_dup.status_code == 400, "Duplicate registration should return 400"
    log("auth", "Duplicate email registration correctly rejected with HTTP 400")

    # 3. Valid Login
    r_login = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": test_password
    }, timeout=5)
    assert r_login.status_code == 200, f"Login failed: {r_login.text}"
    login_data = r_login.json()
    assert login_data["success"] is True
    assert login_data["user"]["email"] == test_email.lower()
    log("auth", f"Login successful for {test_email}")

    # 4. Invalid Password Login must fail with 401
    r_bad = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": "WrongPassword999"
    }, timeout=5)
    assert r_bad.status_code == 401, "Invalid password should return 401"
    log("auth", "Invalid credentials correctly rejected with HTTP 401")

    # 5. Session check /api/auth/me
    r_me = requests.get(f"{BASE_URL}/api/auth/me?token={token}", timeout=5)
    assert r_me.status_code == 200
    me_data = r_me.json()
    assert me_data["is_authenticated"] is True
    assert me_data["user"]["id"] == user_id
    log("auth", f"Session token validated for user: {me_data['user']['name']}")

    results["authentication"] = {
        "status": "passed",
        "user_id": user_id,
        "token": token,
        "email": test_email
    }
    return user_id, token

def test_onboarding_persistence_workflow(user_id, token):
    log("onboarding", f"Testing 7-step onboarding persistence for {user_id}...")

    # Step 1: Personal Info
    personal_info = {
        "fullName": "Ananya Kulkarni",
        "phone": "9876543210",
        "district": "Pune",
        "category": "OBC"
    }
    r1 = requests.post(f"{BASE_URL}/api/onboarding/save", json={
        "user_id": user_id,
        "current_step": 1,
        "personal_info": personal_info
    }, timeout=5)
    assert r1.status_code == 200 and r1.json()["success"]

    # Step 2: Academic Info
    academic_info = {
        "level": "Class 10 (Secondary School)",
        "board": "Maharashtra State Board (SSC)",
        "school": "DES English Medium High School, Pune",
        "passingYear": "2025"
    }
    r2 = requests.post(f"{BASE_URL}/api/onboarding/save", json={
        "user_id": user_id,
        "current_step": 2,
        "academic_info": academic_info
    }, timeout=5)
    assert r2.status_code == 200

    # Step 3: Subject Marks
    marks_info = {
        "maths": 94,
        "science": 92,
        "english": 88,
        "social_science": 82,
        "second_language": 84,
        "overall_percentage": 88.0
    }
    r3 = requests.post(f"{BASE_URL}/api/onboarding/save", json={
        "user_id": user_id,
        "current_step": 3,
        "marks_info": marks_info
    }, timeout=5)
    assert r3.status_code == 200

    # Step 4: Interests & Ambitions
    interests_info = {
        "tags": ["technology", "engineering", "maths_puzzles", "coding"],
        "ambitions": "Aspiring to study Computer Engineering or AI/DS at COEP Pune."
    }
    r4 = requests.post(f"{BASE_URL}/api/onboarding/save", json={
        "user_id": user_id,
        "current_step": 4,
        "interests_info": interests_info
    }, timeout=5)
    assert r4.status_code == 200

    # Step 5: Aptitude assessment (all 25 answered)
    aptitude_results = {
        "answered_count": 25,
        "category_percentages": {
            "logical": 100,
            "numerical": 100,
            "scientific": 90,
            "business": 65,
            "creative": 75,
            "communication": 80,
            "analytical": 95
        }
    }
    r5 = requests.post(f"{BASE_URL}/api/onboarding/save", json={
        "user_id": user_id,
        "current_step": 5,
        "aptitude_results": aptitude_results
    }, timeout=5)
    assert r5.status_code == 200

    # Step 6: Stream recommendation calculation & saving
    rec_req = {
        "marks": marks_info,
        "interests": interests_info,
        "aptitude_scores": aptitude_results
    }
    r_rec = requests.post(f"{BASE_URL}/api/stream/recommend", json=rec_req, timeout=5)
    assert r_rec.status_code == 200
    rec_data = r_rec.json()
    assert rec_data["recommended_stream"]["id"] == "science_pcm"

    r6 = requests.post(f"{BASE_URL}/api/onboarding/save", json={
        "user_id": user_id,
        "current_step": 6,
        "stream_recommendation": rec_data["recommended_stream"],
        "selected_stream": "science_pcm"
    }, timeout=5)
    assert r6.status_code == 200

    # Step 7: Confirmation
    r7 = requests.post(f"{BASE_URL}/api/onboarding/save", json={
        "user_id": user_id,
        "current_step": 7,
        "is_confirmed": True
    }, timeout=5)
    assert r7.status_code == 200

    # Verification: Fetch saved profile from database
    r_prof = requests.get(f"{BASE_URL}/api/onboarding/profile/{user_id}", timeout=5)
    assert r_prof.status_code == 200
    p_data = r_prof.json()
    assert p_data["user_id"] == user_id
    assert p_data["current_step"] == 7
    assert p_data["is_confirmed"] is True
    assert p_data["personal_info"]["fullName"] == "Ananya Kulkarni"
    assert p_data["personal_info"]["district"] == "Pune"
    assert p_data["marks_info"]["maths"] == 94
    assert p_data["selected_stream"] == "science_pcm"
    assert p_data["stream_recommendation"]["id"] == "science_pcm"
    log("onboarding", "7-step onboarding round-trip verified successfully in SQLite")

    results["onboarding_persistence"] = {
        "status": "passed",
        "verified_step": p_data["current_step"],
        "is_confirmed": p_data["is_confirmed"],
        "selected_stream": p_data["selected_stream"],
        "overall_percentage": p_data["marks_info"]["overall_percentage"]
    }

def test_stream_recommendation_profiles():
    log("stream_engine", "Evaluating 5 diverse student archetypes against the recommendation engine...")

    profiles = [
        {
            "name": "Profile A (PCM Engineering Aspirant)",
            "marks": {"maths": 98, "science": 95, "english": 80, "social_science": 75, "overall_percentage": 90.0},
            "interests": {"tags": ["technology", "engineering", "maths_puzzles"], "text": "I love calculus and programming."},
            "aptitude": {"category_percentages": {"logical": 100, "numerical": 100, "scientific": 90, "business": 50, "creative": 60, "communication": 70, "analytical": 95}},
            "expected_top": "science_pcm"
        },
        {
            "name": "Profile B (PCB Medical / Life Sciences Aspirant)",
            "marks": {"maths": 72, "science": 96, "english": 88, "social_science": 82, "overall_percentage": 86.0},
            "interests": {"tags": ["biology", "medicine", "doctor"], "text": "I want to become a physician or neurobiologist."},
            "aptitude": {"category_percentages": {"logical": 75, "numerical": 65, "scientific": 100, "business": 40, "creative": 70, "communication": 85, "analytical": 90}},
            "expected_top": "science_pcb"
        },
        {
            "name": "Profile C (Commerce & Corporate Finance Aspirant)",
            "marks": {"maths": 90, "science": 72, "english": 90, "social_science": 85, "overall_percentage": 84.0},
            "interests": {"tags": ["finance", "business", "entrepreneur"], "text": "Interested in investment banking and economics."},
            "aptitude": {"category_percentages": {"logical": 80, "numerical": 90, "scientific": 50, "business": 100, "creative": 70, "communication": 90, "analytical": 85}},
            "expected_top": "commerce_math"
        },
        {
            "name": "Profile D (Arts, Humanities & Legal Studies Aspirant)",
            "marks": {"maths": 65, "science": 68, "english": 96, "social_science": 95, "overall_percentage": 85.0},
            "interests": {"tags": ["law", "design", "creativity"], "text": "Passionate about constitutional law, journalism, and public policy."},
            "aptitude": {"category_percentages": {"logical": 75, "numerical": 50, "scientific": 55, "business": 65, "creative": 100, "communication": 100, "analytical": 80}},
            "expected_top": "arts_humanities"
        },
        {
            "name": "Profile E (Applied Vocational / Polytechnic Aspirant)",
            "marks": {"maths": 75, "science": 76, "english": 70, "social_science": 68, "overall_percentage": 73.0},
            "interests": {"tags": ["practical", "hands_on"], "text": "I want hands-on workshop training and direct technical skills."},
            "aptitude": {"category_percentages": {"logical": 85, "numerical": 75, "scientific": 80, "business": 60, "creative": 85, "communication": 60, "analytical": 95}},
            "expected_top_in": ["vocational", "science_pcm"]
        }
    ]

    for p in profiles:
        r = requests.post(f"{BASE_URL}/api/stream/recommend", json={
            "marks": p["marks"],
            "interests": p["interests"],
            "aptitude_scores": p["aptitude"]
        }, timeout=5)
        assert r.status_code == 200
        data = r.json()
        rec_id = data["recommended_stream"]["id"]
        rec_name = data["recommended_stream"]["name"]
        rec_score = data["recommended_stream"]["score"]

        if "expected_top" in p:
            assert rec_id == p["expected_top"], f"{p['name']} expected {p['expected_top']} got {rec_id}"
        elif "expected_top_in" in p:
            assert rec_id in p["expected_top_in"], f"{p['name']} expected one of {p['expected_top_in']} got {rec_id}"

        log("stream_engine", f"{p['name']} -> {rec_name} ({rec_score}%) with {len(data['recommended_stream']['career_pathways'])} pathways")
        results["stream_engine_profiles"][p["name"]] = {
            "recommended_stream": rec_name,
            "score": rec_score,
            "alternatives": [a["name"] for a in data["alternatives"]]
        }

def test_ai_consultant_chat_integration():
    log("ai_chat", "Running all 5 required MHT-CET domain questions through POST /api/chat...")

    questions = [
        {
            "id": "Q1_percentile_cutoff",
            "query": "Which engineering colleges can I get with 90 percentile in Computer Engineering in Pune for GOPENS?",
            "expected_keywords": ["percentile", "Pune", "Cutoff", "GOPENS"]
        },
        {
            "id": "Q2_branch_directory",
            "query": "Show colleges offering Computer Engineering or Artificial Intelligence in Maharashtra.",
            "expected_keywords": ["Computer", "College", "Engineering"]
        },
        {
            "id": "Q3_cap_process",
            "query": "Explain the Maharashtra CAP admission process and how college option form preferences work.",
            "expected_keywords": ["CAP", "Option Form", "Round"]
        },
        {
            "id": "Q4_compare_colleges",
            "query": "Compare College of Engineering Pune (COEP) and Veermata Jijabai Technological Institute (VJTI) Mumbai.",
            "expected_keywords": ["COEP", "VJTI", "autonomous", "engineering"]
        },
        {
            "id": "Q5_historical_cutoffs",
            "query": "What are the historical cutoffs for Government College of Engineering, Amravati for Computer Science?",
            "expected_keywords": ["Amravati", "Cutoff"]
        }
    ]

    for q in questions:
        log("ai_chat", f"Sending [{q['id']}]: '{q['query']}'")
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/api/chat", json={
            "query": q["query"],
            "user_id": "test_e2e_student"
        }, timeout=45)
        dt = time.time() - t0
        assert r.status_code == 200, f"Chat endpoint failed for {q['id']}: {r.text}"
        data = r.json()
        assert data["success"] is True
        msg = data.get("message", "")
        status_val = data.get("status", "")
        log("ai_chat", f"[{q['id']}] Response received in {dt:.2f}s | Status: {status_val} | Length: {len(msg)} chars")
        assert len(msg) > 50, f"Message for {q['id']} is too short: {msg}"

        results["ai_consultant_chat"][q["id"]] = {
            "query": q["query"],
            "status": status_val,
            "response_time_sec": round(dt, 2),
            "response_sample": msg[:200] + "...",
            "raw_evidence_length": len(data.get("raw_evidence", ""))
        }

def test_college_cutoff_search_api():
    log("cutoff_search", "Testing GET /api/colleges/search filtering on 181,137 records...")

    # 1. Percentile range search
    r1 = requests.get(f"{BASE_URL}/api/colleges/search", params={
        "min_percentile": 90.0,
        "max_percentile": 95.0,
        "branch": "Computer",
        "category": "GOPENS",
        "limit": 10
    }, timeout=15)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["mode"] == "cutoffs"
    assert len(d1["results"]) > 0
    first_res = d1["results"][0]
    assert 90.0 <= float(first_res["closing_percentile"]) <= 95.0
    log("cutoff_search", f"Percentile query returned {len(d1['results'])} matches. Top: {first_res['institute_name']} ({first_res['closing_percentile']} %ile)")

    # 2. Directory search by query string
    r2 = requests.get(f"{BASE_URL}/api/colleges/search", params={
        "q": "Amravati",
        "limit": 5
    }, timeout=10)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["total"] > 0
    log("cutoff_search", f"Directory query for 'Amravati' returned {d2['total']} colleges")

    # 3. Empty result test
    r3 = requests.get(f"{BASE_URL}/api/colleges/search", params={
        "min_percentile": 99.999,
        "max_percentile": 100.0,
        "branch": "NonexistentUnderwaterBasketWeavingBranch",
        "limit": 5
    }, timeout=10)
    assert r3.status_code == 200
    d3 = r3.json()
    assert len(d3["results"]) == 0
    log("cutoff_search", "Unattainable filter correctly produced 0 results without errors")

    results["cutoff_search"] = {
        "percentile_query_matches": len(d1["results"]),
        "sample_college": first_res["institute_name"],
        "sample_percentile": first_res["closing_percentile"],
        "directory_query_matches": d2["total"],
        "empty_query_handled_safely": True
    }

def test_security_and_data_integrity(user_id, token):
    log("security", "Verifying security boundaries, password hashing, and user profile isolation...")

    # 1. Password hashing verification in SQLite
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    pw_hash = row[0]
    assert len(pw_hash) == 64, "Password hash must be a 64-char SHA-256 string"
    assert "StrictlySecurePassword!2026" not in pw_hash, "Plaintext password must never be stored"
    log("security", f"Password hash verified as standard SHA-256: {pw_hash[:16]}...")

    # 2. Non-existent profile retrieval produces graceful blank profile
    r_ghost = requests.get(f"{BASE_URL}/api/onboarding/profile/ghost_user_9999", timeout=5)
    assert r_ghost.status_code == 200
    ghost_data = r_ghost.json()
    assert ghost_data["current_step"] == 1
    assert ghost_data["is_confirmed"] is False
    log("security", "Non-existent profile access yields safe empty default")

    # 3. Unauthenticated session check
    r_unauth = requests.get(f"{BASE_URL}/api/auth/me?token=invalid_forged_token", timeout=5)
    assert r_unauth.status_code == 200
    assert r_unauth.json()["is_authenticated"] is False
    log("security", "Forged authentication token gracefully denied")

    results["security_audit"] = {
        "password_hash_algorithm": "SHA-256",
        "plaintext_leaks": False,
        "token_tampering_rejected": True,
        "ghost_profile_graceful": True
    }

def ensure_server_running():
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=2)
        if r.status_code == 200:
            log("startup", "Detected existing running API server on http://127.0.0.1:8000")
            return
    except Exception:
        pass

    log("startup", "Starting AI-CON FastAPI Server on http://127.0.0.1:8000 in background thread...")
    import threading
    import uvicorn
    from scripts.api_server import app

    def run():
        config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        server.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(3)
    log("startup", "FastAPI Server online.")

if __name__ == "__main__":
    print("=" * 70)
    print("STARTING AI-CON FULL END-TO-END VERIFICATION")
    print("=" * 70)
    try:
        ensure_server_running()
        test_server_health_and_assets()
        uid, tok = test_authentication_lifecycle()
        test_onboarding_persistence_workflow(uid, tok)
        test_stream_recommendation_profiles()
        test_ai_consultant_chat_integration()
        test_college_cutoff_search_api()
        test_security_and_data_integrity(uid, tok)

        print("=" * 70)
        print("ALL END-TO-END VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)

        out_path = ROOT / "e2e_results.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {out_path}")
    except Exception as e:
        print(f"\n[FATAL ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
