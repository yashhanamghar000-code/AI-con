#!/usr/bin/env python3
"""
AI-CON API Server & Application Backend.
FastAPI backend service powering the modern AI-CON EdTech platform:
- Authentication & Session Management
- 7-Step Student Onboarding & Multi-Step Persistence (SQLite)
- 25-Question Aptitude Assessment & Deterministic Stream Recommendation Engine
- Full Agentic RAG Integration: CutoffAgent (181,137 records) + CollegeInfoAgent (1,041 profiles) + Orchestrator
- Interactive College Explorer & Historical Cutoff Lookup API
- Serves the redesigned responsive frontend.
"""

import os
import sys
import json
import sqlite3
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Path resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
AGENTS_DIR = SCRIPTS_DIR / "agents"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DB_PATH = PROJECT_ROOT / "ai_con_app.db"

for p in (str(PROJECT_ROOT), str(SCRIPTS_DIR), str(AGENTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr

# Initialize FastAPI app
app = FastAPI(
    title="AI-CON College Consultant API",
    description="Evidence-grounded education counselling and student onboarding platform",
    version="2.0.0"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# DATABASE INITIALIZATION (SQLite)
# ============================================================================

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    
    # Student Profiles table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_profiles (
        user_id TEXT PRIMARY KEY,
        personal_info TEXT,
        academic_info TEXT,
        marks_info TEXT,
        interests_info TEXT,
        aptitude_results TEXT,
        stream_recommendation TEXT,
        selected_stream TEXT,
        current_step INTEGER DEFAULT 1,
        is_confirmed INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    
    # Chat History table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT,
        matched_college TEXT,
        evidence TEXT,
        created_at TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

# ============================================================================
# AI-CON AGENTS SINGLETON (Lazy loaded for instant API startup)
# ============================================================================

class AgentManager:
    def __init__(self):
        self.cutoff_agent = None
        self.info_agent = None
        self.orchestrator = None
        self.is_loaded = False
        self._load_error = None

    def load_agents(self):
        if self.is_loaded:
            return
        try:
            from cutoff_agent import CutoffAgent
            from college_info_agent import CollegeInfoAgent
            from orchestrator import Orchestrator

            cutoffs_dir = PROJECT_ROOT / "cutoffs" / "phase3_final_staging"
            vector_index_dir = PROJECT_ROOT / "vector_index"

            if cutoffs_dir.is_dir():
                self.cutoff_agent = CutoffAgent(cutoffs_dir)
            if vector_index_dir.is_dir():
                try:
                    # Detect cached local HuggingFace snapshot to enable 100% offline vector retrieval
                    snap_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots"
                    local_model = "sentence-transformers/all-MiniLM-L6-v2"
                    if snap_dir.is_dir():
                        for s in snap_dir.iterdir():
                            if s.is_dir():
                                local_model = str(s)
                                break
                    self.info_agent = CollegeInfoAgent(vector_index_dir, model=local_model)
                except Exception as e:
                    print(f"[Warning] CollegeInfoAgent load error: {e}")

            self.orchestrator = Orchestrator(self.cutoff_agent, self.info_agent)
            self.is_loaded = True
            print("[AI-CON Backend] Agents loaded successfully.")
        except Exception as e:
            self._load_error = str(e)
            print(f"[Warning] Agent loading error: {e}")

agent_manager = AgentManager()

# Startup event remains non-blocking for lightning-fast server boot
@app.on_event("startup")
def on_startup():
    print("[AI-CON Backend] API Server online and ready. Agents will load lazily on first query.")

# ============================================================================
# DATA MODELS
# ============================================================================

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class OnboardingSaveRequest(BaseModel):
    user_id: str
    current_step: Optional[int] = None
    personal_info: Optional[Dict[str, Any]] = None
    academic_info: Optional[Dict[str, Any]] = None
    marks_info: Optional[Dict[str, Any]] = None
    interests_info: Optional[Dict[str, Any]] = None
    aptitude_results: Optional[Dict[str, Any]] = None
    stream_recommendation: Optional[Dict[str, Any]] = None
    selected_stream: Optional[str] = None
    is_confirmed: Optional[bool] = None

class StreamRecommendRequest(BaseModel):
    marks: Dict[str, Any]
    interests: Dict[str, Any]
    aptitude_scores: Dict[str, Any]

class ChatRequest(BaseModel):
    query: str
    user_id: Optional[str] = "guest"
    stream_context: Optional[str] = None

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email.strip().lower(),))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    
    user_id = "user_" + hashlib.md5(f"{req.email}_{time.time()}".encode()).hexdigest()[:12]
    pw_hash = hash_password(req.password)
    now = datetime.utcnow().isoformat()
    
    cursor.execute(
        "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, req.name.strip(), req.email.strip().lower(), pw_hash, now)
    )
    # Initialize blank profile
    cursor.execute(
        "INSERT INTO student_profiles (user_id, current_step, is_confirmed, updated_at) VALUES (?, 1, 0, ?)",
        (user_id, now)
    )
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "token": f"aicon_token_{user_id}",
        "user": {
            "id": user_id,
            "name": req.name.strip(),
            "email": req.email.strip().lower()
        }
    }

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    pw_hash = hash_password(req.password)
    cursor.execute(
        "SELECT id, name, email FROM users WHERE email = ? AND password_hash = ?",
        (req.email.strip().lower(), pw_hash)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    
    return {
        "success": True,
        "token": f"aicon_token_{row['id']}",
        "user": {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"]
        }
    }

@app.get("/api/auth/me")
def get_current_user(token: Optional[str] = None):
    # Default to demo user if no token provided
    default_user = {
        "id": "demo_student_01",
        "name": "Aarav Sharma",
        "email": "aarav.sharma@example.com"
    }
    if not token or not token.startswith("aicon_token_"):
        return {"user": default_user, "is_authenticated": False}
    
    user_id = token.replace("aicon_token_", "")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"user": default_user, "is_authenticated": False}
    
    return {
        "user": {"id": row["id"], "name": row["name"], "email": row["email"]},
        "is_authenticated": True
    }

