"""
거래소 추상 클래스
신규 거래소 추가 시 이 클래스를 상속해서 구현한다.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.core.models import Order, OrderStatus


class BaseExchange(ABC):

    @abstractmethod
    def get_current_price(self, symbol: str) -> Decimal:
        """현재가 조회"""

    @abstractmethod
    def get_recent_minute_closes(self, symbol: str, unit: int, count: int) -> list[Decimal]:
        """최근 분 캔들 종가 목록 조회"""

    @abstractmethod
    def get_balance(self) -> Decimal:
        """주문 가능 잔고 조회 (현금)"""

    @abstractmethod
    def get_holdings(self, symbol: str) -> Decimal:
        """보유 수량 조회"""

    @abstractmethod
    def get_open_order_ids(
        self,
        symbol: str,
        *,
        states: tuple[str, ...] | None = None,
        limit: int = 100,
    ) -> list[str]:
        """체결 대기 주문 ID 목록 조회"""

    @abstractmethod
    def get_minute_candle_closes(
        self,
        symbol: str,
        *,
        unit_minutes: int,
        count: int,
        to: datetime | None = None,
    ) -> list[Decimal]:
        """완료된 분 캔들 종가 목록 조회. `to` 는 exclusive 상한 시각."""

    @abstractmethod
    def place_order(self, order: Order) -> Optional[str]:
        """주문 실행. 성공 시 거래소 주문 ID 반환, 실패 시 None"""

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        """개별 주문 상태 조회"""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """주문 취소. 성공 시 True"""
