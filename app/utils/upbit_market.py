"""
업비트 KRW 마켓 가격 단위 유틸
"""
from decimal import Decimal, ROUND_DOWN

from app.utils.decimal_utils import quantize_to_step, to_decimal

MIN_KRW_ORDER_AMOUNT = Decimal("5000")


def get_krw_tick_size(price) -> Decimal:
    """업비트 KRW 마켓 가격 구간별 호가 단위."""
    decimal_price = to_decimal(price)

    if decimal_price >= Decimal("1000000"):
        return Decimal("1000")
    if decimal_price >= Decimal("500000"):
        return Decimal("500")
    if decimal_price >= Decimal("100000"):
        return Decimal("100")
    if decimal_price >= Decimal("50000"):
        return Decimal("50")
    if decimal_price >= Decimal("10000"):
        return Decimal("10")
    if decimal_price >= Decimal("5000"):
        return Decimal("5")
    if decimal_price >= Decimal("100"):
        return Decimal("1")
    if decimal_price >= Decimal("10"):
        return Decimal("0.1")
    if decimal_price >= Decimal("1"):
        return Decimal("0.01")
    if decimal_price >= Decimal("0.1"):
        return Decimal("0.001")
    if decimal_price >= Decimal("0.01"):
        return Decimal("0.0001")
    if decimal_price >= Decimal("0.001"):
        return Decimal("0.00001")
    if decimal_price >= Decimal("0.0001"):
        return Decimal("0.000001")
    if decimal_price >= Decimal("0.00001"):
        return Decimal("0.0000001")
    return Decimal("0.00000001")


def normalize_krw_price(price, rounding=ROUND_DOWN) -> Decimal:
    """업비트 KRW 마켓 호가 단위에 맞춰 가격 보정."""
    decimal_price = to_decimal(price)
    tick_size = get_krw_tick_size(decimal_price)
    return quantize_to_step(decimal_price, tick_size, rounding=rounding)
