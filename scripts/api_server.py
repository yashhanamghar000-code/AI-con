#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neev (नींव) API Server & Application Backend.
FastAPI backend service powering the Neev EdTech platform:
- Decoupled Clean Architecture following SOLID Principles
- Authentication & Session Management with 256-bit Cryptographic JWT
- Multi-Tenant Student Isolation with PostgreSQL & SQLite dual persistence
- 7-Step Student Onboarding & 25-Question Aptitude Stream Discovery
- Agentic RAG Cutoffs (181,137 records) & College Resolver (1,041 profiles)
- Serves the responsive frontend with interactive 3D logo & splash experience.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Path resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
AGENTS_DIR = SCRIPTS_DIR / "agents"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DB_PATH = PROJECT_ROOT / "ai_con_app.db"

for p in (str(PROJECT_ROOT), str(SCRIPTS_DIR), str(AGENTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI, HTTPException, Request, Depends, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Neev Decoupled Backend Modular Architecture
from neev_backend.container import container
from neev_backend.core.exceptions import (
    ConflictError,
    AuthenticationError,
    AuthorizationError,
    EntityNotFoundError
)
from neev_backend.api.schemas.auth_schemas import RegisterRequest, LoginRequest
from neev_backend.api.schemas.onboarding_schemas import OnboardingSaveRequest
from neev_backend.api.schemas.stream_schemas import StreamRecommendRequest
from neev_backend.api.schemas.chat_schemas import ChatRequest
from neev_backend.api.routes import (
    auth_router,
    onboarding_router,
    stream_router,
    chat_router,
    college_router
)

# Backward-compatible re-exports
from auth import (
    create_access_token,
    decode_access_token,
    extract_token_from_header,
    hash_password,
    verify_password,
    JWT_SECRET,
    JWT_ALGORITHM
)
from db import db_manager

# Initialize FastAPI app
app = FastAPI(
    title="Neev AI College & Career Foundation API",
    description="Evidence-grounded education counseling and student onboarding platform with JWT & PostgreSQL multi-tenancy",
    version="2.2.0"
)

# Enable CORS for frontend and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Decoupled Modular Service Routers
app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(stream_router)
app.include_router(chat_router)
app.include_router(college_router)

# Mount Static Assets
if FRONTEND_DIR.is_dir():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend_assets")

@app.on_event("startup")
def on_startup():
    print("[Neev Backend] API Server online and ready. Decoupled micro-services operational.")

# Root Route
@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return {
        "service": "Neev AI College Consultant",
        "status": "online",
        "documentation": "/docs"
    }

# ============================================================================
# HEALTH & TELEMETRY ENDPOINT
# ============================================================================

@app.get("/api/health")
def health():
    db_status = "postgresql" if container.db_manager.is_postgres else f"sqlite:{container.db_manager.sqlite_path}"
    return {
        "status": "healthy",
        "service": "AI-CON College Consultant",
        "brand": "Neev (नींव) Career Foundation",
        "version": "2.2.0",
        "agents_loaded": bool(container.chat_service._orchestrator is not None),
        "cutoffs_indexed_institutes": len(getattr(container.cutoff_service.agent, "colleges_data", {})) if container.cutoff_service._cutoff_agent else 0,
        "vector_profiles_indexed": 0,
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# BACKWARD COMPATIBLE HANDLERS (Direct function calls in tests)
# ============================================================================

def register(req: RegisterRequest) -> Dict[str, Any]:
    try:
        user, token = container.auth_service.register(name=req.name, email=req.email, password=req.password)
        return {
            "success": True,
            "message": "Account created successfully.",
            "token": token,
            "user": user
        }
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

def login(req: LoginRequest) -> Dict[str, Any]:
    try:
        user, token = container.auth_service.login(email=req.email, password=req.password)
        return {
            "success": True,
            "message": "Login successful.",
            "token": token,
            "user": user
        }
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

def get_current_user(
    authorization: Optional[Any] = Header(None),
    token: Optional[Any] = Query(None)
) -> Dict[str, Any]:
    raw_token = container.token_provider.extract_token_from_header(authorization, token)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token.")
    try:
        return container.auth_service.get_current_user(raw_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

def save_onboarding(
    req: OnboardingSaveRequest,
    authorization: Optional[Any] = Header(None),
    token: Optional[Any] = Query(None)
) -> Dict[str, Any]:
    effective_token = token if isinstance(token, str) else getattr(req, "token", None)
    raw_token = container.token_provider.extract_token_from_header(authorization, effective_token)
    authenticated_uid = None
    if raw_token:
        try:
            claims = container.token_provider.decode_token(raw_token)
            authenticated_uid = claims.get("sub")
        except Exception:
            pass

    save_payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return container.onboarding_service.save_profile(
        user_id=req.user_id or "user_demo",
        payload=save_payload,
        authenticated_user_id=authenticated_uid
    )

def get_profile(
    user_id: str,
    authorization: Optional[Any] = Header(None),
    token: Optional[Any] = Query(None)
) -> Dict[str, Any]:
    raw_token = container.token_provider.extract_token_from_header(authorization, token)
    authenticated_uid = None
    if raw_token:
        try:
            claims = container.token_provider.decode_token(raw_token)
            authenticated_uid = claims.get("sub")
        except Exception:
            pass

    try:
        return container.onboarding_service.get_profile(user_id=user_id, authenticated_user_id=authenticated_uid)
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

def calculate_stream_recommendation(req: StreamRecommendRequest) -> Dict[str, Any]:
    return container.onboarding_service.calculate_stream(
        marks=req.marks,
        interests=req.interests or {},
        aptitude_scores=req.aptitude_scores or {}
    )

def chat(
    req: ChatRequest,
    authorization: Optional[Any] = Header(None),
    token: Optional[Any] = Query(None)
) -> Dict[str, Any]:
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty query provided.")
    effective_token = token if isinstance(token, str) else getattr(req, "token", None)
    raw_token = container.token_provider.extract_token_from_header(authorization, effective_token)
    return container.chat_service.answer_query(
        query=req.query,
        user_id=req.user_id or "guest",
        raw_token=raw_token
    )

def get_chat_history(
    user_id: str,
    authorization: Optional[Any] = Header(None),
    token: Optional[Any] = Query(None),
    limit: int = 50
) -> Dict[str, Any]:
    raw_token = container.token_provider.extract_token_from_header(authorization, token)
    authenticated_uid = None
    if raw_token:
        try:
            payload = container.token_provider.decode_token(raw_token)
            authenticated_uid = payload.get("sub")
        except Exception:
            pass
    try:
        return container.chat_service.get_user_history(
            user_id=user_id,
            authenticated_uid=authenticated_uid,
            limit=limit
        )
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

def search_colleges(
    branch: Optional[str] = None,
    category: Optional[str] = None,
    min_percentile: Optional[float] = None,
    max_percentile: Optional[float] = None,
    query: Optional[str] = None,
    limit: int = 10
) -> Dict[str, Any]:
    if min_percentile is not None or max_percentile is not None or branch:
        results = container.cutoff_service.search_cutoffs(
            branch=branch,
            category=category or "GOPENS",
            min_percentile=min_percentile,
            max_percentile=max_percentile,
            limit=limit
        )
        return {
            "success": True,
            "mode": "cutoffs",
            "total": len(results),
            "results": results
        }

    if query:
        matches = container.resolver_service.search_directory(query=query, limit=limit)
        return {
            "success": True,
            "mode": "directory",
            "total": len(matches),
            "results": matches
        }

    return {
        "success": True,
        "mode": "empty",
        "total": 0,
        "results": []
    }

# Agent Manager facade for backward compatibility
class AgentManagerFacade:
    def __init__(self, chat_svc):
        self._chat_svc = chat_svc

    @property
    def orchestrator(self):
        return self._chat_svc.orchestrator

    @property
    def cutoff_agent(self):
        return container.cutoff_service.agent

    @property
    def is_loaded(self):
        return self._chat_svc._orchestrator is not None

    def load_agents(self):
        _ = self.orchestrator

agent_manager = AgentManagerFacade(container.chat_service)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=True)
