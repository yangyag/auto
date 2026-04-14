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

    def test_buys_when_price_crosses_up_through_buy_line(self):
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

    def test_sells_only_when_price_crosses_up_through_sell_line(self):
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

    def test_upward_cross_can_trigger_upper_buy_and_lower_sell_together(self):
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

    def test_large_upward_move_buys_all_crossed_empty_slots(self):
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

        self.assertEqual([order.slot_index for order in buy_orders], [1, 2])
        self.assertEqual([order.execution_type for order in buy_orders], [
            OrderExecutionType.MARKET_BUY_BY_PRICE,
            OrderExecutionType.MARKET_BUY_BY_PRICE,
        ])
        self.assertEqual([order.spend_amount for order in buy_orders], [
            Decimal("110"),
            Decimal("100"),
        ])
        self.assertEqual(sell_orders, [])
