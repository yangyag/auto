"""손절 판정 로직 단위 테스트 및 통합 테스트."""
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.core.grid import GridState
from app.core.grid_properties import GridPropertySpec
from app.core.models import GridRow, Order, OrderSide, OrderExecutionType, OrderStatus
from app.strategy.stop_loss import (
    StopLossDecision,
    _resolve_stop_loss_threshold,
    evaluate_stop_loss,
    execute_stop_loss,
    StopLossExecutionResult,
)
from app.utils.decimal_utils import DECIMAL_ZERO


class StopLossThresholdTest(unittest.TestCase):
    def test_resolve_stop_loss_threshold_band_multiple_mode(self):
        lower = Decimal("100000000")
        upper = Decimal("120000000")
        result = _resolve_stop_loss_threshold(
            lower,
            upper,
            level=0,
            mode="band_multiple",
            band_multiple=Decimal("1.5"),
            l0_pct=Decimal("10"),
            l1_pct=Decimal("20"),
            l2_pct=Decimal("30"),
        )
        band_drop_ratio = Decimal("1") - lower / upper
        expected = lower * (Decimal("1") - Decimal("1.5") * band_drop_ratio)
        self.assertEqual(result, expected)
        self.assertLess(result, lower)

    def test_resolve_stop_loss_threshold_fixed_pct_l0(self):
        lower = Decimal("100000000")
        upper = Decimal("120000000")
        result = _resolve_stop_loss_threshold(
            lower,
            upper,
            level=0,
            mode="fixed_pct",
            band_multiple=None,
            l0_pct=Decimal("10"),
            l1_pct=Decimal("20"),
            l2_pct=Decimal("30"),
        )
        expected = lower * (Decimal("1") - Decimal("10") / Decimal("100"))
        self.assertEqual(result, expected)

    def test_resolve_stop_loss_threshold_fixed_pct_l2(self):
        lower = Decimal("100000000")
        upper = Decimal("120000000")
        result = _resolve_stop_loss_threshold(
            lower,
            upper,
            level=2,
            mode="fixed_pct",
            band_multiple=None,
            l0_pct=Decimal("10"),
            l1_pct=Decimal("20"),
            l2_pct=Decimal("30"),
        )
        expected = lower * (Decimal("1") - Decimal("30") / Decimal("100"))
        self.assertEqual(result, expected)

    def test_resolve_stop_loss_threshold_off_mode(self):
        lower = Decimal("100000000")
        upper = Decimal("120000000")
        result = _resolve_stop_loss_threshold(
            lower,
            upper,
            level=0,
            mode="off",
            band_multiple=None,
            l0_pct=None,
            l1_pct=None,
            l2_pct=None,
        )
        self.assertIsNone(result)

