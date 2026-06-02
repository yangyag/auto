from __future__ import annotations

from decimal import Decimal

from app.api.schemas.common import DecimalModel


class PnlBucket(DecimalModel):
    key: str
    order_count: int
    trade_count: int
    realized_pnl_krw: Decimal
    matched_qty_btc: Decimal


class RealizedPnlResponse(DecimalModel):
    period: str
    market: str
    buckets: list[PnlBucket]


class SlotPnlBucket(DecimalModel):
    slot: int
    grid_buy_price: Decimal | None
    order_count: int
    realized_pnl_krw: Decimal
    matched_qty: Decimal


class SellLine(DecimalModel):
    time: str
    slot: int
    matched_qty: Decimal
    realized_pnl_krw: Decimal
    sell_uuid: str


class PnlBySlotResponse(DecimalModel):
    period: str
    market: str
    base_currency: str
    total_realized_pnl_krw: Decimal
    slots: list[SlotPnlBucket]
    sells: list[SellLine]
