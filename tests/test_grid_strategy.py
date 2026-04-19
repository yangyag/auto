import unittest
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import Mock, patch

import config.settings as settings
from core.grid import GridState
from core.models import GridRow, OrderExecutionType
from strategy.grid_strategy import GridStrategy


class GridStrategyCrossingTest(unittest.TestCase):

    def _build_strategy(self, rows):
        return GridStrategy(GridState.from_rows("KRW-BTC", rows), Mock(), "KRW-BTC")

    def _override_settings(self, **overrides):
        stack = ExitStack()
        for name, value in overrides.items():
            stack.enter_context(patch.object(settings, name, value, create=True))
        return stack

    def _phase01_settings(self, *, up_buy_enabled=False, epsilon=Decimal("0.03")):
        return self._override_settings(
            UP_BUY_ENABLED=up_buy_enabled,
            UPWARD_BUY_ENABLED=up_buy_enabled,
            ENABLE_UPWARD_BUY=up_buy_enabled,
            MAX_OPERATING_BUDGET_KRW=Decimal("400"),
            INVENTORY_TARGET_EPSILON=epsilon,
            Q_TARGET_EPSILON=epsilon,
        )

    def _phase04_settings(
        self,
        *,
        below_current_slots,
        above_current_reentry_slots=0,
    ):
        return self._override_settings(
            ACTIVE_WINDOW_ENABLED=True,
            ACTIVE_WINDOW_BELOW_CURRENT_SLOTS=below_current_slots,
            ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS=above_current_reentry_slots,
        )

    def _set_inventory_gate(
        self,
        strategy,
        *,
        current_ratio,
        target_ratio,
        band_position=Decimal("0.50"),
    ):
        strategy.grid.current_inventory_ratio = Mock(return_value=current_ratio)
        strategy.grid.target_inventory_ratio = Mock(return_value=target_ratio)
        strategy.grid.band_position_z = Mock(return_value=band_position)

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
        strategy = self._build_strategy(rows)

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
        strategy = self._build_strategy(rows)

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
        strategy = self._build_strategy(rows)

        strategy.evaluate(Decimal("110"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("90"))

        self.assertEqual([order.slot_index for order in buy_orders], [1, 2, 3])
        self.assertTrue(all(order.execution_type == OrderExecutionType.LIMIT for order in buy_orders))
        self.assertEqual(sell_orders, [])

    def test_active_window_limits_downward_buys_to_nearest_empty_slots(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("115"),
                held_qty=Decimal("0"),
                sell_price=Decimal("125"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("105"),
                held_qty=Decimal("0"),
                sell_price=Decimal("115"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=4,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.00"),
            target_ratio=Decimal("0.85"),
        )

        with self._phase04_settings(below_current_slots=2):
            strategy.evaluate(Decimal("120"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("95"))

        self.assertEqual([order.slot_index for order in buy_orders], [1, 2])
        self.assertTrue(all(order.execution_type == OrderExecutionType.LIMIT for order in buy_orders))
        self.assertEqual(sell_orders, [])

    def test_active_window_ignores_slots_outside_window_on_same_downward_move(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("118"),
                held_qty=Decimal("0"),
                sell_price=Decimal("128"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("116"),
                held_qty=Decimal("0"),
                sell_price=Decimal("126"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("114"),
                held_qty=Decimal("0"),
                sell_price=Decimal("124"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.00"),
            target_ratio=Decimal("0.85"),
        )

        with self._phase04_settings(below_current_slots=1):
            strategy.evaluate(Decimal("120"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("110"))

        self.assertEqual([order.slot_index for order in buy_orders], [1])
        self.assertNotIn(2, [order.slot_index for order in buy_orders])
        self.assertNotIn(3, [order.slot_index for order in buy_orders])
        self.assertEqual(sell_orders, [])

    def test_does_not_buy_when_single_price_line_crosses_up_through_buy_line_by_default(self):
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
        strategy = self._build_strategy(rows)

        strategy.evaluate(Decimal("95"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("100"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(sell_orders, [])

    def test_buys_when_single_price_line_crosses_up_through_buy_line_if_explicitly_enabled(self):
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
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.00"),
            target_ratio=Decimal("0.53"),
        )

        with self._phase01_settings(up_buy_enabled=True):
            strategy.evaluate(Decimal("95"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("100"))

        self.assertEqual(len(buy_orders), 1)
        self.assertEqual(buy_orders[0].slot_index, 2)
        self.assertEqual(buy_orders[0].price, Decimal("100"))
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual(buy_orders[0].spend_amount, Decimal("100"))
        self.assertEqual(sell_orders, [])

    def test_inventory_target_gate_blocks_downward_buy_at_threshold(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("400"),
                held_qty=Decimal("0"),
                sell_price=Decimal("420"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("150"),
                held_qty=Decimal("0"),
                sell_price=Decimal("165"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.50"),
            target_ratio=Decimal("0.53"),
            band_position=Decimal("0.60"),
        )

        with self._phase01_settings():
            strategy.evaluate(Decimal("170"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("150"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(sell_orders, [])
        strategy.grid.current_inventory_ratio.assert_called()
        strategy.grid.target_inventory_ratio.assert_called()
        strategy.grid.band_position_z.assert_called()

    def test_inventory_target_gate_allows_downward_buy_below_threshold(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("400"),
                held_qty=Decimal("0"),
                sell_price=Decimal("420"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("150"),
                held_qty=Decimal("0"),
                sell_price=Decimal("165"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.49"),
            target_ratio=Decimal("0.53"),
            band_position=Decimal("0.20"),
        )

        with self._phase01_settings():
            strategy.evaluate(Decimal("170"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("150"))

        self.assertEqual([order.slot_index for order in buy_orders], [2])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.LIMIT)
        self.assertEqual(sell_orders, [])
        strategy.grid.current_inventory_ratio.assert_called()
        strategy.grid.target_inventory_ratio.assert_called()
        strategy.grid.band_position_z.assert_called()

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
        strategy = self._build_strategy(rows)

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
        strategy = self._build_strategy(rows)
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
        strategy = self._build_strategy(rows)

        buy_orders, sell_orders = strategy.evaluate(Decimal("115"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(len(sell_orders), 1)
        self.assertEqual(sell_orders[0].slot_index, 1)

    def test_active_window_does_not_change_sell_behavior_for_holding_slots(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("115"),
                held_qty=Decimal("0"),
                sell_price=Decimal("125"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("100"),
                held_qty=Decimal("1"),
                sell_price=Decimal("105"),
                planned_qty=Decimal("0"),
            ),
            GridRow(
                index=4,
                buy_price=Decimal("90"),
                held_qty=Decimal("1"),
                sell_price=Decimal("95"),
                planned_qty=Decimal("0"),
            ),
        ]
        strategy = self._build_strategy(rows)

        with self._phase04_settings(below_current_slots=1):
            buy_orders, sell_orders = strategy.evaluate(Decimal("106"))

        self.assertEqual(buy_orders, [])
        self.assertEqual([order.slot_index for order in sell_orders], [3, 4])

    def test_upward_move_with_buy_disabled_by_default_still_sells_all_eligible_holding_slots(self):
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
        strategy = self._build_strategy(rows)

        strategy.evaluate(Decimal("94"))
        buy_orders, sell_orders = strategy.evaluate(Decimal("115"))

        self.assertEqual(buy_orders, [])
        self.assertEqual([order.slot_index for order in sell_orders], [2, 3])

    def test_upward_move_can_trigger_upper_buy_and_lower_sell_together_if_explicitly_enabled(self):
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
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.00"),
            target_ratio=Decimal("0.53"),
        )

        with self._phase01_settings(up_buy_enabled=True):
            strategy.evaluate(Decimal("105"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("110"))

        self.assertEqual([order.slot_index for order in buy_orders], [1])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual([order.slot_index for order in sell_orders], [2])

    def test_large_upward_move_skips_buy_when_multiple_empty_slots_are_crossed_if_explicitly_enabled(self):
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
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.00"),
            target_ratio=Decimal("0.53"),
        )

        with self._phase01_settings(up_buy_enabled=True):
            strategy.evaluate(Decimal("95"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("115"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(sell_orders, [])

    def test_large_upward_move_ignores_pending_slots_when_counting_actionable_buys_if_explicitly_enabled(self):
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
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.00"),
            target_ratio=Decimal("0.53"),
        )

        with self._phase01_settings(up_buy_enabled=True):
            strategy.evaluate(Decimal("95"))
            buy_orders, sell_orders = strategy.evaluate_with_pending(
                Decimal("115"),
                pending_slot_indexes={2},
            )

        self.assertEqual([order.slot_index for order in buy_orders], [1])
        self.assertEqual(buy_orders[0].execution_type, OrderExecutionType.MARKET_BUY_BY_PRICE)
        self.assertEqual(sell_orders, [])

    def test_active_window_still_excludes_pending_slots_from_downward_buys(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("115"),
                held_qty=Decimal("0"),
                sell_price=Decimal("125"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("110"),
                held_qty=Decimal("0"),
                sell_price=Decimal("120"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("105"),
                held_qty=Decimal("0"),
                sell_price=Decimal("115"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.00"),
            target_ratio=Decimal("0.85"),
        )

        with self._phase04_settings(below_current_slots=2):
            strategy.evaluate(Decimal("120"))
            buy_orders, sell_orders = strategy.evaluate_with_pending(
                Decimal("100"),
                pending_slot_indexes={1},
            )

        self.assertEqual([order.slot_index for order in buy_orders], [2])
        self.assertEqual(sell_orders, [])

    def test_inventory_target_gate_blocks_upward_buy_even_if_explicitly_enabled(self):
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("400"),
                held_qty=Decimal("0"),
                sell_price=Decimal("420"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("250"),
                held_qty=Decimal("0"),
                sell_price=Decimal("270"),
                planned_qty=Decimal("1"),
            ),
            GridRow(
                index=3,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            ),
        ]
        strategy = self._build_strategy(rows)
        self._set_inventory_gate(
            strategy,
            current_ratio=Decimal("0.50"),
            target_ratio=Decimal("0.53"),
            band_position=Decimal("0.60"),
        )

        with self._phase01_settings(up_buy_enabled=True):
            strategy.evaluate(Decimal("240"))
            buy_orders, sell_orders = strategy.evaluate(Decimal("250"))

        self.assertEqual(buy_orders, [])
        self.assertEqual(sell_orders, [])
        strategy.grid.current_inventory_ratio.assert_called()
        strategy.grid.target_inventory_ratio.assert_called()
        strategy.grid.band_position_z.assert_called()
