import unittest
from decimal import Decimal

from core.grid import GridState
from core.models import GridRow


class GridStateInventoryMathTest(unittest.TestCase):

    def test_band_position_clamps_outside_band(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                GridRow(index=1, buy_price=Decimal("200"), held_qty=Decimal("0"), sell_price=Decimal("210"), planned_qty=Decimal("1")),
                GridRow(index=2, buy_price=Decimal("100"), held_qty=Decimal("0"), sell_price=Decimal("110"), planned_qty=Decimal("1")),
            ],
        )

        self.assertEqual(state.band_position_z(Decimal("50")), Decimal("0"))
        self.assertEqual(state.band_position_z(Decimal("300")), Decimal("1"))

    def test_current_inventory_ratio_uses_operating_budget_and_falls_back_to_allocated_budget(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                GridRow(index=1, buy_price=Decimal("200"), held_qty=Decimal("1"), sell_price=Decimal("210"), planned_qty=Decimal("0")),
                GridRow(index=2, buy_price=Decimal("100"), held_qty=Decimal("0"), sell_price=Decimal("110"), planned_qty=Decimal("1")),
            ],
        )

        self.assertEqual(state.current_inventory_ratio(operating_budget_krw=Decimal("400")), Decimal("0.5"))
        self.assertEqual(state.current_inventory_ratio(), Decimal("0.6666666666666666666666666667"))

    def test_target_inventory_ratio_decreases_toward_upper_band(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                GridRow(index=1, buy_price=Decimal("200"), held_qty=Decimal("0"), sell_price=Decimal("210"), planned_qty=Decimal("1")),
                GridRow(index=2, buy_price=Decimal("100"), held_qty=Decimal("0"), sell_price=Decimal("110"), planned_qty=Decimal("1")),
            ],
        )

        lower_target = state.target_inventory_ratio(
            Decimal("100"),
            q_min=Decimal("0.10"),
            q_max=Decimal("0.85"),
            gamma=Decimal("1.5"),
        )
        upper_target = state.target_inventory_ratio(
            Decimal("200"),
            q_min=Decimal("0.10"),
            q_max=Decimal("0.85"),
            gamma=Decimal("1.5"),
        )

        self.assertGreater(lower_target, upper_target)
        self.assertEqual(upper_target, Decimal("0.10"))

    def test_active_window_slot_indexes_selects_nearest_lower_and_upper_empty_slots(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                GridRow(index=1, buy_price=Decimal("130"), held_qty=Decimal("0"), sell_price=Decimal("136.5"), planned_qty=Decimal("1")),
                GridRow(index=2, buy_price=Decimal("120"), held_qty=Decimal("0"), sell_price=Decimal("126"), planned_qty=Decimal("1")),
                GridRow(index=3, buy_price=Decimal("110"), held_qty=Decimal("0"), sell_price=Decimal("115.5"), planned_qty=Decimal("1")),
                GridRow(index=4, buy_price=Decimal("100"), held_qty=Decimal("0"), sell_price=Decimal("105"), planned_qty=Decimal("1")),
                GridRow(index=5, buy_price=Decimal("90"), held_qty=Decimal("0"), sell_price=Decimal("94.5"), planned_qty=Decimal("1")),
            ],
        )

        active_indexes = state.active_window_slot_indexes(
            Decimal("108"),
            below_current_slots=2,
            above_current_slots=1,
        )

        self.assertEqual(active_indexes, {3, 4, 5})


if __name__ == "__main__":
    unittest.main()
