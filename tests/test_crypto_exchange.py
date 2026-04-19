import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import requests

from core.models import Order, OrderExecutionType, OrderSide
from exchange.crypto import CryptoExchange, UpbitAPIError


class CryptoExchangeBalanceTest(unittest.TestCase):

    def setUp(self):
        self.exchange = CryptoExchange("access", "secret")

    @staticmethod
    def _success_response(payload: dict | list, *, headers: dict | None = None):
        response = Mock()
        response.headers = headers or {}
        response.status_code = 200
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @staticmethod
    def _http_error_response(
        status_code: int,
        *,
        error_name: str = "too_many_requests",
        error_message: str = "rate limited",
        headers: dict | None = None,
    ):
        response = Mock()
        response.headers = headers or {}
        response.status_code = status_code
        response.json.return_value = {
            "error": {
                "name": error_name,
                "message": error_message,
            }
        }
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        return response

    @staticmethod
    def _valid_buy_chance(balance: str = "1000000") -> dict:
        return {
            "market": {
                "bid_types": ["limit", "price"],
                "bid": {"min_total": "1"},
            },
            "bid_account": {"balance": balance},
        }

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

    def test_get_recent_minute_closes_calls_minute_candle_api_and_parses_trade_price(self):
        now_utc = datetime.now(timezone.utc)
        current_slot_start = now_utc.replace(
            minute=now_utc.minute - (now_utc.minute % 15),
            second=0,
            microsecond=0,
        )
        payload = [
            {
                "trade_price": "111500000",
                "candle_date_time_utc": current_slot_start.replace(tzinfo=None).isoformat(timespec="seconds"),
            },
            {
                "trade_price": "111000000",
                "candle_date_time_utc": (current_slot_start - timedelta(minutes=15)).replace(tzinfo=None).isoformat(timespec="seconds"),
            },
            {
                "trade_price": "110500000",
                "candle_date_time_utc": (current_slot_start - timedelta(minutes=30)).replace(tzinfo=None).isoformat(timespec="seconds"),
            },
            {
                "trade_price": "110000000",
                "candle_date_time_utc": (current_slot_start - timedelta(minutes=45)).replace(tzinfo=None).isoformat(timespec="seconds"),
            },
            {
                "trade_price": "109500000",
                "candle_date_time_utc": (current_slot_start - timedelta(minutes=60)).replace(tzinfo=None).isoformat(timespec="seconds"),
            },
        ]

        with patch.object(self.exchange, "_get", return_value=payload) as get:
            closes = self.exchange.get_recent_minute_closes("KRW-BTC", 15, 4)

        self.assertEqual(
            closes,
            [
                Decimal("111000000"),
                Decimal("110500000"),
                Decimal("110000000"),
                Decimal("109500000"),
            ],
        )
        get.assert_called_once_with(
            "/v1/candles/minutes/15",
            params={"market": "KRW-BTC", "count": 5},
        )

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
        calls: list[tuple[str, dict]] = []

        def fake_post(path, body):
            calls.append((path, body))
            if path == "/v1/orders/test":
                return {"result": "ok"}
            if path == "/v1/orders":
                return {"uuid": "uuid-1"}
            self.fail(f"unexpected path: {path}")

        with patch.object(self.exchange, "get_order_chance", return_value=self._valid_buy_chance()), \
             patch.object(self.exchange, "_post", side_effect=fake_post):
            order_id = self.exchange.place_order(order)

        self.assertEqual(order_id, "uuid-1")
        real_order_calls = [body for path, body in calls if path == "/v1/orders"]
        self.assertEqual(len(real_order_calls), 1)
        self.assertEqual(real_order_calls[0]["market"], "KRW-BTC")
        self.assertEqual(real_order_calls[0]["side"], "bid")
        self.assertEqual(real_order_calls[0]["volume"], "0.001")
        self.assertEqual(real_order_calls[0]["price"], "11000")
        self.assertEqual(real_order_calls[0]["ord_type"], "limit")

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
        calls: list[tuple[str, dict]] = []

        def fake_post(path, body):
            calls.append((path, body))
            if path == "/v1/orders/test":
                return {"result": "ok"}
            if path == "/v1/orders":
                return {"uuid": "uuid-1"}
            self.fail(f"unexpected path: {path}")

        with patch.object(self.exchange, "get_order_chance", return_value=self._valid_buy_chance()), \
             patch.object(self.exchange, "_post", side_effect=fake_post):
            order_id = self.exchange.place_order(order)

        self.assertEqual(order_id, "uuid-1")
        real_order_calls = [body for path, body in calls if path == "/v1/orders"]
        self.assertEqual(len(real_order_calls), 1)
        self.assertEqual(real_order_calls[0]["market"], "KRW-BTC")
        self.assertEqual(real_order_calls[0]["side"], "bid")
        self.assertEqual(real_order_calls[0]["price"], "10000")
        self.assertEqual(real_order_calls[0]["ord_type"], "price")

    def test_place_order_does_not_submit_real_order_when_order_test_fails(self):
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("0.001"),
            symbol="KRW-BTC",
            identifier="phase7-test-order",
        )
        calls: list[tuple[str, dict]] = []

        def fake_post(path, body):
            calls.append((path, body))
            if path == "/v1/orders/test":
                raise UpbitAPIError("order test failed", status_code=400, error_name="under_min_total_bid")
            if path == "/v1/orders":
                return {"uuid": "uuid-should-not-happen"}
            self.fail(f"unexpected path: {path}")

        with patch.object(self.exchange, "get_order_chance", return_value=self._valid_buy_chance()), \
             patch.object(self.exchange, "_post", side_effect=fake_post):
            order_id = self.exchange.place_order(order)

        self.assertIsNone(order_id)
        self.assertEqual([path for path, _body in calls], ["/v1/orders/test"])

    def test_place_order_includes_identifier_in_real_order_request(self):
        order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("0.001"),
            symbol="KRW-BTC",
            identifier="phase7-order-identifier",
        )
        calls: list[tuple[str, dict]] = []

        def fake_post(path, body):
            calls.append((path, body))
            if path == "/v1/orders/test":
                return {"result": "ok"}
            if path == "/v1/orders":
                return {"uuid": "uuid-1"}
            self.fail(f"unexpected path: {path}")

        with patch.object(self.exchange, "get_order_chance", return_value=self._valid_buy_chance()), \
             patch.object(self.exchange, "_post", side_effect=fake_post):
            order_id = self.exchange.place_order(order)

        self.assertEqual(order_id, "uuid-1")
        test_order_calls = [body for path, body in calls if path == "/v1/orders/test"]
        real_order_calls = [body for path, body in calls if path == "/v1/orders"]
        self.assertEqual(len(test_order_calls), 1)
        self.assertEqual(len(real_order_calls), 1)
        self.assertNotIn("identifier", test_order_calls[0])
        self.assertEqual(real_order_calls[0]["identifier"], "phase7-order-identifier")

    def test_request_retries_once_for_upbit_rate_limit_responses(self):
        responses = [
            self._http_error_response(429),
            self._success_response({"ok": True}),
        ]

        with patch("exchange.crypto.requests.request", side_effect=responses) as request:
            result = self.exchange._request("GET", "/v1/test")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.call_count, 2)

    def test_request_retries_short_418_block_once(self):
        responses = [
            self._http_error_response(418, error_message="blocked for 1 seconds"),
            self._success_response({"ok": True}),
        ]

        with patch("exchange.crypto.requests.request", side_effect=responses) as request:
            result = self.exchange._request("GET", "/v1/test")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.call_count, 2)

    def test_request_regenerates_auth_header_for_rate_limit_retry(self):
        responses = [
            self._http_error_response(429),
            self._success_response({"ok": True}),
        ]

        with patch.object(
            self.exchange,
            "_auth_header",
            side_effect=[
                {"Authorization": "Bearer retry-1"},
                {"Authorization": "Bearer retry-2"},
            ],
        ) as auth_header, patch("exchange.crypto.requests.request", side_effect=responses) as request:
            result = self.exchange._request(
                "GET",
                "/v1/orders/chance",
                params={"market": "KRW-BTC"},
                auth=True,
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(auth_header.call_count, 2)
        self.assertEqual(request.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer retry-1")
        self.assertEqual(request.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer retry-2")

    def test_request_does_not_retry_long_418_block(self):
        response = self._http_error_response(418, error_message="blocked for 10 seconds")

        with patch("exchange.crypto.requests.request", side_effect=[response]) as request:
            with self.assertRaises(UpbitAPIError):
                self.exchange._request("GET", "/v1/test")

        self.assertEqual(request.call_count, 1)

    def test_request_does_not_retry_418_when_retry_after_is_missing(self):
        response = self._http_error_response(418, error_message="temporarily blocked")

        with patch("exchange.crypto.requests.request", side_effect=[response]) as request:
            with self.assertRaises(UpbitAPIError):
                self.exchange._request("GET", "/v1/test")

        self.assertEqual(request.call_count, 1)
