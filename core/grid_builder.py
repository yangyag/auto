"""
KRW-BTC용 그리드 생성기
"""
from decimal import Decimal, ROUND_DOWN
from math import exp, log

from core.models import GridRow
from utils.decimal_utils import BTC_QUANTITY_STEP, DECIMAL_ZERO, quantize_to_step, to_decimal
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT, normalize_krw_price


def build_cash_only_grid(
    *,
    lower_price,
    upper_price,
    current_price,
    slot_count: int,
    total_budget_krw,
) -> list[GridRow]:
    """상단/하단 고정 경계 기준 현금 100% 시작 active buy 슬롯 생성."""
    lower = normalize_krw_price(lower_price)
    upper = normalize_krw_price(upper_price)
    current = normalize_krw_price(current_price)
    budget = to_decimal(total_budget_krw)

    if slot_count <= 0:
        raise ValueError("slot_count는 1 이상이어야 합니다.")
    if lower <= DECIMAL_ZERO:
        raise ValueError("lower_price는 0보다 커야 합니다.")
    if upper <= lower:
        raise ValueError("upper_price는 lower_price보다 커야 합니다.")
    if current <= DECIMAL_ZERO:
        raise ValueError("current_price는 0보다 커야 합니다.")
    if budget <= DECIMAL_ZERO:
        raise ValueError("total_budget_krw는 0보다 커야 합니다.")

    slot_budget = budget / Decimal(slot_count)
    growth_ratio = Decimal(str(exp(log(float(upper / lower)) / slot_count)))

    price_levels_desc: list[Decimal] = [upper]
    for index in range(1, slot_count):
        raw_price = upper / (growth_ratio ** index)
        price_levels_desc.append(normalize_krw_price(raw_price))
    price_levels_desc.append(lower)

    if len(set(price_levels_desc)) != slot_count + 1:
        raise ValueError("호가 단위 적용 후 가격 레벨이 중복되었습니다. 슬롯 수를 줄이거나 범위를 넓히세요.")

    rows: list[GridRow] = []
    for index in range(1, slot_count + 1):
        sell_price = price_levels_desc[index - 1]
        buy_price = price_levels_desc[index]
        quantity = quantize_to_step(slot_budget / buy_price, BTC_QUANTITY_STEP, rounding=ROUND_DOWN)
        if quantity <= DECIMAL_ZERO:
            raise ValueError("슬롯 수량이 0이 되었습니다. 예산 또는 슬롯 수를 조정하세요.")

        order_amount = buy_price * quantity
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
                planned_qty=quantity,
            )
        )

    return rows
