import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import config.settings as cfg
from core.grid_properties import (
    GridPropertySpec,
    build_grid_rows_from_property_spec,
    build_sell_price,
    build_target_sell_price,
    build_weighted_slot_buy_amounts,
    load_grid_property_spec,
)


class GridPropertiesTest(unittest.TestCase):
    def test_load_grid_property_spec_parses_required_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nBUY_AMOUNT_KRW=200000\nGRID_COUNT=20\nSELL_PERCENT=5\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(
            spec,
            GridPropertySpec(
                min_buy_price=Decimal("91623000"),
                max_buy_price=Decimal("127886000"),
                buy_amount_krw=Decimal("200000"),
                grid_count=20,
                sell_percent=Decimal("5"),
            ),
        )

    def test_load_grid_property_spec_defaults_sell_percent_to_five_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nBUY_AMOUNT_KRW=200000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(spec.sell_percent, Decimal("5"))

    def test_build_grid_rows_from_property_spec_uses_buy_bounds_as_top_and_bottom_slots(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("91623000"),
            max_buy_price=Decimal("127886000"),
            buy_amount_krw=Decimal("200000"),
            grid_count=20,
            sell_percent=Decimal("5"),
        )

        rows = build_grid_rows_from_property_spec(spec)

        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0].buy_price, Decimal("127886000"))
        self.assertEqual(rows[-1].buy_price, Decimal("91623000"))
        self.assertTrue(all(row.held_qty == Decimal("0") for row in rows))
        self.assertTrue(all(row.planned_qty > Decimal("0") for row in rows))
        self.assertGreater(rows[-1].planned_qty, rows[0].planned_qty)
        self.assertEqual(
            rows[0].sell_price,
            build_target_sell_price(
                rows[0].buy_price,
                tp_model="k",
                lower_price=spec.min_buy_price,
                upper_price=spec.max_buy_price,
                price_interval_count=spec.grid_count - 1,
                tp_k=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            ),
        )
        self.assertEqual(
            rows[-1].sell_price,
            build_target_sell_price(
                rows[-1].buy_price,
                tp_model="k",
                lower_price=spec.min_buy_price,
                upper_price=spec.max_buy_price,
                price_interval_count=spec.grid_count - 1,
                tp_k=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            ),
        )
        self.assertGreater(rows[0].sell_price, rows[0].buy_price)
        self.assertTrue(all(rows[i].buy_price > rows[i + 1].buy_price for i in range(len(rows) - 1)))

    def test_build_grid_rows_from_property_spec_rejects_non_aligned_boundary_prices(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("91623999"),
            max_buy_price=Decimal("127886999"),
            buy_amount_krw=Decimal("200000"),
            grid_count=20,
            sell_percent=Decimal("5"),
        )

        with self.assertRaises(ValueError):
            build_grid_rows_from_property_spec(spec)

    def test_build_weighted_slot_buy_amounts_preserve_total_budget_for_uneven_grid_count(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("130000000"),
            buy_amount_krw=Decimal("200000"),
            grid_count=4,
            sell_percent=Decimal("5"),
        )

        slot_buy_amounts = build_weighted_slot_buy_amounts(spec)

        self.assertEqual(len(slot_buy_amounts), 4)
        self.assertLess(slot_buy_amounts[0], spec.buy_amount_krw)
        self.assertGreater(slot_buy_amounts[-1], spec.buy_amount_krw)
        self.assertLess(abs(sum(slot_buy_amounts, Decimal("0")) - (spec.buy_amount_krw * spec.grid_count)), Decimal("0.0001"))

    def test_build_grid_rows_from_property_spec_computes_slot_qty_from_weighted_buy_amount(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            buy_amount_krw=Decimal("200000"),
            grid_count=3,
            sell_percent=Decimal("5"),
        )

        rows = build_grid_rows_from_property_spec(spec)

        self.assertEqual(build_weighted_slot_buy_amounts(spec), [Decimal("140000.0"), Decimal("200000.0"), Decimal("260000.0")])
        self.assertEqual(rows[0].planned_qty, Decimal("0.00116666"))
        self.assertEqual(rows[1].planned_qty, Decimal("0.00182575"))
        self.assertEqual(rows[2].planned_qty, Decimal("0.00260000"))
        self.assertLess(rows[0].buy_price * rows[0].planned_qty, spec.buy_amount_krw)
        self.assertGreater(rows[2].buy_price * rows[2].planned_qty, spec.buy_amount_krw)
        self.assertEqual(
            rows[0].sell_price,
            build_target_sell_price(
                rows[0].buy_price,
                tp_model="k",
                lower_price=spec.min_buy_price,
                upper_price=spec.max_buy_price,
                price_interval_count=spec.grid_count - 1,
                tp_k=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            ),
        )
        self.assertEqual(
            rows[1].sell_price,
            build_target_sell_price(
                rows[1].buy_price,
                tp_model="k",
                lower_price=spec.min_buy_price,
                upper_price=spec.max_buy_price,
                price_interval_count=spec.grid_count - 1,
                tp_k=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            ),
        )
        self.assertEqual(
            rows[2].sell_price,
            build_target_sell_price(
                rows[2].buy_price,
                tp_model="k",
                lower_price=spec.min_buy_price,
                upper_price=spec.max_buy_price,
                price_interval_count=spec.grid_count - 1,
                tp_k=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            ),
        )

    def test_build_grid_rows_from_property_spec_supports_explicit_percent_tp_mode(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            buy_amount_krw=Decimal("200000"),
            grid_count=3,
            sell_percent=Decimal("5"),
            tp_model="percent",
        )

        rows = build_grid_rows_from_property_spec(spec)

        self.assertEqual(rows[0].sell_price, build_sell_price(rows[0].buy_price, spec.sell_percent))
        self.assertEqual(rows[1].sell_price, build_sell_price(rows[1].buy_price, spec.sell_percent))
        self.assertEqual(rows[2].sell_price, build_sell_price(rows[2].buy_price, spec.sell_percent))

    def test_build_grid_rows_from_property_spec_rejects_weighted_top_slot_below_minimum_order_amount(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            buy_amount_krw=Decimal("5000"),
            grid_count=3,
            sell_percent=Decimal("5"),
        )

        with self.assertRaisesRegex(ValueError, "슬롯 1 매수 금액이 업비트 최소 주문 금액보다 작습니다."):
            build_grid_rows_from_property_spec(spec)

    def test_checked_in_grid_properties_align_with_runtime_k_defaults(self):
        project_root = Path(__file__).resolve().parents[1]
        spec = load_grid_property_spec(project_root / "grid.properties")

        self.assertEqual(spec.tp_model, "k")
        self.assertEqual(spec.tp_k_base, cfg.GRID_TP_K_BASE)
        self.assertEqual(spec.tp_k_floor, cfg.GRID_TP_K_FLOOR)


if __name__ == "__main__":
    unittest.main()
