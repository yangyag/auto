import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import main
from core.grid import GridState
from core.models import GridRow, Order, OrderExecutionType, OrderSide, OrderStatus
from storage.interfaces import GridSnapshot, RepositoryMetadata
from strategy.grid_strategy import GridStrategy


class InMemoryGridRepository:
    def __init__(self, snapshot: GridSnapshot):
        self.snapshot = snapshot

    def load(self) -> GridSnapshot:
        return self.snapshot

    def save(self, snapshot: GridSnapshot) -> GridSnapshot:
        version = 1 if snapshot.metadata.version is None else snapshot.metadata.version + 1
        self.snapshot = GridSnapshot(
            symbol=snapshot.symbol,
            rows=snapshot.rows,
            metadata=RepositoryMetadata(version=version, revision=f"rev-{version}"),
        )
        return self.snapshot

    def has_changed(self, metadata: RepositoryMetadata | None) -> bool:
        return metadata is None or metadata.version != self.snapshot.metadata.version


class InMemoryPendingOrderRepository:
    def __init__(self):
        self._orders: dict[str, Order] = {}

    def add(self, order: Order) -> None:
        if not order.order_id:
            raise ValueError("order_id 없는 주문은 저장할 수 없습니다.")
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def remove(self, order_id: str) -> None:
        self._orders.pop(order_id, None)

    def mark_filled(self, order_id: str) -> None:
        self.remove(order_id)

    def mark_cancelled(self, order_id: str) -> None:
        self.remove(order_id)

    def list_open(self) -> list[Order]:
        return list(self._orders.values())


