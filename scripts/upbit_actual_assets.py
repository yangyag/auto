#!/usr/bin/env python3
"""Upbit account and bot slot ledger asset summary (read-only).

This script separates Upbit's account-wide avg_buy_price basis from the bot's
slot-level residual BUY lot basis. The latter is the useful number when checking
grid-bot book value while BTC is still held.
"""
import argparse
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.config.settings as cfg
from scripts import upbit_realized_pnl as pnl

try:
    from jwt.warnings import InsecureKeyLengthWarning
except ImportError:
    InsecureKeyLengthWarning = Warning

warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
warnings.filterwarnings(
    "ignore",
    message=r"The HMAC key is .* below the minimum recommended length of 64 bytes for SHA512\.",
    category=Warning,
)

DEFAULT_LOOKBACK_DAYS = 120
QTY_TOLERANCE = Decimal("0.00000001")
RATE_LIMIT_RETRY_ATTEMPTS = 5
RATE_LIMIT_RETRY_BASE_SECONDS = 0.5


@dataclass(frozen=True)
class RemainingLotSummary:
    quantity: Decimal
    cost_krw: Decimal
    buy_count: int


@dataclass(frozen=True)
class ActualAssetSummary:
    market: str
    quote_currency: str
    base_currency: str
    current_price: Decimal
    krw_available: Decimal
    krw_locked: Decimal
    krw_total: Decimal
    base_available: Decimal
    base_locked: Decimal
    base_total: Decimal
    market_value_krw: Decimal
    upbit_avg_buy_price: Decimal
    upbit_avg_cost_krw: Decimal
    bot_lot_qty: Decimal
    bot_lot_cost_krw: Decimal
    bot_lot_buy_count: int
    bot_book_total_krw: Decimal
    mark_to_market_total_krw: Decimal
    avg_cost_gap_krw: Decimal
    quantity_gap: Decimal
    quantity_matches: bool


def _to_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _split_market(market: str) -> tuple[str, str]:
    if "-" not in market:
        raise ValueError(f"마켓 코드는 QUOTE-BASE 형식이어야 합니다: {market}")
    quote, base = market.split("-", 1)
    return quote.upper(), base.upper()


def _account_by_currency(accounts: list[dict], currency: str) -> dict:
    for account in accounts:
        if str(account.get("currency", "")).upper() == currency.upper():
            return account
    return {"currency": currency, "balance": "0", "locked": "0", "avg_buy_price": "0"}


def summarize_remaining_lots(queues_by_slot: dict[int, list[dict]]) -> RemainingLotSummary:
    quantity = Decimal("0")
    cost_krw = Decimal("0")
    buy_count = 0

    for entries in queues_by_slot.values():
        for entry in entries:
            qty = _to_decimal(entry["qty"])
            if qty <= Decimal("0"):
                continue
            quantity += qty
            cost_krw += qty * _to_decimal(entry["unit_cost"])
            buy_count += 1

    return RemainingLotSummary(quantity=quantity, cost_krw=cost_krw, buy_count=buy_count)


def build_actual_asset_summary(
    *,
    accounts: list[dict],
    market: str,
    current_price: Decimal,
    queues_by_slot: dict[int, list[dict]],
) -> ActualAssetSummary:
    quote_currency, base_currency = _split_market(market)
    quote_account = _account_by_currency(accounts, quote_currency)
    base_account = _account_by_currency(accounts, base_currency)

    quote_available = _to_decimal(quote_account.get("balance"))
    quote_locked = _to_decimal(quote_account.get("locked"))
    quote_total = quote_available + quote_locked

    base_available = _to_decimal(base_account.get("balance"))
    base_locked = _to_decimal(base_account.get("locked"))
    base_total = base_available + base_locked

    upbit_avg_buy_price = _to_decimal(base_account.get("avg_buy_price"))
    upbit_avg_cost_krw = base_total * upbit_avg_buy_price
    market_value_krw = base_total * current_price

    remaining_lots = summarize_remaining_lots(queues_by_slot)
    bot_book_total_krw = quote_total + remaining_lots.cost_krw
    mark_to_market_total_krw = quote_total + market_value_krw
    avg_cost_gap_krw = remaining_lots.cost_krw - upbit_avg_cost_krw
    quantity_gap = remaining_lots.quantity - base_total

    return ActualAssetSummary(
        market=market,
        quote_currency=quote_currency,
        base_currency=base_currency,
        current_price=current_price,
        krw_available=quote_available,
        krw_locked=quote_locked,
        krw_total=quote_total,
        base_available=base_available,
        base_locked=base_locked,
        base_total=base_total,
        market_value_krw=market_value_krw,
        upbit_avg_buy_price=upbit_avg_buy_price,
        upbit_avg_cost_krw=upbit_avg_cost_krw,
        bot_lot_qty=remaining_lots.quantity,
        bot_lot_cost_krw=remaining_lots.cost_krw,
        bot_lot_buy_count=remaining_lots.buy_count,
        bot_book_total_krw=bot_book_total_krw,
        mark_to_market_total_krw=mark_to_market_total_krw,
        avg_cost_gap_krw=avg_cost_gap_krw,
        quantity_gap=quantity_gap,
        quantity_matches=abs(quantity_gap) <= QTY_TOLERANCE,
    )


