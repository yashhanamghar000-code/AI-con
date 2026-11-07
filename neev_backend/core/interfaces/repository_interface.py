# -*- coding: utf-8 -*-
"""
Repository Interfaces for Multi-Tenant Data Persistence.
Adheres to Liskov Substitution Principle (LSP) and Interface Segregation Principle (ISP).
"""

from typing import Protocol, Dict, Any, Optional, List

class IUserRepository(Protocol):
    """User repository abstraction for multi-tenant account management."""
    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        ...

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        ...

    def create(self, user_id: str, email: str, name: str, password_hash: str) -> Dict[str, Any]:
        ...

class IProfileRepository(Protocol):
    """Student profile repository abstraction for onboarding persistence."""
    def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        ...

    def upsert(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        ...

class IChatRepository(Protocol):
    """Chat repository abstraction for isolated user conversation history."""
    def add_message(
        self, 
        user_id: str, 
        role: str, 
        content: str, 
        status: Optional[str] = None, 
        matched_college: Optional[str] = None, 
        evidence: Optional[str] = None
    ) -> int:
        ...

    def get_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        ...
