import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import main
from core.grid import GridState
from core.models import GridRow, Order, OrderExecutionType, OrderSide, OrderStatus
from storage.file_grid_repository import FileGridRepository, FilePendingOrderRepository
from strategy.grid_strategy import GridStrategy


class PendingOrderSyncTest(unittest.TestCase):

    def _build_strategy_with_empty_slot(self):
        tmpdir = tempfile.TemporaryDirectory()
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("0"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("1"),
            )
        ]
        grid = GridState.from_rows("KRW-BTC", rows)
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        return tmpdir, grid, strategy

    def test_submit_orders_keeps_grid_unchanged_until_order_is_filled(self):
        tmpdir, grid, _strategy = self._build_strategy_with_empty_slot()
        self.addCleanup(tmpdir.cleanup)
        exchange = Mock()
        exchange.place_order.return_value = "uuid-1"
        pending_orders = {}
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )

        submitted = main.submit_orders([order], exchange, pending_orders)

        self.assertEqual(submitted, 1)
        self.assertEqual(order.order_id, "uuid-1")
        self.assertIn("uuid-1", pending_orders)
        self.assertEqual(grid.rows[0].held_qty, Decimal("0"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))

    def test_submit_orders_persists_open_order_in_repository(self):
        exchange = Mock()
        exchange.place_order.return_value = "uuid-1"
        pending_orders = {}
        repository = FilePendingOrderRepository()
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )

        submitted = main.submit_orders(
            [order],
            exchange,
            pending_orders,
            pending_order_repository=repository,
        )

        self.assertEqual(submitted, 1)
        self.assertEqual(len(repository.list_open()), 1)
        self.assertEqual(repository.list_open()[0].order_id, "uuid-1")

    def test_submit_orders_stops_when_repository_add_fails(self):
        exchange = Mock()
        exchange.place_order.return_value = "uuid-1"
        exchange.cancel_order.return_value = True
        pending_orders = {}
        repository = Mock()
        repository.add.side_effect = RuntimeError("db down")
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )

        with self.assertRaises(main.StatePersistenceError):
            main.submit_orders(
                [order],
                exchange,
                pending_orders,
                pending_order_repository=repository,
            )

        exchange.cancel_order.assert_called_once_with("uuid-1")
        self.assertEqual(pending_orders, {})

    def test_reconcile_pending_orders_applies_grid_after_done_fill(self):
        tmpdir, grid, strategy = self._build_strategy_with_empty_slot()
        self.addCleanup(tmpdir.cleanup)
        repository = FileGridRepository(str(Path(tmpdir.name) / "grid.txt"))
        pending_repository = FilePendingOrderRepository()
        runtime = main.GridStateRuntime(metadata=repository.save(grid.to_snapshot()).metadata)
        exchange = Mock()
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("100"),
            order_id="uuid-1",
        )
        pending_orders = {"uuid-1": order}
        pending_repository.add(order)
        exchange.get_order_status.return_value = OrderStatus(
            uuid="uuid-1",
            state="done",
            executed_volume=Decimal("0.95"),
            remaining_volume=Decimal("0"),
        )

        completed = main.reconcile_pending_orders(
            exchange,
            pending_orders,
            strategy,
            on_grid_updated=lambda: main.persist_grid_state(grid, repository, runtime),
            pending_order_repository=pending_repository,
        )

        self.assertEqual(completed, 1)
        self.assertEqual(pending_orders, {})
        self.assertEqual(grid.rows[0].held_qty, Decimal("0.95"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))
        self.assertEqual(repository.load().rows[0].held_qty, Decimal("0.95"))
        self.assertEqual(pending_repository.list_open(), [])

    def test_reconcile_pending_orders_keeps_wait_order_pending(self):
        tmpdir, grid, strategy = self._build_strategy_with_empty_slot()
        self.addCleanup(tmpdir.cleanup)
        exchange = Mock()
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            order_id="uuid-1",
        )
        pending_orders = {"uuid-1": order}
        exchange.get_order_status.return_value = OrderStatus(
            uuid="uuid-1",
            state="wait",
            executed_volume=Decimal("0"),
            remaining_volume=Decimal("1"),
        )

        completed = main.reconcile_pending_orders(exchange, pending_orders, strategy)

        self.assertEqual(completed, 0)
        self.assertIn("uuid-1", pending_orders)
        self.assertEqual(grid.rows[0].held_qty, Decimal("0"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))

    def test_reconcile_sell_resets_to_uniform_empty_slot_quantity(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        grid_path = Path(tmpdir.name) / "grid.txt"
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("100"),
                held_qty=Decimal("2"),
                sell_price=Decimal("110"),
                planned_qty=Decimal("0"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("90"),
                held_qty=Decimal("0"),
                sell_price=Decimal("100"),
                planned_qty=Decimal("1"),
            ),
        ]
        grid = GridState.from_rows("KRW-BTC", rows)
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        exchange = Mock()
        order = Order(
            slot_index=1,
            side=OrderSide.SELL,
            price=Decimal("110"),
            quantity=Decimal("2"),
            symbol="KRW-BTC",
            order_id="uuid-1",
        )
        pending_orders = {"uuid-1": order}
        exchange.get_order_status.return_value = OrderStatus(
            uuid="uuid-1",
            state="done",
            executed_volume=Decimal("2"),
            remaining_volume=Decimal("0"),
        )

        completed = main.reconcile_pending_orders(exchange, pending_orders, strategy)

        self.assertEqual(completed, 1)
        self.assertEqual(grid.rows[0].held_qty, Decimal("0"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))

    def test_process_cycle_orders_reuses_krw_after_immediate_sell_fill(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        grid_path = Path(tmpdir.name) / "grid.txt"
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("10000"),
                held_qty=Decimal("1"),
                sell_price=Decimal("11000"),
                planned_qty=Decimal("0"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("11000"),
                held_qty=Decimal("0"),
                sell_price=Decimal("12000"),
                planned_qty=Decimal("1"),
            ),
        ]
        grid = GridState.from_rows("KRW-BTC", rows)
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        exchange = Mock()
        exchange.place_order.side_effect = ["sell-id", "buy-id"]
        exchange.get_order_status.side_effect = lambda order_id: OrderStatus(
            uuid=order_id,
            state="done" if order_id == "sell-id" else "wait",
            executed_volume=Decimal("1") if order_id == "sell-id" else Decimal("0"),
            remaining_volume=Decimal("0") if order_id == "sell-id" else Decimal("1"),
        )
        exchange.get_balance.return_value = Decimal("11000")
        pending_orders = {}
        sell_order = Order(
            slot_index=1,
            side=OrderSide.SELL,
            price=Decimal("11000"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )
        buy_order = Order(
            slot_index=2,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("11000"),
        )

        with patch.object(main.cfg, "MAX_DAILY_ORDERS", 10), \
             patch.object(main.cfg, "MIN_BALANCE_RESERVE", Decimal("0")):
            submitted = main.process_cycle_orders(
                sell_orders=[sell_order],
                buy_orders=[buy_order],
                exchange=exchange,
                strategy=strategy,
                pending_orders=pending_orders,
                daily_order_count=0,
            )

        self.assertEqual(submitted, 2)
        self.assertNotIn("sell-id", pending_orders)
        self.assertIn("buy-id", pending_orders)
        self.assertEqual(grid.rows[0].held_qty, Decimal("0"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))

    def test_process_cycle_orders_keeps_buy_blocked_until_sell_is_filled(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        grid_path = Path(tmpdir.name) / "grid.txt"
        rows = [
            GridRow(
                index=1,
                buy_price=Decimal("10000"),
                held_qty=Decimal("1"),
                sell_price=Decimal("11000"),
                planned_qty=Decimal("0"),
            ),
            GridRow(
                index=2,
                buy_price=Decimal("11000"),
                held_qty=Decimal("0"),
                sell_price=Decimal("12000"),
                planned_qty=Decimal("1"),
            ),
        ]
        grid = GridState.from_rows("KRW-BTC", rows)
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        exchange = Mock()
        exchange.place_order.return_value = "sell-id"
        exchange.get_order_status.return_value = OrderStatus(
            uuid="sell-id",
            state="wait",
            executed_volume=Decimal("0"),
            remaining_volume=Decimal("1"),
        )
        exchange.get_balance.return_value = Decimal("0")
        pending_orders = {}
        sell_order = Order(
            slot_index=1,
            side=OrderSide.SELL,
            price=Decimal("11000"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )
        buy_order = Order(
            slot_index=2,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("11000"),
        )

        with patch.object(main.cfg, "MAX_DAILY_ORDERS", 10), \
             patch.object(main.cfg, "MIN_BALANCE_RESERVE", Decimal("0")):
            submitted = main.process_cycle_orders(
                sell_orders=[sell_order],
                buy_orders=[buy_order],
                exchange=exchange,
                strategy=strategy,
                pending_orders=pending_orders,
                daily_order_count=0,
            )

        self.assertEqual(submitted, 1)
        self.assertIn("sell-id", pending_orders)
        self.assertEqual(exchange.place_order.call_count, 1)


if __name__ == "__main__":
    unittest.main()
