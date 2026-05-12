from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.api.schemas.common import DecimalModel


class OrderResponse(DecimalModel):
    order_id: str | None
    identifier: str | None = None
    slot_index: int
    side: str
    price: Decimal
    quantity: Decimal
    symbol: str
    execution_type: str
    spend_amount: Decimal | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None


class OrdersResponse(DecimalModel):
    orders: list[OrderResponse]
