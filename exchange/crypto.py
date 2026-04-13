"""
업비트 거래소 구현
API 문서: https://docs.upbit.com/
인증: JWT (Access Key + Secret Key, HMAC SHA512 query hash)
"""
import hashlib
import uuid
from typing import Optional
from urllib.parse import urlencode

import jwt
import requests

from core.models import Order, OrderSide
from exchange.base import BaseExchange
from utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.upbit.com"


class CryptoExchange(BaseExchange):

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        logger.info("업비트 거래소 초기화")

    # ── 인증 헬퍼 ────────────────────────────────────────────

    def _auth_header(self, query: Optional[dict] = None) -> dict:
        """JWT 인증 헤더 생성. query 파라미터가 있으면 SHA512 해시 포함."""
        payload = {
            "access_key": self.api_key,
            "nonce": str(uuid.uuid4()),
        }
        if query:
            query_string = urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload["query_hash"] = m.hexdigest()
            payload["query_hash_alg"] = "SHA512"

        token = jwt.encode(payload, self.api_secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: Optional[dict] = None, auth: bool = False) -> dict | list:
        headers = self._auth_header(params) if auth else {}
        resp = requests.get(f"{BASE_URL}{path}", params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        headers = self._auth_header(body)
        resp = requests.post(f"{BASE_URL}{path}", json=body, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str, params: dict) -> dict:
        headers = self._auth_header(params)
        resp = requests.delete(f"{BASE_URL}{path}", params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── BaseExchange 구현 ────────────────────────────────────

    def get_current_price(self, symbol: str) -> float:
        """
        현재가 조회.
        symbol 예: "KRW-BTC"
        """
        data = self._get("/v1/ticker", params={"markets": symbol})
        price = float(data[0]["trade_price"])
        logger.debug(f"현재가 조회 {symbol}: {price}")
        return price

    def get_balance(self) -> float:
        """KRW 주문 가능 잔고 조회"""
        accounts = self._get("/v1/accounts", auth=True)
        for account in accounts:
            if account["currency"] == "KRW":
                balance = float(account["balance"])
                logger.debug(f"KRW 잔고: {balance:,.0f}")
                return balance
        logger.warning("KRW 잔고 없음 → 0 반환")
        return 0.0

    def get_holdings(self, symbol: str) -> int:
        """
        보유 수량 조회.
        symbol 예: "KRW-BTC" → currency="BTC" 로 조회
        """
        currency = symbol.split("-")[-1]
        accounts = self._get("/v1/accounts", auth=True)
        for account in accounts:
            if account["currency"] == currency:
                qty = int(float(account["balance"]))
                logger.debug(f"{currency} 보유: {qty}")
                return qty
        return 0

    def place_order(self, order: Order) -> Optional[str]:
        """
        지정가 주문 실행.
        성공 시 업비트 uuid 반환, 실패 시 None.
        """
        side = "bid" if order.side == OrderSide.BUY else "ask"
        body = {
            "market": order.symbol,
            "side": side,
            "volume": str(order.quantity),
            "price": str(order.price),
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
        except requests.HTTPError as e:
            logger.error(f"주문 실패: {e.response.text}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """주문 취소. 성공 시 True."""
        try:
            self._delete("/v1/order", {"uuid": order_id})
            logger.info(f"주문 취소 완료: {order_id}")
            return True
        except requests.HTTPError as e:
            logger.error(f"주문 취소 실패: {e.response.text}")
            return False
