import os
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from core.models import GridRow
from storage.file_grid_repository import FileGridRepository
from storage.interfaces import GridSnapshot


INITIAL_GRID = """Grid3 KRW-BTC
1) 100 0 110 1

테이블 총재고 : 0"""

UPDATED_GRID = """Grid3 KRW-BTC
1) 200 0 210 2

테이블 총재고 : 0"""


class FileGridRepositoryTest(unittest.TestCase):

    def test_load_parses_grid_txt_and_returns_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir) / "grid.txt"
            grid_path.write_text(INITIAL_GRID, encoding="utf-8")
            repository = FileGridRepository(str(grid_path))

            snapshot = repository.load()

            self.assertEqual(snapshot.symbol, "KRW-BTC")
            self.assertEqual(len(snapshot.rows), 1)
            self.assertEqual(snapshot.rows[0].buy_price, Decimal("100"))
            self.assertIsNotNone(snapshot.metadata.version)
            self.assertEqual(snapshot.metadata.revision, str(grid_path))

    def test_save_preserves_existing_grid_txt_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir) / "grid.txt"
            repository = FileGridRepository(str(grid_path))
            snapshot = GridSnapshot(
                symbol="KRW-BTC",
                rows=(
                    GridRow(
                        index=1,
                        buy_price=Decimal("100"),
                        held_qty=Decimal("0"),
                        sell_price=Decimal("110"),
                        planned_qty=Decimal("1"),
                    ),
                ),
            )

            repository.save(snapshot)

            self.assertEqual(grid_path.read_text(encoding="utf-8"), INITIAL_GRID)

    def test_has_changed_uses_file_mtime_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir) / "grid.txt"
            repository = FileGridRepository(str(grid_path))
            saved_snapshot = repository.save(
                GridSnapshot(
                    symbol="KRW-BTC",
                    rows=(
                        GridRow(
                            index=1,
                            buy_price=Decimal("100"),
                            held_qty=Decimal("0"),
                            sell_price=Decimal("110"),
                            planned_qty=Decimal("1"),
                        ),
                    ),
                )
            )

            self.assertFalse(repository.has_changed(saved_snapshot.metadata))

            time.sleep(0.02)
            grid_path.write_text(UPDATED_GRID, encoding="utf-8")
            os.utime(grid_path, None)

            self.assertTrue(repository.has_changed(saved_snapshot.metadata))
