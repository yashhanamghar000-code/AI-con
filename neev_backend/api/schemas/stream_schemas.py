# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, Dict, Any

class StreamRecommendRequest(BaseModel):
    marks: Dict[str, Any]
    interests: Optional[Dict[str, Any]] = None
    aptitude_scores: Optional[Dict[str, Any]] = None
