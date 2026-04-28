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
    resolve_total_budget_from_lower,
)


class GridPropertiesTest(unittest.TestCase):
    def test_load_grid_property_spec_parses_required_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nLOWER_BUDGET_KRW=4000000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(
            spec,
            GridPropertySpec(
                min_buy_price=Decimal("91623000"),
                max_buy_price=Decimal("127886000"),
                lower_budget_krw=Decimal("4000000"),
                grid_count=20,
                tp_model="k",
            ),
        )

    def test_load_grid_property_spec_derives_grid_count_from_step_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=100000000\nMAX_BUY_PRICE=121000000\nLOWER_BUDGET_KRW=600000\nGRID_STEP_PCT=10\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(
            spec,
            GridPropertySpec(
                min_buy_price=Decimal("100000000"),
                max_buy_price=Decimal("121000000"),
                lower_budget_krw=Decimal("600000"),
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
                "LOWER_BUDGET_KRW=600000\n"
                "GRID_STEP_PCT=10\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(spec.grid_count, 3)

    def test_load_grid_property_spec_defaults_tp_model_to_k(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nLOWER_BUDGET_KRW=4000000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(spec.tp_model, "k")

    def test_build_grid_rows_from_property_spec_uses_buy_bounds_as_top_and_bottom_slots(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("91623000"),
            max_buy_price=Decimal("127886000"),
            lower_budget_krw=Decimal("4000000"),
            grid_count=20,
        )

        rows = build_grid_rows_from_property_spec(spec, current_price=Decimal("130000000"))

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
            lower_budget_krw=Decimal("4000000"),
            grid_count=20,
        )

        with self.assertRaises(ValueError):
            build_grid_rows_from_property_spec(spec, current_price=Decimal("130000000"))

    def test_build_weighted_slot_budgets_preserve_total_budget_for_uneven_grid_count(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("130000000"),
            lower_budget_krw=Decimal("800000"),
            grid_count=4,
        )

        slot_budgets, lower_indices, lower_ratio, target_total = build_weighted_slot_budgets(
            spec, current_price=Decimal("140000000")
        )

        self.assertEqual(len(slot_budgets), 4)
        self.assertEqual(lower_indices, [0, 1, 2, 3])
        self.assertEqual(lower_ratio, Decimal("1"))
        self.assertEqual(target_total, spec.lower_budget_krw)
        self.assertLess(slot_budgets[0], spec.lower_budget_krw / spec.grid_count)
        self.assertGreater(slot_budgets[-1], spec.lower_budget_krw / spec.grid_count)
        self.assertLess(abs(sum(slot_budgets, Decimal("0")) - spec.lower_budget_krw), Decimal("0.0001"))

    def test_build_grid_rows_from_property_spec_computes_slot_qty_from_weighted_buy_amount(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            lower_budget_krw=Decimal("600000"),
            grid_count=3,
        )

        rows = build_grid_rows_from_property_spec(spec, current_price=Decimal("130000000"))

        slot_budgets, _, _, _ = build_weighted_slot_budgets(spec, current_price=Decimal("130000000"))
        self.assertEqual(slot_budgets, [Decimal("140000.0"), Decimal("200000.0"), Decimal("260000.0")])
        self.assertEqual(rows[0].planned_qty, Decimal("0.00116666"))
        self.assertEqual(rows[1].planned_qty, Decimal("0.00182575"))
        self.assertEqual(rows[2].planned_qty, Decimal("0.00260000"))
        self.assertLess(rows[0].buy_price * rows[0].planned_qty, spec.lower_budget_krw / spec.grid_count)
        self.assertGreater(rows[2].buy_price * rows[2].planned_qty, spec.lower_budget_krw / spec.grid_count)
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
            lower_budget_krw=Decimal("15000"),
            grid_count=3,
        )

        with self.assertRaisesRegex(ValueError, "슬롯 1 매수 금액이 업비트 최소 주문 금액보다 작습니다."):
            build_grid_rows_from_property_spec(spec, current_price=Decimal("130000000"))

    def test_step_pct_path_matches_explicit_grid_count_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            explicit_path = Path(tmpdir) / "explicit-grid.properties"
            explicit_path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nLOWER_BUDGET_KRW=4000000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )
            step_path = Path(tmpdir) / "step-grid.properties"
            step_path.write_text(
                "MIN_BUY_PRICE=91623000\n"
                "MAX_BUY_PRICE=127886000\n"
                "LOWER_BUDGET_KRW=4000000\n"
                "GRID_STEP_PCT=1.77052762586201367544582198090413318873624688088\n",
                encoding="utf-8",
            )

            explicit_spec = load_grid_property_spec(explicit_path)
            step_spec = load_grid_property_spec(step_path)

        self.assertEqual(step_spec.grid_count, explicit_spec.grid_count)
        self.assertEqual(
            build_grid_rows_from_property_spec(step_spec, current_price=Decimal("130000000")),
            build_grid_rows_from_property_spec(explicit_spec, current_price=Decimal("130000000")),
        )

    def test_load_grid_property_spec_rejects_unknown_property(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nLOWER_BUDGET_KRW=4000000\nGRID_COUNT=20\nLEGACY_TP=5\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "grid.properties 지원하지 않는 항목: LEGACY_TP"):
                load_grid_property_spec(path)

    def test_load_grid_property_spec_rejects_other_unknown_property(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nLOWER_BUDGET_KRW=4000000\nGRID_COUNT=20\nEXTRA_FLAG=1\n",
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
                "LOWER_BUDGET_KRW=4000000\n"
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
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nLOWER_BUDGET_KRW=4000000\n",
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
                        "LOWER_BUDGET_KRW=600000\n"
                        f"GRID_STEP_PCT={step_pct}\n",
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(ValueError, "GRID_STEP_PCT는 0보다 커야 합니다."):
                        load_grid_property_spec(path)

    def test_load_grid_property_spec_allows_large_step_pct_to_resolve_two_slots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grid.properties"
            path.write_text(
                "MIN_BUY_PRICE=100000000\nMAX_BUY_PRICE=110000000\nLOWER_BUDGET_KRW=600000\nGRID_STEP_PCT=25\n",
                encoding="utf-8",
            )

            spec = load_grid_property_spec(path)

        self.assertEqual(spec.grid_count, 2)

    def test_resolve_total_budget_from_lower_partial_lower(self):
        raw_weights = [Decimal("0.7"), Decimal("1.0"), Decimal("1.3")]
        buy_prices_desc = [Decimal("120000000"), Decimal("110000000"), Decimal("100000000")]
        target_total, lower_indices, lower_ratio = resolve_total_budget_from_lower(
            raw_weights=raw_weights,
            buy_prices_desc=buy_prices_desc,
            current_price=Decimal("115000000"),
            lower_budget_krw=Decimal("230000"),
        )

        self.assertEqual(lower_indices, [1, 2])
        # lower_weight_sum=2.3, total=3.0 → ratio=23/30
        self.assertEqual(lower_ratio, Decimal("2.3") / Decimal("3.0"))
        # target_total = 230000 / (23/30) = 300000
        self.assertEqual(target_total, Decimal("300000"))

    def test_resolve_total_budget_from_lower_rejects_no_lower_slots(self):
        raw_weights = [Decimal("0.7"), Decimal("1.3")]
        buy_prices_desc = [Decimal("120000000"), Decimal("100000000")]
        with self.assertRaisesRegex(ValueError, "현재가.*미만의 슬롯이 없습니다"):
            resolve_total_budget_from_lower(
                raw_weights=raw_weights,
                buy_prices_desc=buy_prices_desc,
                current_price=Decimal("99000000"),
                lower_budget_krw=Decimal("100000"),
            )

    def test_resolve_total_budget_from_lower_strict_less_than_excludes_equal(self):
        raw_weights = [Decimal("0.7"), Decimal("1.0"), Decimal("1.3")]
        buy_prices_desc = [Decimal("120000000"), Decimal("110000000"), Decimal("100000000")]
        # current_price 가 정확히 110M 과 일치하면 그 슬롯은 lower 에서 제외됨 (strict <)
        target_total, lower_indices, lower_ratio = resolve_total_budget_from_lower(
            raw_weights=raw_weights,
            buy_prices_desc=buy_prices_desc,
            current_price=Decimal("110000000"),
            lower_budget_krw=Decimal("130000"),
        )
        self.assertEqual(lower_indices, [2])
        self.assertEqual(lower_ratio, Decimal("1.3") / Decimal("3.0"))
        self.assertEqual(target_total, Decimal("130000") / (Decimal("1.3") / Decimal("3.0")))

    def test_resolve_total_budget_from_lower_rejects_non_positive_current_price(self):
        raw_weights = [Decimal("0.7"), Decimal("1.3")]
        buy_prices_desc = [Decimal("120000000"), Decimal("100000000")]
        with self.assertRaisesRegex(ValueError, "현재가는 0보다 커야 합니다"):
            resolve_total_budget_from_lower(
                raw_weights=raw_weights,
                buy_prices_desc=buy_prices_desc,
                current_price=Decimal("0"),
                lower_budget_krw=Decimal("100000"),
            )

    def test_build_weighted_slot_budgets_partial_lower_actual_sum_within_quantization(self):
        """현재가가 그리드 중간에 있을 때 양자화 후 하단 매수합이 목표값에 가깝게 수렴하는지 확인."""
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            lower_budget_krw=Decimal("230000"),
            grid_count=3,
        )
        rows = build_grid_rows_from_property_spec(spec, current_price=Decimal("115000000"))
        slot_budgets, lower_indices, lower_ratio, target_total = build_weighted_slot_budgets(
            spec,
            current_price=Decimal("115000000"),
            buy_prices_desc=[row.buy_price for row in rows],
        )

        self.assertEqual(target_total, Decimal("300000"))
        self.assertEqual(lower_indices, [1, 2])
        actual_lower_total = sum((rows[i].buy_price * rows[i].planned_qty for i in lower_indices), Decimal("0"))
        self.assertLessEqual(actual_lower_total, spec.lower_budget_krw)
        max_quant_loss = sum((rows[i].buy_price * Decimal("0.00000001") for i in lower_indices), Decimal("0"))
        self.assertGreater(actual_lower_total, spec.lower_budget_krw - max_quant_loss)

    def test_checked_in_grid_properties_align_with_runtime_k_defaults(self):
        project_root = Path(__file__).resolve().parents[1]
        spec = load_grid_property_spec(project_root / "grid.properties")

        self.assertGreaterEqual(spec.grid_count, 2)
        self.assertEqual(spec.tp_model, "k")
        self.assertEqual(spec.tp_k_base, cfg.GRID_TP_K_BASE)
        self.assertEqual(spec.tp_k_floor, cfg.GRID_TP_K_FLOOR)


if __name__ == "__main__":
    unittest.main()
