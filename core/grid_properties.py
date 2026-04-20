"""grid.properties 기반 그리드 스펙 로딩 및 슬롯 계산."""
from __future__ import annotations

import config.settings as cfg
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from math import exp, log
from pathlib import Path

from core.models import GridRow
from utils.decimal_utils import BTC_QUANTITY_STEP, DECIMAL_ZERO, quantize_to_step, to_decimal
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT, normalize_krw_price

DEFAULT_TP_MODEL = "k"
DEFAULT_TP_K_BASE = Decimal("9.0")
DEFAULT_TP_K_FLOOR = Decimal("7.0")
DEFAULT_TOP_THIRD_WEIGHT = Decimal("0.7")
DEFAULT_MIDDLE_THIRD_WEIGHT = Decimal("1.0")
DEFAULT_BOTTOM_THIRD_WEIGHT = Decimal("1.3")
DEFAULT_GRID_ALLOCATION_WEIGHTS = (
    DEFAULT_TOP_THIRD_WEIGHT,
    DEFAULT_MIDDLE_THIRD_WEIGHT,
    DEFAULT_BOTTOM_THIRD_WEIGHT,
)


@dataclass(frozen=True)
class GridPropertySpec:
    min_buy_price: Decimal
    max_buy_price: Decimal
    buy_amount_krw: Decimal
    grid_count: int
    tp_model: str | None = DEFAULT_TP_MODEL
    tp_k_base: Decimal | None = None
    tp_k_floor: Decimal | None = None


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
    if "SELL_PERCENT" in properties:
        raise ValueError("SELL_PERCENT는 더 이상 지원되지 않습니다. k 기반 TP만 사용하세요.")

    return GridPropertySpec(
        min_buy_price=to_decimal(properties["MIN_BUY_PRICE"]),
        max_buy_price=to_decimal(properties["MAX_BUY_PRICE"]),
        buy_amount_krw=to_decimal(properties["BUY_AMOUNT_KRW"]),
        grid_count=int(properties["GRID_COUNT"]),
        tp_model=properties.get("TP_MODEL") or DEFAULT_TP_MODEL,
        tp_k_base=to_decimal(properties["TP_K_BASE"]) if properties.get("TP_K_BASE") else None,
        tp_k_floor=to_decimal(properties["TP_K_FLOOR"]) if properties.get("TP_K_FLOOR") else None,
    )


def normalize_tp_model(tp_model: str | None = None) -> str:
    raw_tp_model = cfg.GRID_TP_MODEL if tp_model is None else tp_model
    normalized = str(raw_tp_model).strip().lower()
    if normalized in {"k", "k_step", "k_steps"}:
        return "k"
    raise ValueError(f"지원하지 않는 TP 모델입니다: {raw_tp_model}")


def resolve_tp_k_values(
    tp_k: Decimal | None = None,
    tp_k_floor: Decimal | None = None,
) -> tuple[Decimal, Decimal]:
    k_value = cfg.GRID_TP_K_BASE if tp_k is None else to_decimal(tp_k)
    floor_value = cfg.GRID_TP_K_FLOOR if tp_k_floor is None else to_decimal(tp_k_floor)
    if floor_value <= DECIMAL_ZERO:
        raise ValueError("TP_K_FLOOR는 0보다 커야 합니다.")
    if k_value < floor_value:
        raise ValueError("TP_K_BASE는 TP_K_FLOOR보다 크거나 같아야 합니다.")
    return k_value, floor_value


def build_sell_price_from_k(
    buy_price: Decimal,
    *,
    lower_price: Decimal,
    upper_price: Decimal,
    price_interval_count: int,
    tp_k: Decimal | None = None,
    tp_k_floor: Decimal | None = None,
) -> Decimal:
    lower = normalize_krw_price(lower_price)
    upper = normalize_krw_price(upper_price)
    if lower <= DECIMAL_ZERO:
        raise ValueError("하단 가격은 0보다 커야 합니다.")
    if upper <= lower:
        raise ValueError("상단 가격은 하단 가격보다 커야 합니다.")
    if price_interval_count <= 0:
        raise ValueError("price_interval_count는 1 이상이어야 합니다.")

    k_value, floor_value = resolve_tp_k_values(tp_k, tp_k_floor)
    effective_k = k_value if k_value >= floor_value else floor_value
    log_step = Decimal(str(log(float(upper / lower)) / price_interval_count))
    raw_sell_price = buy_price * Decimal(str(exp(float(log_step * effective_k))))
    sell_price = normalize_krw_price(raw_sell_price)
    if sell_price <= buy_price:
        raise ValueError(
            "k 기반 sell_price 계산 결과가 buy_price보다 크지 않습니다: "
            f"buy_price={buy_price}, tp_k={effective_k}, sell_price={sell_price}"
        )
    return sell_price


def build_target_sell_price(
    buy_price: Decimal,
    *,
    tp_model: str | None = None,
    lower_price: Decimal | None = None,
    upper_price: Decimal | None = None,
    price_interval_count: int | None = None,
    tp_k: Decimal | None = None,
    tp_k_floor: Decimal | None = None,
) -> Decimal:
    normalize_tp_model(tp_model)
    if lower_price is None or upper_price is None or price_interval_count is None:
        raise ValueError("k TP 모델에는 lower_price, upper_price, price_interval_count가 필요합니다.")
    return build_sell_price_from_k(
        buy_price,
        lower_price=lower_price,
        upper_price=upper_price,
        price_interval_count=price_interval_count,
        tp_k=tp_k,
        tp_k_floor=tp_k_floor,
    )


def build_weighted_slot_buy_amounts(spec: GridPropertySpec) -> list[Decimal]:
    """grid.properties 경로 전용 슬롯별 KRW 예산을 계산한다.

    BUY_AMOUNT_KRW는 슬롯 평균 예산으로 해석하고, 상/중/하단 가중치를 정규화해
    총예산은 기존과 동일하게 유지한다.
    """
    grid_count = int(spec.grid_count)
    if grid_count < 2:
        raise ValueError("GRID_COUNT는 2 이상이어야 합니다.")

    if grid_count == 2:
        raw_weights = [DEFAULT_TOP_THIRD_WEIGHT, DEFAULT_BOTTOM_THIRD_WEIGHT]
    else:
        raw_weights = []
        for zero_based_index in range(grid_count):
            bucket = min((zero_based_index * 3) // (grid_count - 1), 2)
            raw_weights.append(DEFAULT_GRID_ALLOCATION_WEIGHTS[bucket])

    weight_sum = sum(raw_weights, DECIMAL_ZERO)
    normalized_scale = to_decimal(grid_count) / weight_sum
    return [to_decimal(spec.buy_amount_krw) * weight * normalized_scale for weight in raw_weights]


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

    slot_buy_amounts = build_weighted_slot_buy_amounts(spec)
    rows: list[GridRow] = []
    for index, (buy_price, slot_buy_amount) in enumerate(zip(buy_prices_desc, slot_buy_amounts), start=1):
        sell_price = build_target_sell_price(
            buy_price,
            tp_model=spec.tp_model,
            lower_price=min_buy_price,
            upper_price=max_buy_price,
            price_interval_count=grid_count - 1,
            tp_k=spec.tp_k_base,
            tp_k_floor=spec.tp_k_floor,
        )
        planned_qty = quantize_to_step(
            slot_buy_amount / buy_price,
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
