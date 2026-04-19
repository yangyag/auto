"""
그리드 도메인 상태 관리
"""
from math import log
from dataclasses import replace
from decimal import Decimal
from typing import List, Optional

import config.settings as cfg
from core.models import GridRow
from storage.interfaces import GridSnapshot, RepositoryMetadata
from utils.decimal_utils import DECIMAL_ZERO, format_decimal


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
            if r.is_holding and current_price >= r.sell_price
        ]

    def apply_buy(self, slot_index: int, filled_qty: Decimal | None = None):
        """매수 체결: 실제 체결 수량을 보유 슬롯에 반영"""
        row = self._get_row(slot_index)
        if row and row.is_empty:
            row.held_qty = filled_qty if filled_qty is not None else row.planned_qty

    def apply_sell(self, slot_index: int):
        """매도 체결: 보유 중 → 빈 슬롯으로 전환"""
        row = self._get_row(slot_index)
        if row and row.is_holding:
            if row.planned_qty <= DECIMAL_ZERO:
                reference_qty = self._get_uniform_planned_qty()
                row.planned_qty = reference_qty if reference_qty is not None else row.held_qty
            row.held_qty = DECIMAL_ZERO

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

    def _get_row(self, slot_index: int) -> Optional[GridRow]:
        for row in self.rows:
            if row.index == slot_index:
                return row
        return None

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

    def summary(self) -> str:
        holding = [r for r in self.rows if r.is_holding]
        empty = [r for r in self.rows if r.is_empty]
        return (
            f"심볼: {self.symbol} | 전체 슬롯: {len(self.rows)} | "
            f"보유: {len(holding)} | 빈슬롯: {len(empty)} | "
            f"총재고: {format_decimal(self.total_inventory)} | "
            f"총배정금액: {format_decimal(self.total_allocated_budget)} KRW"
        )
