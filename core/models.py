"""
공용 데이터 모델
"""
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderExecutionType(Enum):
    LIMIT = "limit"
    MARKET_BUY_BY_PRICE = "market_buy_by_price"


class EvalResult(Enum):
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


@dataclass
class GridRow:
    """grid.txt의 한 줄 (그리드 슬롯 1개)"""
    index: int               # 줄 번호 (1-based)
    buy_price: Decimal       # 매수 트리거 가격
    held_qty: Decimal        # 현재 보유 수량 (>0 이면 보유 중)
    sell_price: Decimal      # 매도 트리거 가격
    planned_qty: Decimal     # 슬롯의 기본 목표 수량 (빈 슬롯 대기 / 보유 슬롯 복원 기준)

    @property
    def is_holding(self) -> bool:
        """보유 중 슬롯: held_qty > 0"""
        return self.held_qty > Decimal("0")

    @property
    def is_empty(self) -> bool:
        """빈 슬롯: 아직 매수 안 됨"""
        return self.held_qty == Decimal("0") and self.planned_qty > Decimal("0")


@dataclass
class Order:
    """실행할 주문 1건"""
    slot_index: int             # 해당 그리드 슬롯 번호
    side: OrderSide             # BUY / SELL
    price: Decimal              # 주문 가격
    quantity: Decimal           # 주문 수량
    symbol: str                 # 종목/코인 심볼
    execution_type: OrderExecutionType = OrderExecutionType.LIMIT
    spend_amount: Optional[Decimal] = None  # 시장가 매수 시 사용할 KRW 금액
    order_id: Optional[str] = None   # 거래소 체결 후 채워짐

    @property
    def required_krw(self) -> Decimal:
        if self.side != OrderSide.BUY:
            return Decimal("0")
        if self.execution_type == OrderExecutionType.MARKET_BUY_BY_PRICE:
            if self.spend_amount is None:
                raise ValueError("시장가 매수 주문에는 spend_amount 가 필요합니다.")
            return self.spend_amount
        return self.price * self.quantity

    @property
    def is_market_buy_by_price(self) -> bool:
        return self.execution_type == OrderExecutionType.MARKET_BUY_BY_PRICE


@dataclass
class OrderStatus:
    """거래소의 주문 상태 스냅샷"""
    uuid: str
    state: str
    executed_volume: Decimal
    remaining_volume: Decimal

    @property
    def is_filled(self) -> bool:
        if self.state == "done":
            return True
        return (
            self.state == "cancel"
            and self.executed_volume > Decimal("0")
            and self.remaining_volume == Decimal("0")
        )

    @property
    def is_open(self) -> bool:
        return self.state in {"wait", "watch"}

    @property
    def is_cancelled(self) -> bool:
        return self.state == "cancel" and not self.is_filled


@dataclass
class TradePlan:
    """Planner가 수립한 거래 계획"""
    current_price: float
    buy_slots: list = field(default_factory=list)   # 매수 트리거된 GridRow 목록
    sell_slots: list = field(default_factory=list)  # 매도 트리거된 GridRow 목록

    @property
    def has_action(self) -> bool:
        return bool(self.buy_slots or self.sell_slots)


@dataclass
class EvaluationReport:
    """Evaluator 판정 결과"""
    result: EvalResult
    approved_orders: list = field(default_factory=list)   # pass된 Order 목록
    rejected_orders: list = field(default_factory=list)   # block/revise된 Order 목록
    reason: str = ""
