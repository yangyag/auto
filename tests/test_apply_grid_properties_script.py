import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from core.grid_properties import build_sell_price
from storage.postgres_grid_repository import PostgresGridRepository
from tests.postgres_test_utils import (
    PostgresIntegrationTestCase,
    apply_test_schema,
    drop_test_schema,
    postgres_test_config,
)


class ApplyGridPropertiesScriptTest(PostgresIntegrationTestCase):
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
        with tempfile.TemporaryDirectory() as tmpdir:
            properties_path = Path(tmpdir) / "grid.properties"
            properties_path.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nBUY_AMOUNT_KRW=200000\nGRID_COUNT=20\nSELL_PERCENT=5\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                self._script_args(
                    "--properties-file",
                    str(properties_path),
                ),
                cwd=self.project_root,
                env=self.env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        repository = PostgresGridRepository.from_config(self.config)
        snapshot = repository.load()
        self.assertEqual(snapshot.symbol, "KRW-BTC")
        self.assertEqual(len(snapshot.rows), 20)
        self.assertEqual(snapshot.rows[0].buy_price, Decimal("127886000"))
        self.assertEqual(snapshot.rows[-1].buy_price, Decimal("91623000"))
        self.assertEqual(snapshot.rows[0].sell_price, build_sell_price(snapshot.rows[0].buy_price, Decimal("5")))
        self.assertEqual(snapshot.rows[1].sell_price, build_sell_price(snapshot.rows[1].buy_price, Decimal("5")))
        self.assertGreater(snapshot.rows[0].sell_price, snapshot.rows[0].buy_price)
        self.assertIn("rows: 20", result.stdout)
        self.assertIn("top_buy_price: 127886000", result.stdout)
        self.assertIn("bottom_buy_price: 91623000", result.stdout)

    def test_script_uses_project_root_grid_properties_when_run_from_scripts_dir(self):
        project_properties = self.project_root / "grid.properties"
        original = project_properties.read_text(encoding="utf-8") if project_properties.exists() else None
        try:
            project_properties.write_text(
                "MIN_BUY_PRICE=91623000\nMAX_BUY_PRICE=127886000\nBUY_AMOUNT_KRW=200000\nGRID_COUNT=20\nSELL_PERCENT=5\n",
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


if __name__ == "__main__":
    unittest.main()
