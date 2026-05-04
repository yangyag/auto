import unittest
from decimal import Decimal
from unittest.mock import Mock, call

import app.main as main
from app.core.models import Order, OrderSide


class InMemoryPendingOrderRepository:
    def __init__(self, orders=None):
        self._orders: dict[str, Order] = {o.order_id: o for o in (orders or [])}

    def add(self, order: Order) -> None:
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


def _make_order(order_id: str, side=OrderSide.BUY) -> Order:
    return Order(
        slot_index=1,
        side=side,
        price=Decimal("100"),
        quantity=Decimal("1"),
        symbol="KRW-BTC",
        order_id=order_id,
    )


class CancelUnknownExchangeOrdersTest(unittest.TestCase):

    def test_noop_when_exchange_and_db_match(self):
        exchange = Mock()
        exchange.get_open_order_ids.return_value = ["uuid-1", "uuid-2"]
        repo = InMemoryPendingOrderRepository([_make_order("uuid-1"), _make_order("uuid-2")])

        main.cancel_unknown_exchange_orders(exchange, repo, "KRW-BTC")

        exchange.cancel_order.assert_not_called()

    def test_cancels_uuid_missing_from_db_and_logs_warning(self):
        exchange = Mock()
        exchange.get_open_order_ids.return_value = ["uuid-known", "uuid-unknown"]
        exchange.cancel_order.return_value = True
        repo = InMemoryPendingOrderRepository([_make_order("uuid-known")])

        with self.assertLogs("app.main", level="WARNING") as cm:
            main.cancel_unknown_exchange_orders(exchange, repo, "KRW-BTC")

        exchange.cancel_order.assert_called_once_with("uuid-unknown")
        self.assertTrue(any("uuid-unknown" in line for line in cm.output))

    def test_raises_runtime_error_when_cancel_fails(self):
        exchange = Mock()
        exchange.get_open_order_ids.return_value = ["uuid-ghost"]
        exchange.cancel_order.return_value = False
        repo = InMemoryPendingOrderRepository([])

        with self.assertRaises(RuntimeError):
            main.cancel_unknown_exchange_orders(exchange, repo, "KRW-BTC")

    def test_db_only_uuid_is_not_cancelled(self):
        exchange = Mock()
        exchange.get_open_order_ids.return_value = []
        repo = InMemoryPendingOrderRepository([_make_order("uuid-db-only")])

        main.cancel_unknown_exchange_orders(exchange, repo, "KRW-BTC")

        exchange.cancel_order.assert_not_called()

    def test_does_not_mutate_db_after_cancel(self):
        exchange = Mock()
        exchange.get_open_order_ids.return_value = ["uuid-ghost"]
        exchange.cancel_order.return_value = True
        repo = InMemoryPendingOrderRepository([])

        main.cancel_unknown_exchange_orders(exchange, repo, "KRW-BTC")

        self.assertEqual(repo.list_open(), [])

    def test_uses_provided_symbol(self):
        exchange = Mock()
        exchange.get_open_order_ids.return_value = []
        repo = InMemoryPendingOrderRepository([])

        main.cancel_unknown_exchange_orders(exchange, repo, "KRW-ETH")

        exchange.get_open_order_ids.assert_called_once_with("KRW-ETH")


if __name__ == "__main__":
    unittest.main()
