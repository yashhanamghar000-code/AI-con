# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from typing import Optional
from neev_backend.api.schemas.auth_schemas import RegisterRequest, LoginRequest
from neev_backend.api.dependencies import get_auth_service, get_token_provider
from neev_backend.core.exceptions import ConflictError, AuthenticationError, EntityNotFoundError

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register")
def register_user(req: RegisterRequest, auth_service=Depends(get_auth_service)):
    try:
        user, token = auth_service.register(name=req.name, email=req.email, password=req.password)
        return {
            "success": True,
            "message": "Account created successfully.",
            "token": token,
            "user": user
        }
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Registration failed: {str(e)}")

@router.post("/login")
def login_user(req: LoginRequest, auth_service=Depends(get_auth_service)):
    try:
        user, token = auth_service.login(email=req.email, password=req.password)
        return {
            "success": True,
            "message": "Login successful.",
            "token": token,
            "user": user
        }
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Login failed: {str(e)}")

@router.get("/me")
def get_authenticated_profile(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    auth_service=Depends(get_auth_service),
    token_provider=Depends(get_token_provider)
):
    raw_token = token_provider.extract_token_from_header(authorization, token)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token.")
    try:
        return auth_service.get_current_user(raw_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
