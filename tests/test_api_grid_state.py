import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.api.main import create_app
from app.api.services import grid_service
from app.core.models import GridRow, Order, OrderSide
from app.storage.interfaces import GridSnapshot, RepositoryMetadata


class _FakeGridRepository:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def load(self):
        return self._snapshot


class _FakePendingOrderRepository:
    def __init__(self, orders):
        self._orders = orders

    def list_open(self):
        return self._orders


class MobileApiGridStateTest(unittest.TestCase):
    def test_grid_state_route_is_registered(self):
        app = create_app()
        routes = {route.path: route for route in app.routes}

        self.assertIn("/v1/grid/state", routes)

    def test_grid_state_response_contains_slot_buy_and_holding_amounts(self):
        now = datetime(2026, 5, 12, tzinfo=timezone.utc)
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(
                GridRow(
                    index=1,
                    buy_price=Decimal("100"),
                    held_qty=Decimal("0.25"),
                    sell_price=Decimal("110"),
                    planned_qty=Decimal("0.50"),
                    filled_at=now,
                ),
                GridRow(
                    index=2,
                    buy_price=Decimal("90"),
                    held_qty=Decimal("0"),
                    sell_price=Decimal("99"),
                    planned_qty=Decimal("0.40"),
                ),
            ),
            metadata=RepositoryMetadata(version=3, revision="rev-1"),
        )
        pending_order = Order(
            slot_index=2,
            side=OrderSide.BUY,
            price=Decimal("90"),
            quantity=Decimal("0.40"),
            symbol="KRW-BTC",
            order_id="order-2",
            identifier="grid-2",
        )

        with patch.object(
            grid_service,
            "build_grid_repository",
            return_value=_FakeGridRepository(snapshot),
        ), patch.object(
            grid_service,
            "build_pending_order_repository",
            return_value=_FakePendingOrderRepository([pending_order]),
        ):
            response = grid_service.build_grid_state_response()

        self.assertEqual(response.symbol, "KRW-BTC")
        self.assertEqual(response.version, 3)
        self.assertEqual(response.revision, "rev-1")
        self.assertEqual(len(response.slots), 2)

        holding_slot = response.slots[0]
        self.assertEqual(holding_slot.status, "holding")
        self.assertEqual(holding_slot.buy_price, Decimal("100"))
        self.assertEqual(holding_slot.planned_qty, Decimal("0.50"))
        self.assertEqual(holding_slot.planned_buy_krw, Decimal("50.00"))
        self.assertEqual(holding_slot.held_qty, Decimal("0.25"))
        self.assertEqual(holding_slot.inventory_cost_krw, Decimal("25.00"))
        self.assertIsNone(holding_slot.pending_order)

        empty_slot = response.slots[1]
        self.assertEqual(empty_slot.status, "empty")
        self.assertEqual(empty_slot.buy_price, Decimal("90"))
        self.assertEqual(empty_slot.planned_qty, Decimal("0.40"))
        self.assertEqual(empty_slot.planned_buy_krw, Decimal("36.00"))
        self.assertEqual(empty_slot.held_qty, Decimal("0"))
        self.assertEqual(empty_slot.inventory_cost_krw, Decimal("0"))
        self.assertIsNotNone(empty_slot.pending_order)
        self.assertEqual(empty_slot.pending_order.order_id, "order-2")


if __name__ == "__main__":
    unittest.main()
