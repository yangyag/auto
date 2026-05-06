"""PR4 평가자 재작업 테스트: stop_loss_active 영속화, reset-stop-loss CLI, main.py 통합"""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

import app.config.settings as cfg
from app.core.grid import GridState, GridRow
from app.core.models import Order, OrderSide, OrderExecutionType
from app.main import (
    GridStateRuntime,
    load_grid_state,
    persist_grid_state,
    run_reset_stop_loss,
    run_trading_cycle,
    TradingCycleResult,
)
from app.storage.interfaces import GridSnapshot, RepositoryMetadata
from app.utils.decimal_utils import DECIMAL_ZERO


class StopLossMetadataPersistenceTest(unittest.TestCase):
    """Flaw 2: GridSnapshot round-trip test — stop_loss_armed_at 포함"""

    def test_metadata_round_trip_persists_all_stop_loss_fields(self):
        """GridSnapshot save/load가 모든 stop_loss 필드를 보존한다."""
        armed_at = datetime.now(tz=timezone.utc)
        liquidated_at = datetime.now(tz=timezone.utc)

        runtime = GridStateRuntime(
            stop_loss_active=True,
            stop_loss_level=1,
            stop_loss_armed_at=armed_at,
            liquidated_at=liquidated_at,
        )

        metadata = runtime.save_to_metadata()
        self.assertTrue(metadata.stop_loss_active)
        self.assertEqual(metadata.stop_loss_level, 1)
        self.assertEqual(metadata.stop_loss_armed_at, armed_at.isoformat())
        self.assertEqual(metadata.liquidated_at, liquidated_at.isoformat())

    def test_load_grid_state_restores_stop_loss_armed_at(self):
        """load_grid_state()가 stop_loss_armed_at을 올바르게 복원한다."""
        armed_at = datetime.now(tz=timezone.utc)
        liquidated_at = datetime.now(tz=timezone.utc)

        metadata = RepositoryMetadata(
            stop_loss_active=True,
            stop_loss_level=2,
            stop_loss_armed_at=armed_at.isoformat(),
            liquidated_at=liquidated_at.isoformat(),
        )

        row = GridRow(
            index=0,
            buy_price=Decimal("100"),
            sell_price=Decimal("110"),
            held_qty=Decimal("1"),
            planned_qty=Decimal("1"),
            filled_at=None,
        )

        snapshot = GridSnapshot(symbol="KRW-BTC", rows=(row,), metadata=metadata)

        repository = Mock()
        repository.load.return_value = snapshot

        grid_state, runtime = load_grid_state(repository)

        self.assertTrue(runtime.stop_loss_active)
        self.assertEqual(runtime.stop_loss_level, 2)
        self.assertEqual(runtime.stop_loss_armed_at, armed_at)
        self.assertEqual(runtime.liquidated_at, liquidated_at)

    def test_save_to_metadata_encodes_none_armed_at(self):
        """save_to_metadata()가 None stop_loss_armed_at을 처리한다."""
        runtime = GridStateRuntime(
            stop_loss_active=False,
            stop_loss_level=None,
            stop_loss_armed_at=None,
        )

        metadata = runtime.save_to_metadata()
        self.assertFalse(metadata.stop_loss_active)
        self.assertIsNone(metadata.stop_loss_level)
        self.assertIsNone(metadata.stop_loss_armed_at)


