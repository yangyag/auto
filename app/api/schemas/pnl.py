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
