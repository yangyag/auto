import unittest
from decimal import Decimal

from core.models import GridRow
from storage.interfaces import GridSnapshot, RepositoryMetadata
from storage.postgres_grid_repository import PostgresGridRepository
from tests.postgres_test_utils import (
    PostgresIntegrationTestCase,
    apply_test_schema,
    drop_test_schema,
    postgres_test_config,
)


class PostgresGridRepositoryTest(PostgresIntegrationTestCase):
    def setUp(self):
        self.config = postgres_test_config()
        apply_test_schema(self.config.PGSCHEMA)
        self.repository = PostgresGridRepository.from_config(self.config)

    def tearDown(self):
        drop_test_schema(self.config.PGSCHEMA)

    def test_save_then_load_round_trips_grid_snapshot(self):
        snapshot = self.repository.save(
            GridSnapshot(
                symbol="KRW-BTC",
                rows=(
                    GridRow(1, Decimal("100"), Decimal("0"), Decimal("110"), Decimal("1.23456789")),
                    GridRow(2, Decimal("90"), Decimal("0.5"), Decimal("100"), Decimal("0.5")),
                ),
            )
        )

        loaded = self.repository.load()

        self.assertEqual(snapshot.metadata.version, 1)
        self.assertEqual(loaded.symbol, "KRW-BTC")
        self.assertEqual(len(loaded.rows), 2)
        self.assertEqual(loaded.rows[0].planned_qty, Decimal("1.23456789"))
        self.assertEqual(loaded.rows[1].held_qty, Decimal("0.5"))

    def test_has_changed_uses_version_column(self):
        first = self.repository.save(
            GridSnapshot(
                symbol="KRW-BTC",
                rows=(GridRow(1, Decimal("100"), Decimal("0"), Decimal("110"), Decimal("1")),),
            )
        )
        self.assertFalse(self.repository.has_changed(first.metadata))

        self.repository.save(
            GridSnapshot(
                symbol="KRW-BTC",
                rows=(GridRow(1, Decimal("200"), Decimal("0"), Decimal("210"), Decimal("2")),),
            )
        )
        self.assertTrue(self.repository.has_changed(first.metadata))

    def test_save_rejects_stale_expected_version(self):
        first = self.repository.save(
            GridSnapshot(
                symbol="KRW-BTC",
                rows=(GridRow(1, Decimal("100"), Decimal("0"), Decimal("110"), Decimal("1")),),
            )
        )
        self.repository.save(
            GridSnapshot(
                symbol="KRW-BTC",
                rows=(GridRow(1, Decimal("200"), Decimal("0"), Decimal("210"), Decimal("2")),),
                metadata=first.metadata,
            )
        )

        with self.assertRaises(ValueError):
            self.repository.save(
                GridSnapshot(
                    symbol="KRW-BTC",
                    rows=(GridRow(1, Decimal("300"), Decimal("0"), Decimal("310"), Decimal("3")),),
                    metadata=RepositoryMetadata(version=first.metadata.version),
                )
            )


if __name__ == "__main__":
    unittest.main()
