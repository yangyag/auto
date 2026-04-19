import unittest

from storage.factory import build_grid_repository, build_pending_order_repository
from storage.postgres_grid_repository import PostgresGridRepository
from storage.postgres_order_repository import PostgresOrderRepository
from storage.postgres_common import require_psycopg


class StateFactoryTest(unittest.TestCase):

    def test_factory_builds_postgres_repositories_from_config(self):
        try:
            require_psycopg()
        except ModuleNotFoundError as exc:
            self.skipTest(f"postgres integration prerequisites unavailable: {exc}")
        config = type(
            "Config",
            (),
            {
                "STATE_BOT_KEY": "test-bot",
                "PGHOST": "127.0.0.1",
                "PGPORT": 5432,
                "PGDATABASE": "yangyag",
                "PGUSER": "yangyag",
                "PGPASSWORD": "secret",
                "PGSCHEMA": "auto_trading",
            },
        )()

        self.assertIsInstance(build_grid_repository(config), PostgresGridRepository)
        self.assertIsInstance(build_pending_order_repository(config), PostgresOrderRepository)