def _retry_delay(response, attempt: int) -> float:
    headers = getattr(response, "headers", {}) or {}
    retry_after_raw = None
    try:
        retry_after_raw = headers.get("Retry-After")
    except AttributeError:
        retry_after_raw = None

    if retry_after_raw:
        try:
            return min(float(retry_after_raw), 5.0)
        except (TypeError, ValueError):
            pass
    return RATE_LIMIT_RETRY_BASE_SECONDS * (2 ** attempt)


def get_with_retry(api_key: str, api_secret: str, path: str, params: dict) -> dict | list:
    """GET request with lightweight retry for Upbit rate-limit responses."""
    for attempt in range(RATE_LIMIT_RETRY_ATTEMPTS):
        headers = pnl._auth_header(api_key, api_secret, params if params else None)
        response = requests.get(
            pnl.BASE_URL + path,
            params=params,
            headers=headers,
            timeout=10,
        )
        if response.status_code in {418, 429} and attempt < RATE_LIMIT_RETRY_ATTEMPTS - 1:
            time.sleep(_retry_delay(response, attempt))
            continue
        response.raise_for_status()
        return response.json()

    raise RuntimeError("unreachable Upbit retry state")


def fetch_accounts(api_key: str, api_secret: str) -> list[dict]:
    data = get_with_retry(api_key, api_secret, "/v1/accounts", {})
    assert isinstance(data, list), f"accounts 응답이 list가 아님: {type(data)}"
    return data


