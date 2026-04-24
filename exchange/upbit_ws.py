"""Optional Upbit WebSocket caches."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from utils.decimal_utils import to_decimal
from utils.logger import get_logger

try:
    import websocket
except ModuleNotFoundError:  # pragma: no cover - exercised through start fallback tests
    websocket = None


logger = get_logger(__name__)

UPBIT_PUBLIC_WS_URL = "wss://api.upbit.com/websocket/v1"
UPBIT_PRIVATE_WS_URL = "wss://api.upbit.com/websocket/v1/private"
UPBIT_SUPPORTED_MINUTE_CANDLE_UNITS = {1, 3, 5, 10, 15, 30, 60, 240}


@dataclass(frozen=True)
class UpbitOrderWebSocketStatus:
    """Parsed private myOrder event cached for conservative REST acceleration."""

    uuid: str
    state: str
    executed_volume: Decimal
    remaining_volume: Decimal


class UpbitTickerWebSocketCache:
    """Threaded cache for public Upbit ticker trade_price messages."""

    def __init__(
        self,
        *,
        max_age_seconds: float,
        websocket_app_factory: Optional[Callable] = None,
        time_provider: Callable[[], float] | None = None,
        url: str = UPBIT_PUBLIC_WS_URL,
    ):
        self.max_age_seconds = float(max_age_seconds)
        self._websocket_app_factory = websocket_app_factory
        self._time_provider = time_provider or time.monotonic
        self._url = url
        self._lock = threading.Lock()
        self._prices: dict[str, tuple[Decimal, float]] = {}
        self._codes: set[str] = set()
        self._app = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._start_failed = False
        self._connection_failed = False

    def ensure_started(self, symbol: str) -> bool:
        """Start the background WebSocket thread once, returning False on unsafe setup."""
        code = self._normalize_symbol(symbol)
        if not code:
            return False

        with self._lock:
            self._codes.add(code)
            if self._started:
                return True
            if self._start_failed:
                return False

            app_factory = self._resolve_websocket_app_factory()
            if app_factory is None:
                self._start_failed = True
                logger.warning("Upbit public WebSocket disabled: websocket-client is not installed")
                return False

            codes = sorted(self._codes)
            try:
                app = app_factory(
                    self._url,
                    on_open=lambda ws: self._on_open(ws, codes),
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                thread = threading.Thread(
                    target=self._run_forever,
                    args=(app,),
                    daemon=True,
                    name="upbit-public-ticker-ws",
                )
                self._app = app
                self._thread = thread
                self._started = True
                thread.start()
                return True
            except Exception as exc:
                self._app = None
                self._thread = None
                self._started = False
                self._start_failed = True
                logger.warning(f"Upbit public WebSocket start failed; REST fallback will be used: {exc}")
                return False

    def get_price(self, symbol: str) -> Decimal | None:
        """Return a fresh cached price, or None when missing/stale."""
        code = self._normalize_symbol(symbol)
        if not code:
            return None

        now = self._time_provider()
        with self._lock:
            if self._connection_failed:
                return None
            cached = self._prices.get(code)

        if cached is None:
            return None

        price, updated_at = cached
        if now - updated_at > self.max_age_seconds:
            return None
        return price

    def stop(self) -> None:
        """Best-effort shutdown hook for tests or controlled process teardown."""
        with self._lock:
            app = self._app
            self._app = None
            self._thread = None
            self._started = False
        if app is not None and hasattr(app, "close"):
            app.close()

    def _resolve_websocket_app_factory(self) -> Optional[Callable]:
        if self._websocket_app_factory is not None:
            return self._websocket_app_factory
        if websocket is None:
            return None
        return getattr(websocket, "WebSocketApp", None)

    def _run_forever(self, app) -> None:
        try:
            app.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as exc:  # pragma: no cover - depends on websocket-client runtime
            with self._lock:
                self._connection_failed = True
            logger.warning(f"Upbit public WebSocket stopped unexpectedly; REST fallback remains available: {exc}")
        finally:
            with self._lock:
                if self._app is app:
                    self._app = None
                    self._thread = None
                    self._started = False

    def _on_open(self, ws, codes: list[str]) -> None:
        subscribe_message = [
            {"ticket": "auto-public-ticker"},
            {"type": "ticker", "codes": codes},
            {"format": "SIMPLE"},
        ]
        ws.send(json.dumps(subscribe_message))
        with self._lock:
            self._connection_failed = False
        logger.info(f"Upbit public WebSocket subscribed: codes={codes}")

    def _on_message(self, _ws, message) -> None:
        try:
            payload = self._decode_message(message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("Invalid Upbit ticker WebSocket message ignored")
            return
        if not isinstance(payload, dict):
            return

        for type_key in ("type", "ty"):
            message_type = payload.get(type_key)
            if message_type is not None and str(message_type).lower() != "ticker":
                return

        code = payload.get("code") or payload.get("cd")
        raw_price = payload.get("trade_price")
        if raw_price is None:
            raw_price = payload.get("tp")
        if not code or raw_price is None:
            return

        code = self._normalize_symbol(str(code))
        if not code:
            return
        with self._lock:
            if code not in self._codes:
                return

        try:
            price = to_decimal(raw_price)
        except (InvalidOperation, TypeError, ValueError):
            logger.debug(f"Invalid Upbit ticker price ignored: code={code}, price={raw_price}")
            return
        if price <= 0:
            logger.debug(f"Non-positive Upbit ticker price ignored: code={code}, price={raw_price}")
            return

        with self._lock:
            self._prices[code] = (price, self._time_provider())

    def _on_error(self, _ws, error) -> None:
        with self._lock:
            self._connection_failed = True
        logger.warning(f"Upbit public WebSocket error; REST fallback remains available: {error}")

    def _on_close(self, _ws, close_status_code, close_msg) -> None:
        with self._lock:
            self._connection_failed = True
        logger.info(f"Upbit public WebSocket closed: code={close_status_code}, msg={close_msg}")

    @staticmethod
    def _decode_message(message):
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        return json.loads(message)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()


class UpbitMinuteCandleWebSocketCache:
    """Threaded cache for public Upbit minute candle close messages."""

    def __init__(
        self,
        *,
        max_age_seconds: float,
        websocket_app_factory: Optional[Callable] = None,
        time_provider: Callable[[], float] | None = None,
        url: str = UPBIT_PUBLIC_WS_URL,
    ):
        self.max_age_seconds = float(max_age_seconds)
        self._websocket_app_factory = websocket_app_factory
        self._time_provider = time_provider or time.monotonic
        self._url = url
        self._lock = threading.Lock()
        self._candles: dict[tuple[str, int, datetime], tuple[Decimal, float]] = {}
        self._last_message_at: dict[tuple[str, int], float] = {}
        self._subscriptions: set[tuple[str, int]] = set()
        self._active_subscriptions: set[tuple[str, int]] = set()
        self._app = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._start_failed = False
        self._connection_failed = False

    def ensure_started(self, symbol: str, unit_minutes: int) -> bool:
        """Start the background WebSocket thread once for a supported symbol/unit."""
        code = self._normalize_symbol(symbol)
        unit = self._normalize_unit(unit_minutes)
        if not code or unit is None:
            return False

        with self._lock:
            key = (code, unit)
            if self._started:
                return key in self._active_subscriptions
            if self._start_failed:
                return False

            self._subscriptions.add(key)
            app_factory = self._resolve_websocket_app_factory()
            if app_factory is None:
                self._start_failed = True
                logger.warning("Upbit public candle WebSocket disabled: websocket-client is not installed")
                return False

            subscriptions = sorted(self._subscriptions)
            try:
                app = app_factory(
                    self._url,
                    on_open=lambda ws: self._on_open(ws, subscriptions),
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                thread = threading.Thread(
                    target=self._run_forever,
                    args=(app,),
                    daemon=True,
                    name="upbit-public-candle-ws",
                )
                self._app = app
                self._thread = thread
                self._started = True
                self._active_subscriptions = set(subscriptions)
                thread.start()
                return True
            except Exception as exc:
                self._app = None
                self._thread = None
                self._started = False
                self._active_subscriptions = set()
                self._start_failed = True
                logger.warning(f"Upbit public candle WebSocket start failed; REST fallback will be used: {exc}")
                return False

    def get_closes(
        self,
        symbol: str,
        *,
        unit_minutes: int,
        count: int,
        to: datetime | None,
    ) -> list[Decimal] | None:
        """Return latest completed candle closes, or None when REST should be used."""
        if count <= 0:
            return None
        code = self._normalize_symbol(symbol)
        unit = self._normalize_unit(unit_minutes)
        if not code or unit is None or to is None:
            return None

        cutoff = self._normalize_datetime_utc(to)
        now = self._time_provider()
        key = (code, unit)
        with self._lock:
            if self._connection_failed or key not in self._active_subscriptions:
                return None
            last_message_at = self._last_message_at.get(key)
            if last_message_at is None or now - last_message_at > self.max_age_seconds:
                return None

            candles = [
                (candle_start, price)
                for (candle_code, candle_unit, candle_start), (price, _updated_at) in self._candles.items()
                if candle_code == code
                and candle_unit == unit
                and candle_start < cutoff
            ]

        if len(candles) < count:
            return None

        candles.sort(key=lambda item: item[0], reverse=True)
        return [price for _candle_start, price in candles[:count]]

    def stop(self) -> None:
        """Best-effort shutdown hook for tests or controlled process teardown."""
        with self._lock:
            app = self._app
            self._app = None
            self._thread = None
            self._started = False
            self._active_subscriptions = set()
        if app is not None and hasattr(app, "close"):
            app.close()

    def _resolve_websocket_app_factory(self) -> Optional[Callable]:
        if self._websocket_app_factory is not None:
            return self._websocket_app_factory
        if websocket is None:
            return None
        return getattr(websocket, "WebSocketApp", None)

    def _run_forever(self, app) -> None:
        try:
            app.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as exc:  # pragma: no cover - depends on websocket-client runtime
            with self._lock:
                self._connection_failed = True
            logger.warning(f"Upbit public candle WebSocket stopped unexpectedly; REST fallback remains available: {exc}")
        finally:
            with self._lock:
                if self._app is app:
                    self._app = None
                    self._thread = None
                    self._started = False
                    self._active_subscriptions = set()

    def _on_open(self, ws, subscriptions: list[tuple[str, int]]) -> None:
        by_unit: dict[int, list[str]] = {}
        for code, unit in subscriptions:
            by_unit.setdefault(unit, []).append(code)

        subscribe_message = [{"ticket": "auto-public-candle"}]
        for unit in sorted(by_unit):
            subscribe_message.append(
                {
                    "type": f"candle.{unit}m",
                    "codes": sorted(by_unit[unit]),
                }
            )
        ws.send(json.dumps(subscribe_message))
        with self._lock:
            self._connection_failed = False
        logger.info(f"Upbit public candle WebSocket subscribed: subscriptions={subscriptions}")

    def _on_message(self, _ws, message) -> None:
        try:
            payload = self._decode_message(message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("Invalid Upbit candle WebSocket message ignored")
            return
        if not isinstance(payload, dict):
            return

        unit = self._extract_unit_from_type(payload.get("type"))
        if unit is None:
            return

        code = self._normalize_symbol(str(payload.get("code") or ""))
        if not code:
            return
        key = (code, unit)
        with self._lock:
            if key not in self._active_subscriptions and key not in self._subscriptions:
                return

        raw_price = payload.get("trade_price")
        raw_candle_start = payload.get("candle_date_time_utc")
        if raw_price is None or raw_candle_start is None:
            return

        try:
            price = to_decimal(raw_price)
        except (InvalidOperation, TypeError, ValueError):
            logger.debug(f"Invalid Upbit candle close ignored: code={code}, unit={unit}, price={raw_price}")
            return
        if price <= 0:
            logger.debug(f"Non-positive Upbit candle close ignored: code={code}, unit={unit}, price={raw_price}")
            return

        try:
            candle_start = self._parse_utc_datetime(str(raw_candle_start))
        except ValueError:
            logger.debug(f"Invalid Upbit candle start ignored: code={code}, unit={unit}, start={raw_candle_start}")
            return

        now = self._time_provider()
        with self._lock:
            self._candles[(code, unit, candle_start)] = (price, now)
            self._last_message_at[key] = now
            self._prune_locked(code, unit)

    def _on_error(self, _ws, error) -> None:
        with self._lock:
            self._connection_failed = True
        logger.warning(f"Upbit public candle WebSocket error; REST fallback remains available: {error}")

    def _on_close(self, _ws, close_status_code, close_msg) -> None:
        with self._lock:
            self._connection_failed = True
        logger.info(f"Upbit public candle WebSocket closed: code={close_status_code}, msg={close_msg}")

    def _prune_locked(self, code: str, unit: int, *, max_candles: int = 500) -> None:
        starts = sorted(
            candle_start
            for candle_code, candle_unit, candle_start in self._candles
            if candle_code == code and candle_unit == unit
        )
        for candle_start in starts[:-max_candles]:
            self._candles.pop((code, unit, candle_start), None)

    @staticmethod
    def _decode_message(message):
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        return json.loads(message)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _normalize_unit(unit_minutes: int) -> int | None:
        try:
            unit = int(unit_minutes)
        except (TypeError, ValueError):
            return None
        if unit not in UPBIT_SUPPORTED_MINUTE_CANDLE_UNITS:
            return None
        return unit

    @staticmethod
    def _extract_unit_from_type(raw_type) -> int | None:
        if raw_type is None:
            return None
        match = re.fullmatch(r"candle\.(\d+)m", str(raw_type).strip().lower())
        if match is None:
            return None
        return UpbitMinuteCandleWebSocketCache._normalize_unit(int(match.group(1)))

    @staticmethod
    def _parse_utc_datetime(raw_value: str) -> datetime:
        normalized = raw_value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _normalize_datetime_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class UpbitAssetWebSocketCache:
    """Threaded cache for private Upbit myAsset balance messages."""

    def __init__(
        self,
        *,
        max_age_seconds: float,
        auth_header_provider: Callable[[], dict[str, str]],
        websocket_app_factory: Optional[Callable] = None,
        time_provider: Callable[[], float] | None = None,
        url: str = UPBIT_PRIVATE_WS_URL,
    ):
        self.max_age_seconds = float(max_age_seconds)
        self._auth_header_provider = auth_header_provider
        self._websocket_app_factory = websocket_app_factory
        self._time_provider = time_provider or time.monotonic
        self._url = url
        self._lock = threading.Lock()
        self._balances: dict[str, Decimal] = {}
        self._last_event_at: float | None = None
        self._app = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._start_failed = False
        self._connection_failed = False

    def ensure_started(self) -> bool:
        """Start the private asset stream once, returning False when REST should be used."""
        with self._lock:
            if self._started:
                return True
            if self._start_failed:
                return False

            app_factory = self._resolve_websocket_app_factory()
            if app_factory is None:
                self._start_failed = True
                logger.warning("Upbit private asset WebSocket disabled: websocket-client is not installed")
                return False

            try:
                auth_headers = self._auth_header_provider()
            except Exception:
                self._start_failed = True
                logger.warning("Upbit private asset WebSocket auth header unavailable; REST fallback will be used")
                return False
            if not isinstance(auth_headers, dict) or not auth_headers.get("Authorization"):
                self._start_failed = True
                logger.warning("Upbit private asset WebSocket auth header invalid; REST fallback will be used")
                return False

            try:
                app = app_factory(
                    self._url,
                    header=auth_headers,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                thread = threading.Thread(
                    target=self._run_forever,
                    args=(app,),
                    daemon=True,
                    name="upbit-private-asset-ws",
                )
                self._app = app
                self._thread = thread
                self._started = True
                thread.start()
                return True
            except Exception:
                self._app = None
                self._thread = None
                self._started = False
                self._start_failed = True
                logger.warning("Upbit private asset WebSocket start failed; REST fallback will be used")
                return False

    def get_balance(self, currency: str) -> Decimal | None:
        """Return a fresh cached asset balance, or None when REST should be used."""
        normalized_currency = self._normalize_currency(currency)
        if not normalized_currency:
            return None

        now = self._time_provider()
        with self._lock:
            if self._connection_failed or not self._started or self._last_event_at is None:
                return None
            if now - self._last_event_at > self.max_age_seconds:
                return None
            return self._balances.get(normalized_currency)

    def stop(self) -> None:
        """Best-effort shutdown hook for tests or controlled process teardown."""
        with self._lock:
            app = self._app
            self._app = None
            self._thread = None
            self._started = False
        if app is not None and hasattr(app, "close"):
            app.close()

    def _resolve_websocket_app_factory(self) -> Optional[Callable]:
        if self._websocket_app_factory is not None:
            return self._websocket_app_factory
        if websocket is None:
            return None
        return getattr(websocket, "WebSocketApp", None)

    def _run_forever(self, app) -> None:
        try:
            app.run_forever(ping_interval=30, ping_timeout=10)
        except Exception:  # pragma: no cover - depends on websocket-client runtime
            with self._lock:
                self._connection_failed = True
            logger.warning("Upbit private asset WebSocket stopped unexpectedly; REST fallback remains available")
        finally:
            with self._lock:
                if self._app is app:
                    self._app = None
                    self._thread = None
                    self._started = False

    def _on_open(self, ws) -> None:
        subscribe_message = [
            {"ticket": "auto-private-asset"},
            {"type": "myAsset"},
        ]
        ws.send(json.dumps(subscribe_message))
        with self._lock:
            self._connection_failed = False
        logger.info("Upbit private asset WebSocket subscribed")

    def _on_message(self, _ws, message) -> None:
        try:
            payload = self._decode_message(message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("Invalid Upbit asset WebSocket message ignored")
            return

        for event in self._iter_payloads(payload):
            self._update_from_event(event)

    def _on_error(self, _ws, _error) -> None:
        with self._lock:
            self._connection_failed = True
        logger.warning("Upbit private asset WebSocket error; REST fallback remains available")

    def _on_close(self, _ws, close_status_code, close_msg) -> None:
        with self._lock:
            self._connection_failed = True
        logger.info(f"Upbit private asset WebSocket closed: code={close_status_code}, msg={close_msg}")

    def _update_from_event(self, payload: dict) -> None:
        for type_key in ("type", "ty"):
            message_type = payload.get(type_key)
            if message_type is not None and str(message_type).lower() != "myasset":
                return

        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list):
            return

        balances: dict[str, Decimal] = {}
        for raw_asset in raw_assets:
            if not isinstance(raw_asset, dict):
                continue

            currency = self._normalize_currency(str(raw_asset.get("currency") or ""))
            raw_balance = raw_asset.get("balance")
            if not currency or raw_balance is None:
                continue

            try:
                balance = to_decimal(raw_balance)
            except (InvalidOperation, TypeError, ValueError):
                logger.debug(f"Invalid Upbit asset balance ignored: currency={currency}")
                continue
            if balance < 0:
                logger.debug(f"Negative Upbit asset balance ignored: currency={currency}")
                continue

            balances[currency] = balance

        if not balances:
            return

        with self._lock:
            self._balances = balances
            self._last_event_at = self._time_provider()

    @staticmethod
    def _iter_payloads(payload) -> list[dict]:
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _decode_message(message):
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        return json.loads(message)

    @staticmethod
    def _normalize_currency(currency: str) -> str:
        return currency.strip().upper()


class UpbitOrderWebSocketCache:
    """Threaded cache for private Upbit myOrder messages."""

    def __init__(
        self,
        *,
        max_age_seconds: float,
        symbol: str | None,
        auth_header_provider: Callable[[], dict[str, str]],
        websocket_app_factory: Optional[Callable] = None,
        time_provider: Callable[[], float] | None = None,
        url: str = UPBIT_PRIVATE_WS_URL,
    ):
        self.max_age_seconds = float(max_age_seconds)
        self._symbol = self._normalize_symbol(symbol or "")
        self._auth_header_provider = auth_header_provider
        self._websocket_app_factory = websocket_app_factory
        self._time_provider = time_provider or time.monotonic
        self._url = url
        self._lock = threading.Lock()
        self._orders: dict[str, tuple[UpbitOrderWebSocketStatus, float]] = {}
        self._app = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._start_failed = False
        self._connection_failed = False

    def ensure_started(self) -> bool:
        """Start the private order stream once, returning False when REST should be used."""
        with self._lock:
            if self._started:
                return True
            if self._start_failed:
                return False

            app_factory = self._resolve_websocket_app_factory()
            if app_factory is None:
                self._start_failed = True
                logger.warning("Upbit private order WebSocket disabled: websocket-client is not installed")
                return False

            try:
                auth_headers = self._auth_header_provider()
            except Exception:
                self._start_failed = True
                logger.warning("Upbit private order WebSocket auth header unavailable; REST fallback will be used")
                return False
            if not isinstance(auth_headers, dict) or not auth_headers.get("Authorization"):
                self._start_failed = True
                logger.warning("Upbit private order WebSocket auth header invalid; REST fallback will be used")
                return False

            try:
                app = app_factory(
                    self._url,
                    header=auth_headers,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                thread = threading.Thread(
                    target=self._run_forever,
                    args=(app,),
                    daemon=True,
                    name="upbit-private-order-ws",
                )
                self._app = app
                self._thread = thread
                self._started = True
                thread.start()
                return True
            except Exception:
                self._app = None
                self._thread = None
                self._started = False
                self._start_failed = True
                logger.warning("Upbit private order WebSocket start failed; REST fallback will be used")
                return False

    def get_order_status(self, order_id: str) -> UpbitOrderWebSocketStatus | None:
        """Return a fresh cached order event, or None when REST should be used."""
        normalized_order_id = self._normalize_order_id(order_id)
        if not normalized_order_id:
            return None

        now = self._time_provider()
        with self._lock:
            if self._connection_failed or not self._started:
                return None
            cached = self._orders.get(normalized_order_id)

        if cached is None:
            return None

        status, updated_at = cached
        if now - updated_at > self.max_age_seconds:
            return None
        return status

    def stop(self) -> None:
        """Best-effort shutdown hook for tests or controlled process teardown."""
        with self._lock:
            app = self._app
            self._app = None
            self._thread = None
            self._started = False
        if app is not None and hasattr(app, "close"):
            app.close()

    def _resolve_websocket_app_factory(self) -> Optional[Callable]:
        if self._websocket_app_factory is not None:
            return self._websocket_app_factory
        if websocket is None:
            return None
        return getattr(websocket, "WebSocketApp", None)

    def _run_forever(self, app) -> None:
        try:
            app.run_forever(ping_interval=30, ping_timeout=10)
        except Exception:  # pragma: no cover - depends on websocket-client runtime
            with self._lock:
                self._connection_failed = True
            logger.warning("Upbit private order WebSocket stopped unexpectedly; REST fallback remains available")
        finally:
            with self._lock:
                if self._app is app:
                    self._app = None
                    self._thread = None
                    self._started = False

    def _on_open(self, ws) -> None:
        subscription = {"type": "myOrder"}
        if self._symbol:
            subscription["codes"] = [self._symbol]
        subscribe_message = [
            {"ticket": "auto-private-order"},
            subscription,
        ]
        ws.send(json.dumps(subscribe_message))
        with self._lock:
            self._connection_failed = False
        logger.info(f"Upbit private order WebSocket subscribed: scoped={bool(self._symbol)}")

    def _on_message(self, _ws, message) -> None:
        try:
            payload = self._decode_message(message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("Invalid Upbit order WebSocket message ignored")
            return

        for event in self._iter_payloads(payload):
            self._update_from_event(event)

    def _on_error(self, _ws, _error) -> None:
        with self._lock:
            self._connection_failed = True
        logger.warning("Upbit private order WebSocket error; REST fallback remains available")

    def _on_close(self, _ws, close_status_code, close_msg) -> None:
        with self._lock:
            self._connection_failed = True
        logger.info(f"Upbit private order WebSocket closed: code={close_status_code}, msg={close_msg}")

    def _update_from_event(self, payload: dict) -> None:
        for type_key in ("type", "ty"):
            message_type = payload.get(type_key)
            if message_type is not None and str(message_type).lower() != "myorder":
                return

        raw_code = payload.get("code") or payload.get("cd")
        if raw_code is not None and self._symbol:
            code = self._normalize_symbol(str(raw_code))
            if code != self._symbol:
                return

        order_id = self._normalize_order_id(payload.get("uuid") or payload.get("uid") or "")
        raw_state = payload.get("state") or payload.get("s")
        if not order_id or raw_state is None:
            return

        raw_executed_volume = payload.get("executed_volume")
        if raw_executed_volume is None:
            raw_executed_volume = payload.get("ev")
        raw_remaining_volume = payload.get("remaining_volume")
        if raw_remaining_volume is None:
            raw_remaining_volume = payload.get("rv")
        if raw_executed_volume is None or raw_remaining_volume is None:
            return

        state = str(raw_state).strip().lower()
        if not state:
            return

        try:
            executed_volume = to_decimal(raw_executed_volume)
            remaining_volume = to_decimal(raw_remaining_volume)
        except (InvalidOperation, TypeError, ValueError):
            logger.debug(f"Invalid Upbit order volumes ignored: uuid={order_id}")
            return
        if executed_volume < 0 or remaining_volume < 0:
            logger.debug(f"Negative Upbit order volumes ignored: uuid={order_id}")
            return

        status = UpbitOrderWebSocketStatus(
            uuid=order_id,
            state=state,
            executed_volume=executed_volume,
            remaining_volume=remaining_volume,
        )
        with self._lock:
            self._orders[order_id] = (status, self._time_provider())

    @staticmethod
    def _iter_payloads(payload) -> list[dict]:
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _decode_message(message):
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        return json.loads(message)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _normalize_order_id(order_id) -> str:
        return str(order_id).strip()
