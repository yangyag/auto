from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.api.schemas.common import DecimalModel
from app.api.schemas.order import OrderResponse


class GridSlotResponse(DecimalModel):
    slot_index: int
    buy_price: Decimal
    sell_price: Decimal
    held_qty: Decimal
    planned_qty: Decimal
    filled_at: datetime | None = None
    status: str
    planned_buy_krw: Decimal
    inventory_cost_krw: Decimal
    effective_sell_price: Decimal
    effective_tp_k: Decimal
    pending_order: OrderResponse | None = None


class GridStateResponse(DecimalModel):
    symbol: str
    version: int | str | None
    revision: str | None
    slots: list[GridSlotResponse]


class StopLossStatus(DecimalModel):
    active: bool
    level: int | None = None
    armed_at: str | None = None
    liquidated_at: str | None = None


class BreakoutGuardStatus(DecimalModel):
    active: bool | None = None
    side: str | None = None
    reason: str | None = None


class GridSummaryResponse(DecimalModel):
    symbol: str
    row_count: int
    holding_count: int
    empty_count: int
    total_inventory_btc: Decimal
    current_inventory_cost_krw: Decimal
    total_allocated_budget_krw: Decimal
    planned_buy_budget_total: Decimal
    top_slot_planned_buy_budget: Decimal
    bottom_slot_planned_buy_budget: Decimal
    avg_buy_price: Decimal | None
    lower_price: Decimal | None
    upper_price: Decimal | None
    breakout_guard: BreakoutGuardStatus
    stop_loss: StopLossStatus
