"""브레이크아웃 가드 계산 로직."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from utils.decimal_utils import to_decimal


@dataclass(frozen=True)
class BreakoutGuardStatus:
    active: bool
    reason: str
    side: str | None = None
    close_prices: tuple[Decimal, ...] = ()


def evaluate_breakout_guard(
    close_prices: Sequence[Decimal],
    *,
    lower_price: Decimal,
    upper_price: Decimal,
    consecutive_count: int,
) -> BreakoutGuardStatus:
    """최근 종가가 같은 방향으로 밴드 밖에 연속 존재하는지 판정한다."""
    if consecutive_count <= 0:
        return BreakoutGuardStatus(active=False, reason="guard_disabled")
    if lower_price <= 0 or upper_price <= lower_price:
        return BreakoutGuardStatus(active=False, reason="invalid_band")

    recent_closes = tuple(to_decimal(price) for price in close_prices[:consecutive_count])
    if len(recent_closes) < consecutive_count:
        return BreakoutGuardStatus(
            active=False,
            reason=f"insufficient_candles:{len(recent_closes)}/{consecutive_count}",
            close_prices=recent_closes,
        )

    if all(price > upper_price for price in recent_closes):
        return BreakoutGuardStatus(
            active=True,
            reason="outside_upper_band",
            side="upper",
            close_prices=recent_closes,
        )

    if all(price < lower_price for price in recent_closes):
        return BreakoutGuardStatus(
            active=True,
            reason="outside_lower_band",
            side="lower",
            close_prices=recent_closes,
        )

    return BreakoutGuardStatus(
        active=False,
        reason="inside_band",
        close_prices=recent_closes,
    )
