#!/usr/bin/env python3
"""Phase 6 재중심화 preview-only 계획을 출력한다."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config.settings as cfg
from core.models import OrderSide
from storage.factory import build_grid_repository, build_pending_order_repository
from strategy.recenter_preview import (
    DEFAULT_BREAKOUT_CANDLE_COUNT,
    DEFAULT_CANDLE_UNIT_MINUTES,
    evaluate_recenter_preview,
)
from utils.decimal_utils import format_decimal

KST = timezone(timedelta(hours=9))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 scripts/preview_recenter_plan.py")
    parser.add_argument("--symbol", default=cfg.SYMBOL)
    parser.add_argument("--candle-unit", type=int, default=DEFAULT_CANDLE_UNIT_MINUTES)
    parser.add_argument("--breakout-candles", type=int, default=DEFAULT_BREAKOUT_CANDLE_COUNT)
    return parser


def build_exchange():
    if cfg.EXCHANGE_TYPE == "crypto":
        from exchange.crypto import CryptoExchange

        return CryptoExchange(cfg.API_KEY, cfg.API_SECRET)
    if cfg.EXCHANGE_TYPE == "stock":
        from exchange.stock import StockExchange

        return StockExchange(cfg.API_KEY, cfg.API_SECRET)
    raise ValueError(f"알 수 없는 EXCHANGE_TYPE: {cfg.EXCHANGE_TYPE}")


def resolve_completed_candle_cutoff(
    *,
    unit_minutes: int,
    now: datetime | None = None,
) -> datetime:
    current = (now or datetime.now(tz=KST)).astimezone(KST)
    unit = max(int(unit_minutes), 1)
    floored_minute = current.minute - (current.minute % unit)
    return current.replace(minute=floored_minute, second=0, microsecond=0)


def build_preview(
    *,
    symbol: str,
    candle_unit: int,
    breakout_candles: int,
    now: datetime | None = None,
):
    grid_repository = build_grid_repository(cfg)
    pending_order_repository = build_pending_order_repository(cfg)
    exchange = build_exchange()

    snapshot = grid_repository.load()
    current_price = exchange.get_current_price(symbol)
    close_prices = exchange.get_minute_candle_closes(
        symbol,
        unit_minutes=max(int(candle_unit), 1),
        count=max(int(breakout_candles), 1),
        to=resolve_completed_candle_cutoff(unit_minutes=candle_unit, now=now),
    )
    open_buy_orders = sum(
        1
        for order in pending_order_repository.list_open()
        if order.side == OrderSide.BUY
    )
    return evaluate_recenter_preview(
        snapshot.rows,
        current_price=current_price,
        close_prices=close_prices,
        open_buy_order_count=open_buy_orders,
        breakout_candle_count=breakout_candles,
        candle_unit_minutes=candle_unit,
        operating_budget_krw=cfg.MAX_OPERATING_BUDGET_KRW,
    )


def _format_optional_decimal(value) -> str:
    if value is None:
        return "-"
    return format_decimal(value)


def render_preview(preview, *, symbol: str) -> str:
    lines = [
        "상태: 성공",
        "mode: preview_only",
        f"symbol: {symbol}",
        f"status: {preview.status}",
        f"reason: {preview.reason}",
        f"blockers: {', '.join(preview.blockers) if preview.blockers else '-'}",
        f"current_price: {format_decimal(preview.current_price)}",
        f"breakout_side: {preview.breakout_side or '-'}",
        f"breakout_candle_count: {preview.breakout_candle_count}",
        f"breakout_duration_hours: {format_decimal(preview.breakout_duration_hours)}",
        f"required_breakout_candles: {preview.required_breakout_candles}",
        f"inventory_ratio: {format_decimal(preview.inventory_ratio)}",
        f"inventory_ratio_threshold: {format_decimal(preview.inventory_ratio_threshold)}",
        f"open_buy_orders: {preview.open_buy_orders}",
        f"current_lower: {_format_optional_decimal(preview.current_lower)}",
        f"current_upper: {_format_optional_decimal(preview.current_upper)}",
        f"proposed_lower: {_format_optional_decimal(preview.proposed_lower)}",
        f"proposed_upper: {_format_optional_decimal(preview.proposed_upper)}",
        f"holding_slots_preserved: {preview.holding_slots_preserved}",
        f"empty_slots_rebuilt: {preview.empty_slots_rebuilt}",
        "apply_supported: false",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        preview = build_preview(
            symbol=args.symbol,
            candle_unit=args.candle_unit,
            breakout_candles=args.breakout_candles,
        )
    except Exception as exc:  # pragma: no cover - environment-specific
        print("상태: 실패")
        print(f"사유: {exc}")
        return 1

    print(render_preview(preview, symbol=args.symbol))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
