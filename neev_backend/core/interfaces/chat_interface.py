# -*- coding: utf-8 -*-
"""
Conversational Consultant and Student Context Interfaces.
"""

from typing import Protocol, Dict, Any, Optional

class IContextBuilder(Protocol):
    """Builds personalized student context from profile records."""
    def build_context(self, user_id: str, profile: Dict[str, Any], user_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        ...

class IChatService(Protocol):
    """Handles student chat queries, personalization, and persistence."""
    def answer_query(
        self,
        query: str,
        user_id: str,
        raw_token: Optional[str] = None
    ) -> Dict[str, Any]:
        ...
