import unittest
from decimal import Decimal
from unittest.mock import patch

import main
from core.grid import GridState
from core.models import GridRow


class RuntimeStateGuardTest(unittest.TestCase):
    def test_validate_runtime_grid_state_rejects_symbol_mismatch(self):
        grid_state = GridState.from_rows(
            "KRW-ETH",
            [GridRow(1, Decimal("100"), Decimal("0"), Decimal("110"), Decimal("1"))],
        )

        with self.assertRaises(ValueError):
            main.validate_runtime_grid_state(grid_state)

    def test_validate_runtime_grid_state_rejects_empty_postgres_snapshot(self):
        grid_state = GridState.from_rows("KRW-BTC", [])

        with patch.object(main.cfg, "STATE_BACKEND", "postgres"):
            with self.assertRaises(ValueError):
                main.validate_runtime_grid_state(grid_state)


if __name__ == "__main__":
    unittest.main()
