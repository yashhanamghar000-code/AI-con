# -*- coding: utf-8 -*-
"""
Cutoff Search & College Directory Interfaces.
"""

from typing import Protocol, Dict, Any, Optional, List

class ICutoffService(Protocol):
    """Abstraction for historical CAP cutoff querying and filtering."""
    def search_cutoffs(
        self,
        branch: Optional[str] = None,
        category: Optional[str] = None,
        min_percentile: Optional[float] = None,
        max_percentile: Optional[float] = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        ...

class ICollegeResolverService(Protocol):
    """Abstraction for college directory and entity resolution."""
    def search_directory(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        ...