# ============================================================================
# STUDENT ONBOARDING & PROFILE ENDPOINTS
# ============================================================================

@app.post("/api/onboarding/save")
def save_onboarding(req: OnboardingSaveRequest):
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    # Check if profile exists
    cursor.execute("SELECT user_id FROM student_profiles WHERE user_id = ?", (req.user_id,))
    exists = cursor.fetchone()
    
    if not exists:
        cursor.execute(
            """INSERT INTO student_profiles 
               (user_id, personal_info, academic_info, marks_info, interests_info, 
                aptitude_results, stream_recommendation, selected_stream, current_step, is_confirmed, updated_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                req.user_id,
                json.dumps(req.personal_info) if req.personal_info else None,
                json.dumps(req.academic_info) if req.academic_info else None,
                json.dumps(req.marks_info) if req.marks_info else None,
                json.dumps(req.interests_info) if req.interests_info else None,
                json.dumps(req.aptitude_results) if req.aptitude_results else None,
                json.dumps(req.stream_recommendation) if req.stream_recommendation else None,
                req.selected_stream,
                req.current_step or 1,
                1 if req.is_confirmed else 0,
                now
            )
        )
    else:
        # Build dynamic update
        updates = ["updated_at = ?"]
        params = [now]
        if req.personal_info is not None:
            updates.append("personal_info = ?")
            params.append(json.dumps(req.personal_info))
        if req.academic_info is not None:
            updates.append("academic_info = ?")
            params.append(json.dumps(req.academic_info))
        if req.marks_info is not None:
            updates.append("marks_info = ?")
            params.append(json.dumps(req.marks_info))
        if req.interests_info is not None:
            updates.append("interests_info = ?")
            params.append(json.dumps(req.interests_info))
        if req.aptitude_results is not None:
            updates.append("aptitude_results = ?")
            params.append(json.dumps(req.aptitude_results))
        if req.stream_recommendation is not None:
            updates.append("stream_recommendation = ?")
            params.append(json.dumps(req.stream_recommendation))
        if req.selected_stream is not None:
            updates.append("selected_stream = ?")
            params.append(req.selected_stream)
        if req.current_step is not None:
            updates.append("current_step = ?")
            params.append(req.current_step)
        if req.is_confirmed is not None:
            updates.append("is_confirmed = ?")
            params.append(1 if req.is_confirmed else 0)
        
        params.append(req.user_id)
        sql = f"UPDATE student_profiles SET {', '.join(updates)} WHERE user_id = ?"
        cursor.execute(sql, params)

    conn.commit()
    conn.close()
    return {"success": True, "message": "Profile saved successfully.", "updated_at": now}

@app.get("/api/onboarding/profile/{user_id}")
def get_profile(user_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {
            "user_id": user_id,
            "current_step": 1,
            "is_confirmed": False,
            "personal_info": {},
            "academic_info": {},
            "marks_info": {},
            "interests_info": {},
            "aptitude_results": {},
            "stream_recommendation": {},
            "selected_stream": None
        }
    
    return {
        "user_id": row["user_id"],
        "current_step": row["current_step"],
        "is_confirmed": bool(row["is_confirmed"]),
        "personal_info": json.loads(row["personal_info"]) if row["personal_info"] else {},
        "academic_info": json.loads(row["academic_info"]) if row["academic_info"] else {},
        "marks_info": json.loads(row["marks_info"]) if row["marks_info"] else {},
        "interests_info": json.loads(row["interests_info"]) if row["interests_info"] else {},
        "aptitude_results": json.loads(row["aptitude_results"]) if row["aptitude_results"] else {},
        "stream_recommendation": json.loads(row["stream_recommendation"]) if row["stream_recommendation"] else {},
        "selected_stream": row["selected_stream"],
        "updated_at": row["updated_at"]
    }

# ============================================================================
# DETERMINISTIC STREAM RECOMMENDATION ENGINE
# ============================================================================

@app.post("/api/stream/recommend")
def calculate_stream_recommendation(req: StreamRecommendRequest):
    """
    Deterministic, transparent scoring engine that integrates:
    1. Class 10 academic performance (subject-wise percentages)
    2. Student interests & future ambitions
    3. 25-Question Aptitude Assessment scores across 7 dimensions.
    """
    marks = req.marks or {}
    interests = req.interests or {}
    aptitude = req.aptitude_scores or {}

    # Extract subject percentages
    maths_pct = float(marks.get("maths", 80))
    science_pct = float(marks.get("science", 80))
    english_pct = float(marks.get("english", 80))
    social_pct = float(marks.get("social_science", 75))
    overall_pct = float(marks.get("overall_percentage", 78))

    # Extract category aptitude scores (0 to 100 normalized)
    cat_scores = aptitude.get("category_percentages") or {
        "logical": 75,
        "numerical": 75,
        "scientific": 75,
        "business": 60,
        "creative": 65,
        "communication": 70,
        "analytical": 75
    }

    # Scoring models for each stream (0 - 100)
    # Stream 1: Science (PCM) - Engineering, Tech, Architecture, Defence
    score_pcm = (
        0.30 * maths_pct +
        0.25 * science_pct +
        0.20 * cat_scores.get("numerical", 70) +
        0.15 * cat_scores.get("logical", 70) +
        0.10 * cat_scores.get("analytical", 70)
    )
    if "technology" in str(interests).lower() or "engineering" in str(interests).lower():
        score_pcm += 5

    # Stream 2: Science (PCB) - Medicine, Biotechnology, Pharmacy, Life Sciences
    score_pcb = (
        0.35 * science_pct +
        0.15 * maths_pct +
        0.25 * cat_scores.get("scientific", 70) +
        0.15 * cat_scores.get("analytical", 70) +
        0.10 * cat_scores.get("logical", 70)
    )
    if "medicine" in str(interests).lower() or "biology" in str(interests).lower() or "doctor" in str(interests).lower():
        score_pcb += 6

    # Stream 3: Commerce (with Mathematics) - Finance, CA, Economics, Banking, Fintech
    score_comm_math = (
        0.30 * maths_pct +
        0.15 * english_pct +
        0.25 * cat_scores.get("business", 60) +
        0.20 * cat_scores.get("numerical", 60) +
        0.10 * cat_scores.get("analytical", 60)
    )
    if "business" in str(interests).lower() or "finance" in str(interests).lower() or "entrepreneur" in str(interests).lower():
        score_comm_math += 6

    # Stream 4: Arts & Humanities - Law, Design, Journalism, Psychology, Civil Services
    score_arts = (
        0.30 * social_pct +
        0.25 * english_pct +
        0.20 * cat_scores.get("creative", 65) +
        0.15 * cat_scores.get("communication", 65) +
        0.10 * cat_scores.get("analytical", 65)
    )
    if "design" in str(interests).lower() or "law" in str(interests).lower() or "creativity" in str(interests).lower():
        score_arts += 6

    # Stream 5: Vocational / Applied Skills - Polytechnic Diploma, IT, Applied Design
    score_vocational = (
        0.25 * cat_scores.get("analytical", 65) +
        0.25 * cat_scores.get("creative", 65) +
        0.25 * cat_scores.get("scientific", 65) +
        0.25 * (maths_pct + science_pct) / 2
    )
    if "practical" in str(interests).lower():
        score_vocational += 5

    stream_scores = [
        {
            "id": "science_pcm",
            "name": "Science (PCM)",
            "headline": "Physics, Chemistry, Mathematics",
            "score": round(min(98.0, score_pcm), 1),
            "badge": "Engineering & Technology",
            "description": "Ideal for students driven by quantitative problem-solving, technological innovation, computing, and structural design.",
            "key_subjects": ["Physics", "Chemistry", "Mathematics", "Computer Science / Information Tech"],
            "career_pathways": ["B.Tech / B.E. (Computer, AI/DS, Mechanical, Civil)", "Architecture (B.Arch)", "Data Science & Mathematics", "National Defence Academy (NDA)"],
            "reasons": [
                f"Strong performance in Mathematics ({maths_pct:.0f}%) and Science ({science_pct:.0f}%)",
                f"High Numerical ({cat_scores.get('numerical', 70):.0f}%) and Logical ({cat_scores.get('logical', 70):.0f}%) aptitude score",
                "High alignment with technological and engineering aspirations"
            ]
        },
        {
            "id": "science_pcb",
            "name": "Science (PCB)",
            "headline": "Physics, Chemistry, Biology",
            "score": round(min(98.0, score_pcb), 1),
            "badge": "Medicine & Healthcare",
            "description": "Recommended for inquisitive students passionate about human physiology, living ecosystems, healthcare, and clinical sciences.",
            "key_subjects": ["Physics", "Chemistry", "Biology", "Biotechnology / Psychology"],
            "career_pathways": ["MBBS / BDS / BAMS / BHMS", "Pharmacy (B.Pharm)", "Biotechnology & Bioinformatics", "Clinical Research & Genetics"],
            "reasons": [
                f"Excellent scientific grasp in Science ({science_pct:.0f}%)",
                f"High Scientific Inquiry aptitude ({cat_scores.get('scientific', 70):.0f}%)",
                "Interest in healthcare, life sciences, and biological research"
            ]
        },
        {
            "id": "commerce_math",
            "name": "Commerce (with Mathematics)",
            "headline": "Accountancy, Economics, Business, Mathematics",
            "score": round(min(98.0, score_comm_math), 1),
            "badge": "Finance & Business Strategy",
            "description": "A powerful combination for students fascinated by market dynamics, corporate finance, economics, entrepreneurship, and quantitative wealth management.",
            "key_subjects": ["Accountancy", "Business Studies", "Economics", "Mathematics"],
            "career_pathways": ["Chartered Accountancy (CA)", "Investment Banking & Fintech", "Corporate Law & Management (BBA / BMS)", "Economic Data Analysis"],
            "reasons": [
                f"Solid mathematical ability ({maths_pct:.0f}%) combined with business aptitude",
                f"Commercial & Financial reasoning score: {cat_scores.get('business', 60):.0f}%",
                "Strong analytical foundation for corporate leadership"
            ]
        },
        {
            "id": "arts_humanities",
            "name": "Arts / Humanities",
            "headline": "History, Political Science, Psychology, Sociology",
            "score": round(min(98.0, score_arts), 1),
            "badge": "Law, Design & Public Policy",
            "description": "Tailored for expressive thinkers interested in human culture, constitutional law, public governance, media communications, and creative visual arts.",
            "key_subjects": ["Political Science", "Psychology", "Sociology", "English Literature / Fine Arts"],
            "career_pathways": ["Law (BA LLB / National Law Universities)", "UI/UX & Product Design (B.Des)", "Civil Services (UPSC / MPSC)", "Journalism & Media Communications"],
            "reasons": [
                f"Strong verbal and expressive ability in English ({english_pct:.0f}%) and Social Science ({social_pct:.0f}%)",
                f"Creative and Communication aptitude score: {cat_scores.get('creative', 65):.0f}%",
                "Interest in creative synthesis, societal dynamics, and policy"
            ]
        },
        {
            "id": "vocational",
            "name": "Vocational / Applied Polytechnic",
            "headline": "Hands-on Technical Diploma & Skill Specialization",
            "score": round(min(95.0, score_vocational), 1),
            "badge": "Hands-on Industry Skills",
            "description": "Direct, practical technical education enabling students to learn practical engineering skills and enter industry or transition directly into second-year engineering.",
            "key_subjects": ["Applied Mechanics", "Basic Electrical & Electronics", "Workshop Practice", "Technical Drawing"],
            "career_pathways": ["Polytechnic Engineering Diploma (3-year)", "Direct Second Year B.Tech Entry", "Industrial Design & Robotics Technician", "Skill-Based Entrepreneurship"],
            "reasons": [
                f"Practical problem-solving aptitude: {cat_scores.get('analytical', 65):.0f}%",
                "Preference for hands-on, direct laboratory and workshop learning",
                "Fast-track trajectory to technical employment or lateral degree admission"
            ]
        }
    ]

    # Sort descending by score
    stream_scores.sort(key=lambda s: s["score"], reverse=True)
    primary = stream_scores[0]
    alternatives = stream_scores[1:3]

    return {
        "success": True,
        "recommended_stream": primary,
        "alternatives": alternatives,
        "all_streams": stream_scores,
        "evaluation_summary": {
            "overall_percentage": overall_pct,
            "top_subject_strength": "Mathematics" if maths_pct >= science_pct else "Science",
            "aptitude_strength": max(cat_scores, key=cat_scores.get) if cat_scores else "General Problem Solving",
            "generated_at": datetime.utcnow().isoformat()
        }
    }

# ============================================================================
# AI CONSULTANT CHAT INTEGRATION (Direct Orchestrator RAG)
# ============================================================================

@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    Routes student query directly to AI-CON Orchestrator.
    Retrieves exact cutoff records from CutoffAgent, college profiles from CollegeInfoAgent,
    and returns grounded citations and advice.
    """
    agent_manager.load_agents()
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query provided.")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    # Save user query
    cursor.execute(
        "INSERT INTO chat_history (user_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
        (req.user_id, query, now)
    )

    # Process query through Orchestrator
    if agent_manager.orchestrator is not None:
        try:
            res = agent_manager.orchestrator.answer(query)
            status_val = res.get("status", "answered")
            matched_college = res.get("matched_college")
            evidence = res.get("evidence", "")
            message = res.get("message", "")
            total_matches = res.get("total_matches", 0)
            candidates = res.get("candidates", [])
            intent = res.get("intent", "info")
            query_type = res.get("query_type", "single_college")
            llm_answer = res.get("answer")

            # Format final readable message for student
            if message and not llm_answer:
                display_text = message
            elif llm_answer:
                display_text = llm_answer
            elif evidence:
                # Synthesize clean student-friendly text from retrieved evidence
                display_text = f"Here is the verified information for your query:\n\n{evidence}"
            else:
                display_text = "I could not locate specific historical records matching those exact parameters. Please try refining your college name, category, or branch."

            # Save assistant response
            cursor.execute(
                """INSERT INTO chat_history 
                   (user_id, role, content, status, matched_college, evidence, created_at) 
                   VALUES (?, 'assistant', ?, ?, ?, ?, ?)""",
                (req.user_id, display_text, status_val, matched_college, evidence, now)
            )
            conn.commit()
            conn.close()

            return {
                "success": True,
                "status": status_val,
                "intent": intent,
                "query_type": query_type,
                "matched_college": matched_college,
                "total_matches": total_matches,
                "candidates": candidates,
                "message": display_text,
                "raw_evidence": evidence,
                "timestamp": now
            }
        except Exception as e:
            conn.close()
            return {
                "success": False,
                "status": "error",
                "message": f"Error processing query in RAG pipeline: {str(e)}",
                "raw_evidence": ""
            }
    else:
        conn.close()
        return {
            "success": True,
            "status": "fallback",
            "message": "AI-CON agent pipeline is currently initializing. Please try your question in a moment.",
            "raw_evidence": ""
        }

@app.get("/api/chat/history/{user_id}")
def get_chat_history(user_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, status, matched_college, evidence, created_at FROM chat_history WHERE user_id = ? ORDER BY id ASC LIMIT 50",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return {"history": [dict(r) for r in rows]}

# ============================================================================
# COLLEGE EXPLORER & HISTORICAL CUTOFF API
# ============================================================================

@app.get("/api/colleges/search")
def search_colleges(
    q: Optional[str] = None,
    district: Optional[str] = None,
    branch: Optional[str] = None,
    category: Optional[str] = "GOPENS",
    min_percentile: Optional[float] = None,
    max_percentile: Optional[float] = None,
    limit: int = 15
):
    agent_manager.load_agents()
    results = []
    
    # 1. Use CutoffAgent.find_colleges if percentile or branch search
    if (min_percentile is not None or max_percentile is not None or branch) and agent_manager.cutoff_agent and hasattr(agent_manager.cutoff_agent, "find_colleges"):
        try:
            matches = agent_manager.cutoff_agent.find_colleges(
                min_percentile=min_percentile,
                max_percentile=max_percentile,
                branch_query=branch,
                category=category,
                limit=limit
            )
            for m in matches:
                results.append({
                    "institute_code": m.get("institute_code"),
                    "institute_name": m.get("institute_name"),
                    "branch": m.get("branch"),
                    "category": m.get("category"),
                    "closing_rank": m.get("closing_rank"),
                    "closing_percentile": m.get("closing_percentile"),
                    "academic_year": m.get("academic_year"),
                    "round": m.get("round"),
                    "source_file": m.get("source_file")
                })
            return {"results": results, "total": len(results), "mode": "cutoffs"}
        except Exception as e:
            print(f"[Search Cutoffs Error] {e}")

    # 2. Search directory by query string or list colleges
    # Check CutoffAgent's indexed institutes first
    if agent_manager.cutoff_agent and hasattr(agent_manager.cutoff_agent, "_by_code"):
        seen_codes = set()
        for code, years in agent_manager.cutoff_agent._by_code.items():
            for y in reversed(sorted(years.keys())):
                c_data = years[y]
                name = c_data.get("institute_name", "")
                inst_code = c_data.get("institute_code", code)
                if inst_code in seen_codes:
                    continue
                if q and (q.lower() not in name.lower()) and (q.lower() not in str(inst_code).lower()):
                    continue
                seen_codes.add(inst_code)
                results.append({
                    "institute_code": inst_code,
                    "institute_name": name,
                    "academic_year": y
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        if results:
            return {"results": results, "total": len(results), "mode": "directory"}

    # 3. Fallback to vector collection or name index
    if agent_manager.info_agent:
        try:
            name_idx = agent_manager.info_agent.list_name_index()
            count = 0
            for name, meta in name_idx.items():
                if q and q.lower() not in name.lower():
                    continue
                results.append({
                    "institute_code": meta.get("institute_code"),
                    "institute_name": name,
                    "record_id": meta.get("record_id")
                })
                count += 1
                if count >= limit:
                    break
            return {"results": results, "total": len(results), "mode": "directory"}
        except Exception as e:
            print(f"[Search Directory Error] {e}")

    return {"results": [], "total": 0, "mode": "empty"}

# ============================================================================
# SYSTEM HEALTH & METADATA
# ============================================================================

@app.get("/api/health")
def health():
    cutoff_count = len(agent_manager.cutoff_agent._by_code) if (agent_manager.cutoff_agent and hasattr(agent_manager.cutoff_agent, "_by_code")) else 0
    info_count = agent_manager.info_agent.collection.count() if (agent_manager.info_agent and hasattr(agent_manager.info_agent, "collection")) else 0
    
    return {
        "status": "healthy",
        "service": "AI-CON College Consultant",
        "agents_loaded": agent_manager.is_loaded,
        "cutoffs_indexed_institutes": cutoff_count,
        "vector_profiles_indexed": info_count,
        "database": "sqlite:ai_con_app.db",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# FRONTEND STATIC FILES & SPA FALLBACK
# ============================================================================

if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return {"message": "AI-CON Frontend directory found. index.html is being prepared."}

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    # If path corresponds to an existing static file, serve it
    static_file = FRONTEND_DIR / full_path
    if static_file.is_file():
        return FileResponse(str(static_file))
    
    # Otherwise fallback to index.html for client-side routing
    index_file = FRONTEND_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return JSONResponse(status_code=404, content={"detail": "Not found"})

if __name__ == "__main__":
    import uvicorn
    print("Starting AI-CON API Server on http://127.0.0.1:8000...")
    uvicorn.run("scripts.api_server:app", host="127.0.0.1", port=8000, reload=False)