class ResetStopLossCliTest(unittest.TestCase):
    """Flaw 1, 6: run_reset_stop_loss() 직접 테스트"""

    def _make_grid_row(self):
        """테스트용 GridRow 생성"""
        return GridRow(
            index=0,
            buy_price=Decimal("100"),
            sell_price=Decimal("110"),
            held_qty=Decimal("0"),
            planned_qty=Decimal("1"),
            filled_at=None,
        )

    def test_reset_stop_loss_clears_l1_state(self):
        """reset-stop-loss CLI가 L1 상태를 해제한다."""
        runtime = GridStateRuntime(
            stop_loss_active=True,
            stop_loss_level=1,
            stop_loss_armed_at=datetime.now(tz=timezone.utc),
        )

        row = self._make_grid_row()

        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(row,),
            metadata=runtime.save_to_metadata(),
        )

        repository = Mock()
        repository.load.return_value = snapshot
        repository.save.return_value = snapshot

        with patch("app.main.build_grid_repository", return_value=repository):
            result = run_reset_stop_loss(force=False)

        self.assertEqual(result, 0)
        saved_snapshot = repository.save.call_args[0][0]
        self.assertFalse(saved_snapshot.metadata.stop_loss_active)
        self.assertIsNone(saved_snapshot.metadata.stop_loss_level)
        self.assertIsNone(saved_snapshot.metadata.stop_loss_armed_at)

    def test_reset_stop_loss_respects_24hour_l2_lockout(self):
        """reset-stop-loss CLI가 L2 24시간 잠금을 강제한다."""
        now = datetime.now(tz=timezone.utc)
        liquidated_at = now - timedelta(minutes=30)  # 30분 전 L2 발동

        runtime = GridStateRuntime(
            stop_loss_active=True,
            stop_loss_level=2,
            liquidated_at=liquidated_at,
        )

        row = self._make_grid_row()

        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(row,),
            metadata=runtime.save_to_metadata(),
        )

        repository = Mock()
        repository.load.return_value = snapshot

        with patch("app.main.build_grid_repository", return_value=repository):
            # datetime.now()를 직접 mock하지 말고 실제 시간 사용
            # L2 발동 후 30분이므로 24시간 잠금이 활성 상태
            result = run_reset_stop_loss(force=False)

        # 24시간 잠금 중이므로 실패 반환
        self.assertEqual(result, 2)
        # save가 호출되지 않았으므로 상태 변경 안 함
        repository.save.assert_not_called()

    def test_reset_stop_loss_force_bypasses_24hour_lockout(self):
        """reset-stop-loss --force가 24시간 잠금을 무시한다."""
        now = datetime.now(tz=timezone.utc)
        liquidated_at = now - timedelta(minutes=30)  # 30분 전 L2 발동

        runtime = GridStateRuntime(
            stop_loss_active=True,
            stop_loss_level=2,
            liquidated_at=liquidated_at,
        )

        row = self._make_grid_row()

        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(row,),
            metadata=runtime.save_to_metadata(),
        )

        repository = Mock()
        repository.load.return_value = snapshot
        repository.save.return_value = snapshot

        with patch("app.main.build_grid_repository", return_value=repository):
            # --force로 24시간 잠금을 무시
            result = run_reset_stop_loss(force=True)

        # --force로 강제 해제
        self.assertEqual(result, 0)
        repository.save.assert_called_once()

    def test_reset_stop_loss_returns_0_when_no_active_state(self):
        """손절 상태 없을 때 reset-stop-loss는 성공(0)을 반환한다."""
        runtime = GridStateRuntime(stop_loss_active=False)

        row = self._make_grid_row()

        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(row,),
            metadata=runtime.save_to_metadata(),
        )

        repository = Mock()
        repository.load.return_value = snapshot

        with patch("app.main.build_grid_repository", return_value=repository):
            result = run_reset_stop_loss(force=False)

        self.assertEqual(result, 0)
        # save 호출 안 함 (상태 변경 없음)
        repository.save.assert_not_called()


class L2SkipCycleTest(unittest.TestCase):
    """Flaw 3: L2 발동 후 다음 사이클 스킵 확인"""

    def test_run_trading_cycle_skips_when_l2_active(self):
        """L2 상태일 때 run_trading_cycle()이 전체 사이클을 스킵한다."""
        runtime = GridStateRuntime(
            stop_loss_active=True,
            stop_loss_level=2,
        )

        exchange = Mock()
        strategy = Mock()
        grid_state = Mock()
        grid_repository = Mock()
        pending_orders = {}

        result = run_trading_cycle(
            exchange=exchange,
            strategy=strategy,
            grid_state=grid_state,
            grid_repository=grid_repository,
            runtime=runtime,
            pending_orders=pending_orders,
            current_order_day=__import__("datetime").date.today(),
            daily_order_count=0,
            on_grid_updated=lambda: None,
            pending_order_repository=Mock(),
        )

        # reconcile, strategy.evaluate 등이 호출되지 않음 (초기 가드에서 반환)
        self.assertEqual(result.daily_order_count, 0)
        grid_repository.load.assert_not_called()
        strategy.evaluate_with_pending.assert_not_called()

    def test_run_trading_cycle_proceeds_with_l1_active(self):
        """L1 상태일 때 run_trading_cycle()은 정상 진행한다."""
        runtime = GridStateRuntime(
            stop_loss_active=True,
            stop_loss_level=1,
        )

        exchange = Mock()
        exchange.get_current_price_rest.return_value = Decimal("100")

        strategy = Mock()
        strategy.evaluate_with_pending.return_value = ([], [])
        strategy.spec = Mock()

        grid_state = Mock()
        grid_state.rows = []
        grid_state.summary.return_value = "summary"

        grid_repository = Mock()
        grid_repository.has_changed.return_value = False

        pending_orders = {}

        with patch("app.main.reconcile_pending_orders", return_value=0), \
             patch("app.main.ensure_tp_sell_orders", return_value=0), \
             patch(
                 "app.main.fetch_breakout_guard_status",
                 return_value=Mock(active=False, reason="inside_band"),
             ), \
             patch("app.main.apply_breakout_guard_to_buy_orders", return_value=[]):
            result = run_trading_cycle(
                exchange=exchange,
                strategy=strategy,
                grid_state=grid_state,
                grid_repository=grid_repository,
                runtime=runtime,
                pending_orders=pending_orders,
                current_order_day=__import__("datetime").date.today(),
                daily_order_count=0,
                on_grid_updated=lambda: None,
                pending_order_repository=Mock(),
                current_price=Decimal("100"),
            )

        # 사이클 진행됨 (strategy.evaluate 호출됨)
        strategy.evaluate_with_pending.assert_called_once()


if __name__ == "__main__":
    unittest.main()
