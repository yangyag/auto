from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.api.schemas.common import DecimalModel


class OpenSellRowSchema(DecimalModel):
    slot_index: Optional[int]
    qty: Decimal
    buy_unit_cost: Optional[Decimal]
    sell_limit_price: Decimal
    current_price: Decimal
    unrealized_at_current: Optional[Decimal]
    gap_to_fill_krw: Decimal


class OpenSellSummarySchema(DecimalModel):
    total_count: int
    matched_count: int
    unmatched_count: int
    profit_count: int
    loss_count: int
    total_unrealized_krw: Decimal


class OpenSellDiagnosticSchema(DecimalModel):
    open_orders: int
    matched: int
    unmatched: int
    lookback_days: int


class OpenSellMonitorResponse(DecimalModel):
    market: str
    current_price: Decimal
    generated_at: datetime
    rows: list[OpenSellRowSchema]
    summary: OpenSellSummarySchema
    diagnostic: OpenSellDiagnosticSchema
