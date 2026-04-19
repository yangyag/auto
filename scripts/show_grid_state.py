#!/usr/bin/env python3
"""현재 그리드 슬롯 상태를 읽기 전용으로 출력한다."""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config.settings as cfg
from storage.factory import build_grid_repository
from utils.decimal_utils import DECIMAL_ZERO, format_decimal
from utils.grid_reporting import summarize_planned_buy_budget


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="python3 scripts/show_grid_state.py")


def _format_row_line(index: int, buy_price, held_qty, sell_price, planned_qty, planned_buy_krw) -> str:
    status = "holding" if held_qty > DECIMAL_ZERO else "empty"
    return (
        f"{index:>3}) "
        f"buy={format_decimal(buy_price):>16} "
        f"held={format_decimal(held_qty):>16} "
        f"sell={format_decimal(sell_price):>16} "
        f"planned={format_decimal(planned_qty):>16} "
        f"planned_krw={format_decimal(planned_buy_krw):>16} "
        f"status={status}"
    )


def _source_label() -> str:
    return f"postgres:{cfg.PGSCHEMA}/{cfg.STATE_BOT_KEY}"


def _print_snapshot(snapshot) -> None:
    total_inventory = sum((row.held_qty for row in snapshot.rows), DECIMAL_ZERO)
    budget_summary = summarize_planned_buy_budget(snapshot.rows)
    print("상태: 성공")
    print("backend: postgres")
    print(f"source: {_source_label()}")
    if snapshot.symbol:
        print(f"symbol: {snapshot.symbol}")
    print(f"rows: {len(snapshot.rows)}")
    print(f"total_inventory: {format_decimal(total_inventory)}")
    print(f"planned_buy_budget_total: {format_decimal(budget_summary.total)}")
    print(f"top_slot_planned_buy_budget: {format_decimal(budget_summary.top_slot)}")
    print(f"bottom_slot_planned_buy_budget: {format_decimal(budget_summary.bottom_slot)}")
    print("slot | buy | held | sell | planned | planned_krw | status")
    for row in snapshot.rows:
        print(
            _format_row_line(
                row.index,
                row.buy_price,
                row.held_qty,
                row.sell_price,
                row.planned_qty,
                row.buy_price * row.planned_qty,
            )
        )


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        repository = build_grid_repository(cfg)
        snapshot = repository.load()
    except Exception as exc:  # pragma: no cover - error path depends on environment
        print("상태: 실패")
        print(f"사유: {exc}")
        return 1

    _print_snapshot(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
