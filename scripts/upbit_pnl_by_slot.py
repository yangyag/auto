#!/usr/bin/env python3
"""슬롯(그리드)별 실현손익 분석 (설정 SYMBOL 기본, read-only).

`scripts/upbit_realized_pnl.py` 의 슬롯 1:1 FIFO 매칭 결과를 슬롯/매도 단위로
펼쳐서 "어떤 그리드(슬롯)를 팔아 생긴 실현손익인지" 를 보여준다.

매칭 로직은 복제하지 않고 정본 스크립트의 공용 함수를 그대로 재사용한다
(prepare_sorted_orders → run_fifo → group_realized_by_slot / realized_to_sell_lines).

사용법:
    .venv/bin/python scripts/upbit_pnl_by_slot.py [--period d|w|m|y]
        [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--market MARKET]
        [--reset-sell-uuid UUID] [--lookback DAYS]

기본값:
    옵션 없음 : 오늘 기준 최근 90일 합산
    --period  : d=오늘, w=이번주, m=이번달, y=이번년
    --from/to : 사용자가 직접 지정한 기간 1개 합산
    --market   : app.config.settings.SYMBOL
    --lookback : 30일 (default: DEFAULT_LOOKBACK_DAYS = 30)

정확도 주의:
    그리드 매수가 컬럼은 현재 PostgreSQL 그리드 상태 기준 참고가다. 리센터링
    이력이 있으면 과거 매도 당시의 슬롯 가격과 다를 수 있다. 실현손익 숫자
    자체는 실제 체결 FIFO 매칭 기반이라 정확하며 이 참고가에 영향받지 않는다.
"""
import argparse
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.config.settings as cfg
from scripts.upbit_realized_pnl import (
    DEFAULT_LOOKBACK_DAYS,
    KST,
    _fmt_asset_qty,
    _fmt_krw,
    default_market,
    fetch_closed_orders,
    group_realized_by_slot,
    market_base_currency,
    parse_period_preset,
    prepare_sorted_orders,
    realized_to_sell_lines,
    resolve_report_window,
    run_fifo,
)


# ── 그리드 매수가 (현재 그리드 기준 참고가) ─────────────────────

def load_grid_buy_prices() -> dict[int, Decimal]:
    """현재 PostgreSQL 그리드 스냅샷에서 {slot index: buy_price} 매핑을 만든다.

    DB 미연결/빈 스냅샷/예외 시 빈 dict 를 반환해 호출 측이 컬럼을 '-' 로
    두고 정상 진행하도록 한다 (참고가일 뿐이라 분석 자체를 막지 않는다).
    """
    try:
        from app.api.services.grid_service import load_grid_snapshot

        snapshot = load_grid_snapshot()
        return {row.index: row.buy_price for row in snapshot.rows}
    except Exception:
        return {}


# ── 출력 ─────────────────────────────────────────────────────

SLOT_PNL_TITLE = "[ 슬롯별 실현손익 ]"
SELL_DETAIL_TITLE = "[ 매도별 상세 ]"


def _fmt_grid_buy_price(grid_buy_prices: dict[int, Decimal], slot) -> str:
    """슬롯의 그리드 매수가(참고가)를 포맷. 미상이면 '-'."""
    if slot is None:
        return "-"
    price = grid_buy_prices.get(slot)
    if price is None:
        return "-"
    return _fmt_krw(price)


def print_slot_pnl_section(
    slot_buckets: list[dict],
    grid_buy_prices: dict[int, Decimal],
    base_currency: str,
) -> None:
    """슬롯별 실현손익 집계 섹션 출력 (합계행 포함)."""
    print(SLOT_PNL_TITLE)
    header = (
        f"{'슬롯':>5} {'그리드매수가(참고)':>20} {'매도주문수':>9}"
        f" {'실현손익(KRW)':>18} {f'매도수량({base_currency})':>18}"
    )
    print(header)
    print("-" * len(header))

    if not slot_buckets:
        print("  (실현손익 없음)")
        return

    total_pnl = Decimal("0")
    total_qty = Decimal("0")
    total_orders = 0
    for bucket in slot_buckets:
        slot = bucket["slot"]
        slot_label = "-" if slot is None else str(slot)
        total_pnl += bucket["realized_pnl_krw"]
        total_qty += bucket["matched_qty"]
        total_orders += bucket["order_count"]
        print(
            f"{slot_label:>5} {_fmt_grid_buy_price(grid_buy_prices, slot):>20}"
            f" {bucket['order_count']:>9}"
            f" {_fmt_krw(bucket['realized_pnl_krw']):>18}"
            f" {_fmt_asset_qty(bucket['matched_qty']):>18}"
        )

    print("-" * len(header))
    print(
        f"{'합계':>5} {'-':>20} {total_orders:>9}"
        f" {_fmt_krw(total_pnl):>18} {_fmt_asset_qty(total_qty):>18}"
    )


