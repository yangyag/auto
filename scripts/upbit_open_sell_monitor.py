#!/usr/bin/env python3
"""Upbit open sell order monitor (read-only).

Shows each open sell order on the order book matched against its
bot-slot buy cost so the user can see which positions are
profitable vs underwater at the current market price.

Upbit's average-buy-price view smooths everything into one number;
this script shows per-slot reality.
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
from scripts.upbit_actual_assets import _prepare_valid_orders, get_with_retry

try:
    from jwt.warnings import InsecureKeyLengthWarning
except ImportError:
    InsecureKeyLengthWarning = Warning

warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
warnings.filterwarnings(
    "ignore",
    message=r"The HMAC key is .* below the minimum recommended length of 64 bytes for SHA512\\.",
    category=Warning,
)

DEFAULT_LOOKBACK_DAYS = 120


def _compile_slot_pattern(bot_key: str):
    import re
    return re.compile(rf'^{re.escape(bot_key)}-(buy|sell)-(\d+)-')


def _compile_reset_pattern(bot_key: str):
    import re
    return re.compile(rf'^{re.escape(bot_key)}-reset-sell-')


def _extract_slot_with_key(identifier: str | None, pattern) -> int | None:
    if not identifier:
        return None
    m = pattern.match(identifier)
    if not m:
        return None
    return int(m.group(2))


@dataclass(frozen=True)
class OpenSellRow:
    slot_index: int | None
    qty: Decimal
    buy_unit_cost: Decimal | None
    sell_limit_price: Decimal
    current_price: Decimal
    unrealized_at_current: Decimal | None
    gap_to_fill_krw: Decimal


def fetch_open_orders(api_key: str, api_secret: str, market: str) -> list[dict]:
    all_orders: list[dict] = []
    for state in ("wait", "watch"):
        params: dict = {
            "market": market,
            "state": state,
            "limit": 100,
            "order_by": "desc",
        }
        data = get_with_retry(api_key, api_secret, "/v1/orders/open", params)
        if not isinstance(data, list):
            raise RuntimeError(f"open orders 응답이 list가 아님: {type(data)}")
        all_orders.extend(data)
    seen: set[str] = set()
    deduped: list[dict] = []
    for order in all_orders:
        uid = order.get("uuid", "")
        if uid and uid not in seen:
            seen.add(uid)
            deduped.append(order)
    return deduped


def match_open_sells_to_buy_lots(
    open_orders: list[dict],
    queues_by_slot: dict[int, list[dict]],
    slot_pattern,
) -> dict[str, Decimal | None]:
    """Return mapping from order_uuid -> buy_unit_cost (or None if unmatched)."""
    result: dict[str, Decimal | None] = {}
    for order in open_orders:
        uid = order.get("uuid", "")
        if not uid:
            continue
        slot = _extract_slot_with_key(order.get("identifier"), slot_pattern)
        if slot is None:
            result[uid] = None
            continue
        queue = queues_by_slot.get(slot)
        if not queue:
            result[uid] = None
            continue
        result[uid] = pnl._to_decimal(queue[0]["unit_cost"])
    return result


def build_open_sell_rows(
    open_orders: list[dict],
    buy_cost_map: dict[str, Decimal | None],
    current_price: Decimal,
    slot_pattern,
) -> list[OpenSellRow]:
    """Convert raw orders + matched costs into display rows."""
    rows: list[OpenSellRow] = []

    for order in open_orders:
        qty = pnl._to_decimal(order.get("remaining_volume") or order.get("volume", "0"))
        if qty <= Decimal("0"):
            continue
        sell_limit = pnl._to_decimal(order.get("price", "0"))
        uid = order.get("uuid", "")
        buy_cost = buy_cost_map.get(uid)

        unrealized = None
        if buy_cost is not None:
            unrealized = (current_price - buy_cost) * qty

        gap = sell_limit - current_price
        slot = _extract_slot_with_key(order.get("identifier"), slot_pattern)

        rows.append(OpenSellRow(
            slot_index=slot,
            qty=qty,
            buy_unit_cost=buy_cost,
            sell_limit_price=sell_limit,
            current_price=current_price,
            unrealized_at_current=unrealized,
            gap_to_fill_krw=gap,
        ))

    return rows


def fetch_remaining_buy_queues(
    api_key: str,
    api_secret: str,
    market: str,
    lookback_days: int,
    reset_sell_uuids: set[str],
    bot_key: str,
    slot_pattern,
) -> dict[int, list[dict]]:
    """Fetch closed orders, run FIFO matching, return queues_by_slot."""
    now_kst = datetime.now(pnl.KST)
    start_dt = now_kst - timedelta(days=lookback_days)

    original_get = pnl._get
    original_slot_pattern = pnl.SLOT_PATTERN
    original_reset_pattern = pnl.RESET_SELL_PATTERN
    pnl._get = get_with_retry
    pnl.SLOT_PATTERN = slot_pattern
    pnl.RESET_SELL_PATTERN = _compile_reset_pattern(bot_key)
    try:
        raw_orders = pnl.fetch_closed_orders(api_key, api_secret, market, start_dt, now_kst)
        valid_orders = _prepare_valid_orders(api_key, api_secret, raw_orders)
        sorted_orders = sorted(valid_orders, key=lambda o: (o["_time_key"], o["uuid"]))
        (
            _realized_lines,
            _unmatched_lines,
            _unparseable_buys,
            _unparseable_sells,
            queues_by_slot,
            _reset_residuals,
        ) = pnl.run_fifo(sorted_orders, reset_sell_uuids)
    finally:
        pnl._get = original_get
        pnl.SLOT_PATTERN = original_slot_pattern
        pnl.RESET_SELL_PATTERN = original_reset_pattern

    return queues_by_slot


def _fmt_krw(value: Decimal) -> str:
    return f"{int(value.quantize(Decimal('1'))):,}"


def _fmt_asset_qty(value: Decimal) -> str:
    return f"{value:.8f}"


def _fmt_btc(value: Decimal) -> str:
    return _fmt_asset_qty(value)


def _fmt_pnl(value: Decimal | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else ""
    return f"{sign}{_fmt_krw(value)}"


def print_open_sell_summary(
    rows: list[OpenSellRow],
    market: str,
    current_price: Decimal,
    lookback_days: int,
) -> None:
    now_kst = datetime.now(pnl.KST).strftime("%Y-%m-%d %H:%M KST")
    base_currency = pnl.market_base_currency(market)

    print("=== 매도 대기 주문 현황 ===")
    print(f"마켓: {market} | 현재가: {_fmt_krw(current_price)} KRW | 조회시각: {now_kst}")
    print()

    if not rows:
        print("미체결 매도 주문이 없습니다.")
        print()
        return

    header = (
        f"{'slot':>5}  {f'qty({base_currency})':>12}  {'매수원가':>14}  "
        f"{'매도지정가':>14}  {'현재가':>14}  {'미실현손익':>14}  도달까지"
    )
    print(header)
    print("-" * len(header))

    profit_count = 0
    loss_count = 0
    total_unrealized = Decimal("0")

    for row in rows:
        slot_str = str(row.slot_index) if row.slot_index is not None else "-"
        buy_str = _fmt_krw(row.buy_unit_cost) if row.buy_unit_cost is not None else "-"
        sell_str = _fmt_krw(row.sell_limit_price)
        cur_str = _fmt_krw(row.current_price)
        pnl_str = _fmt_pnl(row.unrealized_at_current)

        gap = row.gap_to_fill_krw
        if gap > 0:
            gap_str = f"{_fmt_krw(gap)} 남음"
        elif gap == 0:
            gap_str = "근접"
        else:
            gap_str = f"즉시체결 가능 ({_fmt_krw(abs(gap))})"

        print(
            f"{slot_str:>5}  {_fmt_asset_qty(row.qty):>12}  {buy_str:>14}  "
            f"{sell_str:>14}  {cur_str:>14}  {pnl_str:>14}  {gap_str}"
        )

        if row.unrealized_at_current is not None:
            total_unrealized += row.unrealized_at_current
            if row.unrealized_at_current >= 0:
                profit_count += 1
            else:
                loss_count += 1

    print()
    total_pnl_str = _fmt_pnl(total_unrealized)
    print(
        f"합계: {len(rows)}개 중 {profit_count}개 수익권, "
        f"{loss_count}개 손실권 | 총 미실현 손익: {total_pnl_str} KRW"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/upbit_open_sell_monitor.py",
        description="현재 걸려있는 매도 대기 주문과 봇 슬롯 매수원가를 비교한다 (읽기 전용)",
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
            "매칭 안 되면 늘려서 재확인"
        ),
    )
    parser.add_argument(
        "--bot-key",
        default=None,
        help=(
            "identifier 에서 사용하는 bot key prefix. "
            f"기본값은 cfg.STATE_BOT_KEY ({cfg.STATE_BOT_KEY})"
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

    bot_key = args.bot_key or cfg.STATE_BOT_KEY
    slot_pattern = _compile_slot_pattern(bot_key)

    try:
        current_price_data = requests.get(
            f"{pnl.BASE_URL}/v1/ticker",
            params={"markets": args.market},
            timeout=10,
        )
        current_price_data.raise_for_status()
        ticker_list = current_price_data.json()
        current_price = pnl._to_decimal(ticker_list[0]["trade_price"])

        open_orders = fetch_open_orders(api_key, api_secret, args.market)
        time.sleep(pnl.RATE_LIMIT_SLEEP_SEC)

        queues_by_slot = fetch_remaining_buy_queues(
            api_key=api_key,
            api_secret=api_secret,
            market=args.market,
            lookback_days=args.lookback_days,
            reset_sell_uuids=set(args.reset_sell_uuid),
            bot_key=bot_key,
            slot_pattern=slot_pattern,
        )

        buy_cost_map = match_open_sells_to_buy_lots(open_orders, queues_by_slot, slot_pattern)
        rows = build_open_sell_rows(open_orders, buy_cost_map, current_price, slot_pattern)

    except Exception as exc:
        print(f"오류: 매도 대기 주문 조회 실패: {exc}", file=sys.stderr)
        return 1

    print_open_sell_summary(rows, args.market, current_price, args.lookback_days)

    matched = sum(1 for r in rows if r.buy_unit_cost is not None)
    unmatched = len(rows) - matched
    print()
    print(
        f"[진단] open_orders={len(open_orders)}  matched={matched}  "
        f"unmatched={unmatched}  lookback_days={args.lookback_days}"
    )

    if unmatched > 0:
        print(
            "일부 매도 주문의 매수원가를 찾지 못했습니다. "
            "수동 주문이거나 --lookback-days를 늘려 재확인하세요."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
