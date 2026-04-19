import unittest
from datetime import datetime, timezone
from decimal import Decimal

from core.models import GridRow
from storage.interfaces import GridSnapshot
from storage.postgres_grid_repository import PostgresGridRepository
from tests.postgres_test_utils import (
    PostgresIntegrationTestCase,
    apply_test_schema,
    drop_test_schema,
    postgres_test_config,
)


class Phase6GridStorageTest(PostgresIntegrationTestCase):
    def setUp(self):
        self.config = postgres_test_config()
        apply_test_schema(self.config.PGSCHEMA)
        self.repository = PostgresGridRepository.from_config(self.config)

    def tearDown(self):
        drop_test_schema(self.config.PGSCHEMA)

    def _make_row(
        self,
        *,
        index: int,
        buy_price: str,
        held_qty: str,
        sell_price: str,
        planned_qty: str,
        filled_at: datetime | None = None,
    ) -> GridRow:
        try:
            return GridRow(
                index=index,
                buy_price=Decimal(buy_price),
                held_qty=Decimal(held_qty),
                sell_price=Decimal(sell_price),
                planned_qty=Decimal(planned_qty),
                filled_at=filled_at,
            )
        except TypeError as exc:
            self.fail(f"Phase 6 GridRow should accept filled_at metadata: {exc}")

    def test_save_then_load_round_trips_filled_at_metadata_for_holding_slots(self):
        filled_at = datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc)
        self.repository.save(
            GridSnapshot(
                symbol="KRW-BTC",
                rows=(
                    self._make_row(
                        index=1,
                        buy_price="100",
                        held_qty="0",
                        sell_price="110",
                        planned_qty="1",
                        filled_at=None,
                    ),
                    self._make_row(
                        index=2,
                        buy_price="90",
                        held_qty="0.25",
                        sell_price="100",
                        planned_qty="0.25",
                        filled_at=filled_at,
                    ),
                ),
            )
        )

        loaded = self.repository.load()

        self.assertIsNone(loaded.rows[0].filled_at)
        self.assertEqual(loaded.rows[1].filled_at, filled_at)


if __name__ == "__main__":
    unittest.main()
