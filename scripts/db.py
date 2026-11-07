# -*- coding: utf-8 -*-
"""
AI-CON Unified Database Engine.
Provides production-ready database connectivity supporting:
1. PostgreSQL (via DATABASE_URL or POSTGRES_* environment variables)
2. SQLite (local fallback to ai_con_app.db)

Ensures 100% strict tenant isolation: every profile and chat record is bound
to authenticated user_id extracted from cryptographically verified JWT tokens.
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "ai_con_app.db"

class DatabaseManager:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        self.is_postgres = False
        self._check_engine()

    def _check_engine(self):
        if self.db_url and (self.db_url.startswith("postgres://") or self.db_url.startswith("postgresql://")):
            # Modern SQLAlchemy/psycopg2 prefers postgresql://
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)
            try:
                import psycopg2
                conn = psycopg2.connect(self.db_url, connect_timeout=3)
                conn.close()
                self.is_postgres = True
                print(f"[AI-CON DB] Connected to PostgreSQL instance.")
                return
            except Exception as e:
                print(f"[AI-CON DB Warning] PostgreSQL connection failed ({e}). Falling back to SQLite.")

        self.is_postgres = False
        self.sqlite_path = DEFAULT_SQLITE_PATH

    def get_connection(self):
        if self.is_postgres:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(self.db_url)
            conn.autocommit = True
            return conn, "%s", RealDictCursor
        else:
            conn = sqlite3.connect(str(self.sqlite_path))
            conn.row_factory = sqlite3.Row
            return conn, "?", None

    def init_db(self):
        conn, ph, _ = self.get_connection()
        cursor = conn.cursor()

        if self.is_postgres:
            # PostgreSQL schema
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_profiles (
                user_id VARCHAR(64) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                personal_info TEXT,
                academic_info TEXT,
                marks_info TEXT,
                interests_info TEXT,
                aptitude_results TEXT,
                stream_recommendation TEXT,
                selected_stream VARCHAR(128),
                current_step INTEGER DEFAULT 1,
                is_confirmed INTEGER DEFAULT 0,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                role VARCHAR(32) NOT NULL,
                content TEXT NOT NULL,
                status VARCHAR(64),
                matched_college TEXT,
                evidence TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_user_id ON chat_history (user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);")
        else:
            # SQLite schema
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
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
            );
            """)
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
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_user_id ON chat_history (user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);")
            conn.commit()

        cursor.close()
        conn.close()

    # User repository operations
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        conn, ph, cursor_factory = self.get_connection()
        cursor = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()
        sql = f"SELECT id, name, email, password_hash, created_at FROM users WHERE LOWER(email) = LOWER({ph})"
        cursor.execute(sql, (email.strip(),))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn, ph, cursor_factory = self.get_connection()
        cursor = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()
        sql = f"SELECT id, name, email, password_hash, created_at FROM users WHERE id = {ph}"
        cursor.execute(sql, (user_id.strip(),))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return dict(row) if row else None

    def create_user(self, user_id: str, name: str, email: str, password_hash: str) -> Dict[str, Any]:
        conn, ph, _ = self.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        sql_u = f"INSERT INTO users (id, name, email, password_hash, created_at) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})"
        cursor.execute(sql_u, (user_id, name.strip(), email.strip().lower(), password_hash, now))
        sql_p = f"INSERT INTO student_profiles (user_id, current_step, is_confirmed, updated_at) VALUES ({ph}, 1, 0, {ph})"
        cursor.execute(sql_p, (user_id, now))
        if not self.is_postgres:
            conn.commit()
        cursor.close()
        conn.close()
        return {"id": user_id, "name": name.strip(), "email": email.strip().lower(), "created_at": now}

    # Profile repository operations (Strict user isolation)
    def get_student_profile(self, user_id: str) -> Dict[str, Any]:
        conn, ph, cursor_factory = self.get_connection()
        cursor = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()
        sql = f"SELECT * FROM student_profiles WHERE user_id = {ph}"
        cursor.execute(sql, (user_id,))
        row = cursor.fetchone()
        cursor.close()
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

        data = dict(row)
        def _parse(field):
            val = data.get(field)
            if not val:
                return {}
            if isinstance(val, dict):
                return val
            try:
                return json.loads(val)
            except Exception:
                return {}

        return {
            "user_id": data["user_id"],
            "current_step": data.get("current_step", 1),
            "is_confirmed": bool(data.get("is_confirmed", 0)),
            "personal_info": _parse("personal_info"),
            "academic_info": _parse("academic_info"),
            "marks_info": _parse("marks_info"),
            "interests_info": _parse("interests_info"),
            "aptitude_results": _parse("aptitude_results"),
            "stream_recommendation": _parse("stream_recommendation"),
            "selected_stream": data.get("selected_stream"),
            "updated_at": str(data.get("updated_at", ""))
        }

    def upsert_student_profile(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        conn, ph, cursor_factory = self.get_connection()
        cursor = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()
        now = datetime.utcnow().isoformat()

        # Check existing
        cursor.execute(f"SELECT user_id FROM student_profiles WHERE user_id = {ph}", (user_id,))
        exists = cursor.fetchone()

        p_info = json.dumps(data["personal_info"]) if data.get("personal_info") is not None else None
        a_info = json.dumps(data["academic_info"]) if data.get("academic_info") is not None else None
        m_info = json.dumps(data["marks_info"]) if data.get("marks_info") is not None else None
        i_info = json.dumps(data["interests_info"]) if data.get("interests_info") is not None else None
        apt_info = json.dumps(data["aptitude_results"]) if data.get("aptitude_results") is not None else None
        s_rec = json.dumps(data["stream_recommendation"]) if data.get("stream_recommendation") is not None else None
        sel_stream = data.get("selected_stream")
        step = data.get("current_step")
        confirmed = 1 if data.get("is_confirmed") else 0

        if not exists:
            sql = f"""
            INSERT INTO student_profiles 
            (user_id, personal_info, academic_info, marks_info, interests_info, 
             aptitude_results, stream_recommendation, selected_stream, current_step, is_confirmed, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """
            cursor.execute(sql, (user_id, p_info, a_info, m_info, i_info, apt_info, s_rec, sel_stream, step or 1, confirmed, now))
        else:
            updates = [f"updated_at = {ph}"]
            params = [now]
            if p_info is not None:
                updates.append(f"personal_info = {ph}")
                params.append(p_info)
            if a_info is not None:
                updates.append(f"academic_info = {ph}")
                params.append(a_info)
            if m_info is not None:
                updates.append(f"marks_info = {ph}")
                params.append(m_info)
            if i_info is not None:
                updates.append(f"interests_info = {ph}")
                params.append(i_info)
            if apt_info is not None:
                updates.append(f"aptitude_results = {ph}")
                params.append(apt_info)
            if s_rec is not None:
                updates.append(f"stream_recommendation = {ph}")
                params.append(s_rec)
            if sel_stream is not None:
                updates.append(f"selected_stream = {ph}")
                params.append(sel_stream)
            if step is not None:
                updates.append(f"current_step = {ph}")
                params.append(step)
            if data.get("is_confirmed") is not None:
                updates.append(f"is_confirmed = {ph}")
                params.append(confirmed)

            params.append(user_id)
            sql = f"UPDATE student_profiles SET {', '.join(updates)} WHERE user_id = {ph}"
            cursor.execute(sql, tuple(params))

        if not self.is_postgres:
            conn.commit()
        cursor.close()
        conn.close()
        return {"success": True, "updated_at": now}

    # Chat history operations (Strict user isolation)
    def add_chat_message(self, user_id: str, role: str, content: str, status: Optional[str] = None,
                         matched_college: Optional[str] = None, evidence: Optional[str] = None):
        conn, ph, _ = self.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        sql = f"""
        INSERT INTO chat_history (user_id, role, content, status, matched_college, evidence, created_at)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        cursor.execute(sql, (user_id, role, content, status, matched_college, evidence, now))
        if not self.is_postgres:
            conn.commit()
        cursor.close()
        conn.close()

    def get_chat_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn, ph, cursor_factory = self.get_connection()
        cursor = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()
        sql = f"""
        SELECT role, content, status, matched_college, evidence, created_at 
        FROM chat_history 
        WHERE user_id = {ph} 
        ORDER BY id ASC LIMIT {ph}
        """
        cursor.execute(sql, (user_id, limit))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [dict(r) for r in rows]

# Singleton instance
db_manager = DatabaseManager()
db_manager.init_db()
