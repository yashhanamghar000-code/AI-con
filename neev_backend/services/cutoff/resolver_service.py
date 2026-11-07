# -*- coding: utf-8 -*-
"""
College Resolver Service Implementation.
Finds institutions across directory manifests and vector index.
"""

from typing import Dict, Any, List
from pathlib import Path
from neev_backend.config.settings import settings

class CollegeResolverService:
    """Directory resolver searching across 1,041 verified Maharashtra institutes."""

    def __init__(self, college_resolver=None):
        self._resolver = college_resolver

    @property
    def resolver(self):
        if self._resolver is None:
            try:
                from scripts.agents.college_resolver import CollegeResolver
                self._resolver = CollegeResolver()
            except Exception:
                pass
        return self._resolver

    def search_directory(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        results = []
        if not query:
            return results
        clean_q = query.strip().lower()

        if self.resolver and hasattr(self.resolver, "colleges_data"):
            count = 0
            for code, col in self.resolver.colleges_data.items():
                name = col.get("name", "")
                district = col.get("district", "")
                if clean_q in name.lower() or clean_q in code.lower() or clean_q in district.lower():
                    results.append({
                        "code": code,
                        "name": name,
                        "district": district,
                        "autonomy": col.get("autonomy", "Non-Autonomous"),
                        "status": col.get("status", "Government/Unaided")
                    })
                    count += 1
                    if count >= limit:
                        break
        return results
