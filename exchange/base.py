"""
거래소 추상 클래스
신규 거래소 추가 시 이 클래스를 상속해서 구현한다.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from core.models import Order, OrderStatus


class BaseExchange(ABC):

    @abstractmethod
    def get_current_price(self, symbol: str) -> Decimal:
        """현재가 조회"""

    @abstractmethod
    def get_balance(self) -> Decimal:
        """주문 가능 잔고 조회 (현금)"""

    @abstractmethod
    def get_holdings(self, symbol: str) -> Decimal:
        """보유 수량 조회"""

    @abstractmethod
    def place_order(self, order: Order) -> Optional[str]:
        """주문 실행. 성공 시 거래소 주문 ID 반환, 실패 시 None"""

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        """개별 주문 상태 조회"""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소. 성공 시 True"""
