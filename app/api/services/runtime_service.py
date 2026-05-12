from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import requests

import app.config.settings as cfg
from app.api.schemas.grid import BreakoutGuardStatus, StopLossStatus
from app.api.schemas.runtime import BotStatusResponse, ConfigResponse, MarketPriceResponse
from app.storage.postgres_runtime_repository import BotHeartbeat, PostgresBotHeartbeatRepository


HEARTBEAT_STALE_SECONDS = int(getattr(cfg, "MOBILE_API_HEARTBEAT_STALE_SECONDS", 30))
PRICE_HEARTBEAT_FRESH_SECONDS = int(getattr(cfg, "MOBILE_API_PRICE_HEARTBEAT_FRESH_SECONDS", 10))


def get_heartbeat() -> BotHeartbeat | None:
    return PostgresBotHeartbeatRepository.from_config(cfg).get()


def _lag_seconds(heartbeat: BotHeartbeat | None) -> Decimal | None:
    if heartbeat is None:
        return None
    now = datetime.now(timezone.utc)
    return Decimal(str(max((now - heartbeat.last_heartbeat_at).total_seconds(), 0.0)))


def build_bot_status_response() -> BotStatusResponse:
    heartbeat = get_heartbeat()
    lag = _lag_seconds(heartbeat)
    is_alive = lag is not None and lag <= Decimal(str(HEARTBEAT_STALE_SECONDS))
    if heartbeat is None:
        return BotStatusResponse(
            bot_key=cfg.STATE_BOT_KEY,
            symbol=cfg.SYMBOL,
            is_alive=False,
            last_heartbeat_at=None,
            last_cycle_at=None,
            lag_seconds=None,
            current_price=None,
            breakout_guard=BreakoutGuardStatus(),
            stop_loss=StopLossStatus(active=False),
        )

    return BotStatusResponse(
        bot_key=heartbeat.bot_key,
        symbol=heartbeat.symbol,
        is_alive=is_alive,
        last_heartbeat_at=heartbeat.last_heartbeat_at,
        last_cycle_at=heartbeat.last_cycle_at,
        lag_seconds=lag,
        current_price=heartbeat.current_price,
        breakout_guard=BreakoutGuardStatus(
            active=heartbeat.breakout_guard_active,
            side=heartbeat.breakout_guard_side,
            reason=heartbeat.breakout_guard_reason,
        ),
        stop_loss=StopLossStatus(
            active=heartbeat.stop_loss_active,
            level=heartbeat.stop_loss_level,
            armed_at=heartbeat.stop_loss_armed_at.isoformat() if heartbeat.stop_loss_armed_at else None,
            liquidated_at=heartbeat.liquidated_at.isoformat() if heartbeat.liquidated_at else None,
        ),
    )


def get_market_price() -> MarketPriceResponse:
    heartbeat = get_heartbeat()
    lag = _lag_seconds(heartbeat)
    if (
        heartbeat is not None
        and heartbeat.current_price is not None
        and lag is not None
        and lag <= Decimal(str(PRICE_HEARTBEAT_FRESH_SECONDS))
    ):
        return MarketPriceResponse(
            symbol=heartbeat.symbol,
            price=heartbeat.current_price,
            source="bot_heartbeat",
            observed_at=heartbeat.last_heartbeat_at,
        )

    response = requests.get(
        "https://api.upbit.com/v1/ticker",
        params={"markets": cfg.SYMBOL},
        timeout=5,
    )
    response.raise_for_status()
    data = response.json()
    return MarketPriceResponse(
        symbol=cfg.SYMBOL,
        price=Decimal(str(data[0]["trade_price"])),
        source="upbit_rest_api",
        observed_at=datetime.now(timezone.utc),
    )


def get_config_response() -> ConfigResponse:
    return ConfigResponse(
        symbol=cfg.SYMBOL,
        state_bot_key=cfg.STATE_BOT_KEY,
        pg_schema=cfg.PGSCHEMA,
        grid_total_budget_krw=cfg.GRID_TOTAL_BUDGET_KRW,
        grid_tp_model=cfg.GRID_TP_MODEL,
        grid_tp_k_base=cfg.GRID_TP_K_BASE,
        grid_tp_k_floor=cfg.GRID_TP_K_FLOOR,
        upward_buy_enabled=cfg.UPWARD_BUY_ENABLED,
        breakout_guard_enabled=cfg.BREAKOUT_GUARD_ENABLED,
        stop_loss_mode=cfg.STOP_LOSS_MODE,
        price_poll_interval=cfg.PRICE_POLL_INTERVAL,
    )
