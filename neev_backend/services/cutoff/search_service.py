# -*- coding: utf-8 -*-
"""
Cutoff Service Implementation.
Wraps CutoffAgent lookups for college cutoffs and cross-college queries.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from neev_backend.config.settings import settings

class CutoffService:
    """Provides high-performance querying over verified cutoff indices."""

    def __init__(self, cutoff_agent=None, cutoffs_dir: Optional[Path] = None):
        self._cutoff_agent = cutoff_agent
        self.cutoffs_dir = cutoffs_dir or settings.CUTOFFS_PATH

    @property
    def agent(self):
        if self._cutoff_agent is None:
            try:
                from scripts.agents.cutoff_agent import CutoffAgent
                base_dir = Path(__file__).resolve().parent.parent.parent.parent
                staging_dir = base_dir / "cutoffs" / "phase3_final_staging"
                target_dir = staging_dir if staging_dir.is_dir() else self.cutoffs_dir
                self._cutoff_agent = CutoffAgent(cutoffs_dir=target_dir)
            except Exception:
                pass
        return self._cutoff_agent

    def search_cutoffs(
        self,
        branch: Optional[str] = None,
        category: Optional[str] = None,
        min_percentile: Optional[float] = None,
        max_percentile: Optional[float] = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        if self.agent and hasattr(self.agent, "find_colleges"):
            try:
                res = self.agent.find_colleges(
                    branch=branch or "Computer",
                    category=category or "GOPENS",
                    min_percentile=min_percentile,
                    max_percentile=max_percentile,
                    limit=limit
                )
                if isinstance(res, list):
                    return res
            except Exception:
                pass
        return []
