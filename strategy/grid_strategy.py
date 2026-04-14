"""
그리드 전략 핵심 로직
현재가를 받아 매수/매도 대상 슬롯을 판별하고 주문을 생성한다.
"""
from decimal import Decimal
from typing import List, Tuple

from core.grid import GridState
from core.models import GridRow, Order, OrderExecutionType, OrderSide
from exchange.base import BaseExchange
from utils.decimal_utils import quantize_to_step
from utils.logger import get_logger

logger = get_logger(__name__)
KRW_ORDER_AMOUNT_STEP = Decimal("1")


class GridStrategy:

    def __init__(self, grid_state: GridState, exchange: BaseExchange, symbol: str):
        self.grid = grid_state
        self.exchange = exchange
        self.symbol = symbol
        self.previous_price: Decimal | None = None

    def evaluate(self, current_price: Decimal) -> Tuple[List[Order], List[Order]]:
        """
        직전 가격 대비 현재가가 그리드 라인을 교차했는지 확인해
        매수/매도 주문 목록을 반환한다.
        """
        if self.previous_price is None:
            self.previous_price = current_price
            return [], []

        buy_orders = self._make_buy_orders(self.previous_price, current_price)
        sell_orders = self._make_sell_orders(self.previous_price, current_price)
        self.previous_price = current_price
        return buy_orders, sell_orders

    def _make_buy_orders(self, previous_price: Decimal, current_price: Decimal) -> List[Order]:
        orders_by_slot: dict[int, Order] = {}
        for row in self.grid.rows:
            if not row.is_empty:
                continue

            crossed_down = previous_price > row.buy_price and current_price <= row.buy_price
            crossed_up = previous_price < row.buy_price and current_price >= row.buy_price
            if not (crossed_down or crossed_up):
                continue

            if crossed_down:
                orders_by_slot[row.index] = Order(
                    slot_index=row.index,
                    side=OrderSide.BUY,
                    price=row.buy_price,
                    quantity=row.planned_qty,
                    symbol=self.symbol,
                    execution_type=OrderExecutionType.LIMIT,
                )
                logger.info(
                    f"매수 교차 조건 충족(하락) → 슬롯 {row.index}: "
                    f"{previous_price} -> {current_price} / {row.buy_price} x {row.planned_qty}"
                )
                continue

            spend_amount = quantize_to_step(
                row.buy_price * row.planned_qty,
                KRW_ORDER_AMOUNT_STEP,
            )
            orders_by_slot[row.index] = Order(
                slot_index=row.index,
                side=OrderSide.BUY,
                price=row.buy_price,
                quantity=row.planned_qty,
                symbol=self.symbol,
                execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
                spend_amount=spend_amount,
            )
            logger.info(
                f"매수 교차 조건 충족(상승) → 슬롯 {row.index}: "
                f"{previous_price} -> {current_price} / trigger={row.buy_price} "
                f"target={row.planned_qty} spend={spend_amount} KRW"
            )
        return list(orders_by_slot.values())

    def _make_sell_orders(self, previous_price: Decimal, current_price: Decimal) -> List[Order]:
        orders = []
        for row in self.grid.rows:
            crossed_up = row.is_holding and previous_price < row.sell_price and current_price >= row.sell_price
            if not crossed_up:
                continue

            orders.append(Order(
                slot_index=row.index,
                side=OrderSide.SELL,
                price=row.sell_price,
                quantity=row.held_qty,
                symbol=self.symbol,
            ))
            logger.info(
                f"매도 교차 조건 충족 → 슬롯 {row.index}: "
                f"{previous_price} -> {current_price} / {row.sell_price} x {row.held_qty}"
            )
        return orders

    def apply_filled_order(self, order: Order):
        """체결된 주문을 그리드 상태에 반영한다."""
        if order.side == OrderSide.BUY:
            self.grid.apply_buy(order.slot_index, order.quantity)
            logger.info(f"매수 체결 반영 → 슬롯 {order.slot_index}")
        else:
            self.grid.apply_sell(order.slot_index)
            logger.info(f"매도 체결 반영 → 슬롯 {order.slot_index}")
