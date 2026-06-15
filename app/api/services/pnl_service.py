from __future__ import annotations

from argparse import Namespace
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

import app.config.settings as cfg
from app.api.schemas.pnl import (
    PnlBucket,
    PnlBySlotResponse,
    RealizedPnlResponse,
    SellLine,
    SlotPnlBucket,
)
from scripts import upbit_realized_pnl as pnl


def _normalize_period(period: str) -> str:
    if period == "all":
        return "all"
    return pnl.parse_period_preset(period)


def _window_args(period: str) -> Namespace:
    if period == "all":
        return Namespace(
            period=None,
            from_date=None,
            to_date=None,
            market=pnl.DEFAULT_MARKET,
            reset_sell_uuid=[],
            lookback=pnl.DEFAULT_LOOKBACK_DAYS,
        )
    return Namespace(
        period=period,
        from_date=None,
        to_date=None,
        market=pnl.DEFAULT_MARKET,
        reset_sell_uuid=[],
        lookback=pnl.DEFAULT_LOOKBACK_DAYS,
    )


def calculate_realized_pnl(*, period: str) -> RealizedPnlResponse:
    if not cfg.API_KEY or not cfg.API_SECRET:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY is not configured")

    normalized_period = _normalize_period(period)
    args = _window_args(normalized_period)
    today_kst = datetime.now(pnl.KST).date()
    report_window = pnl.resolve_report_window(args, today_kst)
    user_from_date = report_window.from_date
    user_to_date = report_window.to_date
    fetch_from_date = user_from_date - timedelta(days=args.lookback)

    fetch_start_dt = datetime(
        fetch_from_date.year,
        fetch_from_date.month,
        fetch_from_date.day,
        0,
        0,
        0,
        tzinfo=pnl.KST,
    )
    display_start_dt = datetime(
        user_from_date.year,
        user_from_date.month,
        user_from_date.day,
        0,
        0,
        0,
        tzinfo=pnl.KST,
    )
    display_end_dt = datetime(
        user_to_date.year,
        user_to_date.month,
        user_to_date.day,
        23,
        59,
        59,
        tzinfo=pnl.KST,
    )

    pnl._anomaly_list.clear()
    raw_orders = pnl.fetch_closed_orders(
        cfg.API_KEY,
        cfg.API_SECRET,
        args.market,
        fetch_start_dt,
        display_end_dt,
    )

    sorted_orders = pnl.prepare_sorted_orders(raw_orders, cfg.API_KEY, cfg.API_SECRET)
    realized_lines, *_ = pnl.run_fifo(sorted_orders, set(args.reset_sell_uuid))
    display_realized_lines = [
        item for item in realized_lines if display_start_dt <= item["time_key"] <= display_end_dt
    ]

    group_period = "all" if normalized_period == "all" else pnl.PERIOD_PRESET_TO_GROUP[normalized_period]
    groups: dict[str, list[dict]] = defaultdict(list)
    for line in display_realized_lines:
        groups[pnl.group_key(line["time_key"], group_period)].append(line)

    buckets: list[PnlBucket] = []
    for key in sorted(groups.keys()):
        items = groups[key]
        sell_orders = {
            item["sell_uuid"]: int(item.get("sell_trade_count", 1))
            for item in items
        }
        buckets.append(
            PnlBucket(
                key=key,
                order_count=len(sell_orders),
                trade_count=sum(sell_orders.values()),
                realized_pnl_krw=sum((item["realized_pnl"] for item in items), Decimal("0")),
                matched_qty_btc=sum((item["matched_qty"] for item in items), Decimal("0")),
            )
        )

    if not buckets:
        buckets.append(
            PnlBucket(
                key="(none)",
                order_count=0,
                trade_count=0,
                realized_pnl_krw=Decimal("0"),
                matched_qty_btc=Decimal("0"),
            )
        )

    return RealizedPnlResponse(period=normalized_period, market=args.market, buckets=buckets)


def _load_grid_buy_prices() -> dict[int, Decimal]:
    """현재 그리드 스냅샷의 {slot index: buy_price} 매핑.

    DB 미연결 등 예외 시 빈 매핑을 반환하고 죽지 않는다.
    """
    try:
        from app.api.services.grid_service import load_grid_snapshot

        snapshot = load_grid_snapshot()
        return {row.index: row.buy_price for row in snapshot.rows}
    except Exception:
        return {}


def calculate_pnl_by_slot(*, period: str, detail: bool) -> PnlBySlotResponse:
    if not cfg.API_KEY or not cfg.API_SECRET:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY is not configured")

    normalized_period = _normalize_period(period)
    args = _window_args(normalized_period)
    today_kst = datetime.now(pnl.KST).date()
    report_window = pnl.resolve_report_window(args, today_kst)
    user_from_date = report_window.from_date
    user_to_date = report_window.to_date
    fetch_from_date = user_from_date - timedelta(days=args.lookback)

    fetch_start_dt = datetime(
        fetch_from_date.year,
        fetch_from_date.month,
        fetch_from_date.day,
        0,
        0,
        0,
        tzinfo=pnl.KST,
    )
    display_start_dt = datetime(
        user_from_date.year,
        user_from_date.month,
        user_from_date.day,
        0,
        0,
        0,
        tzinfo=pnl.KST,
    )
    display_end_dt = datetime(
        user_to_date.year,
        user_to_date.month,
        user_to_date.day,
        23,
        59,
        59,
        tzinfo=pnl.KST,
    )

    pnl._anomaly_list.clear()
    raw_orders = pnl.fetch_closed_orders(
        cfg.API_KEY,
        cfg.API_SECRET,
        args.market,
        fetch_start_dt,
        display_end_dt,
    )

    sorted_orders = pnl.prepare_sorted_orders(raw_orders, cfg.API_KEY, cfg.API_SECRET)
    realized_lines, *_ = pnl.run_fifo(sorted_orders, set(args.reset_sell_uuid))
    display_realized_lines = [
        item for item in realized_lines if display_start_dt <= item["time_key"] <= display_end_dt
    ]

    grid_buy_prices = _load_grid_buy_prices()

    slots: list[SlotPnlBucket] = []
    for bucket in pnl.group_realized_by_slot(display_realized_lines):
        slots.append(
            SlotPnlBucket(
                slot=bucket["slot"],
                grid_buy_price=grid_buy_prices.get(bucket["slot"]),
                order_count=bucket["order_count"],
                realized_pnl_krw=bucket["realized_pnl_krw"],
                matched_qty=bucket["matched_qty"],
            )
        )

    total_realized_pnl_krw = sum((b.realized_pnl_krw for b in slots), Decimal("0"))

    sells: list[SellLine] = []
    if detail:
        for line in pnl.realized_to_sell_lines(display_realized_lines):
            sells.append(
                SellLine(
                    time=line["time_key"].isoformat(timespec="seconds"),
                    slot=line["slot"],
                    matched_qty=line["matched_qty"],
                    realized_pnl_krw=line["realized_pnl"],
                    sell_uuid=line["sell_uuid"],
                )
            )

    return PnlBySlotResponse(
        period=normalized_period,
        market=args.market,
        base_currency=pnl.market_base_currency(args.market),
        total_realized_pnl_krw=total_realized_pnl_krw,
        slots=slots,
        sells=sells,
    )
