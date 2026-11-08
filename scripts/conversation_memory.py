"""
AI-CON Session Conversation Memory and Student Profile Store (Task 3).
Provides:
1. Typed Student Profile (StudentProfileState)
2. Typed Conversation State (ConversationSessionState)
3. Persistent Session Store backed by existing DatabaseManager (SQLite / Postgres)
   with fallback in-memory caching for zero latency.
4. Strict multi-session isolation to prevent context leakage.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from scripts.db import DatabaseManager

logger = logging.getLogger("aicon.conversation_memory")


class ShortlistRecord(BaseModel):
    institute_code: str
    institute_name: str
    branch: str
    category: str
    cutoff_percentile: Optional[float] = None
    closing_rank: Optional[int] = None
    predicted_cutoff: Optional[float] = None
    predicted_rank: Optional[int] = None
    popularity_score: Optional[int] = None
    roi_tier: Optional[str] = None
    tier: Optional[str] = None
    evidence_id: Optional[str] = None
    academic_year: Optional[str] = None
    round_no: Optional[int] = None


class StudentProfileState(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    exam: Optional[str] = None
    percentile: Optional[float] = None
    merit_rank: Optional[int] = None
    category_stated: Optional[str] = None
    normalized_seat_code: Optional[str] = None
    domicile: Optional[str] = None
    home_university: Optional[str] = None
    location_preference: Optional[str] = None
    location_scope_notes: Optional[str] = None
    preferred_branches: List[str] = Field(default_factory=list)
    budget_preference: Optional[str] = None
    preferred_ranking_criteria: Optional[str] = None
    requested_unique_colleges: Optional[int] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    field_update_history: Dict[str, str] = Field(default_factory=dict)

    def update_field(self, field_name: str, new_value: Any) -> bool:
        """Update a field only if a new non-null value is explicitly provided.
        Never infer category, domicile or rank if unknown.
        """
        if new_value is None:
            return False
        curr_val = getattr(self, field_name, None)
        if curr_val != new_value:
            setattr(self, field_name, new_value)
            now_iso = datetime.now(timezone.utc).isoformat()
            self.updated_at = now_iso
            self.field_update_history[field_name] = now_iso
            return True
        return False


class ConversationSessionState(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    profile: StudentProfileState
    last_query: Optional[str] = None
    last_query_timestamp: Optional[str] = None
    last_intent: Optional[str] = None
    last_shortlist: List[ShortlistRecord] = Field(default_factory=list)
    raw_shortlist_dicts: List[Dict[str, Any]] = Field(default_factory=list)
    turn_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_legacy_context(self) -> Dict[str, Any]:
        """Expose compatible dictionary for existing orchestrator callers."""
        return {
            "session_id": self.session_id,
            "last_shortlist": self.raw_shortlist_dicts or [r.model_dump() for r in self.last_shortlist],
            "location": self.profile.location_preference,
            "location_scope_notes": self.profile.location_scope_notes,
            "category": self.profile.normalized_seat_code or self.profile.category_stated,
            "category_stated": self.profile.category_stated,
            "preferred_branches": self.profile.preferred_branches,
            "percentile": self.profile.percentile,
            "rank": self.profile.merit_rank,
            "requested_unique_colleges": self.profile.requested_unique_colleges,
            "ranking_objective": self.profile.preferred_ranking_criteria,
            "last_query": self.last_query,
            "turn_count": self.turn_count,
        }


class ConversationMemoryStore:
    """Session-based conversation memory store supporting SQLite/Postgres persistence."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self._ensure_schema()
        self._cache: Dict[str, ConversationSessionState] = {}

    def _ensure_schema(self):
        try:
            conn, ph, _ = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                session_id VARCHAR(128) PRIMARY KEY,
                user_id VARCHAR(64),
                profile_json TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not initialize conversation_sessions schema: %s", e)

    def get_or_create_session(self, session_id: str, user_id: Optional[str] = None) -> ConversationSessionState:
        """Retrieve existing session state or create a fresh isolated session."""
        if not session_id:
            session_id = f"sess_{int(datetime.now().timestamp() * 1000)}"

        if session_id in self._cache:
            sess = self._cache[session_id]
            if user_id and not sess.user_id:
                sess.user_id = user_id
                sess.profile.user_id = user_id
            return sess

        # Check DB
        try:
            conn, ph, _ = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT profile_json, state_json FROM conversation_sessions WHERE session_id = {ph}", (session_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                prof_data = json.loads(row[0])
                state_data = json.loads(row[1])
                prof = StudentProfileState(**prof_data)
                sess = ConversationSessionState(
                    session_id=session_id,
                    user_id=state_data.get("user_id"),
                    profile=prof,
                    last_query=state_data.get("last_query"),
                    last_query_timestamp=state_data.get("last_query_timestamp"),
                    last_intent=state_data.get("last_intent"),
                    last_shortlist=[ShortlistRecord(**r) for r in state_data.get("last_shortlist", [])],
                    raw_shortlist_dicts=state_data.get("raw_shortlist_dicts", []),
                    turn_count=state_data.get("turn_count", 0),
                    metadata=state_data.get("metadata", {}),
                )
                self._cache[session_id] = sess
                return sess
        except Exception as e:
            logger.debug("Session DB load fallback: %s", e)

        # Fresh session
        prof = StudentProfileState(session_id=session_id, user_id=user_id)
        sess = ConversationSessionState(session_id=session_id, user_id=user_id, profile=prof)
        self._cache[session_id] = sess
        self.save_session(sess)
        return sess

    def save_session(self, sess: ConversationSessionState):
        """Persist session state to cache and database."""
        self._cache[sess.session_id] = sess
        try:
            conn, ph, _ = self.db.get_connection()
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            prof_json = sess.profile.model_dump_json()
            state_dict = {
                "user_id": sess.user_id,
                "last_query": sess.last_query,
                "last_query_timestamp": sess.last_query_timestamp,
                "last_intent": sess.last_intent,
                "last_shortlist": [r.model_dump() for r in sess.last_shortlist],
                "raw_shortlist_dicts": sess.raw_shortlist_dicts,
                "turn_count": sess.turn_count,
                "metadata": sess.metadata,
            }
            state_json = json.dumps(state_dict)

            # SQLite / Postgres upsert
            cursor.execute(
                f"INSERT INTO conversation_sessions (session_id, user_id, profile_json, state_json, updated_at) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}) "
                f"ON CONFLICT(session_id) DO UPDATE SET "
                f"profile_json=excluded.profile_json, state_json=excluded.state_json, updated_at=excluded.updated_at",
                (sess.session_id, sess.user_id, prof_json, state_json, now_iso),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Session DB save fallback: %s", e)

    def reset_session(self, session_id: str):
        """Clear session state completely."""
        if session_id in self._cache:
            del self._cache[session_id]
        try:
            conn, ph, _ = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM conversation_sessions WHERE session_id = {ph}", (session_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Session DB reset fallback: %s", e)

