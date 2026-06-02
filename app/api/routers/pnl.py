from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.api.schemas.pnl import PnlBySlotResponse, RealizedPnlResponse
from app.api.services.pnl_service import calculate_pnl_by_slot, calculate_realized_pnl


router = APIRouter(prefix="/v1/pnl", tags=["pnl"], dependencies=[Depends(get_current_user)])


@router.get("/realized", response_model=RealizedPnlResponse)
def realized_pnl(period: str = Query(default="d", pattern="^(d|w|m|y|all)$")) -> RealizedPnlResponse:
    try:
        return calculate_realized_pnl(period=period)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/by-slot", response_model=PnlBySlotResponse)
def pnl_by_slot(
    period: str = Query(default="d", pattern="^(d|w|m|y|all)$"),
    detail: bool = Query(default=False),
) -> PnlBySlotResponse:
    try:
        return calculate_pnl_by_slot(period=period, detail=detail)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