def print_sell_detail_section(
    sell_lines: list[dict],
    base_currency: str,
) -> None:
    """매도별 상세 섹션 출력 (체결시각 오름차순)."""
    print(SELL_DETAIL_TITLE)
    header = (
        f"{'체결시각(KST)':<25} {'슬롯':>5} {f'매도수량({base_currency})':>18}"
        f" {'실현손익(KRW)':>18} {'sell_uuid':<36}"
    )
    print(header)
    print("-" * len(header))

    if not sell_lines:
        print("  (매도 내역 없음)")
        return

    for line in sell_lines:
        slot = line["slot"]
        slot_label = "-" if slot is None else str(slot)
        t = line["time_key"].isoformat(timespec="seconds")
        print(
            f"{t:<25} {slot_label:>5}"
            f" {_fmt_asset_qty(line['matched_qty']):>18}"
            f" {_fmt_krw(line['realized_pnl']):>18} {line['sell_uuid']:<36}"
        )


# ── argparse ─────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 scripts/upbit_pnl_by_slot.py",
        description="업비트 체결 주문 기반 슬롯(그리드)별 실현손익 분석 (읽기 전용)",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        metavar="YYYY-MM-DD",
        help="직접 조회 시작일 (--period 와 같이 사용 불가)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        metavar="YYYY-MM-DD",
        help="직접 조회 종료일 (기본: 오늘, --period 와 같이 사용 불가)",
    )
    parser.add_argument(
        "--period",
        type=parse_period_preset,
        metavar="{d,w,m,y}",
        help="기간 프리셋: d=오늘, w=이번주, m=이번달, y=이번년 (옵션 없으면 최근 90일 합산)",
    )
    parser.add_argument(
        "--market",
        default=default_market(),
        help=f"업비트 마켓 코드 (기본: {default_market()})",
    )
    parser.add_argument(
        "--reset-sell-uuid",
        action="append",
        default=[],
        help="과거 reset 전량 매도 주문 uuid (반복 지정 가능)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        metavar="DAYS",
        help=f"표시 시작일 이전 매칭용 closed orders 추가 조회 기간, 단위: 일 (기본: {DEFAULT_LOOKBACK_DAYS})",
    )
    return parser


# ── 메인 ─────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    today_kst = datetime.now(KST).date()
    try:
        report_window = resolve_report_window(args, today_kst)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    user_from_date = report_window.from_date
    user_to_date = report_window.to_date

    # fetch 범위: lookback margin 포함 (과거 BUY 매칭용)
    fetch_from_date = user_from_date - timedelta(days=args.lookback)
    fetch_start_dt = datetime(fetch_from_date.year, fetch_from_date.month, fetch_from_date.day,
                              0, 0, 0, tzinfo=KST)
    display_end_dt = datetime(user_to_date.year, user_to_date.month, user_to_date.day,
                              23, 59, 59, tzinfo=KST)
    display_start_dt = datetime(user_from_date.year, user_from_date.month, user_from_date.day,
                                0, 0, 0, tzinfo=KST)

    api_key = cfg.API_KEY
    api_secret = cfg.API_SECRET

    if not api_key or not api_secret:
        print("오류: API_KEY 또는 API_SECRET 이 설정되지 않았습니다.", file=sys.stderr)
        return 1

    if not cfg.STATE_BOT_KEY:
        print("오류: STATE_BOT_KEY 가 빈 문자열입니다. .env 또는 환경변수를 확인하세요.", file=sys.stderr)
        return 1

    market = args.market
    base_currency = market_base_currency(market)

    print(f"조회 범위: {user_from_date} ~ {user_to_date}  마켓: {market}  모드: {report_window.mode_label}")
    if args.lookback > 0:
        print(f"매칭용 lookback: {args.lookback}일 (fetch: {fetch_from_date} ~ {user_to_date})")
    print("closed orders 수집 중...")

    # 1단계: closed orders 수집 (fetch 범위로 확장해서 과거 BUY 포함)
    raw_orders = fetch_closed_orders(api_key, api_secret, market, fetch_start_dt, display_end_dt)
    print(f"  수집 완료: {len(raw_orders)}건 (cancel+done 포함)")

    # 2~3단계: 체결 0건 필터, 수치 검증, time_key 결정, 정렬
    sorted_orders = prepare_sorted_orders(raw_orders, api_key, api_secret)

    # 4단계: 슬롯 1:1 매칭
    (
        realized_lines,
        _unmatched_lines,
        _unparseable_buys,
        _unparseable_sells,
        _queues_by_slot,
        _reset_residuals,
    ) = run_fifo(sorted_orders, set(args.reset_sell_uuid))

    # 5단계: 표시용 윈도우 필터 (SELL 의 _time_key 가 display 범위 내인 것만)
    display_realized_lines = [
        x for x in realized_lines
        if display_start_dt <= x["time_key"] <= display_end_dt
    ]

    # 6단계: 슬롯/매도 단위 집계
    slot_buckets = group_realized_by_slot(display_realized_lines)
    sell_lines = realized_to_sell_lines(display_realized_lines)

    # 7단계: 그리드 매수가(현재 그리드 기준 참고가) 매핑
    grid_buy_prices = load_grid_buy_prices()

    # 8단계: 출력
    print()
    print("=" * 80)
    print("주의: '그리드매수가'는 현재 그리드 기준 참고가입니다 (리센터링 시 과거와 다를 수 있음).")
    print()
    print_slot_pnl_section(slot_buckets, grid_buy_prices, base_currency)
    print()
    print_sell_detail_section(sell_lines, base_currency)
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
