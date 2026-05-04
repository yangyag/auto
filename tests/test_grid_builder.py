import unittest
from decimal import Decimal

from app.core.grid import GridState
from app.core.grid_builder import build_cash_only_grid
from app.core.grid_properties import GridPropertySpec, build_grid_rows_from_property_spec, build_target_sell_price
from app.utils.decimal_utils import BTC_QUANTITY_STEP


class GridBuilderTest(unittest.TestCase):

    def test_build_cash_only_grid_matches_property_spec_generation(self):
        rows = build_cash_only_grid(
            lower_price=Decimal("92253123"),
            upper_price=Decimal("111137221"),
            slot_count=10,
            total_budget_krw=Decimal("2000000"),
        )
        expected_rows = build_grid_rows_from_property_spec(
            GridPropertySpec(
                min_buy_price=Decimal("92253000"),
                max_buy_price=Decimal("111137000"),
                total_budget_krw=Decimal("2000000"),
                grid_count=10,
            ),
        )

        self.assertEqual(rows, expected_rows)

    def test_build_cash_only_grid_uses_fixed_upper_lower_boundaries(self):
        rows = build_cash_only_grid(
            lower_price=Decimal("93695193"),
            upper_price=Decimal("110370483"),
            slot_count=10,
            total_budget_krw=Decimal("2000000"),
        )

        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0].buy_price, Decimal("110370000"))
        self.assertEqual(rows[-1].buy_price, Decimal("93695000"))
        self.assertTrue(all(rows[index].buy_price > rows[index + 1].buy_price for index in range(len(rows) - 1)))
        self.assertEqual(
            rows[0].sell_price,
            build_target_sell_price(
                rows[0].buy_price,
                tp_model="k",
                lower_price=Decimal("93695193"),
                upper_price=Decimal("110370483"),
                price_interval_count=9,
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
            ),
        )

    def test_build_cash_only_grid_preserves_total_budget_with_rounding_tolerance(self):
        total_budget = Decimal("2000000")
        rows = build_cash_only_grid(
            lower_price=Decimal("92253123"),
            upper_price=Decimal("111137221"),
            slot_count=10,
            total_budget_krw=total_budget,
        )

        allocated_budget = sum((row.buy_price * row.planned_qty for row in rows), Decimal("0"))
        max_rounding_loss = sum((row.buy_price * BTC_QUANTITY_STEP for row in rows), Decimal("0"))

        self.assertLessEqual(allocated_budget, total_budget)
        self.assertGreater(allocated_budget, total_budget - max_rounding_loss)
        self.assertGreater(rows[-1].planned_qty, rows[0].planned_qty)

    def test_grid_state_snapshot_round_trip_preserves_decimal_quantities(self):
        rows = build_cash_only_grid(
            lower_price=Decimal("92253123"),
            upper_price=Decimal("111137221"),
            slot_count=10,
            total_budget_krw=Decimal("2000000"),
        )

        state = GridState.from_rows("KRW-BTC", rows)
        snapshot = state.to_snapshot()
        reloaded = GridState.from_snapshot(snapshot)

        self.assertEqual(reloaded.symbol, "KRW-BTC")
        self.assertEqual(len(reloaded.rows), 10)
        self.assertEqual(reloaded.rows[0].planned_qty, rows[0].planned_qty)
        self.assertEqual(reloaded.rows[-1].buy_price, rows[-1].buy_price)
