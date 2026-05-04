"""
KRW-BTC용 총예산 기반 그리드 생성기
"""
from decimal import Decimal

from app.core.grid_properties import GridPropertySpec, build_grid_rows_from_property_spec
from app.core.models import GridRow
from app.utils.upbit_market import normalize_krw_price


def build_cash_only_grid(
    *,
    lower_price: Decimal,
    upper_price: Decimal,
    slot_count: int,
    total_budget_krw: Decimal,
    tp_model: str | None = None,
    tp_k_base: Decimal | None = None,
    tp_k_floor: Decimal | None = None,
) -> list[GridRow]:
    """KRW-BTC 그리드를 생성한다."""
    spec = GridPropertySpec(
        min_buy_price=normalize_krw_price(lower_price),
        max_buy_price=normalize_krw_price(upper_price),
        total_budget_krw=total_budget_krw,
        grid_count=slot_count,
        tp_model=tp_model,
        tp_k_base=tp_k_base,
        tp_k_floor=tp_k_floor,
    )
    return build_grid_rows_from_property_spec(spec)
