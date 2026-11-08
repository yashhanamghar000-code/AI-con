# -*- coding: utf-8 -*-
"""
User Repository Implementation.
Adheres to Single Responsibility Principle (SRP) for User persistence.
"""

from typing import Dict, Any, Optional
from db import db_manager

class UserRepository:
    """Manages user account records in PostgreSQL or SQLite via unified DB manager."""

    def __init__(self, db=None):
        self.db = db or db_manager

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.db.get_user_by_email(email)

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get_user_by_id(user_id)

    def create(self, user_id: str, email: str, name: str, password_hash: str) -> Dict[str, Any]:
        return self.db.create_user(user_id=user_id, name=name, email=email, password_hash=password_hash)
