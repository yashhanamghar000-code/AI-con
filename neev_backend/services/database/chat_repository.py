# -*- coding: utf-8 -*-
"""
Chat Repository Implementation.
Adheres to Single Responsibility Principle (SRP) for multi-tenant conversation logs.
"""

from typing import Dict, Any, Optional, List
from db import db_manager

class ChatRepository:
    """Manages chat messages isolated per user_id via unified DB manager."""

    def __init__(self, db=None):
        self.db = db or db_manager

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        status: Optional[str] = None,
        matched_college: Optional[str] = None,
        evidence: Optional[str] = None
    ) -> int:
        return self.db.add_chat_message(
            user_id=user_id,
            role=role,
            content=content,
            status=status,
            matched_college=matched_college,
            evidence=evidence
        )

    def get_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        res = self.db.get_chat_history(user_id=user_id, limit=limit)
        return res if isinstance(res, list) else res.get("history", [])
