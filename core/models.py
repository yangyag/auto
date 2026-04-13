"""
공용 데이터 모델
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class EvalResult(Enum):
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


@dataclass
class GridRow:
    """grid.txt의 한 줄 (그리드 슬롯 1개)"""
    index: int           # 줄 번호 (1-based)
    buy_price: float     # 매수 트리거 가격
    held_qty: int        # 현재 보유 수량 (>0 이면 보유 중)
    sell_price: float    # 매도 트리거 가격
    planned_qty: int     # 매도 목표 수량 (>0 이면 빈 슬롯)

    @property
    def is_holding(self) -> bool:
        """보유 중 슬롯: held_qty > 0"""
        return self.held_qty > 0

    @property
    def is_empty(self) -> bool:
        """빈 슬롯: 아직 매수 안 됨"""
        return self.held_qty == 0 and self.planned_qty > 0


@dataclass
class Order:
    """실행할 주문 1건"""
    slot_index: int        # 해당 그리드 슬롯 번호
    side: OrderSide        # BUY / SELL
    price: float           # 주문 가격
    quantity: int          # 주문 수량
    symbol: str            # 종목/코인 심볼
    order_id: Optional[str] = None   # 거래소 체결 후 채워짐


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
