"""
업비트 거래소 구현
API 문서: https://docs.upbit.com/
인증: JWT (Access Key + Secret Key, HMAC SHA512 query hash)
"""
import hashlib
import uuid
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import unquote, urlencode

import jwt
import requests

from core.models import Order, OrderSide, OrderStatus
from exchange.base import BaseExchange
from utils.decimal_utils import DECIMAL_ZERO, format_decimal, to_decimal
from utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.upbit.com"


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

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        auth: bool = False,
    ) -> dict | list:
        headers = {}
        if auth:
            headers.update(self._auth_header(body if body is not None else params))
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"

        try:
            resp = requests.request(
                method,
                f"{BASE_URL}{path}",
                params=params,
                json=body,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            response = e.response
            error_name = None
            error_message = None

            if response is not None:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                error_name = error.get("name")
                error_message = error.get("message")

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

    def place_order(self, order: Order) -> Optional[str]:
        """
        지정가 주문 실행.
        성공 시 업비트 uuid 반환, 실패 시 None.
        """
        side = "bid" if order.side == OrderSide.BUY else "ask"
        body = {
            "market": order.symbol,
            "side": side,
            "volume": format_decimal(order.quantity),
            "price": format_decimal(order.price),
            "ord_type": "limit",
        }
        try:
            result = self._post("/v1/orders", body)
            order_id = result.get("uuid")
            logger.info(
                f"주문 접수 [{side}] {order.symbol} "
                f"{order.price} x {order.quantity} → uuid={order_id}"
            )
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
