import unittest
from decimal import Decimal

from core.models import GridRow
from strategy.recenter_preview import evaluate_recenter_preview


class RecenterPreviewTest(unittest.TestCase):

    def _make_row(
        self,
        *,
        index: int,
        buy_price: str,
        held_qty: str,
        sell_price: str,
        planned_qty: str,
    ) -> GridRow:
        return GridRow(
            index=index,
            buy_price=Decimal(buy_price),
            held_qty=Decimal(held_qty),
            sell_price=Decimal(sell_price),
            planned_qty=Decimal(planned_qty),
        )

    def test_evaluate_recenter_preview_blocks_when_guard_conditions_fail(self):
        preview = evaluate_recenter_preview(
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="0.5",
                    sell_price="110",
                    planned_qty="1",
                ),
                self._make_row(
                    index=2,
                    buy_price="90",
                    held_qty="0",
                    sell_price="99",
                    planned_qty="1",
                ),
            ],
            current_price=Decimal("115"),
            close_prices=[Decimal("115")] * 48 + [Decimal("95")] * 48,
            open_buy_order_count=1,
            breakout_candle_count=96,
            candle_unit_minutes=15,
        )

        self.assertEqual(preview.status, "blocked")
        self.assertEqual(preview.reason, "breakout_duration_below_24h")
        self.assertIn("breakout_duration_below_24h", preview.blockers)
        self.assertIn("inventory_ratio_above_threshold", preview.blockers)
        self.assertIn("open_buy_orders_present", preview.blockers)
        self.assertFalse(preview.can_apply)
        self.assertEqual(preview.breakout_side, "upper")
        self.assertEqual(preview.breakout_candle_count, 48)

    def test_evaluate_recenter_preview_becomes_eligible_after_24h_breakout(self):
        preview = evaluate_recenter_preview(
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="0.1",
                    sell_price="110",
                    planned_qty="1",
                ),
                self._make_row(
                    index=2,
                    buy_price="90",
                    held_qty="0",
                    sell_price="99",
                    planned_qty="1",
                ),
            ],
            current_price=Decimal("115"),
            close_prices=[Decimal("115")] * 96,
            open_buy_order_count=0,
            breakout_candle_count=96,
            candle_unit_minutes=15,
        )

        self.assertEqual(preview.status, "eligible")
        self.assertEqual(preview.reason, "ok")
        self.assertEqual(preview.blockers, ())
        self.assertTrue(preview.can_apply)
        self.assertEqual(preview.breakout_side, "upper")
        self.assertEqual(preview.breakout_duration_hours, Decimal("24"))
        self.assertEqual(preview.inventory_ratio, Decimal("0.1"))
        self.assertEqual(preview.current_lower, Decimal("90"))
        self.assertEqual(preview.current_upper, Decimal("100"))
        self.assertEqual(preview.holding_slots_preserved, 1)
        self.assertEqual(preview.empty_slots_rebuilt, 1)
        self.assertAlmostEqual(
            float(preview.proposed_lower * preview.proposed_upper),
            float(preview.current_price * preview.current_price),
            places=9,
        )

    def test_evaluate_recenter_preview_blocks_on_invalid_band(self):
        preview = evaluate_recenter_preview(
            [
                self._make_row(
                    index=1,
                    buy_price="100",
                    held_qty="0",
                    sell_price="110",
                    planned_qty="1",
                )
            ],
            current_price=Decimal("115"),
            close_prices=[Decimal("115")] * 96,
            open_buy_order_count=0,
        )

        self.assertEqual(preview.status, "blocked")
        self.assertEqual(preview.reason, "invalid_band")
        self.assertIn("invalid_band", preview.blockers)
        self.assertIsNone(preview.current_lower)
        self.assertIsNone(preview.current_upper)
        self.assertIsNone(preview.proposed_lower)
        self.assertIsNone(preview.proposed_upper)


if __name__ == "__main__":
    unittest.main()
