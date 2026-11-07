# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from neev_backend.api.schemas.stream_schemas import StreamRecommendRequest
from neev_backend.api.dependencies import get_onboarding_service

router = APIRouter(prefix="/api/stream", tags=["Stream Engine"])

@router.post("/recommend")
def recommend_stream(req: StreamRecommendRequest, onboarding_service=Depends(get_onboarding_service)):
    return onboarding_service.calculate_stream(
        marks=req.marks,
        interests=req.interests or {},
        aptitude_scores=req.aptitude_scores or {}
    )
