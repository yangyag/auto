import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import patch

import scripts.show_grid_state as show_grid_state
from core.models import GridRow
from storage.interfaces import GridSnapshot, RepositoryMetadata


class ShowGridStateScriptTest(unittest.TestCase):

    def test_main_prints_postgres_grid_snapshot(self):
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(
                GridRow(1, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1")),
                GridRow(2, Decimal("90"), Decimal("0.25"), Decimal("94.5"), Decimal("0.5")),
            ),
            metadata=RepositoryMetadata(version=7, revision="rev-7"),
        )

        fake_repository = type("FakeRepository", (), {"load": lambda self: snapshot})()

        with patch.object(show_grid_state.cfg, "PGSCHEMA", "auto_trading"), patch.object(
            show_grid_state.cfg,
            "STATE_BOT_KEY",
            "krw-btc-live",
        ), patch.object(
            show_grid_state,
            "build_grid_repository",
            return_value=fake_repository,
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = show_grid_state.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("상태: 성공", output)
        self.assertIn("backend: postgres", output)
        self.assertIn("source: postgres:auto_trading/krw-btc-live", output)
        self.assertIn("symbol: KRW-BTC", output)
        self.assertIn("rows: 2", output)
        self.assertIn("total_inventory: 0.25", output)
        self.assertIn("planned_buy_budget_total: 145", output)
        self.assertIn("top_slot_planned_buy_budget: 100", output)
        self.assertIn("bottom_slot_planned_buy_budget: 45", output)
        self.assertIn("slot | buy | held | sell | planned | planned_krw | status", output)
        self.assertIn(
            "1) buy=             100 held=               0 sell=             105 planned=               1 planned_krw=             100 status=empty",
            output,
        )
        self.assertIn(
            "2) buy=              90 held=            0.25 sell=            94.5 planned=             0.5 planned_krw=              45 status=holding",
            output,
        )

    def test_main_uses_repository_loader_for_postgres_backend(self):
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(GridRow(1, Decimal("100"), Decimal("0.1"), Decimal("105"), Decimal("1")),),
            metadata=RepositoryMetadata(version=7, revision="rev-7"),
        )

        fake_repository = type("FakeRepository", (), {"load": lambda self: snapshot})()

        with patch.object(show_grid_state.cfg, "PGSCHEMA", "auto_trading"), patch.object(
            show_grid_state.cfg,
            "STATE_BOT_KEY",
            "krw-btc-live",
        ), patch.object(
            show_grid_state,
            "build_grid_repository",
            return_value=fake_repository,
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = show_grid_state.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("backend: postgres", output)
        self.assertIn("source: postgres:auto_trading/krw-btc-live", output)
        self.assertIn("symbol: KRW-BTC", output)
        self.assertIn("rows: 1", output)
        self.assertIn("total_inventory: 0.1", output)
        self.assertIn("planned_buy_budget_total: 100", output)
        self.assertIn("top_slot_planned_buy_budget: 100", output)
        self.assertIn("bottom_slot_planned_buy_budget: 100", output)
        self.assertIn(
            "1) buy=             100 held=             0.1 sell=             105 planned=               1 planned_krw=             100 status=holding",
            output,
        )


if __name__ == "__main__":
    unittest.main()
