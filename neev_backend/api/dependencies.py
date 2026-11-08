# -*- coding: utf-8 -*-
"""
FastAPI Dependency Providers.
Enables clean Dependency Injection into route handlers.
"""

from typing import Optional
from fastapi import Header, Query, HTTPException, status
from neev_backend.container import container
from neev_backend.core.exceptions import AuthenticationError

def get_auth_service():
    return container.auth_service

def get_onboarding_service():
    return container.onboarding_service

def get_chat_service():
    return container.chat_service

def get_cutoff_service():
    return container.cutoff_service

def get_resolver_service():
    return container.resolver_service

def get_token_provider():
    return container.token_provider

def extract_raw_token(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)) -> Optional[str]:
    return container.token_provider.extract_token_from_header(authorization, token)

def get_current_user_id(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)) -> Optional[str]:
    raw_token = extract_raw_token(authorization, token)
    if not raw_token:
        return None
    try:
        payload = container.token_provider.decode_token(raw_token)
        return payload.get("sub")
    except AuthenticationError:
        return None
