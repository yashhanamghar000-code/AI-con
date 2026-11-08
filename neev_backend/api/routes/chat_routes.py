# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Response, status
from typing import Optional
from neev_backend.api.schemas.chat_schemas import ChatRequest
from neev_backend.api.dependencies import get_chat_service, get_token_provider
from neev_backend.core.exceptions import AuthorizationError

router = APIRouter(prefix="/api/chat", tags=["AI Consultant"])

@router.post("")
@router.post("/")
def send_chat_message(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    chat_service=Depends(get_chat_service),
    token_provider=Depends(get_token_provider)
):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty query provided.")

    raw_token = token_provider.extract_token_from_header(authorization, token or req.token)
    return chat_service.answer_query(
        query=req.query,
        user_id=req.user_id or "guest",
        raw_token=raw_token
    )

@router.get("/history/{user_id}")
def get_student_chat_history(
    user_id: str,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    limit: int = 50,
    chat_service=Depends(get_chat_service),
    token_provider=Depends(get_token_provider)
):
    raw_token = token_provider.extract_token_from_header(authorization, token)
    authenticated_uid = None
    if raw_token:
        try:
            payload = token_provider.decode_token(raw_token)
            authenticated_uid = payload.get("sub")
        except Exception:
            pass

    try:
        return chat_service.get_user_history(
            user_id=user_id,
            authenticated_uid=authenticated_uid,
            limit=limit
        )
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/pdf/{user_id}")
def download_shortlist_pdf(
    user_id: str,
    chat_service=Depends(get_chat_service)
):
    pdf_bytes = chat_service.get_shortlist_pdf(user_id)
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No college shortlist available to export. Please ask for a college list in the chat first."
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="AI_CON_College_Shortlist.pdf"'
        }
    )
