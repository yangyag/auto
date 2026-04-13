"""
grid.txt 파싱 및 그리드 상태 관리
"""
import re
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from core.models import GridRow
from utils.decimal_utils import DECIMAL_ZERO, format_decimal, to_decimal


class GridState:
    """그리드 전체 상태를 관리"""

    def __init__(self, grid_file: str = "grid.txt"):
        self.grid_file = Path(grid_file)
        self.rows: List[GridRow] = []
        self.symbol: str = ""
        self.load()

    @classmethod
    def from_rows(cls, symbol: str, rows: List[GridRow], grid_file: str = "grid.txt") -> "GridState":
        state = cls.__new__(cls)
        state.grid_file = Path(grid_file)
        state.rows = rows
        state.symbol = symbol
        return state

    def load(self):
        """grid.txt를 파싱해서 rows에 로드"""
        self.rows = []
        lines = self.grid_file.read_text(encoding="utf-8").splitlines()

        # 첫 줄: "Grid3 SOXL" 같은 헤더
        if lines and not lines[0].strip().startswith("1)"):
            header = lines[0].strip()
            parts = header.split()
            self.symbol = parts[-1] if parts else ""
            lines = lines[1:]

        # 각 줄 파싱: "1) 70.76 0 75.03 5"
        pattern = re.compile(r"(\d+)\)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = pattern.match(line)
            if m:
                self.rows.append(GridRow(
                    index=int(m.group(1)),
                    buy_price=to_decimal(m.group(2)),
                    held_qty=to_decimal(m.group(3)),
                    sell_price=to_decimal(m.group(4)),
                    planned_qty=to_decimal(m.group(5)),
                ))

    def save(self):
        """현재 rows 상태를 grid.txt에 다시 저장"""
        lines = [f"Grid3 {self.symbol}"]
        for row in self.rows:
            lines.append(
                f"{row.index}) {format_decimal(row.buy_price)} {format_decimal(row.held_qty)} "
                f"{format_decimal(row.sell_price)} {format_decimal(row.planned_qty)}"
            )
        total = self.total_inventory
        lines.append("")
        lines.append(f"테이블 총재고 : {format_decimal(total)}")
        self.grid_file.write_text("\n".join(lines), encoding="utf-8")

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

    def apply_buy(self, slot_index: int):
        """매수 체결: 빈 슬롯 → 보유 중으로 전환"""
        row = self._get_row(slot_index)
        if row and row.is_empty:
            row.held_qty = row.planned_qty
            row.planned_qty = DECIMAL_ZERO

    def apply_sell(self, slot_index: int):
        """매도 체결: 보유 중 → 빈 슬롯으로 전환"""
        row = self._get_row(slot_index)
        if row and row.is_holding:
            row.planned_qty = row.held_qty
            row.held_qty = DECIMAL_ZERO

    def _get_row(self, slot_index: int) -> Optional[GridRow]:
        for row in self.rows:
            if row.index == slot_index:
                return row
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