class PendingOrderSyncTest(unittest.TestCase):

    def _make_phase6_row(
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

    def _build_phase6_strategy_with_empty_slot(self):
        tmpdir = tempfile.TemporaryDirectory()
        rows = [
            self._make_phase6_row(
                index=1,
                buy_price="100",
                held_qty="0",
                sell_price="110",
                planned_qty="1",
                filled_at=None,
            )
        ]
        grid = GridState.from_rows("KRW-BTC", rows)
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        return tmpdir, grid, strategy

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
        repository = InMemoryPendingOrderRepository()
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

    def test_submit_orders_generates_identifier_before_exchange_submission(self):
        exchange = Mock()
        exchange.place_order.return_value = "uuid-1"
        pending_orders = {}
        repository = InMemoryPendingOrderRepository()
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )

        with patch.object(main.cfg, "STATE_BOT_KEY", "phase7-bot"):
            submitted = main.submit_orders(
                [order],
                exchange,
                pending_orders,
                pending_order_repository=repository,
            )

        self.assertEqual(submitted, 1)
        self.assertIsNotNone(order.identifier)
        self.assertTrue(order.identifier.startswith("phase7-bot-buy-1-"))
        self.assertEqual(pending_orders["uuid-1"].identifier, order.identifier)
        self.assertEqual(repository.get("uuid-1").identifier, order.identifier)
        exchange.place_order.assert_called_once_with(order)

    def test_submit_orders_leaves_pending_state_untouched_when_exchange_rejects_order(self):
        exchange = Mock()
        exchange.place_order.return_value = None
        pending_orders = {}
        repository = Mock()
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

        self.assertEqual(submitted, 0)
        self.assertEqual(pending_orders, {})
        repository.add.assert_not_called()

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
        repository = InMemoryGridRepository(grid.to_snapshot())
        pending_repository = InMemoryPendingOrderRepository()
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

    def test_reconcile_pending_orders_treats_cancel_with_executed_volume_as_filled(self):
        tmpdir, grid, strategy = self._build_strategy_with_empty_slot()
        self.addCleanup(tmpdir.cleanup)
        repository = InMemoryGridRepository(grid.to_snapshot())
        pending_repository = InMemoryPendingOrderRepository()
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
            state="cancel",
            executed_volume=Decimal("0.90674"),
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
        self.assertEqual(grid.rows[0].held_qty, Decimal("0.90674"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))
        self.assertEqual(repository.load().rows[0].held_qty, Decimal("0.90674"))
        self.assertEqual(pending_repository.list_open(), [])

    def test_reconcile_pending_orders_sets_filled_at_on_buy_fill_and_persists_it(self):
        tmpdir, grid, strategy = self._build_phase6_strategy_with_empty_slot()
        self.addCleanup(tmpdir.cleanup)
        repository = InMemoryGridRepository(grid.to_snapshot())
        pending_repository = InMemoryPendingOrderRepository()
        runtime = main.GridStateRuntime(metadata=repository.save(grid.to_snapshot()).metadata)
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
        self.assertIsNotNone(getattr(grid.rows[0], "filled_at", None))
        self.assertIsNotNone(grid.rows[0].filled_at.tzinfo)
        self.assertEqual(repository.load().rows[0].filled_at, grid.rows[0].filled_at)

    def test_reconcile_pending_orders_sell_fill_clears_existing_filled_at(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        rows = [
            self._make_phase6_row(
                index=1,
                buy_price="100",
                held_qty="1",
                sell_price="110",
                planned_qty="1",
                filled_at=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
            ),
            self._make_phase6_row(
                index=2,
                buy_price="90",
                held_qty="0",
                sell_price="100",
                planned_qty="1",
                filled_at=None,
            ),
        ]
        grid = GridState.from_rows("KRW-BTC", rows)
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        repository = InMemoryGridRepository(grid.to_snapshot())
        pending_repository = InMemoryPendingOrderRepository()
        runtime = main.GridStateRuntime(metadata=repository.save(grid.to_snapshot()).metadata)
        exchange = Mock()
        order = Order(
            slot_index=1,
            side=OrderSide.SELL,
            price=Decimal("110"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            order_id="uuid-1",
        )
        pending_orders = {"uuid-1": order}
        pending_repository.add(order)
        exchange.get_order_status.return_value = OrderStatus(
            uuid="uuid-1",
            state="done",
            executed_volume=Decimal("1"),
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
        self.assertEqual(grid.rows[0].held_qty, Decimal("0"))
        self.assertIsNone(grid.rows[0].filled_at)
        self.assertIsNone(repository.load().rows[0].filled_at)

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

    def test_reconcile_pending_orders_applies_multiple_downward_buy_fills_to_holding_slots(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
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
        ]
        grid = GridState.from_rows("KRW-BTC", rows)
        strategy = GridStrategy(grid, Mock(), "KRW-BTC")
        exchange = Mock()
        order_1 = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("105"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            order_id="uuid-1",
        )
        order_2 = Order(
            slot_index=2,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            order_id="uuid-2",
        )
        pending_orders = {
            "uuid-1": order_1,
            "uuid-2": order_2,
        }

        def get_order_status(order_id):
            volumes = {
                "uuid-1": Decimal("1"),
                "uuid-2": Decimal("1"),
            }
            return OrderStatus(
                uuid=order_id,
                state="done",
                executed_volume=volumes[order_id],
                remaining_volume=Decimal("0"),
            )

        exchange.get_order_status.side_effect = get_order_status

        completed = main.reconcile_pending_orders(exchange, pending_orders, strategy)

        self.assertEqual(completed, 2)
        self.assertEqual(pending_orders, {})
        self.assertEqual(grid.rows[0].held_qty, Decimal("1"))
        self.assertEqual(grid.rows[1].held_qty, Decimal("1"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))
        self.assertEqual(grid.rows[1].planned_qty, Decimal("1"))

    def test_reconcile_sell_resets_to_uniform_empty_slot_quantity(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
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

    def test_process_cycle_orders_does_not_reuse_same_cycle_sell_proceeds_for_buy(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
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
        sell_reconciled = False
        exchange.place_order.return_value = "sell-id"

        def get_order_status(order_id):
            nonlocal sell_reconciled
            if order_id == "sell-id":
                sell_reconciled = True
            return OrderStatus(
                uuid=order_id,
                state="done",
                executed_volume=Decimal("1"),
                remaining_volume=Decimal("0"),
            )

        exchange.get_order_status.side_effect = get_order_status
        exchange.get_balance.side_effect = lambda: Decimal("11000") if sell_reconciled else Decimal("0")
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
        self.assertNotIn("sell-id", pending_orders)
        self.assertEqual(exchange.place_order.call_count, 1)
        self.assertEqual(grid.rows[0].held_qty, Decimal("0"))
        self.assertEqual(grid.rows[0].planned_qty, Decimal("1"))

    def test_process_cycle_orders_submits_buy_without_waiting_for_sell_fill_when_balance_allows(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
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
        sell_checked = False
        exchange.place_order.side_effect = ["sell-id", "buy-id"]

        def get_order_status(order_id):
            nonlocal sell_checked
            if order_id == "sell-id":
                sell_checked = True
            return OrderStatus(
                uuid=order_id,
                state="wait",
                executed_volume=Decimal("0"),
                remaining_volume=Decimal("1"),
            )

        exchange.get_order_status.side_effect = get_order_status
        exchange.get_balance.side_effect = lambda: Decimal("0") if sell_checked else Decimal("11000")
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
        self.assertIn("sell-id", pending_orders)
        self.assertIn("buy-id", pending_orders)
        self.assertEqual(exchange.place_order.call_count, 2)


if __name__ == "__main__":
    unittest.main()
