"""
그리드 전략 핵심 로직
현재가를 받아 매수/매도 대상 슬롯을 판별하고 주문을 생성한다.
"""
from typing import List, Tuple

from core.grid import GridState
from core.models import GridRow, Order, OrderSide
from exchange.base import BaseExchange
from utils.logger import get_logger

logger = get_logger(__name__)


class GridStrategy:

    def __init__(self, grid_state: GridState, exchange: BaseExchange, symbol: str):
        self.grid = grid_state
        self.exchange = exchange
        self.symbol = symbol

    def evaluate(self, current_price: float) -> Tuple[List[Order], List[Order]]:
        """
        현재가 기준으로 체결 조건인 슬롯을 찾아
        매수 주문 목록, 매도 주문 목록을 반환한다.
        """
        buy_orders = self._make_buy_orders(current_price)
        sell_orders = self._make_sell_orders(current_price)
        return buy_orders, sell_orders

    def _make_buy_orders(self, current_price: float) -> List[Order]:
        triggered = self.grid.get_buy_triggered(current_price)
        orders = []
        for row in triggered:
            orders.append(Order(
                slot_index=row.index,
                side=OrderSide.BUY,
                price=row.buy_price,
                quantity=row.planned_qty,
                symbol=self.symbol,
            ))
            logger.info(f"매수 조건 충족 → 슬롯 {row.index}: {row.buy_price} x {row.planned_qty}주")
        return orders

    def _make_sell_orders(self, current_price: float) -> List[Order]:
        triggered = self.grid.get_sell_triggered(current_price)
        orders = []
        for row in triggered:
            orders.append(Order(
                slot_index=row.index,
                side=OrderSide.SELL,
                price=row.sell_price,
                quantity=row.held_qty,
                symbol=self.symbol,
            ))
            logger.info(f"매도 조건 충족 → 슬롯 {row.index}: {row.sell_price} x {row.held_qty}주")
        return orders

    def apply_filled_order(self, order: Order):
        """체결된 주문을 그리드 상태에 반영하고 저장"""
        if order.side == OrderSide.BUY:
            self.grid.apply_buy(order.slot_index)
            logger.info(f"매수 체결 반영 → 슬롯 {order.slot_index}")
        else:
            self.grid.apply_sell(order.slot_index)
            logger.info(f"매도 체결 반영 → 슬롯 {order.slot_index}")
        self.grid.save()
