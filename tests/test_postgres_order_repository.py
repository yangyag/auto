import unittest
from decimal import Decimal

from storage.postgres_common import psycopg
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
            identifier="bot-order-1",
        )
        self.repository.add(order)

        loaded = self.repository.list_open()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].order_id, "order-1")
        self.assertEqual(loaded[0].spend_amount, Decimal("10000"))
        self.assertEqual(loaded[0].identifier, "bot-order-1")
        self.assertEqual(self.repository.get("order-1").identifier, "bot-order-1")

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

    def test_add_rejects_duplicate_identifier_across_bot_keys(self):
        other_config = postgres_test_config(schema=self.config.PGSCHEMA)
        other_repository = PostgresOrderRepository.from_config(other_config)
        shared_identifier = "shared-upbit-identifier"

        self.repository.add(
            Order(
                slot_index=1,
                side=OrderSide.BUY,
                price=Decimal("10000"),
                quantity=Decimal("0.001"),
                symbol="KRW-BTC",
                order_id="order-a",
                identifier=shared_identifier,
            )
        )

        self.assertEqual(self.repository.get("order-a").identifier, shared_identifier)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            other_repository.add(
                Order(
                    slot_index=1,
                    side=OrderSide.BUY,
                    price=Decimal("10050"),
                    quantity=Decimal("0.001"),
                    symbol="KRW-BTC",
                    order_id="order-b",
                    identifier=shared_identifier,
                )
            )


if __name__ == "__main__":
    unittest.main()
