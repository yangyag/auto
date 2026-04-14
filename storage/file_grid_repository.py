import re
from dataclasses import replace
from pathlib import Path

from core.models import GridRow, Order
from storage.interfaces import GridSnapshot, GridStateRepository, PendingOrderRepository, RepositoryMetadata
from utils.decimal_utils import DECIMAL_ZERO, format_decimal, to_decimal


_GRID_ROW_PATTERN = re.compile(r"(\d+)\)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)")


def _copy_row(row: GridRow) -> GridRow:
    return replace(row)


def parse_grid_text(content: str) -> GridSnapshot:
    rows: list[GridRow] = []
    lines = content.splitlines()
    symbol = ""

    if lines and not lines[0].strip().startswith("1)"):
        header = lines[0].strip()
        parts = header.split()
        symbol = parts[-1] if parts else ""
        lines = lines[1:]

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        match = _GRID_ROW_PATTERN.match(line)
        if not match:
            continue
        rows.append(
            GridRow(
                index=int(match.group(1)),
                buy_price=to_decimal(match.group(2)),
                held_qty=to_decimal(match.group(3)),
                sell_price=to_decimal(match.group(4)),
                planned_qty=to_decimal(match.group(5)),
            )
        )

    return GridSnapshot(symbol=symbol, rows=tuple(rows))


def render_grid_text(snapshot: GridSnapshot) -> str:
    lines = [f"Grid3 {snapshot.symbol}"]
    for row in snapshot.rows:
        lines.append(
            f"{row.index}) {format_decimal(row.buy_price)} {format_decimal(row.held_qty)} "
            f"{format_decimal(row.sell_price)} {format_decimal(row.planned_qty)}"
        )

    total_inventory = sum((row.held_qty for row in snapshot.rows), DECIMAL_ZERO)
    lines.append("")
    lines.append(f"테이블 총재고 : {format_decimal(total_inventory)}")
    return "\n".join(lines)


class FileGridRepository(GridStateRepository):

    def __init__(self, grid_file: str = "grid.txt"):
        self.grid_file = Path(grid_file)

    def load(self) -> GridSnapshot:
        snapshot = parse_grid_text(self.grid_file.read_text(encoding="utf-8"))
        return GridSnapshot(
            symbol=snapshot.symbol,
            rows=tuple(_copy_row(row) for row in snapshot.rows),
            metadata=self._read_metadata(),
        )

    def save(self, snapshot: GridSnapshot) -> GridSnapshot:
        self.grid_file.write_text(render_grid_text(snapshot), encoding="utf-8")
        return GridSnapshot(
            symbol=snapshot.symbol,
            rows=tuple(_copy_row(row) for row in snapshot.rows),
            metadata=self._read_metadata(),
        )

    def has_changed(self, metadata: RepositoryMetadata | None) -> bool:
        if metadata is None:
            return True
        return metadata.version != self._read_metadata().version

    def _read_metadata(self) -> RepositoryMetadata:
        stat = self.grid_file.stat()
        return RepositoryMetadata(version=stat.st_mtime_ns, revision=str(self.grid_file))


class FilePendingOrderRepository(PendingOrderRepository):
    """파일 백엔드 이전 단계의 in-memory stub."""

    def __init__(self):
        self._orders: dict[str, Order] = {}

    def add(self, order: Order) -> None:
        if not order.order_id:
            raise ValueError("order_id 없는 주문은 저장할 수 없습니다.")
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def remove(self, order_id: str) -> None:
        self._orders.pop(order_id, None)

    def mark_filled(self, order_id: str) -> None:
        self.remove(order_id)

    def mark_cancelled(self, order_id: str) -> None:
        self.remove(order_id)

    def list_open(self) -> list[Order]:
        return list(self._orders.values())
