from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.schemas.grid import GridStateResponse, GridSummaryResponse
from app.api.services.grid_service import build_grid_state_response, build_grid_summary_response
from app.api.services.runtime_service import get_heartbeat


router = APIRouter(prefix="/v1/grid", tags=["grid"], dependencies=[Depends(get_current_user)])


@router.get("/state", response_model=GridStateResponse)
def grid_state() -> GridStateResponse:
    return build_grid_state_response()


@router.get("/summary", response_model=GridSummaryResponse)
def grid_summary() -> GridSummaryResponse:
    return build_grid_summary_response(get_heartbeat())
