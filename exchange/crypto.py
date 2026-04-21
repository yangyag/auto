"""
업비트 거래소 구현
API 문서: https://docs.upbit.com/
인증: JWT (Access Key + Secret Key, HMAC SHA512 query hash)
"""
import hashlib
import random
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import unquote, urlencode

import jwt
import requests

from core.models import Order, OrderExecutionType, OrderSide, OrderStatus
from exchange.base import BaseExchange
from utils.decimal_utils import DECIMAL_ZERO, format_decimal, to_decimal
from utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.upbit.com"
RATE_LIMIT_RETRY_ATTEMPTS = 3
RATE_LIMIT_BACKOFF_BASE_SECONDS = 0.25
RATE_LIMIT_WINDOW_SECONDS = 1.0
RATE_LIMIT_JITTER_CAP_SECONDS = 0.05
RATE_LIMIT_418_RETRY_MAX_SECONDS = 3.0


@dataclass
class _RateLimitState:
    remaining_sec: int
    updated_at_monotonic: float


class UpbitAPIError(RuntimeError):
    """업비트 API 요청 실패를 나타내는 예외."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, error_name: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_name = error_name


class CryptoExchange(BaseExchange):

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self._rate_limit_states: dict[str, _RateLimitState] = {}
        self._rate_limit_aliases: dict[str, str] = {}
        self._random = random.Random()
        logger.info("업비트 거래소 초기화")

    # ── 인증 헬퍼 ────────────────────────────────────────────

    def _require_credentials(self):
        if not self.api_key or not self.api_secret:
            raise UpbitAPIError(
                "업비트 API 키가 설정되지 않았습니다. "
                "UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 환경변수를 확인하세요."
            )

    def _build_query_string(self, query: dict[str, Any]) -> str:
        """업비트 문서 기준 query hash 생성용 문자열 구성."""
        return unquote(urlencode(query, doseq=True))

    def _auth_header(self, query: Optional[dict] = None) -> dict:
        """JWT 인증 헤더 생성. query 파라미터가 있으면 SHA512 해시 포함."""
        self._require_credentials()

        payload = {
            "access_key": self.api_key,
            "nonce": str(uuid.uuid4()),
        }
        if query:
            query_string = self._build_query_string(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload["query_hash"] = m.hexdigest()
            payload["query_hash_alg"] = "SHA512"

        token = jwt.encode(payload, self.api_secret, algorithm="HS512")
        return {"Authorization": f"Bearer {token}"}

    def _rate_limit_group_hint(self, path: str) -> str | None:
        if path.startswith("/v1/orders/test"):
            return "order_test"
        if path.startswith("/v1/ticker"):
            return "ticker"
        if path.startswith("/v1/candles/"):
            return "candle"
        if path.startswith("/v1/"):
            return "default"
        return None

    def _resolve_rate_limit_group(self, group_hint: str | None) -> str | None:
        if group_hint is None:
            return None
        return self._rate_limit_aliases.get(group_hint, group_hint)

    def _parse_remaining_req_header(self, header_value: str | None) -> tuple[str | None, int | None]:
        if not header_value:
            return None, None

        fields: dict[str, str] = {}
        for segment in header_value.split(";"):
            if "=" not in segment:
                continue
            key, value = segment.split("=", 1)
            fields[key.strip()] = value.strip()

        group = fields.get("group")
        sec_raw = fields.get("sec")
        if sec_raw is None:
            return group, None
        try:
            return group, int(sec_raw)
        except ValueError:
            return group, None

    def _update_rate_limit_from_header(
        self,
        header_value: str | None,
        *,
        group_hint: str | None = None,
    ) -> None:
        group, remaining_sec = self._parse_remaining_req_header(header_value)
        if group is None or remaining_sec is None:
            return

        self._rate_limit_states[group] = _RateLimitState(
            remaining_sec=remaining_sec,
            updated_at_monotonic=time.monotonic(),
        )
        if group_hint is not None and group_hint != group:
            self._rate_limit_aliases[group_hint] = group

    def _remaining_window_delay(self, group_hint: str | None) -> float:
        group = self._resolve_rate_limit_group(group_hint)
        if group is None:
            return 0.0

        state = self._rate_limit_states.get(group)
        if state is None or state.remaining_sec > 0:
            return 0.0

        elapsed = time.monotonic() - state.updated_at_monotonic
        if elapsed >= RATE_LIMIT_WINDOW_SECONDS:
            return 0.0
        return RATE_LIMIT_WINDOW_SECONDS - elapsed

    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def _jitter(self, cap_seconds: float = RATE_LIMIT_JITTER_CAP_SECONDS) -> float:
        if cap_seconds <= 0:
            return 0.0
        return self._random.uniform(0, cap_seconds)

    def _wait_for_rate_limit_slot(self, group_hint: str | None) -> None:
        delay = self._remaining_window_delay(group_hint)
        if delay <= 0:
            return

        sleep_seconds = delay + self._jitter()
        logger.warning(
            f"업비트 rate limit 대기: group={self._resolve_rate_limit_group(group_hint)} "
            f"sleep={sleep_seconds:.3f}s"
        )
        self._sleep(sleep_seconds)

    @staticmethod
    def _extract_retry_after_seconds(payload: dict | list | None) -> int | None:
        if not isinstance(payload, dict):
            return None

        for key in ("retry_after", "retryAfter", "retry_after_seconds", "block_seconds"):
            raw = payload.get(key)
            if raw is None:
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue

        error = payload.get("error", {})
        if isinstance(error, dict):
            error_message = error.get("message", "")
            match = re.search(r"(\d+)", str(error_message))
            if match:
                return int(match.group(1))
        return None

    def _compute_rate_limit_retry_delay(
        self,
        *,
        status_code: int,
        payload: dict | list | None,
        group_hint: str | None,
        attempt: int,
    ) -> float:
        if status_code == 418:
            retry_after_seconds = self._extract_retry_after_seconds(payload)
            if retry_after_seconds is not None and retry_after_seconds > 0:
                return min(float(retry_after_seconds), RATE_LIMIT_418_RETRY_MAX_SECONDS) + self._jitter()

        base_delay = RATE_LIMIT_BACKOFF_BASE_SECONDS * (2 ** attempt)
        return max(base_delay, self._remaining_window_delay(group_hint)) + self._jitter()

    def _should_retry_rate_limit(
        self,
        *,
        status_code: int,
        payload: dict | list | None,
        attempt: int,
    ) -> bool:
        if status_code == 429:
            return attempt < RATE_LIMIT_RETRY_ATTEMPTS - 1
        if status_code != 418 or attempt >= 1:
            return False

        retry_after_seconds = self._extract_retry_after_seconds(payload)
        return (
            retry_after_seconds is not None
            and retry_after_seconds <= RATE_LIMIT_418_RETRY_MAX_SECONDS
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        auth: bool = False,
    ) -> dict | list:
        base_headers = {}
        if body is not None:
            base_headers["Content-Type"] = "application/json; charset=utf-8"

        group_hint = self._rate_limit_group_hint(path)

        for attempt in range(RATE_LIMIT_RETRY_ATTEMPTS):
            self._wait_for_rate_limit_slot(group_hint)
            headers = dict(base_headers)
            if auth:
                headers.update(self._auth_header(body if body is not None else params))

            try:
                resp = requests.request(
                    method,
                    f"{BASE_URL}{path}",
                    params=params,
                    json=body,
                    headers=headers,
                    timeout=10,
                )
                self._update_rate_limit_from_header(
                    resp.headers.get("Remaining-Req"),
                    group_hint=group_hint,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                response = e.response
                error_name = None
                error_message = None
                payload: dict | list | None = None

                if response is not None:
                    self._update_rate_limit_from_header(
                        response.headers.get("Remaining-Req"),
                        group_hint=group_hint,
                    )
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {}
                    error = payload.get("error", {}) if isinstance(payload, dict) else {}
                    error_name = error.get("name")
                    error_message = error.get("message")

                    if self._should_retry_rate_limit(
                        status_code=response.status_code,
                        payload=payload,
                        attempt=attempt,
                    ):
                        delay = self._compute_rate_limit_retry_delay(
                            status_code=response.status_code,
                            payload=payload,
                            group_hint=group_hint,
                            attempt=attempt,
                        )
                        logger.warning(
                            f"업비트 rate limit 재시도 대기: status={response.status_code} "
                            f"group={self._resolve_rate_limit_group(group_hint)} "
                            f"attempt={attempt + 1}/{RATE_LIMIT_RETRY_ATTEMPTS} sleep={delay:.3f}s"
                        )
                        self._sleep(delay)
                        continue

                    auth_messages = {
                        "invalid_query_payload": "업비트 JWT 페이로드가 올바르지 않습니다.",
                        "jwt_verification": "업비트 JWT 검증에 실패했습니다.",
                        "expired_access_key": "업비트 API 키가 만료되었습니다.",
                        "nonce_used": "이미 사용된 nonce 입니다. 다시 시도하세요.",
                        "no_authorization_ip": "현재 IP가 업비트 API 키 허용 목록에 없습니다.",
                        "no_authorization_token": "업비트 인증 토큰이 누락되었습니다.",
                        "out_of_scope": "업비트 API 키 권한이 부족합니다. [자산조회] 권한을 확인하세요.",
                    }
                    rate_limit_messages = {
                        418: "업비트 요청 제한에 걸렸습니다. 잠시 후 다시 시도하세요.",
                        429: "업비트 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
                    }

                    message = auth_messages.get(error_name)
                    if message is None:
                        message = rate_limit_messages.get(response.status_code)
                    if message is None and error_name and error_message:
                        message = f"업비트 API 오류 ({error_name}): {error_message}"
                    if message is None:
                        message = f"업비트 API 요청이 실패했습니다. (HTTP {response.status_code})"

                    raise UpbitAPIError(
                        message,
                        status_code=response.status_code,
                        error_name=error_name,
                    ) from e

                raise UpbitAPIError("업비트 API 요청이 실패했습니다.") from e
            except requests.Timeout as e:
                raise UpbitAPIError("업비트 API 요청이 시간 초과되었습니다.") from e
            except requests.RequestException as e:
                raise UpbitAPIError(f"업비트 API 연결에 실패했습니다: {e}") from e

        raise UpbitAPIError("업비트 API 요청 재시도 한도를 초과했습니다.")

    def _get(self, path: str, params: Optional[dict] = None, auth: bool = False) -> dict | list:
        return self._request("GET", path, params=params, auth=auth)

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body=body, auth=True)

    def _delete(self, path: str, params: dict) -> dict:
        return self._request("DELETE", path, params=params, auth=True)

    # ── BaseExchange 구현 ────────────────────────────────────

    def get_current_price(self, symbol: str) -> Decimal:
        """
        현재가 조회.
        symbol 예: "KRW-BTC"
        """
        data = self._get("/v1/ticker", params={"markets": symbol})
        price = to_decimal(data[0]["trade_price"])
        logger.debug(f"현재가 조회 {symbol}: {price}")
        return price

    def get_recent_minute_closes(self, symbol: str, unit: int, count: int) -> list[Decimal]:
        """최근 완료된 분 캔들 종가 목록 조회."""
        if count <= 0:
            return []

        data = self._get(
            f"/v1/candles/minutes/{unit}",
            params={
                "market": symbol,
                "count": count + 1,
            },
        )
        now_utc = datetime.now(timezone.utc)
        closes: list[Decimal] = []
        for candle in data:
            candle_start = datetime.fromisoformat(candle["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
            if now_utc < candle_start + timedelta(minutes=unit):
                continue
            closes.append(to_decimal(candle["trade_price"]))
            if len(closes) >= count:
                break
        logger.debug(f"분 캔들 종가 조회 {symbol} unit={unit} count={count}: {closes}")
        return closes

    def get_balance(self) -> Decimal:
        """KRW 주문 가능 잔고 조회"""
        accounts = self._get("/v1/accounts", auth=True)
        for account in accounts:
            if account["currency"] == "KRW":
                balance = to_decimal(account["balance"])
                logger.debug(f"KRW 잔고: {format_decimal(balance)}")
                return balance
        logger.warning("KRW 잔고 없음 → 0 반환")
        return DECIMAL_ZERO

    def get_holdings(self, symbol: str) -> Decimal:
        """
        보유 수량 조회.
        symbol 예: "KRW-BTC" → currency="BTC" 로 조회
        """
        currency = symbol.split("-")[-1]
        accounts = self._get("/v1/accounts", auth=True)
        for account in accounts:
            if account["currency"] == currency:
                qty = to_decimal(account["balance"])
                logger.debug(f"{currency} 보유: {format_decimal(qty)}")
                return qty
        return DECIMAL_ZERO

    def get_open_order_ids(
        self,
        symbol: str,
        *,
        states: tuple[str, ...] | None = None,
        limit: int = 100,
    ) -> list[str]:
        params: dict[str, Any] = {
            "market": symbol,
            "limit": max(int(limit), 1),
            "order_by": "desc",
        }
        normalized_states = tuple(state for state in (states or ("wait", "watch")) if state)
        if len(normalized_states) == 1:
            params["state"] = normalized_states[0]
        elif normalized_states:
            params["states[]"] = list(normalized_states)

        result = self._get("/v1/orders/open", params=params, auth=True)
        if not isinstance(result, list):
            raise UpbitAPIError("업비트 미체결 주문 조회 응답 형식이 올바르지 않습니다.")

        order_ids = [
            order["uuid"]
            for order in result
            if isinstance(order, dict) and order.get("uuid")
        ]
        logger.debug(f"{symbol} 미체결 주문 조회: count={len(order_ids)}")
        return order_ids

    def get_minute_candle_closes(
        self,
        symbol: str,
        *,
        unit_minutes: int,
        count: int,
        to: datetime | None = None,
    ) -> list[Decimal]:
        """업비트 분 캔들 종가 목록을 최신순으로 반환한다."""
        params: dict[str, Any] = {
            "market": symbol,
            "count": count,
        }
        if to is not None:
            params["to"] = to.isoformat(timespec="seconds")

        data = self._get(f"/v1/candles/minutes/{unit_minutes}", params=params)
        closes = [to_decimal(candle["trade_price"]) for candle in data]
        logger.debug(
            f"{symbol} {unit_minutes}분 캔들 종가 조회: "
            f"count={count}, fetched={len(closes)}, to={params.get('to')}"
        )
        return closes

    def get_order_chance(self, symbol: str) -> dict:
        result = self._get("/v1/orders/chance", params={"market": symbol}, auth=True)
        if not isinstance(result, dict):
            raise UpbitAPIError("업비트 주문 가능 정보 응답 형식이 올바르지 않습니다.")
        return result

    def test_order_request(self, order: Order) -> dict:
        result = self._post("/v1/orders/test", self._build_order_body(order, include_identifier=False))
        if not isinstance(result, dict):
            raise UpbitAPIError("업비트 주문 테스트 응답 형식이 올바르지 않습니다.")
        return result

    def _ensure_order_identifier(self, order: Order) -> str:
        if order.identifier:
            return order.identifier
        order.identifier = f"upbit-{uuid.uuid4().hex}"
        return order.identifier

    def _build_order_body(
        self,
        order: Order,
        *,
        include_identifier: bool,
    ) -> dict[str, str]:
        if order.execution_type == OrderExecutionType.MARKET_BUY_BY_PRICE:
            if order.side != OrderSide.BUY:
                raise ValueError("시장가 매수 금액 주문은 BUY 에서만 사용할 수 있습니다.")
            body: dict[str, str] = {
                "market": order.symbol,
                "side": "bid",
                "price": format_decimal(order.required_krw),
                "ord_type": "price",
            }
        elif order.execution_type == OrderExecutionType.MARKET_SELL_BY_VOLUME:
            if order.side != OrderSide.SELL:
                raise ValueError("시장가 매도 수량 주문은 SELL 에서만 사용할 수 있습니다.")
            body = {
                "market": order.symbol,
                "side": "ask",
                "volume": format_decimal(order.quantity),
                "ord_type": "market",
            }
        else:
            body = {
                "market": order.symbol,
                "side": "bid" if order.side == OrderSide.BUY else "ask",
                "volume": format_decimal(order.quantity),
                "price": format_decimal(order.price),
                "ord_type": "limit",
            }

        if include_identifier and order.identifier:
            body["identifier"] = order.identifier
        return body

    def _supported_order_types(self, chance: dict, side: OrderSide) -> set[str]:
        market = chance.get("market", {})
        if not isinstance(market, dict):
            return set()
        key = "bid_types" if side == OrderSide.BUY else "ask_types"
        values = market.get(key) or market.get("order_types") or []
        if not isinstance(values, list):
            return set()
        return {str(value).strip().lower() for value in values}

    @staticmethod
    def _extract_min_total(chance: dict, *, side: OrderSide) -> Decimal | None:
        market = chance.get("market", {})
        if not isinstance(market, dict):
            return None

        side_key = "bid" if side == OrderSide.BUY else "ask"
        side_info = market.get(side_key)
        if not isinstance(side_info, dict):
            return None

        min_total = side_info.get("min_total")
        if min_total in (None, ""):
            return None
        return to_decimal(min_total)

    def _validate_order_with_chance(self, order: Order, chance: dict) -> None:
        if order.execution_type == OrderExecutionType.MARKET_BUY_BY_PRICE:
            required_order_type = "price"
        elif order.execution_type == OrderExecutionType.MARKET_SELL_BY_VOLUME:
            required_order_type = "market"
        else:
            required_order_type = "limit"
        supported_order_types = self._supported_order_types(chance, order.side)
        if supported_order_types and required_order_type not in supported_order_types:
            raise UpbitAPIError(
                f"업비트 주문 가능 정보가 현재 주문 유형을 지원하지 않습니다: "
                f"side={order.side.value} ord_type={required_order_type}"
            )

        market = chance.get("market", {})
        max_total = None
        if isinstance(market, dict) and market.get("max_total") not in (None, ""):
            max_total = to_decimal(market["max_total"])

        min_total = self._extract_min_total(chance, side=order.side)
        if order.side == OrderSide.BUY:
            bid_account = chance.get("bid_account", {})
            if isinstance(bid_account, dict) and bid_account.get("balance") not in (None, ""):
                available_balance = to_decimal(bid_account["balance"])
                if order.required_krw > available_balance:
                    raise UpbitAPIError(
                        f"orders/chance 기준 KRW 잔고가 부족합니다: "
                        f"required={format_decimal(order.required_krw)}, "
                        f"available={format_decimal(available_balance)}"
                    )

            if max_total is not None and max_total > DECIMAL_ZERO and order.required_krw > max_total:
                raise UpbitAPIError(
                    f"orders/chance 기준 최대 주문 가능 금액을 초과했습니다: "
                    f"required={format_decimal(order.required_krw)}, max_total={format_decimal(max_total)}"
                )
            if min_total is not None and min_total > DECIMAL_ZERO and order.required_krw < min_total:
                raise UpbitAPIError(
                    f"orders/chance 기준 최소 주문 금액보다 작습니다: "
                    f"required={format_decimal(order.required_krw)}, min_total={format_decimal(min_total)}"
                )
            return

        ask_account = chance.get("ask_account", {})
        if isinstance(ask_account, dict) and ask_account.get("balance") not in (None, ""):
            available_quantity = to_decimal(ask_account["balance"])
            if order.quantity > available_quantity:
                raise UpbitAPIError(
                    f"orders/chance 기준 보유 수량이 부족합니다: "
                    f"required={format_decimal(order.quantity)}, "
                    f"available={format_decimal(available_quantity)}"
                )

        if min_total is not None and min_total > DECIMAL_ZERO:
            order_total = order.price * order.quantity
            if order_total < min_total:
                raise UpbitAPIError(
                    f"orders/chance 기준 최소 주문 금액보다 작습니다: "
                    f"required={format_decimal(order_total)}, min_total={format_decimal(min_total)}"
                )

    def place_order(self, order: Order) -> Optional[str]:
        """
        주문 실행.
        성공 시 업비트 uuid 반환, 실패 시 None.
        """
        self._ensure_order_identifier(order)
        side = "bid" if order.side == OrderSide.BUY else "ask"
        body = self._build_order_body(order, include_identifier=True)
        if order.execution_type == OrderExecutionType.MARKET_BUY_BY_PRICE:
            log_message = (
                f"주문 접수 [{side}] {order.symbol} 시장가 {format_decimal(order.required_krw)} KRW "
                f"(trigger={format_decimal(order.price)}, qty={format_decimal(order.quantity)}, "
                f"identifier={order.identifier})"
            )
        elif order.execution_type == OrderExecutionType.MARKET_SELL_BY_VOLUME:
            log_message = (
                f"주문 접수 [{side}] {order.symbol} 시장가 qty={format_decimal(order.quantity)} "
                f"(trigger={format_decimal(order.price)}, identifier={order.identifier})"
            )
        else:
            log_message = (
                f"주문 접수 [{side}] {order.symbol} "
                f"{format_decimal(order.price)} x {format_decimal(order.quantity)} "
                f"(identifier={order.identifier})"
            )
        try:
            chance = self.get_order_chance(order.symbol)
            self._validate_order_with_chance(order, chance)
            self.test_order_request(order)
            result = self._post("/v1/orders", body)
            order_id = result.get("uuid")
            logger.info(f"{log_message} → uuid={order_id}")
            return order_id
        except UpbitAPIError as e:
            logger.error(f"주문 실패: {e}")
            return None

    def get_order_status(self, order_id: str) -> OrderStatus:
        """개별 주문 상태 조회."""
        result = self._get("/v1/order", params={"uuid": order_id}, auth=True)
        return OrderStatus(
            uuid=result["uuid"],
            state=result["state"],
            executed_volume=to_decimal(result.get("executed_volume", "0")),
            remaining_volume=to_decimal(result.get("remaining_volume", "0")),
        )

    def cancel_order(self, order_id: str) -> bool:
        """주문 취소. 성공 시 True."""
        try:
            self._delete("/v1/order", {"uuid": order_id})
            logger.info(f"주문 취소 완료: {order_id}")
            return True
        except UpbitAPIError as e:
            logger.error(f"주문 취소 실패: {e}")
            return False
