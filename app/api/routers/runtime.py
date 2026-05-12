from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.schemas.runtime import BotStatusResponse, ConfigResponse, MarketPriceResponse
from app.api.services.runtime_service import build_bot_status_response, get_config_response, get_market_price


bot_router = APIRouter(prefix="/v1/bot", tags=["bot"], dependencies=[Depends(get_current_user)])
market_router = APIRouter(prefix="/v1/market", tags=["market"], dependencies=[Depends(get_current_user)])
config_router = APIRouter(prefix="/v1/config", tags=["config"], dependencies=[Depends(get_current_user)])


@bot_router.get("/status", response_model=BotStatusResponse)
def bot_status() -> BotStatusResponse:
    return build_bot_status_response()


@market_router.get("/price", response_model=MarketPriceResponse)
def market_price() -> MarketPriceResponse:
    return get_market_price()


@config_router.get("", response_model=ConfigResponse)
def config() -> ConfigResponse:
    return get_config_response()
