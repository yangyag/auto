import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from core.grid_properties import build_target_sell_price
from storage.postgres_grid_repository import PostgresGridRepository
from tests.postgres_test_utils import (
    PostgresIntegrationTestCase,
    apply_test_schema,
    drop_test_schema,
    postgres_test_config,
)
from utils.decimal_utils import format_decimal


class ApplyGridPropertiesScriptTest(PostgresIntegrationTestCase):
    STEP_PCT_FOR_20_SLOTS = "1.770527625862"

    def _script_args(self, *extra_args):
        return [
            sys.executable,
            "scripts/apply_grid_properties_to_postgres.py",
            *extra_args,
            "--bot-key",
            self.config.STATE_BOT_KEY,
            "--schema",
            self.config.PGSCHEMA,
            "--host",
            self.config.PGHOST,
            "--port",
            str(self.config.PGPORT),
            "--dbname",
            self.config.PGDATABASE,
            "--user",
            self.config.PGUSER,
            "--password",
            self.config.PGPASSWORD,
            "--force",
        ]

    def _run_script_with_properties(self, properties_text, *, cwd=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            properties_path = Path(tmpdir) / "grid.properties"
            properties_path.write_text(properties_text, encoding="utf-8")
            result = subprocess.run(
                self._script_args(
                    "--properties-file",
                    str(properties_path),
                ),
                cwd=self.project_root if cwd is None else cwd,
                env=self.env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        repository = PostgresGridRepository.from_config(self.config)
        return result, repository.load()

    def _grid_signature(self, snapshot):
        return [
            (row.index, row.buy_price, row.sell_price, row.planned_qty)
            for row in snapshot.rows
        ]

    def _assert_20_slot_grid(self, snapshot):
        self.assertEqual(snapshot.symbol, "KRW-BTC")
        self.assertEqual(len(snapshot.rows), 20)
        self.assertEqual(snapshot.rows[0].buy_price, Decimal("127886000"))
        self.assertEqual(snapshot.rows[-1].buy_price, Decimal("91623000"))
        self.assertEqual(
            snapshot.rows[0].sell_price,
            build_target_sell_price(
                snapshot.rows[0].buy_price,
                tp_model="k",
                lower_price=Decimal("91623000"),
                upper_price=Decimal("127886000"),
                price_interval_count=19,
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
            ),
        )
        self.assertEqual(
            snapshot.rows[1].sell_price,
            build_target_sell_price(
                snapshot.rows[1].buy_price,
                tp_model="k",
                lower_price=Decimal("91623000"),
                upper_price=Decimal("127886000"),
                price_interval_count=19,
                tp_k=Decimal("9.0"),
                tp_k_floor=Decimal("7.0"),
            ),
        )
        self.assertGreater(snapshot.rows[-1].planned_qty, snapshot.rows[0].planned_qty)
        average_budget = Decimal("4000000") / Decimal("20")
        self.assertLess(snapshot.rows[0].buy_price * snapshot.rows[0].planned_qty, average_budget)
        self.assertGreater(snapshot.rows[-1].buy_price * snapshot.rows[-1].planned_qty, average_budget)
        self.assertGreater(snapshot.rows[0].sell_price, snapshot.rows[0].buy_price)
        top_budget = snapshot.rows[0].buy_price * snapshot.rows[0].planned_qty
        bottom_budget = snapshot.rows[-1].buy_price * snapshot.rows[-1].planned_qty
        total_budget = sum((row.buy_price * row.planned_qty for row in snapshot.rows), Decimal("0"))
        return top_budget, bottom_budget, total_budget

    def setUp(self):
        self.config = postgres_test_config()
        apply_test_schema(self.config.PGSCHEMA)
        self.project_root = Path(__file__).resolve().parents[1]
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(self.project_root)
        self.env["PGPASSWORD"] = self.config.PGPASSWORD

    def tearDown(self):
        drop_test_schema(self.config.PGSCHEMA)

    def test_script_reads_properties_and_writes_grid_to_postgres(self):
        step_pct_properties = (
            "MIN_BUY_PRICE=91623000\n"
            "MAX_BUY_PRICE=127886000\n"
            "TOTAL_BUDGET_KRW=4000000\n"
            f"GRID_STEP_PCT={self.STEP_PCT_FOR_20_SLOTS}\n"
        )
        count_properties = (
            "MIN_BUY_PRICE=91623000\n"
            "MAX_BUY_PRICE=127886000\n"
            "TOTAL_BUDGET_KRW=4000000\n"
            "GRID_COUNT=20\n"
        )

        step_result, step_snapshot = self._run_script_with_properties(step_pct_properties)
        count_result, count_snapshot = self._run_script_with_properties(count_properties)

        self.assertEqual(self._grid_signature(step_snapshot), self._grid_signature(count_snapshot))
        top_budget, bottom_budget, total_budget = self._assert_20_slot_grid(step_snapshot)
        self.assertIn("rows: 20", step_result.stdout)
        self.assertIn("top_buy_price: 127886000", step_result.stdout)
        self.assertIn("bottom_buy_price: 91623000", step_result.stdout)
        self.assertIn(f"planned_buy_budget_total: {format_decimal(total_budget)}", step_result.stdout)
        self.assertIn(f"top_slot_planned_buy_budget: {format_decimal(top_budget)}", step_result.stdout)
        self.assertIn(f"bottom_slot_planned_buy_budget: {format_decimal(bottom_budget)}", step_result.stdout)
        self.assertIn("rows: 20", count_result.stdout)

    def test_script_uses_project_root_grid_properties_when_run_from_scripts_dir(self):
        project_properties = self.project_root / "grid.properties"
        original = project_properties.read_text(encoding="utf-8") if project_properties.exists() else None
        try:
            project_properties.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nTOTAL_BUDGET_KRW=4000000\nGRID_COUNT=20\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "./apply_grid_properties_to_postgres.py",
                    "--bot-key",
                    self.config.STATE_BOT_KEY,
                    "--schema",
                    self.config.PGSCHEMA,
                    "--host",
                    self.config.PGHOST,
                    "--port",
                    str(self.config.PGPORT),
                    "--dbname",
                    self.config.PGDATABASE,
                    "--user",
                    self.config.PGUSER,
                    "--password",
                    self.config.PGPASSWORD,
                    "--force",
                ],
                cwd=self.project_root / "scripts",
                env=self.env,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            if original is None:
                project_properties.unlink(missing_ok=True)
            else:
                project_properties.write_text(original, encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("rows: 20", result.stdout)
        self.assertIn("planned_buy_budget_total:", result.stdout)
        self.assertIn("top_slot_planned_buy_budget:", result.stdout)
        self.assertIn("bottom_slot_planned_buy_budget:", result.stdout)


if __name__ == "__main__":
    unittest.main()