class EvaluateStopLossTest(unittest.TestCase):
    def setUp(self):
        rows = [
            GridRow(
                index=i,
                buy_price=Decimal("100000000") + Decimal("2000000") * i,
                held_qty=DECIMAL_ZERO,
                sell_price=Decimal("101000000") + Decimal("2000000") * i,
                planned_qty=Decimal("0.001"),
            )
            for i in range(10)
        ]
        self.grid_state = GridState(symbol="KRW-BTC", rows=rows)
        self.mock_exchange = MagicMock()

    def test_evaluate_stop_loss_off_mode(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="off",
        )

        result = evaluate_stop_loss(
            self.grid_state,
            Decimal("95000000"),
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertFalse(result.triggered)
        self.assertIsNone(result.level)
        self.mock_exchange.get_minute_candle_closes.assert_not_called()

    def test_evaluate_stop_loss_not_triggered_above_threshold(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="band_multiple",
            stop_loss_band_multiple=Decimal("1.5"),
            stop_loss_l0_pct=Decimal("10"),
            stop_loss_l1_pct=Decimal("20"),
            stop_loss_l2_pct=Decimal("30"),
        )

        result = evaluate_stop_loss(
            self.grid_state,
            Decimal("96000000"),
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertFalse(result.triggered)
        self.mock_exchange.get_minute_candle_closes.assert_not_called()

    def test_evaluate_stop_loss_triggers_at_l0_with_consecutive_closes(self):
        # fixed_pct 모드로 L0 단계 트리거 검증 (band_multiple 모드에선 L0/L1/L2 임계값이 동일)
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="fixed_pct",
            stop_loss_candle_unit=15,
            stop_loss_l0_pct=Decimal("10"),
            stop_loss_l1_pct=Decimal("20"),
            stop_loss_l2_pct=Decimal("30"),
            stop_loss_l0_consecutive_closes=4,
        )

        l0_threshold = Decimal("100000000") * (Decimal("1") - Decimal("10") / Decimal("100"))
        current_price = l0_threshold - Decimal("1000000")

        close_prices = (
            l0_threshold - Decimal("500000"),
            l0_threshold - Decimal("500000"),
            l0_threshold - Decimal("500000"),
            l0_threshold - Decimal("500000"),
        )

        self.mock_exchange.get_minute_candle_closes.return_value = close_prices

        result = evaluate_stop_loss(
            self.grid_state,
            current_price,
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertTrue(result.triggered)
        self.assertEqual(result.level, 0)
        self.mock_exchange.get_minute_candle_closes.assert_called_once_with("KRW-BTC", unit_minutes=15, count=4)

    def test_evaluate_stop_loss_triggers_at_l1_with_consecutive_closes(self):
        # fixed_pct 모드로 L1 단계 트리거 검증
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="fixed_pct",
            stop_loss_candle_unit=15,
            stop_loss_l0_pct=Decimal("10"),
            stop_loss_l1_pct=Decimal("20"),
            stop_loss_l2_pct=Decimal("30"),
            stop_loss_l1_consecutive_closes=4,
        )

        l0_threshold = Decimal("100000000") * (Decimal("1") - Decimal("10") / Decimal("100"))
        l1_threshold = Decimal("100000000") * (Decimal("1") - Decimal("20") / Decimal("100"))
        current_price = l1_threshold - Decimal("500000")

        close_prices = (
            l1_threshold - Decimal("1000000"),
            l1_threshold - Decimal("1000000"),
            l1_threshold - Decimal("1000000"),
            l1_threshold - Decimal("1000000"),
        )

        self.mock_exchange.get_minute_candle_closes.return_value = close_prices

        result = evaluate_stop_loss(
            self.grid_state,
            current_price,
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertTrue(result.triggered)
        self.assertEqual(result.level, 1)

    def test_evaluate_stop_loss_not_triggered_with_insufficient_candles(self):
        # fixed_pct 모드로 캔들 불충분 시 미발동 검증
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="fixed_pct",
            stop_loss_candle_unit=15,
            stop_loss_l0_pct=Decimal("10"),
            stop_loss_l1_pct=Decimal("20"),
            stop_loss_l2_pct=Decimal("30"),
            stop_loss_l2_consecutive_closes=2,
        )

        l2_threshold = Decimal("100000000") * (Decimal("1") - Decimal("30") / Decimal("100"))
        current_price = l2_threshold - Decimal("500000")

        close_prices = (
            l2_threshold + Decimal("1000000"),
            l2_threshold - Decimal("1000000"),
        )

        self.mock_exchange.get_minute_candle_closes.return_value = close_prices

        result = evaluate_stop_loss(
            self.grid_state,
            current_price,
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertFalse(result.triggered)
        self.assertEqual(result.level, None)

    def test_evaluate_stop_loss_includes_candle_prices_in_decision(self):
        # fixed_pct 모드로 캔들 종가 decision 포함 검증
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="fixed_pct",
            stop_loss_candle_unit=15,
            stop_loss_l0_pct=Decimal("10"),
            stop_loss_l1_pct=Decimal("20"),
            stop_loss_l2_pct=Decimal("30"),
            stop_loss_l0_consecutive_closes=4,
        )

        l0_threshold = Decimal("100000000") * (Decimal("1") - Decimal("10") / Decimal("100"))
        current_price = l0_threshold - Decimal("1000000")

        close_prices = (
            l0_threshold - Decimal("500000"),
            l0_threshold - Decimal("500000"),
            l0_threshold - Decimal("500000"),
            l0_threshold - Decimal("500000"),
        )

        self.mock_exchange.get_minute_candle_closes.return_value = close_prices

        result = evaluate_stop_loss(
            self.grid_state,
            current_price,
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertTrue(len(result.candle_close_prices) > 0)
        self.assertEqual(len(result.candle_close_prices), 4)

    def test_evaluate_stop_loss_triggers_at_l2_with_consecutive_closes(self):
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="band_multiple",
            stop_loss_band_multiple=Decimal("1.5"),
            stop_loss_candle_unit=15,
            stop_loss_l0_pct=Decimal("10"),
            stop_loss_l1_pct=Decimal("20"),
            stop_loss_l2_pct=Decimal("30"),
            stop_loss_l2_consecutive_closes=2,
        )

        l2_threshold = Decimal("100000000") * (Decimal("1") - Decimal("30") / Decimal("100"))
        current_price = l2_threshold - Decimal("1000000")

        close_prices = (
            l2_threshold - Decimal("1000000"),
            l2_threshold - Decimal("1000000"),
        )

        self.mock_exchange.get_minute_candle_closes.return_value = close_prices

        result = evaluate_stop_loss(
            self.grid_state,
            current_price,
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertTrue(result.triggered)
        self.assertEqual(result.level, 2)
        self.assertIsNotNone(result.armed_at)
        self.mock_exchange.get_minute_candle_closes.assert_called_once_with("KRW-BTC", unit_minutes=15, count=2)


    def test_evaluate_stop_loss_band_multiple_mode_without_pct_values(self):
        # band_multiple 모드에서 l*_pct=None이어도 정상 동작 (TypeErrorn 없어야 함)
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="band_multiple",
            stop_loss_band_multiple=Decimal("1.5"),
            stop_loss_candle_unit=15,
            stop_loss_l2_consecutive_closes=2,
        )
        # L=100M, U=120M, band_multiple=1.5 → threshold = 100M*(1-1.5*0.1667) = 75M
        band_threshold = Decimal("75000000")
        current_price = band_threshold - Decimal("1000000")

        close_prices = (
            band_threshold - Decimal("500000"),
            band_threshold - Decimal("500000"),
        )
        self.mock_exchange.get_minute_candle_closes.return_value = close_prices

        result = evaluate_stop_loss(
            self.grid_state,
            current_price,
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertTrue(result.triggered)
        self.assertEqual(result.level, 2)

    def test_evaluate_stop_loss_band_multiple_mode_above_threshold_not_triggered(self):
        # band_multiple 모드에서 임계값 위 가격 → 미발동
        spec = GridPropertySpec(
            min_buy_price=Decimal("100000000"),
            max_buy_price=Decimal("120000000"),
            total_budget_krw=Decimal("1000000"),
            grid_count=10,
            stop_loss_mode="band_multiple",
            stop_loss_band_multiple=Decimal("1.5"),
            stop_loss_candle_unit=15,
        )
        current_price = Decimal("80000000")  # 75M 임계값 위

        result = evaluate_stop_loss(
            self.grid_state,
            current_price,
            self.mock_exchange,
            spec,
            symbol="KRW-BTC",
        )

        self.assertFalse(result.triggered)
        self.mock_exchange.get_minute_candle_closes.assert_not_called()


class TestExecuteStopLoss(unittest.TestCase):
    """execute_stop_loss() 통합 테스트"""

    def setUp(self):
        """각 테스트마다 grid_state와 mock exchange 설정"""
        rows = [
            GridRow(
                index=i,
                buy_price=Decimal("100000000") + Decimal("2000000") * i,
                held_qty=Decimal("0.001") if i % 2 == 0 else DECIMAL_ZERO,
                sell_price=Decimal("101000000") + Decimal("2000000") * i,
                planned_qty=Decimal("0.001"),
            )
            for i in range(10)
        ]
        self.grid_state = GridState(symbol="KRW-BTC", rows=rows)
        self.mock_exchange = MagicMock()

    def test_execute_stop_loss_no_holding_slots(self):
        """보유 슬롯이 없는 경우: 즉시 성공 반환"""
        empty_grid = GridState(
            symbol="KRW-BTC",
            rows=[
                GridRow(
                    index=i,
                    buy_price=Decimal("100000000") + Decimal("2000000") * i,
                    held_qty=DECIMAL_ZERO,
                    sell_price=Decimal("101000000") + Decimal("2000000") * i,
                    planned_qty=Decimal("0.001"),
                )
                for i in range(5)
            ],
        )

        decision = StopLossDecision(
            level=1,
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            current_price=Decimal("75000000"),
            triggered=True,
            candle_close_prices=(Decimal("75000000"),) * 2,
            armed_at=datetime.now(tz=timezone.utc),
        )

        reconcile_called = False
        def mock_reconcile():
            nonlocal reconcile_called
            reconcile_called = True

        result = execute_stop_loss(
            self.mock_exchange,
            empty_grid,
            decision,
            "KRW-BTC",
            mock_reconcile,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.level, 1)
        self.assertEqual(result.total_slots_to_sell, 0)

    def test_execute_stop_loss_l1_partial_liquidation(self):
        """L1 손절: 보유 슬롯에서 매도 주문 생성"""
        decision = StopLossDecision(
            level=1,
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            current_price=Decimal("75000000"),
            triggered=True,
            candle_close_prices=(Decimal("75000000"),) * 4,
            armed_at=datetime.now(tz=timezone.utc),
        )

        # exchange.get_open_order_ids 반환: 열린 주문 없음
        self.mock_exchange.get_open_order_ids.return_value = []

        # exchange.place_order: 시장가 매도 주문 생성 성공
        placed_order_ids = {}
        def mock_place_order(order):
            order_id = f"order_{order.slot_index}"
            placed_order_ids[order_id] = order
            return order_id

        self.mock_exchange.place_order.side_effect = mock_place_order

        # reconcile 후 grid_state 업데이트 (매도 완료)
        def mock_reconcile():
            for row in self.grid_state.rows:
                if row.is_holding:
                    row.held_qty = DECIMAL_ZERO

        result = execute_stop_loss(
            self.mock_exchange,
            self.grid_state,
            decision,
            "KRW-BTC",
            mock_reconcile,
        )

        # 보유 슬롯은 5개 (0, 2, 4, 6, 8)
        self.assertEqual(result.level, 1)
        self.assertEqual(result.total_slots_to_sell, 5)
        self.assertEqual(self.mock_exchange.place_order.call_count, 5)

        # L1 매도 주문은 LIMIT이어야 함 (지정가)
        for call in self.mock_exchange.place_order.call_args_list:
            order = call[0][0]
            self.assertEqual(order.execution_type, OrderExecutionType.LIMIT)
            self.assertEqual(order.side, OrderSide.SELL)
            self.assertEqual(order.price, Decimal("80000000"))  # threshold

    def test_execute_stop_loss_cancels_open_orders(self):
        """열린 주문이 있으면 먼저 취소"""
        decision = StopLossDecision(
            level=2,
            threshold=Decimal("70000000"),
            lower_price=Decimal("100000000"),
            current_price=Decimal("65000000"),
            triggered=True,
            candle_close_prices=(Decimal("65000000"),) * 2,
            armed_at=datetime.now(tz=timezone.utc),
        )

        # 열린 주문 3개
        open_order_ids = ["order_001", "order_002", "order_003"]
        self.mock_exchange.get_open_order_ids.return_value = open_order_ids
        self.mock_exchange.cancel_order.return_value = True

        # place_order: 성공
        self.mock_exchange.place_order.side_effect = lambda o: f"new_sell_{o.slot_index}"

        def mock_reconcile():
            for row in self.grid_state.rows:
                if row.is_holding:
                    row.held_qty = DECIMAL_ZERO

        result = execute_stop_loss(
            self.mock_exchange,
            self.grid_state,
            decision,
            "KRW-BTC",
            mock_reconcile,
        )

        # cancel_order가 3번 호출되었는지 확인
        self.assertEqual(self.mock_exchange.cancel_order.call_count, 3)
        for call in self.mock_exchange.cancel_order.call_args_list:
            order_id = call[0][0]
            self.assertIn(order_id, open_order_ids)

    def test_execute_stop_loss_l2_full_liquidation(self):
        """L2 손절: 모든 보유 슬롯 100% 청산"""
        decision = StopLossDecision(
            level=2,
            threshold=Decimal("70000000"),
            lower_price=Decimal("100000000"),
            current_price=Decimal("65000000"),
            triggered=True,
            candle_close_prices=(Decimal("65000000"),) * 2,
            armed_at=datetime.now(tz=timezone.utc),
        )

        self.mock_exchange.get_open_order_ids.return_value = []
        self.mock_exchange.place_order.side_effect = lambda o: f"sell_{o.slot_index}"

        def mock_reconcile():
            for row in self.grid_state.rows:
                row.held_qty = DECIMAL_ZERO

        result = execute_stop_loss(
            self.mock_exchange,
            self.grid_state,
            decision,
            "KRW-BTC",
            mock_reconcile,
        )

        self.assertEqual(result.level, 2)
        self.assertTrue(result.success)
        self.assertEqual(result.successful_sells, 5)

    def test_execute_stop_loss_not_triggered(self):
        """decision.triggered=False인 경우: 함수 조기 종료"""
        decision = StopLossDecision(
            level=None,
            threshold=None,
            lower_price=Decimal("100000000"),
            current_price=Decimal("95000000"),
            triggered=False,
        )

        reconcile_called = False
        def mock_reconcile():
            nonlocal reconcile_called
            reconcile_called = True

        result = execute_stop_loss(
            self.mock_exchange,
            self.grid_state,
            decision,
            "KRW-BTC",
            mock_reconcile,
        )

        self.assertFalse(result.success)
        self.assertFalse(reconcile_called)

    def test_execute_stop_loss_partial_order_failure(self):
        """일부 주문 실패: 계속 진행 (best-effort)"""
        decision = StopLossDecision(
            level=1,
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            current_price=Decimal("75000000"),
            triggered=True,
            candle_close_prices=(Decimal("75000000"),) * 4,
            armed_at=datetime.now(tz=timezone.utc),
        )

        self.mock_exchange.get_open_order_ids.return_value = []

        # 일부 주문은 실패 (None 반환), 일부는 성공
        place_order_call_count = [0]
        def mock_place_order(order):
            place_order_call_count[0] += 1
            if place_order_call_count[0] % 2 == 0:
                return None  # 실패
            return f"order_{order.slot_index}"

        self.mock_exchange.place_order.side_effect = mock_place_order

        def mock_reconcile():
            for row in self.grid_state.rows:
                if row.is_holding:
                    row.held_qty = DECIMAL_ZERO

        result = execute_stop_loss(
            self.mock_exchange,
            self.grid_state,
            decision,
            "KRW-BTC",
            mock_reconcile,
        )

        self.assertEqual(result.level, 1)
        # 보유 슬롯 5개 중 일부는 주문 실패
        self.assertGreater(result.total_slots_to_sell, 0)

    def test_execute_stop_loss_reconcile_exception(self):
        """reconcile 예외 발생 시: 로그만 기록하고 계속 진행"""
        decision = StopLossDecision(
            level=1,
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            current_price=Decimal("75000000"),
            triggered=True,
            candle_close_prices=(Decimal("75000000"),) * 4,
            armed_at=datetime.now(tz=timezone.utc),
        )

        self.mock_exchange.get_open_order_ids.return_value = []
        self.mock_exchange.place_order.side_effect = lambda o: f"order_{o.slot_index}"

        def mock_reconcile():
            raise RuntimeError("reconcile 실패")

        with patch("app.strategy.stop_loss.logger") as mock_logger:
            result = execute_stop_loss(
                self.mock_exchange,
                self.grid_state,
                decision,
                "KRW-BTC",
                mock_reconcile,
            )

            # 예외 로깅 확인
            mock_logger.error.assert_called()

    def test_execute_stop_loss_cancel_order_exception(self):
        """주문 취소 예외 발생 시: 경고만 기록하고 계속"""
        decision = StopLossDecision(
            level=1,
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            current_price=Decimal("75000000"),
            triggered=True,
            candle_close_prices=(Decimal("75000000"),) * 4,
            armed_at=datetime.now(tz=timezone.utc),
        )

        self.mock_exchange.get_open_order_ids.return_value = ["order_fail"]
        self.mock_exchange.cancel_order.side_effect = RuntimeError("cancel 실패")
        self.mock_exchange.place_order.side_effect = lambda o: f"order_{o.slot_index}"

        def mock_reconcile():
            for row in self.grid_state.rows:
                if row.is_holding:
                    row.held_qty = DECIMAL_ZERO

        with patch("app.strategy.stop_loss.logger"):
            result = execute_stop_loss(
                self.mock_exchange,
                self.grid_state,
                decision,
                "KRW-BTC",
                mock_reconcile,
            )

            # 매도는 계속 진행되어야 함
            self.assertEqual(self.mock_exchange.place_order.call_count, 5)


if __name__ == "__main__":
    unittest.main()
