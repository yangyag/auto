"""그리드 상태의 계획 매수 금액 요약 유틸."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.utils.decimal_utils import DECIMAL_ZERO


@dataclass(frozen=True)
class PlannedBudgetSummary:
    total: Decimal
    top_slot: Decimal
    bottom_slot: Decimal


def planned_buy_budget(row) -> Decimal:
    return row.buy_price * row.planned_qty


def summarize_planned_buy_budget(rows: Iterable[object]) -> PlannedBudgetSummary:
    row_list = list(rows)
    if not row_list:
        return PlannedBudgetSummary(
            total=DECIMAL_ZERO,
            top_slot=DECIMAL_ZERO,
            bottom_slot=DECIMAL_ZERO,
        )

    total = sum((planned_buy_budget(row) for row in row_list), DECIMAL_ZERO)
    return PlannedBudgetSummary(
        total=total,
        top_slot=planned_buy_budget(row_list[0]),
        bottom_slot=planned_buy_budget(row_list[-1]),
    )
