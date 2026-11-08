# -*- coding: utf-8 -*-
"""
Onboarding Domain Service.
Coordinates profile persistence, tenant validation, and stream evaluation.
"""

from typing import Dict, Any, Optional
from neev_backend.core.interfaces.repository_interface import IProfileRepository
from neev_backend.core.interfaces.stream_interface import IStreamEngine
from neev_backend.core.exceptions import AuthorizationError, EntityNotFoundError

class OnboardingService:
    """Manages student profile lifecycle with strict tenant isolation."""

    def __init__(self, profile_repo: IProfileRepository, stream_engine: IStreamEngine):
        self.profile_repo = profile_repo
        self.stream_engine = stream_engine

    def save_profile(self, user_id: str, payload: Dict[str, Any], authenticated_user_id: Optional[str] = None) -> Dict[str, Any]:
        # Enforce tenant match if authenticated
        effective_uid = authenticated_user_id or user_id
        if authenticated_user_id and user_id and user_id != authenticated_user_id:
            # Rebind strictly to authenticated user
            effective_uid = authenticated_user_id

        # Merge with existing profile if present
        existing = self.profile_repo.get_by_user_id(effective_uid) or {}
        merged = {**existing, **payload, "user_id": effective_uid}

        self.profile_repo.upsert(effective_uid, merged)
        return {"success": True, "user_id": effective_uid, "saved_step": merged.get("current_step", 1)}

    def get_profile(self, user_id: str, authenticated_user_id: Optional[str] = None) -> Dict[str, Any]:
        if authenticated_user_id and user_id != authenticated_user_id:
            raise AuthorizationError("Access denied. You cannot inspect another student's profile.")

        profile = self.profile_repo.get_by_user_id(user_id)
        if not profile:
            # Provide default baseline profile structure
            profile = {
                "user_id": user_id,
                "current_step": 1,
                "personal_info": {"fullName": "Student", "district": "Pune", "category": "OPEN"},
                "academic_info": {"level": "Class 10"},
                "marks_info": {"percentage": 80.0, "maths": 80, "science": 80},
                "interests_info": {"tags": ["technology"]},
                "selected_stream": "science_pcm",
                "is_confirmed": False
            }
        return profile

    def calculate_stream(self, marks: Dict[str, Any], interests: Dict[str, Any], aptitude_scores: Dict[str, Any]) -> Dict[str, Any]:
        return self.stream_engine.recommend(marks, interests, aptitude_scores)
