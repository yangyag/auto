import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

import config.settings as cfg
from core.grid_properties import (
    GridPropertySpec,
    build_grid_rows_from_property_spec,
    build_target_sell_price,
    build_weighted_slot_budgets,
    load_grid_property_spec,
)


class GridPropertiesTest(unittest.TestCase):
    def test_load_grid_property_spec_parses_required_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nTOTAL_BUDGET_KRW=4000000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(
            spec,
            GridPropertySpec(
                min_buy_price=Decimal("91623000"),
                max_buy_price=Decimal("127886000"),
                total_budget_krw=Decimal("4000000"),
                grid_count=20,
                tp_model="k",
            ),
        )

    def test_load_grid_property_spec_derives_grid_count_from_step_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=100000000\nMAX_BUY_PRICE=121000000\nTOTAL_BUDGET_KRW=600000\nGRID_STEP_PCT=10\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(
            spec,
            GridPropertySpec(
                min_buy_price=Decimal("100000000"),
                max_buy_price=Decimal("121000000"),
                total_budget_krw=Decimal("600000"),
                grid_count=3,
                tp_model="k",
            ),
        )

    def test_load_grid_property_spec_prefers_more_intervals_on_tie(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            with localcontext() as ctx:
                ctx.prec = 80
                target_log_step = (Decimal("1") + (Decimal("10") / Decimal("100"))).ln()
                max_buy_price = Decimal("100000000") * (
                    (target_log_step * (Decimal("4") / Decimal("3"))).exp()
                )
            path.write_text(
                "MIN_BUY_PRICE=100000000\n"
                f"MAX_BUY_PRICE={max_buy_price}\n"
                "TOTAL_BUDGET_KRW=600000\n"
                "GRID_STEP_PCT=10\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(spec.grid_count, 3)

    def test_load_grid_property_spec_defaults_tp_model_to_k(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nTOTAL_BUDGET_KRW=4000000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(spec.tp_model, "k")

    def test_build_grid_rows_from_property_spec_uses_buy_bounds_as_top_and_bottom_slots(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("91623000"),
            max_buy_price=Decimal("127886000"),
            total_budget_krw=Decimal("4000000"),
            grid_count=20,
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
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
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
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
            ),
        )
        self.assertGreater(rows[0].sell_price, rows[0].buy_price)
        self.assertTrue(all(rows[i].buy_price > rows[i + 1].buy_price for i in range(len(rows) - 1)))

    def test_build_grid_rows_from_property_spec_rejects_non_aligned_boundary_prices(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("91623999"),
            max_buy_price=Decimal("127886999"),
            total_budget_krw=Decimal("4000000"),
            grid_count=20,
        )

        with self.assertRaises(ValueError):
            build_grid_rows_from_property_spec(spec)

    def test_build_weighted_slot_budgets_preserve_total_budget_for_uneven_grid_count(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("130000000"),
            total_budget_krw=Decimal("800000"),
            grid_count=4,
        )

        slot_budgets = build_weighted_slot_budgets(spec)

        self.assertEqual(len(slot_budgets), 4)
        self.assertLess(slot_budgets[0], spec.total_budget_krw / spec.grid_count)
        self.assertGreater(slot_budgets[-1], spec.total_budget_krw / spec.grid_count)
        self.assertLess(abs(sum(slot_budgets, Decimal("0")) - spec.total_budget_krw), Decimal("0.0001"))

    def test_build_grid_rows_from_property_spec_computes_slot_qty_from_weighted_buy_amount(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("600000"),
            grid_count=3,
        )

        rows = build_grid_rows_from_property_spec(spec)

        self.assertEqual(build_weighted_slot_budgets(spec), [Decimal("140000.0"), Decimal("200000.0"), Decimal("260000.0")])
        self.assertEqual(rows[0].planned_qty, Decimal("0.00116666"))
        self.assertEqual(rows[1].planned_qty, Decimal("0.00182575"))
        self.assertEqual(rows[2].planned_qty, Decimal("0.00260000"))
        self.assertLess(rows[0].buy_price * rows[0].planned_qty, spec.total_budget_krw / spec.grid_count)
        self.assertGreater(rows[2].buy_price * rows[2].planned_qty, spec.total_budget_krw / spec.grid_count)
        self.assertEqual(
            rows[0].sell_price,
            build_target_sell_price(
                rows[0].buy_price,
                tp_model="k",
                lower_price=spec.min_buy_price,
                upper_price=spec.max_buy_price,
                price_interval_count=spec.grid_count - 1,
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
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
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
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
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
            ),
        )

    def test_build_grid_rows_from_property_spec_rejects_weighted_top_slot_below_minimum_order_amount(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("15000"),
            grid_count=3,
        )

        with self.assertRaisesRegex(ValueError, "슬롯 1 매수 금액이 업비트 최소 주문 금액보다 작습니다."):
            build_grid_rows_from_property_spec(spec)

    def test_step_pct_path_matches_explicit_grid_count_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            explicit_path = Path(tmpdir) / "explicit-grid.properties"
            explicit_path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nTOTAL_BUDGET_KRW=4000000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )
            step_path = Path(tmpdir) / "step-grid.properties"
            step_path.write_text(
                "MIN_BUY_PRICE=91623000\n"
                "MAX_BUY_PRICE=127886000\n"
                "TOTAL_BUDGET_KRW=4000000\n"
                "GRID_STEP_PCT=1.77052762586201367544582198090413318873624688088\n",
                encoding="utf-8",
            )

            explicit_spec = load_grid_property_spec(explicit_path)
            step_spec = load_grid_property_spec(step_path)

        self.assertEqual(step_spec.grid_count, explicit_spec.grid_count)
        self.assertEqual(
            build_grid_rows_from_property_spec(step_spec),
            build_grid_rows_from_property_spec(explicit_spec),
        )

    def test_load_grid_property_spec_rejects_unknown_property(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nTOTAL_BUDGET_KRW=4000000\nGRID_COUNT=20\nLEGACY_TP=5\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "grid.properties 지원하지 않는 항목: LEGACY_TP"):
                load_grid_property_spec(path)

    def test_load_grid_property_spec_rejects_other_unknown_property(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nTOTAL_BUDGET_KRW=4000000\nGRID_COUNT=20\nEXTRA_FLAG=1\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "grid.properties 지원하지 않는 항목: EXTRA_FLAG"):
                load_grid_property_spec(path)

    def test_load_grid_property_spec_rejects_both_count_and_step_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\n"
                "MAX_BUY_PRICE=127886000\n"
                "TOTAL_BUDGET_KRW=4000000\n"
                "GRID_COUNT=20\n"
                "GRID_STEP_PCT=1.77052762586201367544582198090413318873624688088\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "GRID_STEP_PCT와 GRID_COUNT는 동시에 지정할 수 없습니다."):
                load_grid_property_spec(path)

    def test_load_grid_property_spec_rejects_missing_count_and_step_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nTOTAL_BUDGET_KRW=4000000\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "grid.properties 필수 항목 누락: GRID_COUNT 또는 GRID_STEP_PCT"):
                load_grid_property_spec(path)

    def test_load_grid_property_spec_rejects_non_positive_step_pct(self):
        for step_pct in ("0", "-1"):
            with self.subTest(step_pct=step_pct):
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = Path(tmpdir) / "grid.properties"
                    path.write_text(
                        "MIN_BUY_PRICE=100000000\n"
                        "MAX_BUY_PRICE=121000000\n"
                        "TOTAL_BUDGET_KRW=600000\n"
                        f"GRID_STEP_PCT={step_pct}\n",
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(ValueError, "GRID_STEP_PCT는 0보다 커야 합니다."):
                        load_grid_property_spec(path)

    def test_load_grid_property_spec_allows_large_step_pct_to_resolve_two_slots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=100000000\nMAX_BUY_PRICE=110000000\nTOTAL_BUDGET_KRW=600000\nGRID_STEP_PCT=25\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(spec.grid_count, 2)

    def test_checked_in_grid_properties_align_with_runtime_k_defaults(self):
        project_root = Path(__file__).resolve().parents[1]
        spec = load_grid_property_spec(project_root / "grid.properties")

        self.assertGreaterEqual(spec.grid_count, 2)
        self.assertEqual(spec.tp_model, "k")
        self.assertEqual(spec.tp_k_base, cfg.GRID_TP_K_BASE)
        self.assertEqual(spec.tp_k_floor, cfg.GRID_TP_K_FLOOR)


if __name__ == "__main__":
    unittest.main()
