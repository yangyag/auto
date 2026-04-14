import unittest
from decimal import Decimal

from core.models import Order, OrderExecutionType, OrderSide
from storage.postgres_order_repository import PostgresOrderRepository
from tests.postgres_test_utils import (
    PostgresIntegrationTestCase,
    apply_test_schema,
    drop_test_schema,
    postgres_test_config,
)


class PostgresOrderRepositoryTest(PostgresIntegrationTestCase):
    def setUp(self):
        self.config = postgres_test_config()
        apply_test_schema(self.config.PGSCHEMA)
        self.repository = PostgresOrderRepository.from_config(self.config)

    def tearDown(self):
        drop_test_schema(self.config.PGSCHEMA)

    def test_add_and_list_open_round_trips_order(self):
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("0.001"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("10000"),
            order_id="order-1",
        )
        self.repository.add(order)

        loaded = self.repository.list_open()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].order_id, "order-1")
        self.assertEqual(loaded[0].spend_amount, Decimal("10000"))

    def test_mark_filled_removes_order_from_open_list(self):
        order = Order(
            slot_index=2,
            side=OrderSide.SELL,
            price=Decimal("12000"),
            quantity=Decimal("0.002"),
            symbol="KRW-BTC",
            order_id="order-2",
        )
        self.repository.add(order)
        self.repository.mark_filled("order-2")

        self.assertEqual(self.repository.list_open(), [])
        self.assertIsNotNone(self.repository.get("order-2"))


if __name__ == "__main__":
    unittest.main()
