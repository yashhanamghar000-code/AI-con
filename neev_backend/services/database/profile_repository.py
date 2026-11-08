# -*- coding: utf-8 -*-
"""
Student Profile Repository Implementation.
Adheres to Single Responsibility Principle (SRP) for Profile persistence.
"""

from typing import Dict, Any, Optional
from db import db_manager

class ProfileRepository:
    """Manages student profile records in PostgreSQL or SQLite via unified DB manager."""

    def __init__(self, db=None):
        self.db = db or db_manager

    def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get_student_profile(user_id)

    def upsert(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        return self.db.upsert_student_profile(user_id, profile_data)
