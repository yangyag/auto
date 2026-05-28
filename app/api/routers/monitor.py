from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

import app.config.settings as cfg
from app.api.deps import get_current_user
from app.api.schemas.monitor import OpenSellMonitorResponse
from app.api.services.monitor_service import get_open_sell_monitor_data

router = APIRouter(
    prefix="/v1/monitor",
    tags=["monitor"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/open-sells", response_model=OpenSellMonitorResponse)
def open_sells(
    market: str = Query(default=cfg.SYMBOL),
    lookback_days: int = Query(default=120, ge=1),
    bot_key: str | None = Query(default=None),
    reset_sell_uuid: list[str] = Query(default=[]),
) -> OpenSellMonitorResponse:
    try:
        return get_open_sell_monitor_data(
            market=market,
            lookback_days=lookback_days,
            bot_key=bot_key,
            reset_sell_uuids=reset_sell_uuid,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
