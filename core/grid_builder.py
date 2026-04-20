"""
KRW-BTC용 그리드 생성기
"""
from decimal import Decimal, ROUND_DOWN
from math import exp, log

from core.grid_properties import build_target_sell_price
from core.models import GridRow
from utils.decimal_utils import BTC_QUANTITY_STEP, DECIMAL_ZERO, quantize_to_step, to_decimal
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT, normalize_krw_price


def build_cash_only_grid(
    *,
    lower_price,
    upper_price,
    current_price,
    slot_count: int,
    first_buy_amount_krw,
    tp_model: str | None = None,
    tp_k_base: Decimal | None = None,
    tp_k_floor: Decimal | None = None,
) -> list[GridRow]:
    """첫 칸 매수 금액 기준 고정 수량으로 KRW-BTC 그리드를 생성한다."""
    lower = normalize_krw_price(lower_price)
    upper = normalize_krw_price(upper_price)
    current = normalize_krw_price(current_price)
    first_buy_amount = to_decimal(first_buy_amount_krw)

    if slot_count <= 0:
        raise ValueError("slot_count는 1 이상이어야 합니다.")
    if lower <= DECIMAL_ZERO:
        raise ValueError("lower_price는 0보다 커야 합니다.")
    if upper <= lower:
        raise ValueError("upper_price는 lower_price보다 커야 합니다.")
    if current <= DECIMAL_ZERO:
        raise ValueError("current_price는 0보다 커야 합니다.")
    if first_buy_amount <= DECIMAL_ZERO:
        raise ValueError("first_buy_amount_krw는 0보다 커야 합니다.")

    growth_ratio = Decimal(str(exp(log(float(upper / lower)) / slot_count)))

    price_levels_desc: list[Decimal] = [upper]
    for index in range(1, slot_count):
        raw_price = upper / (growth_ratio ** index)
        price_levels_desc.append(normalize_krw_price(raw_price))
    price_levels_desc.append(lower)

    if len(set(price_levels_desc)) != slot_count + 1:
        raise ValueError("호가 단위 적용 후 가격 레벨이 중복되었습니다. 슬롯 수를 줄이거나 범위를 넓히세요.")

    first_buy_price = price_levels_desc[1]
    fixed_quantity = quantize_to_step(
        first_buy_amount / first_buy_price,
        BTC_QUANTITY_STEP,
        rounding=ROUND_DOWN,
    )
    if fixed_quantity <= DECIMAL_ZERO:
        raise ValueError("첫 칸 기준 매수 금액으로 계산한 고정 수량이 0이 되었습니다.")

    rows: list[GridRow] = []
    for index in range(1, slot_count + 1):
        buy_price = price_levels_desc[index]
        sell_price = build_target_sell_price(
            buy_price,
            tp_model=tp_model,
            lower_price=lower,
            upper_price=upper,
            price_interval_count=slot_count,
            tp_k=tp_k_base,
            tp_k_floor=tp_k_floor,
        )
        order_amount = buy_price * fixed_quantity
        if order_amount < MIN_KRW_ORDER_AMOUNT:
            raise ValueError("업비트 최소 주문 가능 금액(5,000 KRW)보다 작은 슬롯이 생성되었습니다.")
        if sell_price <= buy_price:
            raise ValueError("sell_price는 buy_price보다 커야 합니다.")

        rows.append(
            GridRow(
                index=index,
                buy_price=buy_price,
                held_qty=DECIMAL_ZERO,
                sell_price=sell_price,
                planned_qty=fixed_quantity,
            )
        )

    return rows
