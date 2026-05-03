"""
Decimal 처리 공용 유틸
"""
from decimal import Decimal, ROUND_DOWN

DECIMAL_ZERO = Decimal("0")
BTC_QUANTITY_STEP = Decimal("0.00000001")


def to_decimal(value) -> Decimal:
    """int/float/str/Decimal 입력을 Decimal로 변환."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_to_step(value, step, rounding=ROUND_DOWN) -> Decimal:
    """임의의 step 단위로 내림/반올림."""
    decimal_value = to_decimal(value)
    decimal_step = to_decimal(step)
    units = (decimal_value / decimal_step).to_integral_value(rounding=rounding)
    return units * decimal_step


def format_decimal(value) -> str:
    """과학적 표기 없이 저장용 문자열로 변환."""
    decimal_value = to_decimal(value)
    if decimal_value == DECIMAL_ZERO:
        return "0"
    return format(decimal_value.normalize(), "f")
