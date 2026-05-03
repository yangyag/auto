import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import app.main as main
from app.core.grid import GridState
from app.core.models import GridRow, Order, OrderExecutionType, OrderSide, OrderStatus
from app.strategy.breakout_guard import BreakoutGuardStatus, evaluate_breakout_guard
from app.strategy.grid_strategy import GridStrategy


class BreakoutGuardTest(unittest.TestCase):

    def _grid_state(self) -> GridState:
        return GridState.from_rows(
            "KRW-BTC",
            [
                GridRow(1, Decimal("120"), Decimal("0"), Decimal("126"), Decimal("1")),
                GridRow(2, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1")),
                GridRow(3, Decimal("90"), Decimal("0"), Decimal("94.5"), Decimal("1")),
            ],
        )

    def test_evaluate_breakout_guard_activates_on_upper_breakout(self):
        status = evaluate_breakout_guard(
            [Decimal("125"), Decimal("124"), Decimal("123"), Decimal("122")],
            lower_price=Decimal("90"),
            upper_price=Decimal("120"),
            consecutive_count=4,
        )

        self.assertTrue(status.active)
        self.assertEqual(status.side, "upper")
        self.assertEqual(status.reason, "outside_upper_band")

    def test_evaluate_breakout_guard_activates_on_lower_breakout(self):
        status = evaluate_breakout_guard(
            [Decimal("89"), Decimal("88"), Decimal("87"), Decimal("86")],
            lower_price=Decimal("90"),
            upper_price=Decimal("120"),
            consecutive_count=4,
        )

        self.assertTrue(status.active)
        self.assertEqual(status.side, "lower")
        self.assertEqual(status.reason, "outside_lower_band")

    def test_evaluate_breakout_guard_stays_inactive_inside_band(self):
        status = evaluate_breakout_guard(
            [Decimal("119"), Decimal("118"), Decimal("117"), Decimal("116")],
            lower_price=Decimal("90"),
            upper_price=Decimal("120"),
            consecutive_count=4,
        )

        self.assertFalse(status.active)
        self.assertIsNone(status.side)
        self.assertEqual(status.reason, "inside_band")

    def test_fetch_breakout_guard_status_uses_recent_minute_closes(self):
        now = datetime(2026, 4, 19, 23, 7, tzinfo=timezone.utc)
        exchange = Mock()
        exchange.get_minute_candle_closes.return_value = [
            Decimal("125"),
            Decimal("124"),
            Decimal("123"),
            Decimal("122"),
        ]

        with patch.object(main.cfg, "BREAKOUT_GUARD_ENABLED", True), \
             patch.object(main.cfg, "BREAKOUT_GUARD_CANDLE_UNIT", 15), \
             patch.object(main.cfg, "BREAKOUT_GUARD_CONSECUTIVE_CANDLES", 4):
            status = main.fetch_breakout_guard_status(exchange, self._grid_state(), now=now)

        self.assertTrue(status.active)
        self.assertEqual(status.side, "upper")
        exchange.get_minute_candle_closes.assert_called_once_with(
            "KRW-BTC",
            unit_minutes=15,
            count=4,
            to=main._resolve_breakout_guard_cutoff(now),
        )

    def test_fetch_breakout_guard_status_fail_open_keeps_guard_inactive(self):
        exchange = Mock()
        exchange.get_minute_candle_closes.side_effect = RuntimeError("boom")

        with patch.object(main.cfg, "BREAKOUT_GUARD_ENABLED", True), \
             patch.object(main.cfg, "BREAKOUT_GUARD_FAIL_OPEN", True), \
             patch.object(main.cfg, "BREAKOUT_GUARD_CANDLE_UNIT", 15), \
             patch.object(main.cfg, "BREAKOUT_GUARD_CONSECUTIVE_CANDLES", 4):
            status = main.fetch_breakout_guard_status(exchange, self._grid_state())

        self.assertFalse(status.active)
        self.assertTrue(status.reason.startswith("guard_eval_failed:fail_open:"))

    def test_fetch_breakout_guard_status_fail_close_blocks_new_buys_on_api_error(self):
        exchange = Mock()
        exchange.get_minute_candle_closes.side_effect = RuntimeError("boom")

        with patch.object(main.cfg, "BREAKOUT_GUARD_ENABLED", True), \
             patch.object(main.cfg, "BREAKOUT_GUARD_FAIL_OPEN", False), \
             patch.object(main.cfg, "BREAKOUT_GUARD_CANDLE_UNIT", 15), \
             patch.object(main.cfg, "BREAKOUT_GUARD_CONSECUTIVE_CANDLES", 4):
            status = main.fetch_breakout_guard_status(exchange, self._grid_state())

        self.assertTrue(status.active)
        self.assertTrue(status.reason.startswith("guard_eval_failed:fail_close:"))

    def test_process_cycle_orders_still_submits_sells_when_guard_blocks_buys(self):
        grid = GridState.from_rows(
            "KRW-BTC",
            [
                GridRow(1, Decimal("100"), Decimal("1"), Decimal("110"), Decimal("0")),
                GridRow(2, Decimal("90"), Decimal("0"), Decimal("99"), Decimal("1")),
            ],
        )
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        exchange = Mock()
        exchange.place_order.return_value = "sell-id"
        exchange.get_order_status.return_value = OrderStatus(
            uuid="sell-id",
            state="wait",
            executed_volume=Decimal("0"),
            remaining_volume=Decimal("1"),
        )
        sell_order = Order(
            slot_index=1,
            side=OrderSide.SELL,
            price=Decimal("110"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )
        buy_order = Order(
            slot_index=2,
            side=OrderSide.BUY,
            price=Decimal("90"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("90"),
        )
        pending_orders = {}
        blocked_buys = main.apply_breakout_guard_to_buy_orders(
            [buy_order],
            BreakoutGuardStatus(active=True, reason="outside_upper_band", side="upper"),
        )

        with patch.object(main.cfg, "MAX_DAILY_ORDERS", 10), \
             patch.object(main.cfg, "MIN_BALANCE_RESERVE", Decimal("0")):
            submitted = main.process_cycle_orders(
                sell_orders=[sell_order],
                buy_orders=blocked_buys,
                exchange=exchange,
                strategy=strategy,
                pending_orders=pending_orders,
                daily_order_count=0,
            )

        self.assertEqual(submitted, 1)
        self.assertIn("sell-id", pending_orders)
        self.assertEqual(exchange.place_order.call_count, 1)
        self.assertEqual(exchange.place_order.call_args.args[0].side, OrderSide.SELL)
