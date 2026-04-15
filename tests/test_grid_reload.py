import unittest
from decimal import Decimal

from core.grid import GridState
from core.models import GridRow
from main import GridStateRuntime, refresh_grid_state_if_changed
from storage.interfaces import GridSnapshot, RepositoryMetadata


INITIAL_SNAPSHOT = GridSnapshot(
    symbol="KRW-BTC",
    rows=(
        GridRow(1, Decimal("100"), Decimal("0"), Decimal("110"), Decimal("1")),
    ),
    metadata=RepositoryMetadata(version=1, revision="rev-1"),
)

UPDATED_SNAPSHOT = GridSnapshot(
    symbol="KRW-BTC",
    rows=(
        GridRow(1, Decimal("200"), Decimal("0"), Decimal("210"), Decimal("2")),
    ),
    metadata=RepositoryMetadata(version=2, revision="rev-2"),
)


class InMemoryGridRepository:
    def __init__(self, snapshot: GridSnapshot):
        self.snapshot = snapshot

    def load(self) -> GridSnapshot:
        return self.snapshot

    def save(self, snapshot: GridSnapshot) -> GridSnapshot:
        self.snapshot = GridSnapshot(
            symbol=snapshot.symbol,
            rows=snapshot.rows,
            metadata=RepositoryMetadata(version=(snapshot.metadata.version or 0) + 1, revision="rev-saved"),
        )
        return self.snapshot

    def has_changed(self, metadata: RepositoryMetadata | None) -> bool:
        return metadata is None or metadata.version != self.snapshot.metadata.version


class GridReloadTest(unittest.TestCase):

    def test_refresh_grid_state_if_changed_refreshes_rows_from_repository(self):
        repository = InMemoryGridRepository(INITIAL_SNAPSHOT)
        snapshot = repository.load()
        state = GridState.from_snapshot(snapshot)
        runtime = GridStateRuntime(metadata=snapshot.metadata)

        repository.snapshot = UPDATED_SNAPSHOT

        changed = refresh_grid_state_if_changed(state, repository, runtime)

        self.assertTrue(changed)
        self.assertEqual(state.rows[0].buy_price, Decimal("200"))
        self.assertEqual(state.rows[0].sell_price, Decimal("210"))
        self.assertEqual(state.rows[0].planned_qty, Decimal("2"))

    def test_refresh_grid_state_if_changed_returns_true_for_external_grid_update(self):
        repository = InMemoryGridRepository(INITIAL_SNAPSHOT)
        snapshot = repository.load()
        state = GridState.from_snapshot(snapshot)
        runtime = GridStateRuntime(metadata=snapshot.metadata)

        repository.snapshot = UPDATED_SNAPSHOT

        changed = refresh_grid_state_if_changed(state, repository, runtime)

        self.assertTrue(changed)
        self.assertEqual(state.rows[0].buy_price, Decimal("200"))


if __name__ == "__main__":
    unittest.main()
