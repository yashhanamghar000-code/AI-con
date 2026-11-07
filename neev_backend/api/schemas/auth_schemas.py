# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, Dict, Any

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: Optional[str] = None

class AuthResponse(BaseModel):
    success: bool
    token: str
    user: Dict[str, Any]
