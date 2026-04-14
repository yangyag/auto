"""grid.properties 기반 그리드 스펙 로딩 및 슬롯 계산."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from math import exp, log
from pathlib import Path

from core.models import GridRow
from utils.decimal_utils import BTC_QUANTITY_STEP, DECIMAL_ZERO, quantize_to_step, to_decimal
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT, normalize_krw_price


@dataclass(frozen=True)
class GridPropertySpec:
    min_buy_price: Decimal
    max_buy_price: Decimal
    buy_amount_krw: Decimal
    grid_count: int


def load_grid_property_spec(path: str | Path) -> GridPropertySpec:
    properties: dict[str, str] = {}
    file_path = Path(path)
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        properties[key.strip()] = value.strip()

    missing = [
        key for key in ("MIN_BUY_PRICE", "MAX_BUY_PRICE", "BUY_AMOUNT_KRW", "GRID_COUNT")
        if key not in properties or not properties[key]
    ]
    if missing:
        raise ValueError(f"grid.properties 필수 항목 누락: {', '.join(missing)}")

    return GridPropertySpec(
        min_buy_price=to_decimal(properties["MIN_BUY_PRICE"]),
        max_buy_price=to_decimal(properties["MAX_BUY_PRICE"]),
        buy_amount_krw=to_decimal(properties["BUY_AMOUNT_KRW"]),
        grid_count=int(properties["GRID_COUNT"]),
    )


def build_grid_rows_from_property_spec(spec: GridPropertySpec) -> list[GridRow]:
    raw_min_buy_price = to_decimal(spec.min_buy_price)
    raw_max_buy_price = to_decimal(spec.max_buy_price)
    min_buy_price = normalize_krw_price(raw_min_buy_price)
    max_buy_price = normalize_krw_price(raw_max_buy_price)
    buy_amount_krw = to_decimal(spec.buy_amount_krw)
    grid_count = int(spec.grid_count)

    if raw_min_buy_price != min_buy_price:
        raise ValueError(
            f"MIN_BUY_PRICE는 업비트 호가 단위에 맞아야 합니다: 입력={raw_min_buy_price}, 보정={min_buy_price}"
        )
    if raw_max_buy_price != max_buy_price:
        raise ValueError(
            f"MAX_BUY_PRICE는 업비트 호가 단위에 맞아야 합니다: 입력={raw_max_buy_price}, 보정={max_buy_price}"
        )

    if grid_count < 2:
        raise ValueError("GRID_COUNT는 2 이상이어야 합니다.")
    if min_buy_price <= DECIMAL_ZERO:
        raise ValueError("MIN_BUY_PRICE는 0보다 커야 합니다.")
    if max_buy_price <= min_buy_price:
        raise ValueError("MAX_BUY_PRICE는 MIN_BUY_PRICE보다 커야 합니다.")
    if buy_amount_krw < MIN_KRW_ORDER_AMOUNT:
        raise ValueError("BUY_AMOUNT_KRW는 업비트 최소 주문 금액(5,000 KRW) 이상이어야 합니다.")

    growth_ratio = Decimal(str(exp(log(float(max_buy_price / min_buy_price)) / (grid_count - 1))))

    buy_prices_desc: list[Decimal] = [max_buy_price]
    for index in range(1, grid_count - 1):
        raw_price = max_buy_price / (growth_ratio ** index)
        buy_prices_desc.append(normalize_krw_price(raw_price))
    buy_prices_desc.append(min_buy_price)

    if len(set(buy_prices_desc)) != grid_count:
        raise ValueError("호가 단위 적용 후 buy_price 레벨이 중복되었습니다. 범위를 넓히거나 슬롯 수를 줄이세요.")

    top_sell_price = normalize_krw_price(max_buy_price * growth_ratio)
    if top_sell_price <= max_buy_price:
        raise ValueError("상단 sell_price 계산 결과가 top buy_price보다 크지 않습니다.")

    rows: list[GridRow] = []
    for index, buy_price in enumerate(buy_prices_desc, start=1):
        sell_price = top_sell_price if index == 1 else buy_prices_desc[index - 2]
        planned_qty = quantize_to_step(
            buy_amount_krw / buy_price,
            BTC_QUANTITY_STEP,
            rounding=ROUND_DOWN,
        )
        if planned_qty <= DECIMAL_ZERO:
            raise ValueError(f"슬롯 {index} planned_qty가 0이 되었습니다.")
        if buy_price * planned_qty < MIN_KRW_ORDER_AMOUNT:
            raise ValueError(f"슬롯 {index} 매수 금액이 업비트 최소 주문 금액보다 작습니다.")
        rows.append(
            GridRow(
                index=index,
                buy_price=buy_price,
                held_qty=DECIMAL_ZERO,
                sell_price=sell_price,
                planned_qty=planned_qty,
            )
        )

    return rows
