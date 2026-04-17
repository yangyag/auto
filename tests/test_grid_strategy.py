import unittest
from decimal import Decimal
from unittest.mock import Mock

from core.grid import GridState
from core.models import GridRow, OrderExecutionType
from strategy.grid_strategy import GridStrategy


class GridStrategyCrossingTest(unittest.TestCase):

    def test_does_not_buy_immediately_when_starting_below_buy_line(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            )
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        buy_orders, sell_orders = strategy.evaluate(Decimal("95"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(sell_orders, [])

    def test_buys_only_when_price_crosses_down_through_buy_line(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            )
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("105"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("100"))

        self.assertEqual(len(buy_orders), 1)
        self.assertEqual(buy_orders[0].slot_index, 1)
        self.assertEqual(buy_orders[0].price, Decimal("100"))
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.LIMIT)
        self.assertEqual(sell_orders, [])

    def test_large_downward_move_buys_all_crossed_empty_slots(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("105"),
                held_qty=Decimal("0"),
                sell_price=Decimal("115"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("95"),
                held_qty=Decimal("0"),
                sell_price=Decimal("105"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("110"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("90"))

        self.assertEqual([order.slot_index for order in buy_orders], [1, 2, 3])
        self.assertTrue(all(order.execution_type == OrderExecutionType.LIMIT for order in buy_orders))
        self.assertEqual(sell_orders, [])

    def test_buys_when_single_price_line_crosses_up_through_buy_line(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            )
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("95"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("100"))

        self.assertEqual(len(buy_orders), 1)
        self.assertEqual(buy_orders[0].slot_index, 1)
        self.assertEqual(buy_orders[0].price, Decimal("100"))
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual(buy_orders[0].spend_amount, Decimal("100"))
        self.assertEqual(sell_orders, [])

    def test_buys_crossed_empty_slots_one_by_one_on_gradual_upward_moves(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("130"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("95"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("100"))
        self.assertEqual([order.slot_index for order in buy_orders], [2])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual(sell_orders, [])

        strategy.apply_filled_order(buy_orders[0])
        buy_orders, sell_orders = strategy.evaluate(Decimal("110"))
        self.assertEqual([order.slot_index for order in buy_orders], [1])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual(sell_orders, [])

    def test_sells_when_current_price_reaches_sell_line(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("1"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("0"),
            )
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("105"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("110"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(len(sell_orders), 1)
        self.assertEqual(sell_orders[0].slot_index, 1)
        self.assertEqual(sell_orders[0].price, Decimal("110"))

    def test_sells_when_price_stays_above_sell_line(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("1"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("0"),
            )
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")
        strategy.previous_price = Decimal("115")

        buy_orders, sell_orders = strategy.evaluate(Decimal("115"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(len(sell_orders), 1)
        self.assertEqual(sell_orders[0].slot_index, 1)

    def test_sells_on_first_snapshot_when_holding_is_already_above_sell_line(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("1"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("0"),
            )
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        buy_orders, sell_orders = strategy.evaluate(Decimal("115"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(len(sell_orders), 1)
        self.assertEqual(sell_orders[0].slot_index, 1)

    def test_upward_move_can_trigger_upper_buy_and_lower_sell_together(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("100"),
                held_qty=Decimal("1"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("0"),
            ),
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("105"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("110"))

        self.assertEqual([order.slot_index for order in buy_orders], [1])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual([order.slot_index for order in sell_orders], [2])

    def test_large_upward_move_skips_buy_when_multiple_empty_slots_are_crossed(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("95"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("115"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(sell_orders, [])

    def test_large_upward_move_ignores_pending_slots_when_counting_actionable_buys(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("95"))
        buy_orders, sell_orders = strategy.evaluate_with_pending(
            Decimal("115"),
            pending_slot_indexes={2},
        )

        self.assertEqual([order.slot_index for order in buy_orders], [1])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual(sell_orders, [])

    def test_upward_move_with_single_cross_still_sells_all_eligible_holding_slots(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("100"),
                held_qty=Decimal("1"),
                sell_price=Decimal("103"),
                planned_qty=Decimal("0"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("90"),
                held_qty=Decimal("1"),
                sell_price=Decimal("95"),
                planned_qty=Decimal("0"),
            ),
        ]
        strategy = GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

        strategy.evaluate(Decimal("94"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("115"))

        self.assertEqual([order.slot_index for order in buy_orders], [1])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual([order.slot_index for order in sell_orders], [2, 3])
