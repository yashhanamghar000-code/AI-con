# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, Query
from typing import Optional
from neev_backend.api.dependencies import get_cutoff_service, get_resolver_service

router = APIRouter(prefix="/api/colleges", tags=["Colleges & Cutoffs"])

@router.get("/search")
def search_colleges(
    branch: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    min_percentile: Optional[float] = Query(None),
    max_percentile: Optional[float] = Query(None),
    query: Optional[str] = Query(None),
    limit: int = Query(10),
    cutoff_service=Depends(get_cutoff_service),
    resolver_service=Depends(get_resolver_service)
):
    if min_percentile is not None or max_percentile is not None or branch:
        results = cutoff_service.search_cutoffs(
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
        matches = resolver_service.search_directory(query=query, limit=limit)
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
