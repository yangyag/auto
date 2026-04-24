import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import requests

from core.models import Order, OrderExecutionType, OrderSide
from exchange.crypto import CryptoExchange, UpbitAPIError
import exchange.upbit_ws as upbit_ws
from exchange.upbit_ws import (
    UPBIT_PRIVATE_WS_URL,
    UpbitAssetWebSocketCache,
    UpbitMinuteCandleWebSocketCache,
    UpbitOrderWebSocketCache,
    UpbitOrderWebSocketStatus,
    UpbitTickerPriceEvent,
    UpbitTickerWebSocketCache,
)


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

    @staticmethod
    def _valid_sell_chance(balance: str = "1") -> dict:
        return {
            "market": {
                "ask_types": ["limit", "market"],
                "ask": {"min_total": "5000"},
            },
            "ask_account": {"balance": balance},
        }

    @staticmethod
    def _subscribe_cache_symbols(cache: UpbitTickerWebSocketCache, *symbols: str) -> None:
        cache._codes.update(symbol.strip().upper() for symbol in symbols)

    @staticmethod
    def _subscribe_candle_cache(
        cache: UpbitMinuteCandleWebSocketCache,
        *subscriptions: tuple[str, int],
    ) -> None:
        normalized = {(symbol.strip().upper(), int(unit)) for symbol, unit in subscriptions}
        cache._subscriptions.update(normalized)
        cache._active_subscriptions.update(normalized)

    def test_get_current_price_uses_fresh_websocket_cache(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_price.return_value = Decimal("110000000")
        self.exchange._ticker_cache = cache

        with patch.object(self.exchange, "_get") as get:
            price = self.exchange.get_current_price("KRW-BTC")

        self.assertEqual(price, Decimal("110000000"))
        cache.ensure_started.assert_called_once_with("KRW-BTC")
        cache.get_price.assert_called_once_with("KRW-BTC")
        get.assert_not_called()

    def test_get_current_price_falls_back_to_rest_when_websocket_price_is_stale(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_price.return_value = None
        self.exchange._ticker_cache = cache

        with patch.object(self.exchange, "_get", return_value=[{"trade_price": "111000000"}]) as get:
            price = self.exchange.get_current_price("KRW-BTC")

        self.assertEqual(price, Decimal("111000000"))
        get.assert_called_once_with("/v1/ticker", params={"markets": "KRW-BTC"})

    def test_get_current_price_falls_back_to_rest_when_websocket_disabled(self):
        self.exchange._ticker_cache = None

        with patch.object(self.exchange, "_get", return_value=[{"trade_price": "112000000"}]) as get:
            price = self.exchange.get_current_price("KRW-BTC")

        self.assertEqual(price, Decimal("112000000"))
        get.assert_called_once_with("/v1/ticker", params={"markets": "KRW-BTC"})

    def test_get_current_price_falls_back_to_rest_when_websocket_start_fails(self):
        cache = Mock()
        cache.ensure_started.return_value = False
        self.exchange._ticker_cache = cache

        with patch.object(self.exchange, "_get", return_value=[{"trade_price": "113000000"}]) as get:
            price = self.exchange.get_current_price("KRW-BTC")

        self.assertEqual(price, Decimal("113000000"))
        cache.ensure_started.assert_called_once_with("KRW-BTC")
        cache.get_price.assert_not_called()
        get.assert_called_once_with("/v1/ticker", params={"markets": "KRW-BTC"})

    def test_get_current_price_propagates_rest_error_after_stale_websocket_cache(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_price.return_value = None
        self.exchange._ticker_cache = cache

        with patch.object(self.exchange, "_get", side_effect=UpbitAPIError("rest failed")):
            with self.assertRaisesRegex(UpbitAPIError, "rest failed"):
                self.exchange.get_current_price("KRW-BTC")

    def test_upbit_ticker_websocket_cache_subscribes_with_uppercase_codes(self):
        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            time_provider=lambda: 1000.0,
        )
        ws = Mock()

        with patch.object(upbit_ws, "websocket", None):
            self.assertFalse(cache.ensure_started("krw-btc"))

        cache._on_open(ws, sorted(cache._codes))
        subscribe_message = json.loads(ws.send.call_args.args[0])
        self.assertEqual(
            subscribe_message,
            [
                {"ticket": "auto-public-ticker"},
                {"type": "ticker", "codes": ["KRW-BTC"]},
                {"format": "SIMPLE"},
            ],
        )

    def test_upbit_ticker_websocket_cache_parses_default_format_payload(self):
        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_cache_symbols(cache, "KRW-BTC")

        cache._on_message(
            None,
            '{"type":"ticker","code":"KRW-BTC","trade_price":110000000}',
        )

        self.assertEqual(cache.get_price("KRW-BTC"), Decimal("110000000"))

    def test_upbit_ticker_websocket_cache_ignores_non_ticker_payload_type(self):
        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_cache_symbols(cache, "KRW-BTC")

        cache._on_message(
            None,
            '{"type":"orderbook","code":"KRW-BTC","trade_price":110000000}',
        )

        self.assertIsNone(cache.get_price("KRW-BTC"))

    def test_upbit_ticker_websocket_cache_ignores_unsubscribed_symbol_payload(self):
        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_cache_symbols(cache, "KRW-BTC")

        cache._on_message(None, b'{"ty":"ticker","cd":"KRW-ETH","tp":110000000}')

        self.assertIsNone(cache.get_price("KRW-BTC"))
        self.assertIsNone(cache.get_price("KRW-ETH"))

    def test_upbit_ticker_websocket_cache_returns_none_for_stale_tick(self):
        current_time = 1000.0

        def time_provider():
            return current_time

        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=time_provider,
        )
        self._subscribe_cache_symbols(cache, "KRW-BTC")
        cache._on_message(None, b'{"cd":"KRW-BTC","tp":110000000}')
        self.assertEqual(cache.get_price("KRW-BTC"), Decimal("110000000"))

        current_time = 1006.0
        self.assertIsNone(cache.get_price("KRW-BTC"))

    def test_upbit_ticker_websocket_cache_waits_for_newer_price_event(self):
        current_time = 1000.0

        def time_provider():
            return current_time

        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=time_provider,
        )
        self._subscribe_cache_symbols(cache, "KRW-BTC")

        cache._on_message(None, b'{"cd":"KRW-BTC","tp":110000000}')
        event = cache.wait_for_price_event("KRW-BTC", timeout=0, since=None)

        self.assertEqual(
            event,
            UpbitTickerPriceEvent(
                symbol="KRW-BTC",
                price=Decimal("110000000"),
                updated_at=1000.0,
            ),
        )
        self.assertIsNone(cache.wait_for_price_event("KRW-BTC", timeout=0, since=1000.0))

        current_time = 1001.0
        cache._on_message(None, b'{"cd":"KRW-BTC","tp":111000000}')

        event = cache.wait_for_price_event("KRW-BTC", timeout=0, since=1000.0)
        self.assertEqual(event.price, Decimal("111000000"))
        self.assertEqual(event.updated_at, 1001.0)

    def test_upbit_ticker_websocket_cache_returns_none_after_connection_error(self):
        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_cache_symbols(cache, "KRW-BTC")
        cache._on_message(None, b'{"cd":"KRW-BTC","tp":110000000}')
        cache._on_error(None, "connection failed")

        self.assertIsNone(cache.get_price("KRW-BTC"))

    def test_upbit_ticker_websocket_cache_ignores_non_positive_price(self):
        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_cache_symbols(cache, "KRW-BTC", "KRW-ETH")

        cache._on_message(None, b'{"cd":"KRW-BTC","tp":0}')
        cache._on_message(None, b'{"cd":"KRW-ETH","tp":-1}')

        self.assertIsNone(cache.get_price("KRW-BTC"))
        self.assertIsNone(cache.get_price("KRW-ETH"))

    def test_upbit_ticker_websocket_cache_start_fails_when_dependency_missing(self):
        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            time_provider=lambda: 1000.0,
        )

        with patch.object(upbit_ws, "websocket", None):
            self.assertFalse(cache.ensure_started("KRW-BTC"))

    def test_get_minute_candle_closes_uses_completed_websocket_candles_before_cutoff(self):
        cache = UpbitMinuteCandleWebSocketCache(
            max_age_seconds=30,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_candle_cache(cache, ("krw-btc", 15))
        cutoff = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)

        for candle_start, price in [
            ("2026-01-01T12:30:00", "300"),
            ("2026-01-01T12:15:00", "200"),
            ("2026-01-01T12:00:00", "100"),
        ]:
            cache._on_message(
                None,
                json.dumps(
                    {
                        "type": "candle.15m",
                        "code": "KRW-BTC",
                        "candle_date_time_utc": candle_start,
                        "trade_price": price,
                    }
                ),
            )

        closes = cache.get_closes(
            "KRW-BTC",
            unit_minutes=15,
            count=2,
            to=cutoff,
        )

        self.assertEqual(closes, [Decimal("200"), Decimal("100")])

    def test_get_minute_candle_closes_falls_back_to_rest_when_cache_is_insufficient(self):
        cache = UpbitMinuteCandleWebSocketCache(
            max_age_seconds=30,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_candle_cache(cache, ("KRW-BTC", 15))
        cache._started = True
        cutoff = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
        cache._on_message(
            None,
            json.dumps(
                {
                    "type": "candle.15m",
                    "code": "KRW-BTC",
                    "candle_date_time_utc": "2026-01-01T12:15:00",
                    "trade_price": "200",
                }
            ),
        )
        self.exchange._candle_cache = cache

        with patch.object(
            self.exchange,
            "_get",
            return_value=[{"trade_price": "200"}, {"trade_price": "100"}],
        ) as get:
            closes = self.exchange.get_minute_candle_closes(
                "KRW-BTC",
                unit_minutes=15,
                count=2,
                to=cutoff,
            )

        self.assertEqual(closes, [Decimal("200"), Decimal("100")])
        get.assert_called_once_with(
            "/v1/candles/minutes/15",
            params={"market": "KRW-BTC", "count": 2, "to": cutoff.isoformat(timespec="seconds")},
        )

    def test_get_minute_candle_closes_falls_back_to_rest_when_candle_stream_is_stale(self):
        current_time = 1000.0

        def time_provider():
            return current_time

        cache = UpbitMinuteCandleWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=Mock(),
            time_provider=time_provider,
        )
        self._subscribe_candle_cache(cache, ("KRW-BTC", 15))
        cache._started = True
        cutoff = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
        cache._on_message(
            None,
            json.dumps(
                {
                    "type": "candle.15m",
                    "code": "KRW-BTC",
                    "candle_date_time_utc": "2026-01-01T12:15:00",
                    "trade_price": "200",
                }
            ),
        )
        current_time = 1006.0
        self.exchange._candle_cache = cache

        with patch.object(self.exchange, "_get", return_value=[{"trade_price": "200"}]) as get:
            closes = self.exchange.get_minute_candle_closes(
                "KRW-BTC",
                unit_minutes=15,
                count=1,
                to=cutoff,
            )

        self.assertEqual(closes, [Decimal("200")])
        get.assert_called_once()

    def test_upbit_candle_websocket_cache_ignores_wrong_symbol_type_unit_and_bad_payloads(self):
        cache = UpbitMinuteCandleWebSocketCache(
            max_age_seconds=30,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_candle_cache(cache, ("KRW-BTC", 15))
        cutoff = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)

        cache._on_message(
            None,
            b'{"type":"candle.15m","code":"KRW-ETH","candle_date_time_utc":"2026-01-01T12:15:00","trade_price":200}',
        )
        cache._on_message(
            None,
            b'{"type":"ticker","code":"KRW-BTC","candle_date_time_utc":"2026-01-01T12:15:00","trade_price":200}',
        )
        cache._on_message(
            None,
            b'{"type":"candle.1m","code":"KRW-BTC","candle_date_time_utc":"2026-01-01T12:15:00","trade_price":200}',
        )
        cache._on_message(None, b'{"type":"candle.15m"')
        cache._on_message(
            None,
            b'{"type":"candle.15m","code":"KRW-BTC","candle_date_time_utc":"2026-01-01T12:15:00","trade_price":0}',
        )

        self.assertIsNone(
            cache.get_closes(
                "KRW-BTC",
                unit_minutes=15,
                count=1,
                to=cutoff,
            )
        )

    def test_get_minute_candle_closes_falls_back_to_rest_when_candle_connection_failed(self):
        cache = UpbitMinuteCandleWebSocketCache(
            max_age_seconds=30,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self._subscribe_candle_cache(cache, ("KRW-BTC", 15))
        cache._started = True
        cutoff = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
        cache._on_message(
            None,
            b'{"type":"candle.15m","code":"KRW-BTC","candle_date_time_utc":"2026-01-01T12:15:00","trade_price":200}',
        )
        cache._on_error(None, "connection failed")
        self.exchange._candle_cache = cache

        with patch.object(self.exchange, "_get", return_value=[{"trade_price": "200"}]) as get:
            closes = self.exchange.get_minute_candle_closes(
                "KRW-BTC",
                unit_minutes=15,
                count=1,
                to=cutoff,
            )

        self.assertEqual(closes, [Decimal("200")])
        get.assert_called_once()

    def test_get_minute_candle_closes_propagates_rest_error_after_cache_miss(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_closes.return_value = None
        self.exchange._candle_cache = cache

        with patch.object(self.exchange, "_get", side_effect=UpbitAPIError("rest candle failed")):
            with self.assertRaisesRegex(UpbitAPIError, "rest candle failed"):
                self.exchange.get_minute_candle_closes(
                    "KRW-BTC",
                    unit_minutes=15,
                    count=1,
                    to=datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc),
                )

    def test_get_minute_candle_closes_falls_back_to_rest_for_unsupported_websocket_unit(self):
        cache = UpbitMinuteCandleWebSocketCache(
            max_age_seconds=30,
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self.exchange._candle_cache = cache

        with patch.object(cache, "get_closes", wraps=cache.get_closes) as get_closes, \
             patch.object(self.exchange, "_get", return_value=[{"trade_price": "200"}]) as get:
            closes = self.exchange.get_minute_candle_closes(
                "KRW-BTC",
                unit_minutes=2,
                count=1,
                to=datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc),
            )

        self.assertEqual(closes, [Decimal("200")])
        get_closes.assert_not_called()
        get.assert_called_once()

    def test_close_stops_websocket_cache(self):
        ticker_cache = Mock()
        candle_cache = Mock()
        asset_cache = Mock()
        order_cache = Mock()
        self.exchange._ticker_cache = ticker_cache
        self.exchange._candle_cache = candle_cache
        self.exchange._asset_cache = asset_cache
        self.exchange._order_cache = order_cache

        self.exchange.close()

        ticker_cache.stop.assert_called_once_with()
        candle_cache.stop.assert_called_once_with()
        asset_cache.stop.assert_called_once_with()
        order_cache.stop.assert_called_once_with()

    def test_get_balance_uses_fresh_asset_websocket_cache_for_krw(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_balance.return_value = Decimal("1234567.89")
        self.exchange._asset_cache = cache

        with patch.object(self.exchange, "_get") as get:
            balance = self.exchange.get_balance()

        self.assertEqual(balance, Decimal("1234567.89"))
        cache.ensure_started.assert_called_once_with()
        cache.get_balance.assert_called_once_with("KRW")
        get.assert_not_called()

    def test_get_holdings_uses_fresh_asset_websocket_cache_for_symbol_currency(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_balance.return_value = Decimal("0.01234567")
        self.exchange._asset_cache = cache

        with patch.object(self.exchange, "_get") as get:
            holdings = self.exchange.get_holdings("KRW-BTC")

        self.assertEqual(holdings, Decimal("0.01234567"))
        cache.ensure_started.assert_called_once_with()
        cache.get_balance.assert_called_once_with("BTC")
        get.assert_not_called()

    def test_get_balance_returns_krw_balance(self):
        accounts = [
            {"currency": "BTC", "balance": "0.01234567"},
            {"currency": "KRW", "balance": "1234567.89"},
        ]
        self.exchange._asset_cache = None

        with patch.object(self.exchange, "_get", return_value=accounts) as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("1234567.89"))
        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_returns_zero_when_krw_missing(self):
        accounts = [{"currency": "BTC", "balance": "0.01234567"}]
        self.exchange._asset_cache = None

        with patch.object(self.exchange, "_get", return_value=accounts) as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("0"))
        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_holdings_returns_rest_balance_when_asset_websocket_disabled(self):
        accounts = [
            {"currency": "KRW", "balance": "10000"},
            {"currency": "BTC", "balance": "0.01234567"},
        ]
        self.exchange._asset_cache = None

        with patch.object(self.exchange, "_get", return_value=accounts) as get:
            self.assertEqual(self.exchange.get_holdings("KRW-BTC"), Decimal("0.01234567"))

        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_falls_back_to_rest_when_asset_cache_has_no_event(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True
        self.exchange._asset_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(self.exchange, "_get", return_value=[{"currency": "KRW", "balance": "10"}]) as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("10"))

        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_falls_back_to_rest_when_asset_cache_is_stale(self):
        current_time = 1000.0

        def time_provider():
            return current_time

        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=time_provider,
        )
        cache._started = True
        cache._on_message(
            None,
            b'{"type":"myAsset","assets":[{"currency":"KRW","balance":"20"}]}',
        )
        current_time = 1006.0
        self.exchange._asset_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(self.exchange, "_get", return_value=[{"currency": "KRW", "balance": "30"}]) as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("30"))

        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_falls_back_to_rest_when_asset_connection_failed(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True
        cache._on_message(
            None,
            b'{"type":"myAsset","assets":[{"currency":"KRW","balance":"20"}]}',
        )
        cache._on_error(None, "connection failed")
        self.exchange._asset_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(self.exchange, "_get", return_value=[{"currency": "KRW", "balance": "30"}]) as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("30"))

        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_falls_back_to_rest_when_asset_dependency_missing(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            time_provider=lambda: 1000.0,
        )
        self.exchange._asset_cache = cache

        with patch.object(upbit_ws, "websocket", None), \
             patch.object(self.exchange, "_get", return_value=[{"currency": "KRW", "balance": "40"}]) as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("40"))

        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_falls_back_to_rest_when_asset_auth_header_fails(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(side_effect=UpbitAPIError("credentials missing")),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self.exchange._asset_cache = cache

        with patch.object(self.exchange, "_get", return_value=[{"currency": "KRW", "balance": "50"}]) as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("50"))

        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_accepts_zero_asset_cache_balance(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True
        cache._on_message(
            None,
            b'{"type":"myAsset","assets":[{"currency":"KRW","balance":"0"}]}',
        )
        self.exchange._asset_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(self.exchange, "_get") as get:
            self.assertEqual(self.exchange.get_balance(), Decimal("0"))

        get.assert_not_called()

    def test_get_holdings_falls_back_to_rest_when_asset_currency_missing(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True
        cache._on_message(
            None,
            b'{"type":"myAsset","assets":[{"currency":"KRW","balance":"20"}]}',
        )
        self.exchange._asset_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(self.exchange, "_get", return_value=[{"currency": "BTC", "balance": "0.01"}]) as get:
            self.assertEqual(self.exchange.get_holdings("KRW-BTC"), Decimal("0.01"))

        get.assert_called_once_with("/v1/accounts", auth=True)

    def test_get_balance_propagates_rest_error_after_asset_cache_miss(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_balance.return_value = None
        self.exchange._asset_cache = cache

        with patch.object(self.exchange, "_get", side_effect=UpbitAPIError("rest asset failed")):
            with self.assertRaisesRegex(UpbitAPIError, "rest asset failed"):
                self.exchange.get_balance()

    def test_upbit_asset_websocket_cache_subscribes_without_codes(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        ws = Mock()

        cache._on_open(ws)

        subscribe_message = json.loads(ws.send.call_args.args[0])
        self.assertEqual(
            subscribe_message,
            [
                {"ticket": "auto-private-asset"},
                {"type": "myAsset"},
            ],
        )
        self.assertNotIn("codes", subscribe_message[1])

    def test_upbit_asset_websocket_cache_start_uses_private_url_and_auth_header(self):
        app = Mock()
        app.run_forever.return_value = None
        app_factory = Mock(return_value=app)
        auth_headers = {"Authorization": "Bearer test-token"}
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value=auth_headers),
            websocket_app_factory=app_factory,
            time_provider=lambda: 1000.0,
        )

        self.assertTrue(cache.ensure_started())

        app_factory.assert_called_once()
        self.assertEqual(app_factory.call_args.args[0], UPBIT_PRIVATE_WS_URL)
        self.assertEqual(app_factory.call_args.kwargs["header"], auth_headers)

    def test_upbit_asset_websocket_cache_parses_default_format_payload(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True

        cache._on_message(
            None,
            b'{"type":"myAsset","assets":[{"currency":"KRW","balance":"0"},{"currency":"BTC","balance":"0.01234567"}]}',
        )

        self.assertEqual(cache.get_balance("KRW"), Decimal("0"))
        self.assertEqual(cache.get_balance("BTC"), Decimal("0.01234567"))

    def test_upbit_asset_websocket_cache_parses_list_wrapped_payload(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True

        cache._on_message(
            None,
            b'[{"type":"myAsset","assets":[{"currency":"BTC","balance":"0.02"}]}]',
        )

        self.assertEqual(cache.get_balance("BTC"), Decimal("0.02"))

    def test_upbit_asset_websocket_cache_ignores_wrong_type_and_malformed_assets(self):
        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True

        cache._on_message(
            None,
            b'{"type":"myOrder","assets":[{"currency":"KRW","balance":"100"}]}',
        )
        cache._on_message(None, b'{"type":"myAsset"')
        cache._on_message(None, b'{"type":"myAsset","assets":"not-list"}')
        cache._on_message(
            None,
            b'{"type":"myAsset","assets":[{"balance":"100"},{"currency":"BTC"},{"currency":"ETH","balance":"bad"},{"currency":"XRP","balance":"-1"}]}',
        )

        self.assertIsNone(cache.get_balance("KRW"))
        self.assertIsNone(cache.get_balance("BTC"))
        self.assertIsNone(cache.get_balance("ETH"))
        self.assertIsNone(cache.get_balance("XRP"))

    def test_get_open_order_ids_uses_states_array_and_parses_uuid(self):
        payload = [
            {"uuid": "uuid-1", "state": "wait"},
            {"uuid": "uuid-2", "state": "watch"},
        ]

        with patch.object(self.exchange, "_get", return_value=payload) as get:
            order_ids = self.exchange.get_open_order_ids("KRW-BTC")

        self.assertEqual(order_ids, ["uuid-1", "uuid-2"])
        get.assert_called_once_with(
            "/v1/orders/open",
            params={
                "market": "KRW-BTC",
                "limit": 100,
                "order_by": "desc",
                "states[]": ["wait", "watch"],
            },
            auth=True,
        )

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

    def test_get_order_status_uses_rest_when_order_websocket_disabled(self):
        self.exchange._order_cache = None
        payload = {
            "uuid": "uuid-1",
            "state": "done",
            "executed_volume": "0.001",
            "remaining_volume": "0",
        }

        with patch.object(self.exchange, "_get", return_value=payload) as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "done")
        get.assert_called_once_with("/v1/order", params={"uuid": "uuid-1"}, auth=True)

    def test_get_order_status_uses_terminal_done_websocket_cache(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_order_status.return_value = UpbitOrderWebSocketStatus(
            uuid="uuid-1",
            state="done",
            executed_volume=Decimal("0.001"),
            remaining_volume=Decimal("0"),
        )
        self.exchange._order_cache = cache

        with patch.object(self.exchange, "_get") as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.uuid, "uuid-1")
        self.assertEqual(status.state, "done")
        self.assertEqual(status.executed_volume, Decimal("0.001"))
        self.assertEqual(status.remaining_volume, Decimal("0"))
        cache.ensure_started.assert_called_once_with()
        cache.get_order_status.assert_called_once_with("uuid-1")
        get.assert_not_called()

    def test_get_order_status_uses_terminal_cancel_websocket_cache(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_order_status.return_value = UpbitOrderWebSocketStatus(
            uuid="uuid-1",
            state="cancel",
            executed_volume=Decimal("0.0004"),
            remaining_volume=Decimal("0.0005"),
        )
        self.exchange._order_cache = cache

        with patch.object(self.exchange, "_get") as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "cancel")
        self.assertEqual(status.executed_volume, Decimal("0.0004"))
        self.assertEqual(status.remaining_volume, Decimal("0.0005"))
        get.assert_not_called()

    def test_get_order_status_falls_back_to_rest_for_non_terminal_websocket_states(self):
        rest_payload = {
            "uuid": "uuid-1",
            "state": "done",
            "executed_volume": "0.001",
            "remaining_volume": "0",
        }

        for state in ("wait", "watch", "trade", "prevented"):
            with self.subTest(state=state):
                cache = Mock()
                cache.ensure_started.return_value = True
                cache.get_order_status.return_value = UpbitOrderWebSocketStatus(
                    uuid="uuid-1",
                    state=state,
                    executed_volume=Decimal("0.0005"),
                    remaining_volume=Decimal("0.0005"),
                )
                self.exchange._order_cache = cache

                with patch.object(self.exchange, "_get", return_value=rest_payload) as get:
                    status = self.exchange.get_order_status("uuid-1")

                self.assertEqual(status.state, "done")
                get.assert_called_once_with("/v1/order", params={"uuid": "uuid-1"}, auth=True)

    def test_get_order_status_falls_back_to_rest_when_order_cache_has_no_event(self):
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True
        self.exchange._order_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(
                 self.exchange,
                 "_get",
                 return_value={
                     "uuid": "uuid-1",
                     "state": "done",
                     "executed_volume": "0.001",
                     "remaining_volume": "0",
                 },
             ) as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "done")
        get.assert_called_once_with("/v1/order", params={"uuid": "uuid-1"}, auth=True)

    def test_get_order_status_falls_back_to_rest_when_order_cache_is_stale(self):
        current_time = 1000.0

        def time_provider():
            return current_time

        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=time_provider,
        )
        cache._started = True
        cache._on_message(
            None,
            b'{"type":"myOrder","code":"KRW-BTC","uuid":"uuid-1","state":"done","executed_volume":"0.001","remaining_volume":"0"}',
        )
        current_time = 1006.0
        self.exchange._order_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(
                 self.exchange,
                 "_get",
                 return_value={
                     "uuid": "uuid-1",
                     "state": "done",
                     "executed_volume": "0.001",
                     "remaining_volume": "0",
                 },
             ) as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "done")
        get.assert_called_once_with("/v1/order", params={"uuid": "uuid-1"}, auth=True)

    def test_get_order_status_falls_back_to_rest_when_order_connection_failed(self):
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True
        cache._on_message(
            None,
            b'{"type":"myOrder","code":"KRW-BTC","uuid":"uuid-1","state":"done","executed_volume":"0.001","remaining_volume":"0"}',
        )
        cache._on_error(None, "connection failed")
        self.exchange._order_cache = cache

        with patch.object(cache, "ensure_started", return_value=True), \
             patch.object(
                 self.exchange,
                 "_get",
                 return_value={
                     "uuid": "uuid-1",
                     "state": "done",
                     "executed_volume": "0.001",
                     "remaining_volume": "0",
                 },
             ) as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "done")
        get.assert_called_once_with("/v1/order", params={"uuid": "uuid-1"}, auth=True)

    def test_get_order_status_falls_back_to_rest_when_order_dependency_missing(self):
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            time_provider=lambda: 1000.0,
        )
        self.exchange._order_cache = cache

        with patch.object(upbit_ws, "websocket", None), \
             patch.object(
                 self.exchange,
                 "_get",
                 return_value={
                     "uuid": "uuid-1",
                     "state": "done",
                     "executed_volume": "0.001",
                     "remaining_volume": "0",
                 },
             ) as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "done")
        get.assert_called_once_with("/v1/order", params={"uuid": "uuid-1"}, auth=True)

    def test_get_order_status_falls_back_to_rest_when_order_auth_header_fails(self):
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(side_effect=UpbitAPIError("credentials missing")),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        self.exchange._order_cache = cache

        with patch.object(
            self.exchange,
            "_get",
            return_value={
                "uuid": "uuid-1",
                "state": "done",
                "executed_volume": "0.001",
                "remaining_volume": "0",
            },
        ) as get:
            status = self.exchange.get_order_status("uuid-1")

        self.assertEqual(status.state, "done")
        get.assert_called_once_with("/v1/order", params={"uuid": "uuid-1"}, auth=True)

    def test_get_order_status_propagates_rest_error_after_order_cache_miss(self):
        cache = Mock()
        cache.ensure_started.return_value = True
        cache.get_order_status.return_value = None
        self.exchange._order_cache = cache

        with patch.object(self.exchange, "_get", side_effect=UpbitAPIError("rest order failed")):
            with self.assertRaisesRegex(UpbitAPIError, "rest order failed"):
                self.exchange.get_order_status("uuid-1")

    def test_upbit_order_websocket_cache_parses_default_format_payload(self):
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True

        cache._on_message(
            None,
            b'{"type":"myOrder","code":"KRW-BTC","uuid":"uuid-1","state":"done","executed_volume":"0.001","remaining_volume":"0"}',
        )

        status = cache.get_order_status("uuid-1")
        self.assertIsNotNone(status)
        self.assertEqual(status.uuid, "uuid-1")
        self.assertEqual(status.state, "done")
        self.assertEqual(status.executed_volume, Decimal("0.001"))
        self.assertEqual(status.remaining_volume, Decimal("0"))

    def test_upbit_order_websocket_cache_parses_list_wrapped_simple_payload(self):
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True

        cache._on_message(
            None,
            b'[{"ty":"myOrder","cd":"KRW-BTC","uid":"uuid-1","s":"cancel","ev":"0.001","rv":"0"}]',
        )

        status = cache.get_order_status("uuid-1")
        self.assertIsNotNone(status)
        self.assertEqual(status.state, "cancel")
        self.assertEqual(status.executed_volume, Decimal("0.001"))
        self.assertEqual(status.remaining_volume, Decimal("0"))

    def test_upbit_order_websocket_cache_ignores_wrong_symbol_type_and_malformed_payloads(self):
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": "Bearer test-token"}),
            websocket_app_factory=Mock(),
            time_provider=lambda: 1000.0,
        )
        cache._started = True

        cache._on_message(
            None,
            b'{"type":"myAsset","code":"KRW-BTC","uuid":"uuid-1","state":"done","executed_volume":"0.001","remaining_volume":"0"}',
        )
        cache._on_message(
            None,
            b'{"type":"myOrder","code":"KRW-ETH","uuid":"uuid-1","state":"done","executed_volume":"0.001","remaining_volume":"0"}',
        )
        cache._on_message(None, b'{"type":"myOrder"')
        cache._on_message(
            None,
            b'{"type":"myOrder","code":"KRW-BTC","state":"done","executed_volume":"0.001","remaining_volume":"0"}',
        )
        cache._on_message(
            None,
            b'{"type":"myOrder","code":"KRW-BTC","uuid":"uuid-1","executed_volume":"0.001","remaining_volume":"0"}',
        )
        cache._on_message(
            None,
            b'{"type":"myOrder","code":"KRW-BTC","uuid":"uuid-1","state":"done","executed_volume":"bad","remaining_volume":"0"}',
        )

        self.assertIsNone(cache.get_order_status("uuid-1"))

    def test_upbit_order_websocket_cache_start_uses_private_url_auth_header_and_uppercase_codes(self):
        app = Mock()
        app.run_forever.return_value = None
        app_factory = Mock(return_value=app)
        auth_headers = {"Authorization": "Bearer test-token"}
        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="krw-btc",
            auth_header_provider=Mock(return_value=auth_headers),
            websocket_app_factory=app_factory,
            time_provider=lambda: 1000.0,
        )

        self.assertTrue(cache.ensure_started())

        app_factory.assert_called_once()
        self.assertEqual(app_factory.call_args.args[0], UPBIT_PRIVATE_WS_URL)
        self.assertEqual(app_factory.call_args.kwargs["header"], auth_headers)

        ws = Mock()
        cache._on_open(ws)
        subscribe_message = json.loads(ws.send.call_args.args[0])
        self.assertEqual(
            subscribe_message,
            [
                {"ticket": "auto-private-order"},
                {"type": "myOrder", "codes": ["KRW-BTC"]},
            ],
        )

    def test_upbit_order_websocket_cache_does_not_log_auth_token_on_start_failure(self):
        token = "secret-token"
        cache_holder: list[UpbitOrderWebSocketCache] = []

        def stop_after_first_backoff(_duration: float) -> None:
            cache_holder[0]._shutdown.set()

        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=Mock(return_value={"Authorization": f"Bearer {token}"}),
            websocket_app_factory=Mock(side_effect=RuntimeError(f"Bearer {token}")),
            time_provider=lambda: 1000.0,
            sleep_fn=stop_after_first_backoff,
        )
        cache_holder.append(cache)

        with patch.object(upbit_ws.logger, "warning") as warning:
            self.assertTrue(cache.ensure_started())
            cache._thread.join(timeout=2)

        self.assertFalse(cache._thread is not None and cache._thread.is_alive())

        messages = " ".join(str(call.args[0]) for call in warning.call_args_list)
        self.assertNotIn(token, messages)
        self.assertNotIn("Bearer", messages)

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

    def test_place_order_uses_market_body_for_market_sell_by_volume(self):
        order = Order(
            slot_index=0,
            side=OrderSide.SELL,
            price=Decimal("110000000"),
            quantity=Decimal("0.01"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_SELL_BY_VOLUME,
        )
        calls: list[tuple[str, dict]] = []

        def fake_post(path, body):
            calls.append((path, body))
            if path == "/v1/orders/test":
                return {"result": "ok"}
            if path == "/v1/orders":
                return {"uuid": "uuid-sell-1"}
            self.fail(f"unexpected path: {path}")

        with patch.object(self.exchange, "get_order_chance", return_value=self._valid_sell_chance()), \
             patch.object(self.exchange, "_post", side_effect=fake_post):
            order_id = self.exchange.place_order(order)

        self.assertEqual(order_id, "uuid-sell-1")
        real_order_calls = [body for path, body in calls if path == "/v1/orders"]
        self.assertEqual(len(real_order_calls), 1)
        self.assertEqual(real_order_calls[0]["market"], "KRW-BTC")
        self.assertEqual(real_order_calls[0]["side"], "ask")
        self.assertEqual(real_order_calls[0]["volume"], "0.01")
        self.assertEqual(real_order_calls[0]["ord_type"], "market")

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

    def test_upbit_ticker_websocket_cache_reconnect_loop_retries_with_exponential_backoff(self):
        factory_calls = []
        app = Mock()
        app.run_forever = Mock(return_value=None)
        app.close = Mock()

        def factory(*args, **kwargs):
            factory_calls.append((args, kwargs))
            return app

        sleeps: list[float] = []
        cache_holder: list[UpbitTickerWebSocketCache] = []

        def sleep_fn(duration: float) -> None:
            sleeps.append(duration)
            if len(sleeps) >= 3:
                cache_holder[0]._shutdown.set()

        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=factory,
            time_provider=lambda: 1000.0,
            sleep_fn=sleep_fn,
            random_fn=lambda: 0.5,
        )
        cache_holder.append(cache)

        self.assertTrue(cache.ensure_started("KRW-BTC"))
        cache._thread.join(timeout=2)

        self.assertFalse(cache._thread is not None and cache._thread.is_alive())
        self.assertGreaterEqual(len(factory_calls), 3)
        self.assertEqual(sleeps[:3], [1.0, 2.0, 4.0])

    def test_upbit_ticker_websocket_cache_stop_ends_reconnect_loop(self):
        app = Mock()
        app.close = Mock()
        running = threading.Event()

        def run_forever(*_args, **_kwargs):
            running.set()
            cache._shutdown.wait(timeout=2)

        app.run_forever = run_forever

        cache = UpbitTickerWebSocketCache(
            max_age_seconds=5,
            websocket_app_factory=lambda *a, **kw: app,
            time_provider=lambda: 1000.0,
            sleep_fn=lambda _d: None,
            random_fn=lambda: 0.5,
        )

        self.assertTrue(cache.ensure_started("KRW-BTC"))
        self.assertTrue(running.wait(timeout=2))

        cache.stop()
        cache._thread.join(timeout=2)

        self.assertFalse(cache._thread is not None and cache._thread.is_alive())
        app.close.assert_called()

    def test_upbit_asset_websocket_cache_reissues_auth_header_on_each_attempt(self):
        auth_calls = []

        def auth_provider():
            auth_calls.append(len(auth_calls))
            return {"Authorization": f"Bearer token-{len(auth_calls)}"}

        app = Mock()
        app.run_forever = Mock(return_value=None)
        app.close = Mock()

        factory_headers: list[dict] = []

        def factory(*_args, **kwargs):
            factory_headers.append(kwargs.get("header"))
            return app

        sleeps: list[float] = []
        cache_holder: list[UpbitAssetWebSocketCache] = []

        def sleep_fn(duration: float) -> None:
            sleeps.append(duration)
            if len(sleeps) >= 3:
                cache_holder[0]._shutdown.set()

        cache = UpbitAssetWebSocketCache(
            max_age_seconds=5,
            auth_header_provider=auth_provider,
            websocket_app_factory=factory,
            time_provider=lambda: 1000.0,
            sleep_fn=sleep_fn,
            random_fn=lambda: 0.5,
        )
        cache_holder.append(cache)

        self.assertTrue(cache.ensure_started())
        cache._thread.join(timeout=2)

        self.assertFalse(cache._thread is not None and cache._thread.is_alive())
        # 1 initial bootstrap call + at least 3 reconnect loop reissues
        self.assertGreaterEqual(len(auth_calls), 4)
        authorizations = [h.get("Authorization") for h in factory_headers if h]
        self.assertEqual(len(authorizations), len(set(authorizations)))  # 매번 다른 Authorization
        self.assertGreaterEqual(len(factory_headers), 3)

    def test_upbit_order_websocket_cache_reissues_auth_header_on_each_attempt(self):
        auth_calls = []

        def auth_provider():
            auth_calls.append(len(auth_calls))
            return {"Authorization": f"Bearer order-token-{len(auth_calls)}"}

        app = Mock()
        app.run_forever = Mock(return_value=None)
        app.close = Mock()

        factory_headers: list[dict] = []

        def factory(*_args, **kwargs):
            factory_headers.append(kwargs.get("header"))
            return app

        sleeps: list[float] = []
        cache_holder: list[UpbitOrderWebSocketCache] = []

        def sleep_fn(duration: float) -> None:
            sleeps.append(duration)
            if len(sleeps) >= 3:
                cache_holder[0]._shutdown.set()

        cache = UpbitOrderWebSocketCache(
            max_age_seconds=5,
            symbol="KRW-BTC",
            auth_header_provider=auth_provider,
            websocket_app_factory=factory,
            time_provider=lambda: 1000.0,
            sleep_fn=sleep_fn,
            random_fn=lambda: 0.5,
        )
        cache_holder.append(cache)

        self.assertTrue(cache.ensure_started())
        cache._thread.join(timeout=2)

        self.assertFalse(cache._thread is not None and cache._thread.is_alive())
        self.assertGreaterEqual(len(auth_calls), 4)
        authorizations = [h.get("Authorization") for h in factory_headers if h]
        self.assertEqual(len(authorizations), len(set(authorizations)))
        self.assertGreaterEqual(len(factory_headers), 3)

    def test_upbit_candle_websocket_cache_reconnect_loop_retries_after_disconnect(self):
        app = Mock()
        app.run_forever = Mock(return_value=None)
        app.close = Mock()

        factory_calls = []

        def factory(*args, **kwargs):
            factory_calls.append((args, kwargs))
            return app

        sleeps: list[float] = []
        cache_holder: list[UpbitMinuteCandleWebSocketCache] = []

        def sleep_fn(duration: float) -> None:
            sleeps.append(duration)
            if len(sleeps) >= 3:
                cache_holder[0]._shutdown.set()

        cache = UpbitMinuteCandleWebSocketCache(
            max_age_seconds=30,
            websocket_app_factory=factory,
            time_provider=lambda: 1000.0,
            sleep_fn=sleep_fn,
            random_fn=lambda: 0.5,
        )
        cache_holder.append(cache)

        self.assertTrue(cache.ensure_started("KRW-BTC", 15))
        cache._thread.join(timeout=2)

        self.assertFalse(cache._thread is not None and cache._thread.is_alive())
        self.assertGreaterEqual(len(factory_calls), 3)
