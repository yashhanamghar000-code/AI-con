# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class OnboardingSaveRequest(BaseModel):
    user_id: str
    current_step: Optional[int] = 1
    personal_info: Optional[Dict[str, Any]] = None
    academic_info: Optional[Dict[str, Any]] = None
    marks_info: Optional[Dict[str, Any]] = None
    interests_info: Optional[Dict[str, Any]] = None
    aptitude_results: Optional[Dict[str, Any]] = None
    stream_recommendation: Optional[Dict[str, Any]] = None
    selected_stream: Optional[str] = None
    is_confirmed: Optional[bool] = False
    token: Optional[str] = None
