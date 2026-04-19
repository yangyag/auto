import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import scripts.export_postgres_grid as export_postgres_grid
from core.models import GridRow
from storage.interfaces import GridSnapshot, RepositoryMetadata


class ExportPostgresGridTest(unittest.TestCase):

    def test_render_grid_text_formats_snapshot(self):
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(
                GridRow(1, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1")),
                GridRow(2, Decimal("90"), Decimal("0.25"), Decimal("94.5"), Decimal("0.5")),
            ),
            metadata=RepositoryMetadata(version=3, revision="rev-3"),
        )

        text = export_postgres_grid.render_grid_text(snapshot)

        self.assertEqual(
            text,
            "Grid3 KRW-BTC\n"
            "1) 100 0 105 1\n"
            "2) 90 0.25 94.5 0.5\n"
            "\n"
            "테이블 총재고 : 0.25\n"
            "총 계획매수금액 : 145\n"
            "최상단 슬롯 계획매수금액 : 100\n"
            "최하단 슬롯 계획매수금액 : 45",
        )

    def test_main_writes_rendered_snapshot_to_output_file(self):
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(GridRow(1, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1")),),
            metadata=RepositoryMetadata(version=3, revision="rev-3"),
        )
        fake_repository = type("FakeRepository", (), {"load": lambda self: snapshot})()

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            export_postgres_grid,
            "PostgresGridRepository",
            return_value=fake_repository,
        ):
            output_path = Path(tmpdir) / "grid.postgres-export.txt"
            exit_code = export_postgres_grid.main(
                [
                    "--output",
                    str(output_path),
                    "--bot-key",
                    "krw-btc-live",
                    "--schema",
                    "auto_trading",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5432",
                    "--dbname",
                    "yangyag",
                    "--user",
                    "yangyag",
                    "--password",
                    "",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                export_postgres_grid.render_grid_text(snapshot),
            )


if __name__ == "__main__":
    unittest.main()
