from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.api.schemas.common import DecimalModel
from app.api.schemas.grid import BreakoutGuardStatus, StopLossStatus


class BotStatusResponse(DecimalModel):
    bot_key: str
    symbol: str
    is_alive: bool
    last_heartbeat_at: datetime | None
    last_cycle_at: datetime | None
    lag_seconds: Decimal | None
    current_price: Decimal | None
    breakout_guard: BreakoutGuardStatus
    stop_loss: StopLossStatus


class MarketPriceResponse(DecimalModel):
    symbol: str
    price: Decimal
    source: str
    observed_at: datetime


class ConfigResponse(DecimalModel):
    symbol: str
    state_bot_key: str
    pg_schema: str
    grid_total_budget_krw: Decimal
    grid_tp_model: str
    grid_tp_k_base: Decimal
    grid_tp_k_floor: Decimal
    upward_buy_enabled: bool
    breakout_guard_enabled: bool
    stop_loss_mode: str
    price_poll_interval: int | float