def fetch_current_price(market: str) -> Decimal:
    resp = requests.get(
        f"{pnl.BASE_URL}/v1/ticker",
        params={"markets": market},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    assert isinstance(data, list) and data, f"ticker 응답이 비어 있거나 list가 아님: {type(data)}"
    return _to_decimal(data[0]["trade_price"])


def _prepare_valid_orders(api_key: str, api_secret: str, raw_orders: list[dict]) -> list[dict]:
    valid_orders: list[dict] = []

    for order in raw_orders:
        exec_vol = pnl._to_decimal(order.get("executed_volume", "0"))

        if exec_vol == Decimal("0"):
            if pnl.is_cancelled_tp_sell_candidate(order):
                order["executed_funds"] = order.get("executed_funds") or "0"
                order["paid_fee"] = order.get("paid_fee") or "0"
                order["_time_key"] = pnl.to_kst(order["created_at"])
                order["_cancelled_tp_sell_candidate"] = True
                valid_orders.append(order)
            continue

        if order.get("executed_funds") is None or order.get("paid_fee") is None:
            continue

        executed_funds = pnl._to_decimal(order["executed_funds"])
        if executed_funds == Decimal("0"):
            continue

        try:
            order["_time_key"] = pnl._extract_time_key(order, api_key, api_secret)
        except AssertionError:
            continue
        valid_orders.append(order)

    return valid_orders


def fetch_remaining_lot_queues(
    *,
    api_key: str,
    api_secret: str,
    market: str,
    lookback_days: int,
    reset_sell_uuids: set[str],
) -> tuple[dict[int, list[dict]], dict[str, int]]:
    now_kst = datetime.now(pnl.KST)
    start_dt = now_kst - timedelta(days=lookback_days)
    original_get = pnl._get
    pnl._get = get_with_retry
    try:
        raw_orders = pnl.fetch_closed_orders(api_key, api_secret, market, start_dt, now_kst)
        valid_orders = _prepare_valid_orders(api_key, api_secret, raw_orders)
    finally:
        pnl._get = original_get
    sorted_orders = sorted(valid_orders, key=lambda order: (order["_time_key"], order["uuid"]))

    (
        _realized_lines,
        unmatched_lines,
        unparseable_buys,
        unparseable_sells,
        queues_by_slot,
        reset_residuals,
    ) = pnl.run_fifo(sorted_orders, reset_sell_uuids)

    diagnostics = {
        "raw_orders": len(raw_orders),
        "valid_orders": sum(1 for order in valid_orders if not order.get("_cancelled_tp_sell_candidate")),
        "reset_candidates": sum(1 for order in valid_orders if order.get("_cancelled_tp_sell_candidate")),
        "unmatched": len(unmatched_lines),
        "unparseable_buys": len(unparseable_buys),
        "unparseable_sells": len(unparseable_sells),
        "reset_residuals": len(reset_residuals),
    }
    return queues_by_slot, diagnostics


def _fmt_krw(value: Decimal) -> str:
    return f"{int(value.quantize(Decimal('1'))):,}"


def _fmt_btc(value: Decimal) -> str:
    return f"{value:.8f}"


def print_summary(summary: ActualAssetSummary, *, lookback_days: int, diagnostics: dict[str, int]) -> None:
    print("=== Upbit 실제 자산 / 봇 슬롯 장부 요약 ===")
    print(f"마켓: {summary.market}")
    print(f"조회 lookback: {lookback_days}일")
    print(f"현재가: {_fmt_krw(summary.current_price)} KRW")
    print()
    print("[ Upbit 잔고 ]")
    print(f"주문 가능 {summary.quote_currency}: {_fmt_krw(summary.krw_available)} KRW")
    print(f"잠김 {summary.quote_currency}: {_fmt_krw(summary.krw_locked)} KRW")
    print(f"{summary.base_currency} 보유 수량: {_fmt_btc(summary.base_total)}")
    print(f"{summary.base_currency} 잠김 수량: {_fmt_btc(summary.base_locked)}")
    print()
    print("[ 원가 기준 비교 ]")
    print(f"Upbit 평균매수가: {_fmt_krw(summary.upbit_avg_buy_price)} KRW")
    print(f"Upbit 평균매수가 기준 원가: {_fmt_krw(summary.upbit_avg_cost_krw)} KRW")
    print(f"봇 슬롯별 잔여 매수원가: {_fmt_krw(summary.bot_lot_cost_krw)} KRW")
    print(f"평균매수가 착시 차이(봇-업비트): {_fmt_krw(summary.avg_cost_gap_krw)} KRW")
    print()
    print("[ 합계 ]")
    print(f"{summary.quote_currency} + 봇 슬롯별 잔여 매수원가: {_fmt_krw(summary.bot_book_total_krw)} KRW")
    print(f"{summary.quote_currency} + 현재 평가액: {_fmt_krw(summary.mark_to_market_total_krw)} KRW")
    print(f"{summary.base_currency} 현재 평가액: {_fmt_krw(summary.market_value_krw)} KRW")
    print()
    print("[ 검증 ]")
    print(f"잔여 BUY 큐 수량: {_fmt_btc(summary.bot_lot_qty)}")
    print(f"Upbit {summary.base_currency} 수량: {_fmt_btc(summary.base_total)}")
    print(f"수량 차이(큐-Upbit): {_fmt_btc(summary.quantity_gap)}")
    print(f"수량 일치: {'예' if summary.quantity_matches else '아니오'}")
    if not summary.quantity_matches:
        print("주의: lookback 이 부족하거나 수동/외부 주문이 섞였을 수 있습니다. --lookback-days 값을 늘려 재확인하세요.")
    print()
    print("[ 주문 매칭 진단 ]")
    print(
        "raw_orders={raw_orders} valid_orders={valid_orders} reset_candidates={reset_candidates} "
        "unmatched={unmatched} unparseable_buys={unparseable_buys} "
        "unparseable_sells={unparseable_sells} reset_residuals={reset_residuals}".format(**diagnostics)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 scripts/upbit_actual_assets.py",
        description="Upbit 잔고와 봇 슬롯별 잔여 BUY 원가를 함께 조회한다 (읽기 전용)",
    )
    parser.add_argument(
        "--market",
        default=pnl.DEFAULT_MARKET,
        help=f"업비트 마켓 코드 (기본: {pnl.DEFAULT_MARKET})",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=(
            f"잔여 BUY 큐 계산용 주문 조회 기간. 기본 {DEFAULT_LOOKBACK_DAYS}일이며, "
            "수량 불일치가 날 때만 늘려서 사용한다."
        ),
    )
    parser.add_argument(
        "--reset-sell-uuid",
        action="append",
        default=[],
        help="과거 reset 시장가 SELL uuid를 수동 지정할 때 사용 (반복 가능)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback_days <= 0:
        print("오류: --lookback-days 는 1 이상이어야 합니다.", file=sys.stderr)
        return 1

    api_key = cfg.API_KEY
    api_secret = cfg.API_SECRET
    if not api_key or not api_secret:
        print("오류: UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 환경변수를 먼저 설정하세요.", file=sys.stderr)
        return 1

    try:
        accounts = fetch_accounts(api_key, api_secret)
        time.sleep(pnl.RATE_LIMIT_SLEEP_SEC)
        current_price = fetch_current_price(args.market)
        queues_by_slot, diagnostics = fetch_remaining_lot_queues(
            api_key=api_key,
            api_secret=api_secret,
            market=args.market,
            lookback_days=args.lookback_days,
            reset_sell_uuids=set(args.reset_sell_uuid),
        )
        summary = build_actual_asset_summary(
            accounts=accounts,
            market=args.market,
            current_price=current_price,
            queues_by_slot=queues_by_slot,
        )
    except Exception as exc:
        print(f"오류: 실제 자산 조회 실패: {exc}", file=sys.stderr)
        return 1

    print_summary(summary, lookback_days=args.lookback_days, diagnostics=diagnostics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
