"""
그리드 도메인 상태 관리
"""
from dataclasses import replace
from decimal import Decimal
from typing import List, Optional

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

    def _get_row(self, slot_index: int) -> Optional[GridRow]:
        for row in self.rows:
            if row.index == slot_index:
                return row
        return None

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
