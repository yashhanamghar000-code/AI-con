# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from typing import Optional
from neev_backend.api.schemas.onboarding_schemas import OnboardingSaveRequest
from neev_backend.api.dependencies import get_onboarding_service, get_token_provider
from neev_backend.core.exceptions import AuthorizationError

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])

@router.post("/save")
def save_student_onboarding(
    req: OnboardingSaveRequest,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    onboarding_service=Depends(get_onboarding_service),
    token_provider=Depends(get_token_provider)
):
    raw_token = token_provider.extract_token_from_header(authorization, token or req.token)
    authenticated_uid = None
    if raw_token:
        try:
            claims = token_provider.decode_token(raw_token)
            authenticated_uid = claims.get("sub")
        except Exception:
            pass

    # Support model_dump / dict across pydantic versions
    save_payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return onboarding_service.save_profile(
        user_id=req.user_id,
        payload=save_payload,
        authenticated_user_id=authenticated_uid
    )

@router.get("/profile/{user_id}")
def get_student_profile(
    user_id: str,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    onboarding_service=Depends(get_onboarding_service),
    token_provider=Depends(get_token_provider)
):
    raw_token = token_provider.extract_token_from_header(authorization, token)
    authenticated_uid = None
    if raw_token:
        try:
            claims = token_provider.decode_token(raw_token)
            authenticated_uid = claims.get("sub")
        except Exception:
            pass

    try:
        return onboarding_service.get_profile(user_id=user_id, authenticated_user_id=authenticated_uid)
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
