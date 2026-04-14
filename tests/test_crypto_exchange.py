import unittest
from decimal import Decimal
from unittest.mock import patch

from core.models import Order, OrderExecutionType, OrderSide
from exchange.crypto import CryptoExchange


class CryptoExchangeBalanceTest(unittest.TestCase):

    def setUp(self):
        self.exchange = CryptoExchange("access", "secret")

    def test_get_balance_returns_krw_balance(self):
        accounts = [
            {"currency": "BTC", "balance": "0.01234567"},
            {"currency": "KRW", "balance": "1234567.89"},
        ]

        with patch.object(self.exchange, "_get", return_value=accounts):
            self.assertEqual(self.exchange.get_balance(), Decimal("1234567.89"))

    def test_get_balance_returns_zero_when_krw_missing(self):
        accounts = [{"currency": "BTC", "balance": "0.01234567"}]

        with patch.object(self.exchange, "_get", return_value=accounts):
            self.assertEqual(self.exchange.get_balance(), Decimal("0"))

    def test_get_order_status_parses_upbit_response(self):
        payload = {
            "uuid": "uuid-1",
            "state": "done",
            "executed_volume": "0.001",
            "remaining_volume": "0",
        }

        with patch.object(self.exchange, "_get", return_value=payload):
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.uuid, "uuid-1")
        self.assertEqual(status.state, "done")
        self.assertEqual(status.executed_volume, Decimal("0.001"))
        self.assertEqual(status.remaining_volume, Decimal("0"))

    def test_get_order_status_treats_cancel_with_full_execution_as_filled(self):
        payload = {
            "uuid": "uuid-1",
            "state": "cancel",
            "executed_volume": "0.00090674",
            "remaining_volume": "0",
        }

        with patch.object(self.exchange, "_get", return_value=payload):
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "cancel")
        self.assertEqual(status.executed_volume, Decimal("0.00090674"))
        self.assertEqual(status.remaining_volume, Decimal("0"))
        self.assertTrue(status.is_filled)
        self.assertFalse(status.is_cancelled)

    def test_get_order_status_keeps_partial_cancel_as_cancelled(self):
        payload = {
            "uuid": "uuid-1",
            "state": "cancel",
            "executed_volume": "0.0004",
            "remaining_volume": "0.0005",
        }

        with patch.object(self.exchange, "_get", return_value=payload):
            status = self.exchange.get_order_status("uuid-1")

        self.assertFalse(status.is_filled)
        self.assertTrue(status.is_cancelled)

    def test_place_order_uses_limit_body_for_limit_orders(self):
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("0.001"),
            symbol="KRW-BTC",
        )

        with patch.object(self.exchange, "_post", return_value={"uuid": "uuid-1"}) as post:
            order_id = self.exchange.place_order(order)

        self.assertEqual(order_id, "uuid-1")
        post.assert_called_once_with("/v1/orders", {
            "market": "KRW-BTC",
            "side": "bid",
            "volume": "0.001",
            "price": "11000",
            "ord_type": "limit",
        })

    def test_place_order_uses_price_body_for_market_buy_by_price(self):
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("0.001"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("10000"),
        )

        with patch.object(self.exchange, "_post", return_value={"uuid": "uuid-1"}) as post:
            order_id = self.exchange.place_order(order)

        self.assertEqual(order_id, "uuid-1")
        post.assert_called_once_with("/v1/orders", {
            "market": "KRW-BTC",
            "side": "bid",
            "price": "10000",
            "ord_type": "price",
        })
