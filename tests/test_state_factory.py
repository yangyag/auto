import tempfile
import unittest
from pathlib import Path

from storage.factory import build_grid_repository, build_pending_order_repository
from storage.file_grid_repository import FileGridRepository, FilePendingOrderRepository
from storage.postgres_grid_repository import PostgresGridRepository
from storage.postgres_order_repository import PostgresOrderRepository
from storage.postgres_common import require_psycopg


class StateFactoryTest(unittest.TestCase):

    def test_factory_defaults_to_file_backend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir) / "grid.txt"
            config = type("Config", (), {"GRID_FILE": str(grid_path)})()

            grid_repository = build_grid_repository(config)
            pending_repository = build_pending_order_repository(config)

            self.assertIsInstance(grid_repository, FileGridRepository)
            self.assertEqual(grid_repository.grid_file, grid_path)
            self.assertIsInstance(pending_repository, FilePendingOrderRepository)

    def test_factory_raises_for_unknown_backend(self):
        config = type("Config", (), {"STATE_BACKEND": "unknown", "GRID_FILE": "grid.txt"})()

        with self.assertRaises(ValueError):
            build_grid_repository(config)

    def test_factory_builds_postgres_repositories_when_enabled(self):
        require_psycopg()
        config = type(
            "Config",
            (),
            {
                "STATE_BACKEND": "postgres",
                "STATE_BOT_KEY": "test-bot",
                "PGHOST": "127.0.0.1",
                "PGPORT": 5432,
                "PGDATABASE": "yangyag",
                "PGUSER": "yangyag",
                "PGPASSWORD": "secret",
                "PGSCHEMA": "auto_trading",
                "GRID_FILE": "grid.txt",
            },
        )()

        self.assertIsInstance(build_grid_repository(config), PostgresGridRepository)
        self.assertIsInstance(build_pending_order_repository(config), PostgresOrderRepository)
