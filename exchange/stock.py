"""
주식 거래소 구현 (stub)
실제 연동 시 한국투자증권 KIS API, LS증권 등으로 교체
"""
from typing import Optional

from core.models import Order
from exchange.base import BaseExchange
from utils.logger import get_logger

logger = get_logger(__name__)


class StockExchange(BaseExchange):

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        logger.info("StockExchange 초기화 (stub 모드)")

    def get_current_price(self, symbol: str) -> float:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_current_price 미구현")

    def get_balance(self) -> float:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_balance 미구현")

    def get_holdings(self, symbol: str) -> int:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 get_holdings 미구현")

    def place_order(self, order: Order) -> Optional[str]:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 place_order 미구현")

    def cancel_order(self, order_id: str) -> bool:
        # TODO: KIS API 등 실거래소 연동
        raise NotImplementedError("주식 거래소 cancel_order 미구현")
