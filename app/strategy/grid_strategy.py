"""
그리드 전략 핵심 로직
현재가를 받아 매수/매도 대상 슬롯을 판별하고 주문을 생성한다.
"""
import time
from decimal import Decimal
from typing import List, Tuple

import app.config.settings as cfg
from app.core.grid import GridState
from app.core.models import Order, OrderExecutionType, OrderSide
from app.exchange.base import BaseExchange
from app.utils.decimal_utils import quantize_to_step
from app.utils.logger import get_logger
from app.utils.upbit_market import MIN_KRW_ORDER_AMOUNT

logger = get_logger(__name__)
KRW_ORDER_AMOUNT_STEP = Decimal("1")


class GridStrategy:

    def __init__(self, grid_state: GridState, exchange: BaseExchange, symbol: str):
        self.grid = grid_state
        self.exchange = exchange
        self.symbol = symbol
        self.previous_price: Decimal | None = None
        self.previous_price_at: float | None = None  # time.monotonic() 기준

    def evaluate(self, current_price: Decimal) -> Tuple[List[Order], List[Order]]:
        return self.evaluate_with_pending(current_price)

    def evaluate_with_pending(
        self,
        current_price: Decimal,
        pending_slot_indexes: set[int] | None = None,
    ) -> Tuple[List[Order], List[Order]]:
        """
        직전 가격 대비 현재가가 그리드 라인을 교차했는지 확인해
        매수/매도 주문 목록을 반환한다.
        """
        effective_pending_slots = pending_slot_indexes or set()
        now = time.monotonic()

        if self.previous_price is None:
            self.previous_price = current_price
            self.previous_price_at = now
            return [], self._make_sell_orders(current_price)

        if self.previous_price_at is not None:
            elapsed = now - self.previous_price_at
            if elapsed > cfg.STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS:
                logger.info(
                    f"매수 평가 스킵(stale previous_price) → "
                    f"prev={self.previous_price} cur={current_price} elapsed={elapsed:.1f}s"
                )
                self.previous_price = current_price
                self.previous_price_at = now
                return [], self._make_sell_orders(current_price)

        active_slot_indexes = self._resolve_active_buy_window_slot_indexes(self.previous_price)
        buy_orders = self._make_buy_orders(
            self.previous_price,
            current_price,
            effective_pending_slots,
            active_slot_indexes,
        )
        sell_orders = self._make_sell_orders(current_price)
        self.previous_price = current_price
        self.previous_price_at = now
        return buy_orders, sell_orders

    def _make_buy_orders(
        self,
        previous_price: Decimal,
        current_price: Decimal,
        pending_slot_indexes: set[int],
        active_slot_indexes: set[int] | None,
    ) -> List[Order]:
        orders_by_slot: dict[int, Order] = {}
        projected_inventory_krw = self.grid.current_inventory_cost
        for row in self.grid.rows:
            if not row.is_empty or row.index in pending_slot_indexes:
                continue
            if active_slot_indexes is not None and row.index not in active_slot_indexes:
                continue

            crossed_down = previous_price > row.buy_price and current_price <= row.buy_price
            if not crossed_down:
                continue

            gate_passed, current_ratio, target_ratio, z = self._passes_inventory_target_gate(
                current_price=current_price,
                projected_inventory_krw=projected_inventory_krw,
            )
            if not gate_passed:
                logger.info(
                    f"매수 차단(q_target) → 슬롯 {row.index}: "
                    f"current={current_price} z={z:.4f} q_current={current_ratio:.4f} "
                    f"q_target={target_ratio:.4f} epsilon={cfg.INVENTORY_TARGET_EPSILON}"
                )
                continue

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
            projected_inventory_krw += row.buy_price * row.planned_qty

        upward_buy_order, _ = self._make_upward_buy_order(
            previous_price,
            current_price,
            pending_slot_indexes,
            projected_inventory_krw,
            active_slot_indexes,
        )
        if upward_buy_order is not None:
            orders_by_slot[upward_buy_order.slot_index] = upward_buy_order

        return list(orders_by_slot.values())

    def _make_upward_buy_order(
        self,
        previous_price: Decimal,
        current_price: Decimal,
        pending_slot_indexes: set[int],
        projected_inventory_krw: Decimal,
        active_slot_indexes: set[int] | None,
    ) -> tuple[Order | None, Decimal]:
        if not self._is_upward_buy_enabled():
            return None, projected_inventory_krw

        if current_price <= previous_price:
            return None, projected_inventory_krw

        # 전체 그리드 기준 burst guard: pending/active 필터 이전에 교차 슬롯 수 확인
        all_crossed_rows = [
            row for row in self.grid.rows
            if row.is_empty
            and previous_price < row.buy_price <= current_price
        ]
        if not all_crossed_rows:
            return None, projected_inventory_krw

        if len(all_crossed_rows) > 1:
            skipped_slots = ", ".join(str(row.index) for row in all_crossed_rows)
            logger.info(
                f"급등 상승 매수 스킵(다중 상향 돌파) → {previous_price} -> {current_price} / "
                f"slots={skipped_slots}"
            )
            return None, projected_inventory_krw

        crossed_up_rows = [
            row for row in all_crossed_rows
            if row.index not in pending_slot_indexes
            and (active_slot_indexes is None or row.index in active_slot_indexes)
        ]
        if not crossed_up_rows:
            return None, projected_inventory_krw

        current_row = crossed_up_rows[0]
        gate_passed, current_ratio, target_ratio, z = self._passes_inventory_target_gate(
            current_price=current_price,
            projected_inventory_krw=projected_inventory_krw,
        )
        if not gate_passed:
            logger.info(
                f"상승 매수 차단(q_target) → 슬롯 {current_row.index}: "
                f"current={current_price} z={z:.4f} q_current={current_ratio:.4f} "
                f"q_target={target_ratio:.4f} epsilon={cfg.INVENTORY_TARGET_EPSILON}"
            )
            return None, projected_inventory_krw

        spend_amount = quantize_to_step(
            current_row.buy_price * current_row.planned_qty,
            KRW_ORDER_AMOUNT_STEP,
        )
        logger.info(
            f"매수 교차 조건 충족(상승) → 슬롯 {current_row.index}: "
            f"{previous_price} -> {current_price} / trigger={current_row.buy_price} "
            f"target={current_row.planned_qty} spend={spend_amount} KRW"
        )
        order = Order(
            slot_index=current_row.index,
            side=OrderSide.BUY,
            price=current_row.buy_price,
            quantity=current_row.planned_qty,
            symbol=self.symbol,
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=spend_amount,
        )
        return order, projected_inventory_krw + (current_row.buy_price * current_row.planned_qty)

    def _make_sell_orders(self, current_price: Decimal) -> List[Order]:
        orders = []
        for row in self.grid.rows:
            if not row.is_holding:
                continue

            effective_sell_price = self.grid.effective_sell_price(row.index)
            if current_price < effective_sell_price:
                continue

            orders.append(Order(
                slot_index=row.index,
                side=OrderSide.SELL,
                price=effective_sell_price,
                quantity=row.held_qty,
                symbol=self.symbol,
            ))
            logger.info(
                f"매도 조건 충족 → 슬롯 {row.index}: "
                f"current={current_price} / {effective_sell_price} x {row.held_qty}"
            )
        return orders

    def apply_filled_order(self, order: Order):
        """체결된 주문을 그리드 상태에 반영한다."""
        if order.side == OrderSide.BUY:
            self.grid.apply_buy(
                order.slot_index,
                order.quantity,
                filled_at=order.filled_at,
            )
            logger.info(f"매수 체결 반영 → 슬롯 {order.slot_index}")
        else:
            self.grid.apply_sell(order.slot_index)
            logger.info(f"매도 체결 반영 → 슬롯 {order.slot_index}")

    def apply_partial_sell(self, slot_index: int, filled_qty: Decimal) -> None:
        """부분 매도 체결 후 잔여 보유 수량을 유지한다."""
        self.grid.apply_sell(slot_index, filled_qty=filled_qty)
        logger.info(
            f"부분 매도 체결 반영 → 슬롯 {slot_index}: executed={filled_qty}"
        )

    def build_tp_sell_order_for_slot(self, slot_index: int) -> Order | None:
        row = next((candidate for candidate in self.grid.rows if candidate.index == slot_index), None)
        if row is None or not row.is_holding:
            return None

        effective_sell_price = self.grid.effective_sell_price(slot_index)
        if effective_sell_price * row.held_qty < MIN_KRW_ORDER_AMOUNT:
            logger.warning(
                f"TP 지정가 매도 스킵 → 슬롯 {slot_index}: "
                f"order_total={effective_sell_price * row.held_qty} < {MIN_KRW_ORDER_AMOUNT}"
            )
            return None

        return Order(
            slot_index=slot_index,
            side=OrderSide.SELL,
            price=effective_sell_price,
            quantity=row.held_qty,
            symbol=self.symbol,
        )

    def build_missing_tp_sell_orders(self, pending_sell_slot_indexes: set[int]) -> List[Order]:
        orders = []
        for row in self.grid.rows:
            if not row.is_holding or row.index in pending_sell_slot_indexes:
                continue
            order = self.build_tp_sell_order_for_slot(row.index)
            if order is not None:
                orders.append(order)
        return orders

    def _passes_inventory_target_gate(
        self,
        *,
        current_price: Decimal,
        projected_inventory_krw: Decimal,
    ) -> tuple[bool, Decimal, Decimal, Decimal]:
        current_ratio = self.grid.current_inventory_ratio(
            operating_budget_krw=cfg.MAX_OPERATING_BUDGET_KRW,
            inventory_cost_krw=projected_inventory_krw,
        )
        target_ratio = self.grid.target_inventory_ratio(
            current_price,
            q_min=cfg.INVENTORY_TARGET_Q_MIN,
            q_max=cfg.INVENTORY_TARGET_Q_MAX,
            gamma=cfg.INVENTORY_TARGET_GAMMA,
        )
        z = self.grid.band_position_z(current_price)
        threshold = max(target_ratio - cfg.INVENTORY_TARGET_EPSILON, Decimal("0"))
        return current_ratio < threshold, current_ratio, target_ratio, z

    def _is_upward_buy_enabled(self) -> bool:
        return bool(
            getattr(cfg, "UPWARD_SINGLE_SLOT_BUY_ENABLED", False)
            or getattr(cfg, "UPWARD_BUY_ENABLED", False)
            or getattr(cfg, "UP_BUY_ENABLED", False)
            or getattr(cfg, "ENABLE_UPWARD_BUY", False)
        )

    def _resolve_active_buy_window_slot_indexes(
        self,
        reference_price: Decimal | None,
    ) -> set[int] | None:
        if reference_price is None or not self._is_active_window_enabled():
            return None

        below_slots = self._active_window_below_current_slots()
        above_slots = self._active_window_above_current_slots()
        return self.grid.active_window_slot_indexes(
            reference_price,
            below_current_slots=below_slots,
            above_current_slots=above_slots,
        )

    def _is_active_window_enabled(self) -> bool:
        return bool(
            getattr(cfg, "ACTIVE_WINDOW_ENABLED", False)
            or getattr(cfg, "ACTIVE_BUY_WINDOW_ENABLED", False)
        )

    def _active_window_below_current_slots(self) -> int:
        raw_value = getattr(
            cfg,
            "ACTIVE_WINDOW_BELOW_CURRENT_SLOTS",
            getattr(cfg, "ACTIVE_BUY_WINDOW_BELOW_CURRENT_SLOTS", 48),
        )
        return max(int(raw_value), 0)

    def _active_window_above_current_slots(self) -> int:
        raw_value = getattr(
            cfg,
            "ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS",
            getattr(cfg, "ACTIVE_WINDOW_ABOVE_CURRENT_SLOTS", 4),
        )
        return max(int(raw_value), 0)
