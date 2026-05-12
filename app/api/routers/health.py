from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.common import HealthResponse, VersionResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(app="auto", api_version="v1")
