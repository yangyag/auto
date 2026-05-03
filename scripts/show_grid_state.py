#!/usr/bin/env python3
"""현재 그리드 슬롯 상태를 읽기 전용으로 출력한다."""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.config.settings as cfg
from app.core.grid import GridState
from app.storage.factory import build_grid_repository
from app.utils.decimal_utils import DECIMAL_ZERO, format_decimal
from app.utils.grid_reporting import summarize_planned_buy_budget


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="python3 scripts/show_grid_state.py")


def _format_row_line(index: int, buy_price, held_qty, sell_price, planned_qty, planned_buy_krw, extras: str = "") -> str:
    status = "holding" if held_qty > DECIMAL_ZERO else "empty"
    line = (
        f"{index:>3}) "
        f"buy={format_decimal(buy_price):>16} "
        f"held={format_decimal(held_qty):>16} "
        f"sell={format_decimal(sell_price):>16} "
        f"planned={format_decimal(planned_qty):>16} "
        f"planned_krw={format_decimal(planned_buy_krw):>16} "
        f"status={status}"
    )
    if extras:
        return f"{line} {extras}"
    return line


def _source_label() -> str:
    return f"postgres:{cfg.PGSCHEMA}/{cfg.STATE_BOT_KEY}"


def _preview_field(preview, field_name: str):
    if isinstance(preview, dict):
        return preview.get(field_name)
    return getattr(preview, field_name, None)


def _print_snapshot(snapshot) -> None:
    state = GridState.from_snapshot(snapshot)
    now = datetime.now(timezone.utc)
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
        extras: list[str] = []
        if row.is_holding and row.filled_at is not None:
            extras.append(f"filled_at={row.filled_at.isoformat()}")
            if state.is_age_compressed_tp_active(
                row.index,
                tp_k_base=cfg.GRID_TP_K_BASE,
                tp_k_floor=cfg.GRID_TP_K_FLOOR,
            ):
                effective_tp_k = state.effective_tp_k(
                    row.index,
                    now=now,
                    tp_k_base=cfg.GRID_TP_K_BASE,
                    tp_k_floor=cfg.GRID_TP_K_FLOOR,
                )
                tp_age_step = effective_tp_k - cfg.GRID_TP_K_BASE
                extras.extend(
                    [
                        f"tp_age_step={format_decimal(tp_age_step)}",
                        f"effective_tp_k={format_decimal(effective_tp_k)}",
                    ]
                )
        print(
            _format_row_line(
                row.index,
                row.buy_price,
                row.held_qty,
                row.sell_price,
                row.planned_qty,
                row.buy_price * row.planned_qty,
                " ".join(extras),
            )
        )

    recenter_preview = getattr(snapshot, "recenter_preview", None)
    if recenter_preview is None:
        recenter_preview = getattr(snapshot.metadata, "recenter_preview", None)
    if recenter_preview is not None:
        blockers = _preview_field(recenter_preview, "blockers") or []
        proposed_lower = _preview_field(recenter_preview, "proposed_lower")
        proposed_upper = _preview_field(recenter_preview, "proposed_upper")
        if proposed_lower is None:
            proposed_lower = _preview_field(recenter_preview, "proposed_lower_price")
        if proposed_upper is None:
            proposed_upper = _preview_field(recenter_preview, "proposed_upper_price")
        print(f"recenter_preview: {_preview_field(recenter_preview, 'status')}")
        print(f"recenter_can_apply: {'yes' if _preview_field(recenter_preview, 'can_apply') else 'no'}")
        print(f"recenter_blockers: {', '.join(blockers) if blockers else '-'}")
        print(
            "recenter_proposed_band: "
            f"{format_decimal(proposed_lower) if proposed_lower is not None else '-'} -> "
            f"{format_decimal(proposed_upper) if proposed_upper is not None else '-'}"
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
