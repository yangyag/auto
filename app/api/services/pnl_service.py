from __future__ import annotations

from argparse import Namespace
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

import app.config.settings as cfg
from app.api.schemas.pnl import PnlBucket, RealizedPnlResponse
from scripts import upbit_realized_pnl as pnl


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

    args = _window_args(period)
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

        exec_funds = order.get("executed_funds")
        paid_fee = order.get("paid_fee")
        if exec_funds is None or paid_fee is None:
            continue
        if pnl._to_decimal(exec_funds) == Decimal("0") and exec_vol > Decimal("0"):
            continue
        try:
            order["_time_key"] = pnl._extract_time_key(order, cfg.API_KEY, cfg.API_SECRET)
        except AssertionError:
            continue
        valid_orders.append(order)

    sorted_orders = sorted(valid_orders, key=lambda o: (o["_time_key"], o["uuid"]))
    realized_lines, *_ = pnl.run_fifo(sorted_orders, set(args.reset_sell_uuid))
    display_realized_lines = [
        item for item in realized_lines if display_start_dt <= item["time_key"] <= display_end_dt
    ]

    group_period = "all" if period == "all" else pnl.PERIOD_PRESET_TO_GROUP[period]
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

    return RealizedPnlResponse(period=period, market=args.market, buckets=buckets)
