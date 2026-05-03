import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.core.grid import GridState
from app.core.models import GridRow
from app.strategy.recenter_preview import evaluate_recenter_preview


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


class GridStatePhase6MetadataTest(unittest.TestCase):
    def _make_row(
        self,
        *,
        index: int,
        buy_price: str,
        held_qty: str,
        sell_price: str,
        planned_qty: str,
        filled_at: datetime | None = None,
    ) -> GridRow:
        try:
            return GridRow(
                index=index,
                buy_price=Decimal(buy_price),
                held_qty=Decimal(held_qty),
                sell_price=Decimal(sell_price),
                planned_qty=Decimal(planned_qty),
                filled_at=filled_at,
            )
        except TypeError as exc:
            self.fail(f"Phase 6 GridRow should accept filled_at metadata: {exc}")

    def _preview_field(self, preview, field_name: str):
        if isinstance(preview, dict):
            value = preview[field_name]
        else:
            value = getattr(preview, field_name)
        if field_name == "blockers" and isinstance(value, tuple):
            return list(value)
        return value

    def test_apply_buy_records_filled_at_for_age_tracking(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="0",
                    sell_price="110",
                    planned_qty="1",
                    filled_at=None,
                )
            ],
        )
        filled_at = datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc)

        try:
            state.apply_buy(1, filled_qty=Decimal("0.95"), filled_at=filled_at)
        except TypeError as exc:
            self.fail(f"GridState.apply_buy should accept filled_at for Phase 6: {exc}")

        self.assertEqual(state.rows[0].held_qty, Decimal("0.95"))
        self.assertEqual(state.rows[0].filled_at, filled_at)

    def test_apply_sell_clears_filled_at_when_slot_returns_to_empty(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="1",
                    sell_price="110",
                    planned_qty="1",
                    filled_at=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
                )
            ],
        )

        state.apply_sell(1)

        self.assertEqual(state.rows[0].held_qty, Decimal("0"))
        self.assertIsNone(state.rows[0].filled_at)

    def test_apply_sell_with_partial_fill_keeps_remaining_qty_and_filled_at(self):
        filled_at = datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc)
        state = GridState.from_rows(
            "KRW-BTC",
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="1",
                    sell_price="110",
                    planned_qty="1",
                    filled_at=filled_at,
                )
            ],
        )

        state.apply_sell(1, filled_qty=Decimal("0.4"))

        self.assertEqual(state.rows[0].held_qty, Decimal("0.6"))
        self.assertEqual(state.rows[0].filled_at, filled_at)

    def test_effective_tp_k_steps_down_by_age_and_respects_floor(self):
        filled_at = datetime(2026, 4, 12, 0, 0, tzinfo=timezone.utc)
        state = GridState.from_rows(
            "KRW-BTC",
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="1",
                    sell_price="110",
                    planned_qty="1",
                    filled_at=filled_at,
                )
            ],
        )

        try:
            before_48h = state.effective_tp_k(
                1,
                now=filled_at + timedelta(hours=47, minutes=59),
                tp_k_base=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            )
            after_48h = state.effective_tp_k(
                1,
                now=filled_at + timedelta(hours=49),
                tp_k_base=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            )
            after_7d = state.effective_tp_k(
                1,
                now=filled_at + timedelta(days=8),
                tp_k_base=Decimal("11.0"),
                tp_k_floor=Decimal("8.0"),
            )
            floored = state.effective_tp_k(
                1,
                now=filled_at + timedelta(days=8),
                tp_k_base=Decimal("8.4"),
                tp_k_floor=Decimal("8.0"),
            )
        except AttributeError as exc:
            self.fail(f"GridState.effective_tp_k is required for Phase 6 age-based TP compression: {exc}")

        self.assertEqual(before_48h, Decimal("11.0"))
        self.assertEqual(after_48h, Decimal("10.5"))
        self.assertEqual(after_7d, Decimal("10.0"))
        self.assertEqual(floored, Decimal("8.0"))

    def test_build_recenter_preview_reports_blockers_without_mutating_grid(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="0.5",
                    sell_price="110",
                    planned_qty="1",
                    filled_at=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
                ),
                self._make_row(
                    index=2,
                    buy_price="90",
                    held_qty="0",
                    sell_price="100",
                    planned_qty="1",
                    filled_at=None,
                ),
            ],
        )
        original_buy_prices = [row.buy_price for row in state.rows]

        try:
            with patch("app.core.grid.cfg.MAX_OPERATING_BUDGET_KRW", Decimal("2")):
                preview = state.build_recenter_preview(
                    current_price=Decimal("115"),
                    breakout_duration=timedelta(hours=12),
                    open_buy_order_count=1,
                )
        except AttributeError as exc:
            self.fail(f"GridState.build_recenter_preview is required for Phase 6: {exc}")

        self.assertFalse(self._preview_field(preview, "can_apply"))
        self.assertIn("breakout_duration_below_24h", self._preview_field(preview, "blockers"))
        self.assertIn("inventory_ratio_above_threshold", self._preview_field(preview, "blockers"))
        self.assertIn("open_buy_orders_present", self._preview_field(preview, "blockers"))
        self.assertEqual([row.buy_price for row in state.rows], original_buy_prices)

    def test_build_recenter_preview_becomes_applicable_after_guard_conditions_pass(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="0.1",
                    sell_price="110",
                    planned_qty="1",
                    filled_at=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
                ),
                self._make_row(
                    index=2,
                    buy_price="90",
                    held_qty="0",
                    sell_price="100",
                    planned_qty="1",
                    filled_at=None,
                ),
            ],
        )

        try:
            preview = state.build_recenter_preview(
                current_price=Decimal("115"),
                breakout_duration=timedelta(hours=25),
                open_buy_order_count=0,
            )
        except AttributeError as exc:
            self.fail(f"GridState.build_recenter_preview is required for Phase 6: {exc}")

        self.assertTrue(self._preview_field(preview, "can_apply"))
        self.assertEqual(self._preview_field(preview, "blockers"), [])
        self.assertEqual(self._preview_field(preview, "current_price"), Decimal("115"))

    def test_build_recenter_preview_matches_preview_helper_for_same_breakout_case(self):
        state = GridState.from_rows(
            "KRW-BTC",
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="0.1",
                    sell_price="110",
                    planned_qty="1",
                    filled_at=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
                ),
                self._make_row(
                    index=2,
                    buy_price="90",
                    held_qty="0",
                    sell_price="100",
                    planned_qty="1",
                    filled_at=None,
                ),
            ],
        )

        preview_from_state = state.build_recenter_preview(
            current_price=Decimal("115"),
            breakout_duration=timedelta(hours=24),
            open_buy_order_count=0,
        )
        preview_from_helper = evaluate_recenter_preview(
            state.rows,
            current_price=Decimal("115"),
            close_prices=[Decimal("115")] * 96,
            open_buy_order_count=0,
            breakout_candle_count=96,
            candle_unit_minutes=15,
        )

        self.assertEqual(self._preview_field(preview_from_state, "status"), preview_from_helper.status)
        self.assertEqual(self._preview_field(preview_from_state, "can_apply"), preview_from_helper.can_apply)
        self.assertEqual(tuple(self._preview_field(preview_from_state, "blockers")), preview_from_helper.blockers)
        self.assertEqual(self._preview_field(preview_from_state, "current_lower"), preview_from_helper.current_lower)
        self.assertEqual(self._preview_field(preview_from_state, "current_upper"), preview_from_helper.current_upper)


if __name__ == "__main__":
    unittest.main()
