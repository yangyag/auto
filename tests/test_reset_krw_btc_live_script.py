import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.core.models import OrderExecutionType, OrderSide
from app.core.models import OrderStatus
import scripts.reset_krw_btc_live as reset_script


class ResetKrwBtcLiveScriptTest(unittest.TestCase):
    def test_cancel_open_orders_cancels_live_orders_and_repository_entries(self):
        exchange = Mock()
        exchange.get_open_order_ids.side_effect = [
            ["uuid-1", "uuid-2"],
            [],
        ]
        exchange.cancel_order.return_value = True

        repository = Mock()
        repository.get.side_effect = [
            SimpleNamespace(order_id="uuid-1"),
            None,
        ]
        repository.list_open.return_value = [
            SimpleNamespace(order_id="uuid-1"),
            SimpleNamespace(order_id="uuid-stale"),
        ]

        reset_script.cancel_open_orders(exchange, repository)

        self.assertEqual(
            exchange.cancel_order.call_args_list,
            [call("uuid-1"), call("uuid-2")],
        )
        repository.mark_cancelled.assert_has_calls(
            [call("uuid-1"), call("uuid-1"), call("uuid-stale")]
        )

    def test_liquidate_btc_position_places_market_sell_order_and_waits_for_fill(self):
        exchange = Mock()
        exchange.get_holdings.side_effect = [
            Decimal("0.025"),
            Decimal("0"),
        ]
        exchange.get_current_price.return_value = Decimal("100000000")
        exchange.place_order.return_value = "sell-1"
        exchange.get_order_status.side_effect = [
            OrderStatus(
                uuid="sell-1",
                state="wait",
                executed_volume=Decimal("0"),
                remaining_volume=Decimal("0.025"),
            ),
            OrderStatus(
                uuid="sell-1",
                state="done",
                executed_volume=Decimal("0.025"),
                remaining_volume=Decimal("0"),
            ),
        ]

        with patch.object(reset_script.time, "time", return_value=1234.567), \
             patch.object(reset_script.uuid, "uuid4", return_value=Mock(hex="abcdef1234567890")):
            order_id = reset_script.liquidate_btc_position(
                exchange,
                timeout_seconds=5,
                poll_interval=0.01,
            )

        self.assertEqual(order_id, "sell-1")
        submitted_order = exchange.place_order.call_args.args[0]
        self.assertEqual(submitted_order.side, OrderSide.SELL)
        self.assertEqual(
            submitted_order.execution_type,
            OrderExecutionType.MARKET_SELL_BY_VOLUME,
        )
        self.assertEqual(submitted_order.quantity, Decimal("0.025"))
        self.assertEqual(submitted_order.price, Decimal("100000000"))
        self.assertEqual(
            submitted_order.identifier,
            f"{reset_script.cfg.STATE_BOT_KEY}-reset-sell-1234567-abcdef123456",
        )

    def test_liquidate_btc_position_skips_when_notional_is_below_minimum(self):
        exchange = Mock()
        exchange.get_holdings.return_value = Decimal("0.00001")
        exchange.get_current_price.return_value = Decimal("1000000")

        order_id = reset_script.liquidate_btc_position(
            exchange,
            timeout_seconds=5,
            poll_interval=0.01,
        )

        self.assertIsNone(order_id)
        exchange.place_order.assert_not_called()

    def test_main_runs_expected_sequence(self):
        exchange = Mock()
        repository = Mock()

        with patch.object(reset_script, "validate_environment"), \
             patch.object(reset_script, "PostgresRuntimeLock") as mock_lock_cls, \
             patch.object(reset_script, "build_exchange", return_value=exchange), \
             patch.object(reset_script, "build_pending_order_repository", return_value=repository), \
             patch.object(reset_script.os, "chdir") as chdir, \
             patch.object(reset_script, "print_runtime_snapshot") as print_runtime_snapshot, \
             patch.object(reset_script, "run_project_command") as run_project_command, \
             patch.object(reset_script, "cancel_open_orders") as cancel_open_orders, \
             patch.object(reset_script, "liquidate_btc_position") as liquidate_btc_position:
            mock_lock_cls.return_value.acquire.return_value = True
            exit_code = reset_script.main([])

        self.assertEqual(exit_code, 0)
        chdir.assert_called_once_with(reset_script.PROJECT_ROOT)
        print_runtime_snapshot.assert_called_once_with(exchange)
        cancel_open_orders.assert_called_once_with(
            exchange,
            repository,
            timeout_seconds=30,
            poll_interval=1.0,
        )
        liquidate_btc_position.assert_called_once()
        self.assertEqual(run_project_command.call_args_list[0].args[0], [str(reset_script.PROJECT_ROOT / "stop.sh")])
        self.assertEqual(
            run_project_command.call_args_list[1].args[0],
            [reset_script.sys.executable, "scripts/apply_grid_properties_to_postgres.py", "--force"],
        )
        self.assertEqual(
            run_project_command.call_args_list[2].args[0],
            [reset_script.sys.executable, "scripts/show_grid_state.py"],
        )
        self.assertEqual(len(run_project_command.call_args_list), 3)
