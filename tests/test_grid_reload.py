import os
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from core.grid import GridState
from main import refresh_grid_state_if_changed


INITIAL_GRID = """Grid3 KRW-BTC
1) 100 0 110 1

테이블 총재고 : 0
"""

UPDATED_GRID = """Grid3 KRW-BTC
1) 200 0 210 2

테이블 총재고 : 0
"""


class GridReloadTest(unittest.TestCase):

    def test_grid_state_reload_if_changed_refreshes_rows_from_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir) / "grid.txt"
            grid_path.write_text(INITIAL_GRID, encoding="utf-8")
            state = GridState(str(grid_path))

            time.sleep(0.02)
            grid_path.write_text(UPDATED_GRID, encoding="utf-8")
            os.utime(grid_path, None)

            changed = state.reload_if_changed()

            self.assertTrue(changed)
            self.assertEqual(state.rows[0].buy_price, Decimal("200"))
            self.assertEqual(state.rows[0].sell_price, Decimal("210"))
            self.assertEqual(state.rows[0].planned_qty, Decimal("2"))

    def test_refresh_grid_state_if_changed_returns_true_for_external_grid_update(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir) / "grid.txt"
            grid_path.write_text(INITIAL_GRID, encoding="utf-8")
            state = GridState(str(grid_path))

            time.sleep(0.02)
            grid_path.write_text(UPDATED_GRID, encoding="utf-8")
            os.utime(grid_path, None)

            changed = refresh_grid_state_if_changed(state)

            self.assertTrue(changed)
            self.assertEqual(state.rows[0].buy_price, Decimal("200"))
