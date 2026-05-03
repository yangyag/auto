"""Phase 6 preview-only 재중심화 계산 로직."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from math import sqrt
from typing import Iterable, Sequence

from app.core.models import GridRow
from app.utils.decimal_utils import DECIMAL_ZERO, to_decimal

DEFAULT_BREAKOUT_CANDLE_COUNT = 96
DEFAULT_CANDLE_UNIT_MINUTES = 15
DEFAULT_INVENTORY_RATIO_THRESHOLD = Decimal("0.20")


@dataclass(frozen=True)
class RecenterPreview:
    status: str
    reason: str
    blockers: tuple[str, ...]
    current_price: Decimal
    breakout_side: str | None
    breakout_candle_count: int
    breakout_duration_hours: Decimal
    required_breakout_candles: int
    open_buy_orders: int
    inventory_ratio: Decimal
    inventory_ratio_threshold: Decimal
    current_lower: Decimal | None
    current_upper: Decimal | None
    proposed_lower: Decimal | None
    proposed_upper: Decimal | None
    holding_slots_preserved: int
    empty_slots_rebuilt: int
    mode: str = "preview_only"

    @property
    def can_apply(self) -> bool:
        return self.status == "eligible"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["can_apply"] = self.can_apply
        return payload


def evaluate_recenter_preview(
    rows: Iterable[GridRow],
    *,
    current_price: Decimal,
    close_prices: Sequence[Decimal],
    open_buy_order_count: int,
    breakout_candle_count: int = DEFAULT_BREAKOUT_CANDLE_COUNT,
    candle_unit_minutes: int = DEFAULT_CANDLE_UNIT_MINUTES,
    inventory_ratio_threshold: Decimal = DEFAULT_INVENTORY_RATIO_THRESHOLD,
    operating_budget_krw: Decimal | None = None,
) -> RecenterPreview:
    """현재 스냅샷 기준 preview-only 재중심화 가능 여부를 계산한다."""
    normalized_rows = tuple(rows)
    normalized_price = to_decimal(current_price)
    threshold = to_decimal(inventory_ratio_threshold)
    required_candles = max(int(breakout_candle_count), 1)
    unit_minutes = max(int(candle_unit_minutes), 1)
    open_buy_orders = max(int(open_buy_order_count), 0)

    lower_price, upper_price = _resolve_band_bounds(normalized_rows)
    inventory_ratio = _inventory_ratio(
        normalized_rows,
        operating_budget_krw=operating_budget_krw,
    )
    breakout_side, breakout_run_count = _breakout_run(
        close_prices,
        lower_price=lower_price,
        upper_price=upper_price,
    )
    blockers = _collect_blockers(
        lower_price=lower_price,
        upper_price=upper_price,
        close_prices=close_prices,
        breakout_side=breakout_side,
        breakout_run_count=breakout_run_count,
        required_breakout_candles=required_candles,
        inventory_ratio=inventory_ratio,
        inventory_ratio_threshold=threshold,
        open_buy_orders=open_buy_orders,
    )
    proposed_lower, proposed_upper = _proposed_band_bounds(
        current_price=normalized_price,
        lower_price=lower_price,
        upper_price=upper_price,
    )

    status = "eligible" if not blockers else "blocked"
    reason = "ok" if not blockers else blockers[0]
    breakout_duration_hours = Decimal(breakout_run_count * unit_minutes) / Decimal("60")

    return RecenterPreview(
        status=status,
        reason=reason,
        blockers=tuple(blockers),
        current_price=normalized_price,
        breakout_side=breakout_side,
        breakout_candle_count=breakout_run_count,
        breakout_duration_hours=breakout_duration_hours,
        required_breakout_candles=required_candles,
        open_buy_orders=open_buy_orders,
        inventory_ratio=inventory_ratio,
        inventory_ratio_threshold=threshold,
        current_lower=lower_price,
        current_upper=upper_price,
        proposed_lower=proposed_lower,
        proposed_upper=proposed_upper,
        holding_slots_preserved=sum(1 for row in normalized_rows if row.is_holding),
        empty_slots_rebuilt=sum(1 for row in normalized_rows if not row.is_holding),
    )


def _resolve_band_bounds(rows: Sequence[GridRow]) -> tuple[Decimal | None, Decimal | None]:
    buy_prices = [row.buy_price for row in rows if row.buy_price > DECIMAL_ZERO]
    if not buy_prices:
        return None, None

    lower_price = min(buy_prices)
    upper_price = max(buy_prices)
    if upper_price <= lower_price:
        return None, None
    return lower_price, upper_price


def _inventory_ratio(
    rows: Sequence[GridRow],
    *,
    operating_budget_krw: Decimal | None,
) -> Decimal:
    budget = to_decimal(operating_budget_krw) if operating_budget_krw is not None else DECIMAL_ZERO
    if budget <= DECIMAL_ZERO:
        budget = sum(
            (
                row.buy_price * (row.held_qty if row.is_holding else row.planned_qty)
                for row in rows
            ),
            DECIMAL_ZERO,
        )

    if budget <= DECIMAL_ZERO:
        return DECIMAL_ZERO

    inventory_cost = sum(
        (row.buy_price * row.held_qty for row in rows if row.is_holding),
        DECIMAL_ZERO,
    )
    return inventory_cost / budget


def _breakout_run(
    close_prices: Sequence[Decimal],
    *,
    lower_price: Decimal | None,
    upper_price: Decimal | None,
) -> tuple[str | None, int]:
    if lower_price is None or upper_price is None:
        return None, 0

    normalized_closes = tuple(to_decimal(price) for price in close_prices)
    if not normalized_closes:
        return None, 0

    first_close = normalized_closes[0]
    if first_close > upper_price:
        side = "upper"
        predicate = lambda price: price > upper_price
    elif first_close < lower_price:
        side = "lower"
        predicate = lambda price: price < lower_price
    else:
        return None, 0

    run_count = 0
    for price in normalized_closes:
        if predicate(price):
            run_count += 1
            continue
        break
    return side, run_count


def _collect_blockers(
    *,
    lower_price: Decimal | None,
    upper_price: Decimal | None,
    close_prices: Sequence[Decimal],
    breakout_side: str | None,
    breakout_run_count: int,
    required_breakout_candles: int,
    inventory_ratio: Decimal,
    inventory_ratio_threshold: Decimal,
    open_buy_orders: int,
) -> list[str]:
    blockers: list[str] = []

    if lower_price is None or upper_price is None:
        blockers.append("invalid_band")
    elif len(close_prices) < required_breakout_candles:
        blockers.append(f"insufficient_candles:{len(close_prices)}/{required_breakout_candles}")
    elif breakout_side is None:
        blockers.append("breakout_not_outside_band")
    elif breakout_run_count < required_breakout_candles:
        blockers.append("breakout_duration_below_24h")

    if inventory_ratio > inventory_ratio_threshold:
        blockers.append("inventory_ratio_above_threshold")

    if open_buy_orders > 0:
        blockers.append("open_buy_orders_present")

    return blockers


def _proposed_band_bounds(
    *,
    current_price: Decimal,
    lower_price: Decimal | None,
    upper_price: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    if (
        lower_price is None
        or upper_price is None
        or current_price <= DECIMAL_ZERO
        or upper_price <= lower_price
    ):
        return None, None

    width_ratio = upper_price / lower_price
    center_scale = Decimal(str(sqrt(float(width_ratio))))
    if center_scale <= DECIMAL_ZERO:
        return None, None

    return current_price / center_scale, current_price * center_scale
