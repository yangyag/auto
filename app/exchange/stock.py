"""
주식 거래소 구현 (stub)
실제 연동 시 한국투자증권 KIS API, LS증권 등으로 교체
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.core.models import Order, OrderStatus
from app.exchange.base import BaseExchange
from app.utils.logger import get_logger

logger = get_logger(__name__)


class StockExchange(BaseExchange):

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        logger.info("StockExchange 초기화 (stub 모드)")

    def get_current_price(self, symbol: str) -> Decimal:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_current_price 미구현")

    def get_recent_minute_closes(self, symbol: str, unit: int, count: int) -> list[Decimal]:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_recent_minute_closes 미구현")

    def get_balance(self) -> Decimal:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_balance 미구현")

    def get_holdings(self, symbol: str) -> Decimal:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_holdings 미구현")

    def get_open_order_ids(
        self,
        symbol: str,
        *,
        states: tuple[str, ...] | None = None,
        limit: int = 100,
    ) -> list[str]:
        del symbol, states, limit
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_open_order_ids 미구현")

    def get_minute_candle_closes(
        self,
        symbol: str,
        *,
        unit_minutes: int,
        count: int,
        to: datetime | None = None,
    ) -> list[Decimal]:
        del symbol, unit_minutes, count, to
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_minute_candle_closes 미구현")

    def place_order(self, order: Order) -> Optional[str]:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 place_order 미구현")

    def get_order_status(self, order_id: str) -> OrderStatus:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_order_status 미구현")

    def cancel_order(self, order_id: str) -> bool:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 cancel_order 미구현")
