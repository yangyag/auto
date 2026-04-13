import unittest
from decimal import Decimal
from unittest.mock import patch

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
