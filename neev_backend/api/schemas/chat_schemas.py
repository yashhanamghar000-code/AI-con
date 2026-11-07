# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class ChatRequest(BaseModel):
    query: str
    user_id: Optional[str] = "guest"
    token: Optional[str] = None
    stream: Optional[str] = None
    category: Optional[str] = None

class ChatResponse(BaseModel):
    success: bool
    status: str
    intent: Optional[str] = "info"
    query_type: Optional[str] = "single_college"
    matched_college: Optional[str] = None
    total_matches: Optional[int] = 0
    candidates: Optional[List[Dict[str, Any]]] = []
    message: str
    raw_evidence: Optional[str] = ""
    student_context_applied: Optional[bool] = False
    personalized_for: Optional[str] = None
