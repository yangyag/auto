import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_user
from app.api.main import create_app
from app.api.routers import pnl as pnl_router
from app.api.schemas.pnl import PnlBySlotResponse, SellLine, SlotPnlBucket
from app.api.services import pnl_service


KST = pnl_service.pnl.KST


def _today_kst_at(second: int) -> datetime:
    """period='d' 표시 윈도우(오늘 KST) 안에 드는 time_key 를 만든다."""
    today = datetime.now(KST).date()
    return datetime(today.year, today.month, today.day, 10, 0, second, tzinfo=KST)


def _realized_line(*, slot, sell_uuid, pnl_krw, qty, second):
    return {
        "time_key": _today_kst_at(second),
        "realized_pnl": Decimal(pnl_krw),
        "matched_qty": Decimal(qty),
        "sell_uuid": sell_uuid,
        "sell_trade_count": 1,
        "slot": slot,
    }


class MobileApiPnlBySlotRouteTest(unittest.TestCase):
    def test_by_slot_route_is_registered(self):
        app = create_app()
        routes = {route.path: route for route in app.routes}

        self.assertIn("/v1/pnl/by-slot", routes)

    def test_by_slot_router_enforces_auth_dependency(self):
        # 라우터 자체가 get_current_user 의존성을 강제하는지 확인
        dep_callables = [dep.dependency for dep in pnl_router.router.dependencies]
        self.assertIn(get_current_user, dep_callables)

    def test_missing_bearer_credentials_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_bearer_scheme_raises_401(self):
        creds = HTTPAuthorizationCredentials(scheme="Basic", credentials="abc")
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(creds)
        self.assertEqual(ctx.exception.status_code, 401)


class CalculatePnlBySlotTest(unittest.TestCase):
    def _patch_engine(self, realized_lines, grid_prices):
        """네트워크(fetch)·전처리·FIFO·DB(grid snapshot) 의존성을 모킹한다."""
        run_fifo_return = (realized_lines, [], [], [], {}, [])
        patches = [
            patch.object(pnl_service.cfg, "API_KEY", "test-key"),
            patch.object(pnl_service.cfg, "API_SECRET", "test-secret"),
            patch.object(pnl_service.pnl, "fetch_closed_orders", return_value=[]),
            patch.object(
                pnl_service.pnl, "prepare_sorted_orders", return_value=[]
            ),
            patch.object(pnl_service.pnl, "run_fifo", return_value=run_fifo_return),
            patch.object(
                pnl_service, "_load_grid_buy_prices", return_value=grid_prices
            ),
        ]
        return patches

    def _run(self, *, period, detail, realized_lines, grid_prices):
        for p in self._patch_engine(realized_lines, grid_prices):
            p.start()
            self.addCleanup(p.stop)
        return pnl_service.calculate_pnl_by_slot(period=period, detail=detail)

    def test_response_structure_aggregates_slots_and_total(self):
        realized_lines = [
            _realized_line(slot=2, sell_uuid="sell-a", pnl_krw="100", qty="0.01", second=1),
            _realized_line(slot=2, sell_uuid="sell-a", pnl_krw="50", qty="0.02", second=2),
            _realized_line(slot=1, sell_uuid="sell-c", pnl_krw="-30", qty="0.005", second=3),
        ]
        grid_prices = {1: Decimal("90000000"), 2: Decimal("95000000")}

        response = self._run(
            period="d",
            detail=False,
            realized_lines=realized_lines,
            grid_prices=grid_prices,
        )

        self.assertIsInstance(response, PnlBySlotResponse)
        self.assertEqual(response.period, "d")
        self.assertEqual(response.market, pnl_service.pnl.DEFAULT_MARKET)
        self.assertEqual(
            response.base_currency,
            pnl_service.pnl.market_base_currency(response.market),
        )

        # slots: slot 오름차순, 슬롯별 합산
        self.assertEqual([s.slot for s in response.slots], [1, 2])
        for slot in response.slots:
            self.assertIsInstance(slot, SlotPnlBucket)

        slot1, slot2 = response.slots
        self.assertEqual(slot1.realized_pnl_krw, Decimal("-30"))
        self.assertEqual(slot1.grid_buy_price, Decimal("90000000"))
        self.assertEqual(slot1.order_count, 1)
        self.assertEqual(slot1.matched_qty, Decimal("0.005"))

        self.assertEqual(slot2.realized_pnl_krw, Decimal("150"))
        self.assertEqual(slot2.grid_buy_price, Decimal("95000000"))
        self.assertEqual(slot2.order_count, 1)
        self.assertEqual(slot2.matched_qty, Decimal("0.03"))

        # 합계 = 슬롯 합산의 합
        self.assertEqual(response.total_realized_pnl_krw, Decimal("120"))

    def test_grid_buy_price_is_none_when_slot_missing_in_snapshot(self):
        realized_lines = [
            _realized_line(slot=9, sell_uuid="sell-x", pnl_krw="5", qty="0.001", second=1),
        ]

        response = self._run(
            period="d",
            detail=False,
            realized_lines=realized_lines,
            grid_prices={},
        )

        self.assertEqual(len(response.slots), 1)
        self.assertIsNone(response.slots[0].grid_buy_price)

    def test_detail_false_returns_empty_sells(self):
        realized_lines = [
            _realized_line(slot=1, sell_uuid="sell-a", pnl_krw="10", qty="0.001", second=1),
        ]

        response = self._run(
            period="d",
            detail=False,
            realized_lines=realized_lines,
            grid_prices={},
        )

        self.assertEqual(response.sells, [])

    def test_detail_true_populates_sell_lines(self):
        realized_lines = [
            _realized_line(slot=2, sell_uuid="sell-late", pnl_krw="30", qty="0.003", second=20),
            _realized_line(slot=1, sell_uuid="sell-early", pnl_krw="10", qty="0.001", second=5),
        ]

        response = self._run(
            period="d",
            detail=True,
            realized_lines=realized_lines,
            grid_prices={},
        )

        self.assertEqual(len(response.sells), 2)
        for sell in response.sells:
            self.assertIsInstance(sell, SellLine)
        # 시각 오름차순
        self.assertEqual(
            [s.sell_uuid for s in response.sells],
            ["sell-early", "sell-late"],
        )
        early = response.sells[0]
        self.assertEqual(early.slot, 1)
        self.assertEqual(early.matched_qty, Decimal("0.001"))
        self.assertEqual(early.realized_pnl_krw, Decimal("10"))
        # time 은 ISO 8601 문자열(오늘 KST 날짜)
        today_iso = datetime.now(KST).date().isoformat()
        self.assertTrue(early.time.startswith(f"{today_iso}T"))

    def test_empty_realized_lines_returns_empty_slots_and_zero_total(self):
        response = self._run(
            period="d",
            detail=True,
            realized_lines=[],
            grid_prices={},
        )

        self.assertEqual(response.slots, [])
        self.assertEqual(response.sells, [])
        self.assertEqual(response.total_realized_pnl_krw, Decimal("0"))

    def test_missing_api_credentials_raises_runtime_error(self):
        with patch.object(pnl_service.cfg, "API_KEY", ""), patch.object(
            pnl_service.cfg, "API_SECRET", ""
        ):
            with self.assertRaises(RuntimeError):
                pnl_service.calculate_pnl_by_slot(period="d", detail=False)


if __name__ == "__main__":
    unittest.main()
