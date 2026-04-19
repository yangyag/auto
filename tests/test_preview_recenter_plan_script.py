import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import Mock, patch

import scripts.preview_recenter_plan as preview_recenter_plan
from core.models import GridRow, Order, OrderSide
from storage.interfaces import GridSnapshot, RepositoryMetadata


class PreviewRecenterPlanScriptTest(unittest.TestCase):

    def test_main_prints_preview_only_summary(self):
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(
                GridRow(1, Decimal("100"), Decimal("0.1"), Decimal("110"), Decimal("1")),
                GridRow(2, Decimal("90"), Decimal("0"), Decimal("99"), Decimal("1")),
            ),
            metadata=RepositoryMetadata(version=9, revision="rev-9"),
        )
        fake_grid_repository = type("FakeGridRepository", (), {"load": lambda self: snapshot})()
        fake_pending_repository = type(
            "FakePendingRepository",
            (),
            {
                "list_open": lambda self: [
                    Order(1, OrderSide.BUY, Decimal("100"), Decimal("0.1"), "KRW-BTC"),
                    Order(2, OrderSide.SELL, Decimal("110"), Decimal("0.1"), "KRW-BTC"),
                ]
            },
        )()
        exchange = Mock()
        exchange.get_current_price.return_value = Decimal("115")
        exchange.get_minute_candle_closes.return_value = [Decimal("115")] * 96

        with patch.object(
            preview_recenter_plan,
            "build_grid_repository",
            return_value=fake_grid_repository,
        ), patch.object(
            preview_recenter_plan,
            "build_pending_order_repository",
            return_value=fake_pending_repository,
        ), patch.object(
            preview_recenter_plan,
            "build_exchange",
            return_value=exchange,
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = preview_recenter_plan.main(["--symbol", "KRW-BTC"])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("상태: 성공", output)
        self.assertIn("mode: preview_only", output)
        self.assertIn("symbol: KRW-BTC", output)
        self.assertIn("status: blocked", output)
        self.assertIn("reason: open_buy_orders_present", output)
        self.assertIn("open_buy_orders: 1", output)
        self.assertIn("apply_supported: false", output)
        exchange.get_minute_candle_closes.assert_called_once()
        self.assertEqual(exchange.get_minute_candle_closes.call_args.kwargs["unit_minutes"], 15)
        self.assertEqual(exchange.get_minute_candle_closes.call_args.kwargs["count"], 96)
        self.assertIsNotNone(exchange.get_minute_candle_closes.call_args.kwargs["to"])

    def test_main_reports_failure_without_writing(self):
        with patch.object(
            preview_recenter_plan,
            "build_grid_repository",
            side_effect=RuntimeError("boom"),
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = preview_recenter_plan.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("상태: 실패", output)
        self.assertIn("사유: boom", output)


if __name__ == "__main__":
    unittest.main()
