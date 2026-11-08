# -*- coding: utf-8 -*-
"""
Stream Discovery and Aptitude Interfaces.
"""

from typing import Protocol, Dict, Any, List

class IStreamEngine(Protocol):
    """Calculates stream fit scores based on marks, interests, and aptitude."""
    def recommend(
        self, 
        marks: Dict[str, Any], 
        interests: Dict[str, Any], 
        aptitude_scores: Dict[str, Any]
    ) -> Dict[str, Any]:
        ...

class IAptitudeEvaluator(Protocol):
    """Scores student responses on the 25-question diagnostic assessment."""
    def evaluate(self, answers: Dict[str, int]) -> Dict[str, Any]:
        ...
