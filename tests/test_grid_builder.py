import unittest
from decimal import Decimal

from core.grid import GridState
from core.grid_builder import build_cash_only_grid
from core.grid_properties import build_sell_price
from utils.decimal_utils import BTC_QUANTITY_STEP


class GridBuilderTest(unittest.TestCase):

    def test_build_cash_only_grid_returns_10_active_buy_slots(self):
        rows = build_cash_only_grid(
            lower_price=Decimal("92253123"),
            upper_price=Decimal("111137221"),
            current_price=Decimal("112000000"),
            slot_count=10,
            first_buy_amount_krw=Decimal("200000"),
            sell_percent=Decimal("5"),
        )

        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row.held_qty == Decimal("0") for row in rows))
        self.assertTrue(all(row.planned_qty > Decimal("0") for row in rows))
        self.assertTrue(all(row.planned_qty == rows[0].planned_qty for row in rows))
        self.assertTrue(all(rows[index].buy_price > rows[index + 1].buy_price for index in range(len(rows) - 1)))
        self.assertTrue(all(row.buy_price < Decimal("112000000") for row in rows))
        self.assertEqual(rows[0].sell_price, build_sell_price(rows[0].buy_price, Decimal("5")))
        self.assertEqual(rows[-1].buy_price, Decimal("92253000"))
        self.assertTrue(all(row.sell_price > row.buy_price for row in rows))

        first_order_amount = rows[0].buy_price * rows[0].planned_qty
        self.assertEqual(rows[0].planned_qty, Decimal("0.00183341"))
        self.assertLessEqual(first_order_amount, Decimal("200000"))
        self.assertGreater(first_order_amount, Decimal("200000") - (rows[0].buy_price * BTC_QUANTITY_STEP))

    def test_build_cash_only_grid_uses_fixed_upper_lower_boundaries(self):
        rows = build_cash_only_grid(
            lower_price=Decimal("93695193"),
            upper_price=Decimal("110370483"),
            current_price=Decimal("115000000"),
            slot_count=10,
            first_buy_amount_krw=Decimal("200000"),
            sell_percent=Decimal("5"),
        )

        expected_buy_prices = [
            Decimal("108576000"),
            Decimal("106813000"),
            Decimal("105077000"),
            Decimal("103370000"),
            Decimal("101691000"),
            Decimal("100039000"),
            Decimal("98413000"),
            Decimal("96815000"),
            Decimal("95242000"),
            Decimal("93695000"),
        ]

        self.assertEqual(
            [(row.buy_price, row.sell_price) for row in rows],
            [
                (buy_price, build_sell_price(buy_price, Decimal("5")))
                for buy_price in expected_buy_prices
            ],
        )

    def test_build_cash_only_grid_allows_current_price_below_top_buy_level(self):
        rows = build_cash_only_grid(
            lower_price=Decimal("93695193"),
            upper_price=Decimal("110370483"),
            current_price=Decimal("105695000"),
            slot_count=10,
            first_buy_amount_krw=Decimal("200000"),
            sell_percent=Decimal("5"),
        )

        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0].buy_price, Decimal("108576000"))

    def test_grid_state_snapshot_round_trip_preserves_decimal_quantities(self):
        rows = build_cash_only_grid(
            lower_price=Decimal("92253123"),
            upper_price=Decimal("111137221"),
            current_price=Decimal("112000000"),
            slot_count=10,
            first_buy_amount_krw=Decimal("200000"),
            sell_percent=Decimal("5"),
        )

        state = GridState.from_rows("KRW-BTC", rows)
        snapshot = state.to_snapshot()
        reloaded = GridState.from_snapshot(snapshot)

        self.assertEqual(reloaded.symbol, "KRW-BTC")
        self.assertEqual(len(reloaded.rows), 10)
        self.assertEqual(reloaded.rows[0].planned_qty, rows[0].planned_qty)
        self.assertEqual(reloaded.rows[-1].buy_price, rows[-1].buy_price)
