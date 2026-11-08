# -*- coding: utf-8 -*-
"""
Student Context Builder.
Constructs personalized student profile context for grounded reasoning.
Adheres to Single Responsibility Principle (SRP).
"""

from typing import Dict, Any, Optional

class StudentContextBuilder:
    """Transforms raw stored profile and user records into normalized AI context."""

    def build_context(
        self,
        user_id: str,
        profile: Dict[str, Any],
        user_record: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        if not profile and not user_record:
            return None

        p_info = profile.get("personal_info", {}) if profile else {}
        m_info = profile.get("marks_info", {}) if profile else {}
        i_info = profile.get("interests_info", {}) if profile else {}
        apt_info = profile.get("aptitude_results", {}) if profile else {}

        name = p_info.get("fullName")
        if not name and user_record:
            name = user_record.get("name")
        if not name:
            name = "Student"

        percentage = m_info.get("overall_percentage") or m_info.get("percentage")

        return {
            "user_id": user_id,
            "name": name,
            "district": p_info.get("district", "Maharashtra"),
            "category": p_info.get("category", "OPEN"),
            "percentage": float(percentage) if percentage is not None else None,
            "maths": m_info.get("maths"),
            "science": m_info.get("science"),
            "stream": (
                profile.get("selected_stream")
                or (profile.get("stream_recommendation") or {}).get("name")
                or "Science (PCM)"
            ),
            "interests": i_info.get("tags", []),
            "ambitions": i_info.get("ambitions", ""),
            "aptitude_strengths": apt_info.get("category_percentages", {})
        }
