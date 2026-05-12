from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_api_repository, get_current_user
from app.api.schemas.order import OrdersResponse
from app.api.services.grid_service import _order_response_from_order, order_response_from_row
from app.api.services.repository import MobileApiRepository
from app.storage.factory import build_pending_order_repository
import app.config.settings as cfg


router = APIRouter(prefix="/v1/orders", tags=["orders"], dependencies=[Depends(get_current_user)])


@router.get("/pending", response_model=OrdersResponse)
def pending_orders() -> OrdersResponse:
    return OrdersResponse(
        orders=[
            _order_response_from_order(order, status="open")
            for order in build_pending_order_repository(cfg).list_open()
        ]
    )


@router.get("/recent", response_model=OrdersResponse)
def recent_orders(
    limit: int = Query(default=50, ge=1, le=200),
    repository: MobileApiRepository = Depends(get_api_repository),
) -> OrdersResponse:
    return OrdersResponse(orders=[order_response_from_row(row) for row in repository.list_recent_orders(limit=limit)])
