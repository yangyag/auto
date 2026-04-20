"""
그리드 도메인 상태 관리
"""
from math import exp, log
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

import config.settings as cfg
from core.grid_properties import (
    build_sell_price_from_k,
    normalize_tp_model,
    resolve_tp_k_values,
)
from core.models import GridRow
from storage.interfaces import GridSnapshot, RepositoryMetadata
from strategy.recenter_preview import evaluate_recenter_preview
from utils.decimal_utils import DECIMAL_ZERO, format_decimal
from utils.upbit_market import normalize_krw_price


def _copy_row(row: GridRow) -> GridRow:
    return replace(row)


class GridState:
    """그리드 전체 상태를 관리하는 도메인 객체"""

    def __init__(self, symbol: str = "", rows: List[GridRow] | None = None):
        self.symbol = symbol
        self.rows: List[GridRow] = [_copy_row(row) for row in (rows or [])]

    @classmethod
    def from_rows(
        cls,
        symbol: str,
        rows: List[GridRow],
        grid_file: str | None = None,
    ) -> "GridState":
        del grid_file  # 기존 테스트/호출부 호환용 인자
        return cls(symbol=symbol, rows=rows)

    @classmethod
    def from_snapshot(cls, snapshot: GridSnapshot) -> "GridState":
        return cls(symbol=snapshot.symbol, rows=list(snapshot.rows))

    def to_snapshot(self, metadata: RepositoryMetadata | None = None) -> GridSnapshot:
        rows = tuple(_copy_row(row) for row in self.rows)
        if metadata is None:
            return GridSnapshot(symbol=self.symbol, rows=rows)
        return GridSnapshot(symbol=self.symbol, rows=rows, metadata=metadata)

    def replace_with(self, snapshot: GridSnapshot) -> None:
        self.symbol = snapshot.symbol
        self.rows = [_copy_row(row) for row in snapshot.rows]

    @property
    def total_inventory(self) -> Decimal:
        """현재 보유 중인 전체 수량"""
        return sum((r.held_qty for r in self.rows), DECIMAL_ZERO)

    @property
    def total_allocated_budget(self) -> Decimal:
        """전체 슬롯에 배정된 총 KRW 예산."""
        total = DECIMAL_ZERO
        for row in self.rows:
            quantity = row.held_qty if row.is_holding else row.planned_qty
            total += row.buy_price * quantity
        return total

    @property
    def current_inventory_cost(self) -> Decimal:
        """현재 보유 수량을 슬롯 원가 기준 KRW로 환산한 값."""
        total = DECIMAL_ZERO
        for row in self.rows:
            if row.is_holding:
                total += row.buy_price * row.held_qty
        return total

    def get_buy_triggered(self, current_price: Decimal) -> List[GridRow]:
        """현재가 이상의 buy_price를 가진 빈 슬롯 (매수 조건 충족)"""
        return [
            r for r in self.rows
            if r.is_empty and current_price <= r.buy_price
        ]

    def get_sell_triggered(self, current_price: Decimal) -> List[GridRow]:
        """현재가 이상의 sell_price를 가진 보유 슬롯 (매도 조건 충족)"""
        return [
            r for r in self.rows
            if r.is_holding and current_price >= self.effective_sell_price(r.index)
        ]

    def apply_buy(
        self,
        slot_index: int,
        filled_qty: Decimal | None = None,
        *,
        filled_at: datetime | None = None,
    ):
        """매수 체결: 실제 체결 수량을 보유 슬롯에 반영"""
        row = self._get_row(slot_index)
        if row and row.is_empty:
            row.held_qty = filled_qty if filled_qty is not None else row.planned_qty
            row.filled_at = self._normalize_timestamp(filled_at) or datetime.now(timezone.utc)

    def apply_sell(self, slot_index: int, filled_qty: Decimal | None = None):
        """매도 체결: 전량 또는 부분 체결을 보유 슬롯에 반영"""
        row = self._get_row(slot_index)
        if row and row.is_holding:
            if filled_qty is not None and filled_qty > DECIMAL_ZERO and filled_qty < row.held_qty:
                row.held_qty -= filled_qty
                return
            if row.planned_qty <= DECIMAL_ZERO:
                reference_qty = self._get_uniform_planned_qty()
                row.planned_qty = reference_qty if reference_qty is not None else row.held_qty
            row.held_qty = DECIMAL_ZERO
            row.filled_at = None

    def band_position_z(
        self,
        current_price: Decimal,
        *,
        lower_price: Decimal | None = None,
        upper_price: Decimal | None = None,
    ) -> Decimal:
        """현재가의 밴드 내 로그 위치 z를 [0, 1] 범위로 반환한다."""
        bounds = self._resolve_band_bounds(lower_price=lower_price, upper_price=upper_price)
        if bounds is None or current_price <= DECIMAL_ZERO:
            return DECIMAL_ZERO

        lower, upper = bounds
        if current_price <= lower:
            return DECIMAL_ZERO
        if current_price >= upper:
            return Decimal("1")

        z = (log(float(current_price)) - log(float(lower))) / (
            log(float(upper)) - log(float(lower))
        )
        return Decimal(str(z))

    def current_inventory_ratio(
        self,
        *,
        operating_budget_krw: Decimal | None = None,
        inventory_cost_krw: Decimal | None = None,
    ) -> Decimal:
        """현재 보유 재고의 원가 기준 비율 q_current."""
        budget = self._resolve_operating_budget(operating_budget_krw)
        if budget <= DECIMAL_ZERO:
            return DECIMAL_ZERO

        inventory_cost = self.current_inventory_cost if inventory_cost_krw is None else inventory_cost_krw
        return inventory_cost / budget

    def target_inventory_ratio(
        self,
        current_price: Decimal,
        *,
        q_min: Decimal | None = None,
        q_max: Decimal | None = None,
        gamma: Decimal | None = None,
        lower_price: Decimal | None = None,
        upper_price: Decimal | None = None,
    ) -> Decimal:
        """현재 가격 위치 z에서의 목표 재고 비율 q_target(z)."""
        minimum, maximum, exponent = self._resolve_inventory_target_params(
            q_min=q_min,
            q_max=q_max,
            gamma=gamma,
        )
        z = self.band_position_z(
            current_price,
            lower_price=lower_price,
            upper_price=upper_price,
        )
        scaled_gap = Decimal(str((1 - float(z)) ** float(exponent)))
        target = minimum + (maximum - minimum) * scaled_gap
        if target < minimum:
            return minimum
        if target > maximum:
            return maximum
        return target

    def active_window_slot_indexes(
        self,
        reference_price: Decimal,
        *,
        below_current_slots: int,
        above_current_slots: int,
    ) -> set[int]:
        """기준 가격 주변에서 활성화할 빈 슬롯 인덱스를 계산한다."""
        if reference_price <= DECIMAL_ZERO:
            return set()

        empty_rows = [row for row in self.rows if row.is_empty]
        if not empty_rows:
            return set()

        lower_count = max(int(below_current_slots), 0)
        upper_count = max(int(above_current_slots), 0)

        below_rows = sorted(
            (row for row in empty_rows if row.buy_price <= reference_price),
            key=lambda row: (-row.buy_price, row.index),
        )
        above_rows = sorted(
            (row for row in empty_rows if row.buy_price > reference_price),
            key=lambda row: (row.buy_price, row.index),
        )

        active_rows = below_rows[:lower_count] + above_rows[:upper_count]
        return {row.index for row in active_rows}

    def effective_tp_k(
        self,
        slot_index: int,
        *,
        now: datetime | None = None,
        tp_k_base: Decimal | None = None,
        tp_k_floor: Decimal | None = None,
    ) -> Decimal:
        row = self._require_row(slot_index)
        base_k, floor_k = resolve_tp_k_values(tp_k_base, tp_k_floor)
        filled_at = self._normalize_timestamp(row.filled_at)
        if not row.is_holding or filled_at is None:
            return base_k

        current_time = self._normalize_timestamp(now) or datetime.now(timezone.utc)
        age = current_time - filled_at
        effective_k = base_k
        if age >= timedelta(days=7):
            effective_k -= Decimal("1.0")
        elif age >= timedelta(hours=48):
            effective_k -= Decimal("0.5")

        return effective_k if effective_k >= floor_k else floor_k

    def effective_sell_price(
        self,
        slot_index: int,
        *,
        now: datetime | None = None,
        tp_model: str | None = None,
        tp_k_base: Decimal | None = None,
        tp_k_floor: Decimal | None = None,
    ) -> Decimal:
        row = self._require_row(slot_index)
        if not self.is_age_compressed_tp_active(
            slot_index,
            tp_model=tp_model,
            tp_k_base=tp_k_base,
            tp_k_floor=tp_k_floor,
        ):
            return row.sell_price

        base_k, _ = resolve_tp_k_values(tp_k_base, tp_k_floor)
        effective_k = self.effective_tp_k(
            slot_index,
            now=now,
            tp_k_base=tp_k_base,
            tp_k_floor=tp_k_floor,
        )
        if effective_k >= base_k or row.buy_price <= DECIMAL_ZERO or row.sell_price <= row.buy_price:
            return row.sell_price

        base_log_gap = Decimal(str(log(float(row.sell_price / row.buy_price))))
        compressed_log_gap = base_log_gap * effective_k / base_k
        raw_sell_price = row.buy_price * Decimal(str(exp(float(compressed_log_gap))))
        compressed_sell_price = normalize_krw_price(raw_sell_price)
        if compressed_sell_price <= row.buy_price:
            return row.sell_price
        if compressed_sell_price >= row.sell_price:
            return row.sell_price
        return compressed_sell_price

    def is_age_compressed_tp_active(
        self,
        slot_index: int,
        *,
        tp_model: str | None = None,
        tp_k_base: Decimal | None = None,
        tp_k_floor: Decimal | None = None,
    ) -> bool:
        row = self._require_row(slot_index)
        if not row.is_holding or row.filled_at is None:
            return False

        try:
            model = normalize_tp_model(tp_model)
        except ValueError:
            return False
        if model != "k":
            return False
        return self._matches_current_k_grid(
            tp_k_base=tp_k_base,
            tp_k_floor=tp_k_floor,
        )

    def build_recenter_preview(
        self,
        *,
        current_price: Decimal,
        breakout_duration: timedelta,
        open_buy_order_count: int,
        min_breakout_duration: timedelta = timedelta(hours=24),
        max_inventory_ratio: Decimal = Decimal("0.20"),
    ):
        candle_unit_minutes = 15
        required_breakout_candles = max(
            int(min_breakout_duration.total_seconds() // (candle_unit_minutes * 60)),
            1,
        )
        breakout_run_count = max(
            int(breakout_duration.total_seconds() // (candle_unit_minutes * 60)),
            0,
        )
        bounds = self._resolve_band_bounds()
        close_prices = self._synthetic_breakout_closes(
            current_price=current_price,
            breakout_run_count=breakout_run_count,
            required_breakout_candles=required_breakout_candles,
            bounds=bounds,
        )
        return evaluate_recenter_preview(
            self.rows,
            current_price=current_price,
            close_prices=close_prices,
            open_buy_order_count=open_buy_order_count,
            breakout_candle_count=required_breakout_candles,
            candle_unit_minutes=candle_unit_minutes,
            inventory_ratio_threshold=max_inventory_ratio,
            operating_budget_krw=cfg.MAX_OPERATING_BUDGET_KRW,
        )

    def _get_row(self, slot_index: int) -> Optional[GridRow]:
        for row in self.rows:
            if row.index == slot_index:
                return row
        return None

    def _require_row(self, slot_index: int) -> GridRow:
        row = self._get_row(slot_index)
        if row is None:
            raise ValueError(f"존재하지 않는 슬롯입니다: {slot_index}")
        return row

    def _resolve_band_bounds(
        self,
        *,
        lower_price: Decimal | None = None,
        upper_price: Decimal | None = None,
    ) -> tuple[Decimal, Decimal] | None:
        lower = lower_price
        upper = upper_price

        if lower is None:
            buy_prices = [row.buy_price for row in self.rows if row.buy_price > DECIMAL_ZERO]
            if buy_prices:
                lower = min(buy_prices)
            elif cfg.GRID_LOWER_PRICE > DECIMAL_ZERO:
                lower = cfg.GRID_LOWER_PRICE

        if upper is None:
            upper_candidates = [row.buy_price for row in self.rows if row.buy_price > DECIMAL_ZERO]
            if upper_candidates:
                upper = max(upper_candidates)
            elif cfg.GRID_UPPER_PRICE > DECIMAL_ZERO:
                upper = cfg.GRID_UPPER_PRICE

        if lower is None or upper is None or lower <= DECIMAL_ZERO or upper <= lower:
            return None
        return lower, upper

    def _resolve_operating_budget(self, operating_budget_krw: Decimal | None) -> Decimal:
        if operating_budget_krw is not None and operating_budget_krw > DECIMAL_ZERO:
            return operating_budget_krw
        if self.total_allocated_budget > DECIMAL_ZERO:
            return self.total_allocated_budget
        if cfg.MAX_OPERATING_BUDGET_KRW is not None and cfg.MAX_OPERATING_BUDGET_KRW > DECIMAL_ZERO:
            return cfg.MAX_OPERATING_BUDGET_KRW
        return DECIMAL_ZERO

    def _resolve_inventory_target_params(
        self,
        *,
        q_min: Decimal | None,
        q_max: Decimal | None,
        gamma: Decimal | None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        minimum = cfg.INVENTORY_TARGET_Q_MIN if q_min is None else q_min
        maximum = cfg.INVENTORY_TARGET_Q_MAX if q_max is None else q_max
        exponent = cfg.INVENTORY_TARGET_GAMMA if gamma is None else gamma

        if minimum < DECIMAL_ZERO:
            minimum = DECIMAL_ZERO
        if maximum < minimum:
            maximum = minimum
        if exponent <= DECIMAL_ZERO:
            exponent = Decimal("1")
        return minimum, maximum, exponent

    def _get_uniform_planned_qty(self) -> Optional[Decimal]:
        quantities = {row.planned_qty for row in self.rows if row.planned_qty > DECIMAL_ZERO}
        if len(quantities) == 1:
            return next(iter(quantities))
        return None

    def _matches_current_k_grid(
        self,
        *,
        tp_k_base: Decimal | None,
        tp_k_floor: Decimal | None,
    ) -> bool:
        comparable_rows = [
            row for row in self.rows
            if row.buy_price > DECIMAL_ZERO and row.sell_price > row.buy_price
        ]
        if not comparable_rows:
            return False
        if len(comparable_rows) == 1:
            return True

        bounds = self._resolve_band_bounds()
        if bounds is None:
            return False
        lower_price, upper_price = bounds

        interval_candidates = {
            interval for interval in {len(self.rows), len(self.rows) - 1}
            if interval > 0
        }
        for interval_count in interval_candidates:
            try:
                if all(
                    build_sell_price_from_k(
                        row.buy_price,
                        lower_price=lower_price,
                        upper_price=upper_price,
                        price_interval_count=interval_count,
                        tp_k=tp_k_base,
                        tp_k_floor=tp_k_floor,
                    ) == row.sell_price
                    for row in comparable_rows
                ):
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _synthetic_breakout_closes(
        *,
        current_price: Decimal,
        breakout_run_count: int,
        required_breakout_candles: int,
        bounds: tuple[Decimal, Decimal] | None,
    ) -> list[Decimal]:
        if bounds is None or required_breakout_candles <= 0:
            return []
        lower_price, upper_price = bounds
        if current_price > upper_price:
            outside_price = current_price
            inside_price = upper_price
        elif current_price < lower_price:
            outside_price = current_price
            inside_price = lower_price
        else:
            outside_price = current_price
            inside_price = current_price

        closes = [outside_price] * breakout_run_count
        closes.extend([inside_price] * max(required_breakout_candles - breakout_run_count, 0))
        return closes

    @staticmethod
    def _normalize_timestamp(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def summary(self) -> str:
        holding = [r for r in self.rows if r.is_holding]
        empty = [r for r in self.rows if r.is_empty]
        return (
            f"심볼: {self.symbol} | 전체 슬롯: {len(self.rows)} | "
            f"보유: {len(holding)} | 빈슬롯: {len(empty)} | "
            f"총재고: {format_decimal(self.total_inventory)} | "
            f"총배정금액: {format_decimal(self.total_allocated_budget)} KRW"
        )
