import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import Mock, patch

import main
from core.models import Order, OrderExecutionType, OrderSide
from exchange.crypto import UpbitAPIError
from storage.interfaces import GridSnapshot, RepositoryMetadata


class BalanceCommandTest(unittest.TestCase):

    def test_validate_grid_state_skips_budget_check_when_limit_disabled(self):
        state = Mock()
        state.total_allocated_budget = Decimal("8157489.21988")

        with patch.object(main.cfg, "MAX_TOTAL_BUDGET_KRW", None):
            main.validate_grid_state(state)

    def test_check_risk_uses_actual_available_balance_only(self):
        exchange = Mock()
        exchange.get_balance.return_value = Decimal("0")
        grid_state = Mock()
        grid_state.total_allocated_budget = Decimal("0")
        sell_order = Order(
            slot_index=1,
            side=OrderSide.SELL,
            price=Decimal("11000"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )
        buy_order = Order(
            slot_index=2,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("10000"),
        )

        with patch.object(main.cfg, "MAX_TOTAL_BUDGET_KRW", None), \
             patch.object(main.cfg, "MIN_BALANCE_RESERVE", Decimal("0")):
            approved = main.check_risk([sell_order, buy_order], exchange, grid_state)

        self.assertEqual(approved, [sell_order])

    def test_check_risk_includes_fee_buffer_in_required_buy_balance(self):
        exchange = Mock()
        exchange.get_balance.return_value = Decimal("10050")
        grid_state = Mock()
        grid_state.total_allocated_budget = Decimal("0")
        buy_order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("11000"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
            execution_type=OrderExecutionType.MARKET_BUY_BY_PRICE,
            spend_amount=Decimal("10000"),
        )

        with patch.object(main.cfg, "MAX_TOTAL_BUDGET_KRW", None), \
             patch.object(main.cfg, "MIN_BALANCE_RESERVE", Decimal("0")), \
             patch.object(main.cfg, "UPBIT_FEE_RATE", Decimal("0.0005")), \
             patch.object(main.cfg, "FEE_BUFFER_KRW", Decimal("100")):
            approved = main.check_risk([buy_order], exchange, grid_state)

        self.assertEqual(approved, [])

    def test_run_balance_check_success(self):
        exchange = Mock()
        exchange.get_balance.return_value = Decimal("1000000")

        with patch.object(main.cfg, "EXCHANGE_TYPE", "crypto"), \
             patch.object(main.cfg, "SYMBOL", "KRW-BTC"), \
             patch.object(main.cfg, "API_KEY", "access"), \
             patch.object(main.cfg, "API_SECRET", "secret"), \
             patch("main.build_exchange", return_value=exchange):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main.run_balance_check()

        self.assertEqual(result, 0)
        self.assertIn("주문 가능 KRW 잔고: 1000000 KRW", stdout.getvalue())
        self.assertIn("상태: 성공", stdout.getvalue())

    def test_run_balance_check_fails_when_credentials_missing(self):
        with patch.object(main.cfg, "EXCHANGE_TYPE", "crypto"), \
             patch.object(main.cfg, "SYMBOL", "KRW-BTC"), \
             patch.object(main.cfg, "API_KEY", ""), \
             patch.object(main.cfg, "API_SECRET", ""):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main.run_balance_check()

        self.assertEqual(result, 1)
        self.assertIn("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY", stdout.getvalue())
        self.assertIn("상태: 실패", stdout.getvalue())

    def test_run_balance_check_fails_on_upbit_api_error(self):
        exchange = Mock()
        exchange.get_balance.side_effect = UpbitAPIError("현재 IP가 업비트 API 키 허용 목록에 없습니다.")

        with patch.object(main.cfg, "EXCHANGE_TYPE", "crypto"), \
             patch.object(main.cfg, "SYMBOL", "KRW-BTC"), \
             patch.object(main.cfg, "API_KEY", "access"), \
             patch.object(main.cfg, "API_SECRET", "secret"), \
             patch("main.build_exchange", return_value=exchange):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main.run_balance_check()

        self.assertEqual(result, 1)
        self.assertIn("상태: 실패", stdout.getvalue())
        self.assertIn("허용 목록", stdout.getvalue())

    def test_main_dispatches_balance_command(self):
        with patch("main.run_balance_check", return_value=0) as run_balance_check:
            result = main.main(["balance"])

        self.assertEqual(result, 0)
        run_balance_check.assert_called_once_with()

    def test_run_grid_init_saves_postgres_snapshot(self):
        exchange = Mock()
        exchange.get_current_price.return_value = Decimal("112000000")
        repository = Mock()
        repository.load.return_value = GridSnapshot(symbol="", rows=tuple(), metadata=RepositoryMetadata())
        repository.save.return_value = GridSnapshot(
            symbol="KRW-BTC",
            rows=tuple(),
            metadata=RepositoryMetadata(version=1, revision="rev-1"),
        )

        with patch.object(main.cfg, "EXCHANGE_TYPE", "crypto"), \
             patch.object(main.cfg, "SYMBOL", "KRW-BTC"), \
             patch.object(main.cfg, "PGSCHEMA", "auto_trading"), \
             patch.object(main.cfg, "STATE_BOT_KEY", "krw-btc-live"), \
             patch.object(main.cfg, "GRID_LOWER_PRICE", Decimal("92253123")), \
             patch.object(main.cfg, "GRID_UPPER_PRICE", Decimal("111137221")), \
             patch.object(main.cfg, "GRID_SLOT_COUNT", 10), \
             patch.object(main.cfg, "GRID_TOTAL_BUDGET_KRW", Decimal("2000000")), \
             patch.object(main.cfg, "GRID_TP_MODEL", "k"), \
             patch.object(main.cfg, "GRID_TP_K_BASE", Decimal("9.0")), \
             patch.object(main.cfg, "GRID_TP_K_FLOOR", Decimal("7.0")), \
             patch.object(main.cfg, "MAX_TOTAL_BUDGET_KRW", Decimal("2000000")), \
             patch("main.build_exchange", return_value=exchange), \
             patch("main.build_grid_repository", return_value=repository):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main.run_grid_init(
                    lower_price=Decimal("92253123"),
                    upper_price=Decimal("111137221"),
                    slot_count=10,
                    total_budget=Decimal("2000000"),
                    current_price=None,
                )

        self.assertEqual(result, 0)
        repository.save.assert_called_once()
        saved_snapshot = repository.save.call_args.args[0]
        self.assertEqual(saved_snapshot.symbol, "KRW-BTC")
        self.assertIn("저장 대상: postgres:auto_trading/krw-btc-live", stdout.getvalue())
        self.assertIn("총예산: 2000000 KRW", stdout.getvalue())
        self.assertIn("TP 모델: k", stdout.getvalue())
        self.assertIn("TP k_base: 9", stdout.getvalue())
        self.assertIn("TP k_floor: 7", stdout.getvalue())
        self.assertIn("총 배정 금액:", stdout.getvalue())
        self.assertIn("상단 슬롯 배정 금액:", stdout.getvalue())
        self.assertIn("하단 슬롯 배정 금액:", stdout.getvalue())
        self.assertIn("버전: 1", stdout.getvalue())
        self.assertIn("상태: 성공", stdout.getvalue())

    def test_run_grid_init_rejects_existing_postgres_snapshot_without_force(self):
        exchange = Mock()
        exchange.get_current_price.return_value = Decimal("105817000")
        repository = Mock()
        repository.load.return_value = GridSnapshot(
            symbol="KRW-BTC",
            rows=tuple(),
            metadata=RepositoryMetadata(version=7, revision="rev-7"),
        )

        with patch.object(main.cfg, "EXCHANGE_TYPE", "crypto"), \
             patch.object(main.cfg, "SYMBOL", "KRW-BTC"), \
             patch.object(main.cfg, "PGSCHEMA", "auto_trading"), \
             patch.object(main.cfg, "STATE_BOT_KEY", "krw-btc-live"), \
             patch.object(main.cfg, "GRID_LOWER_PRICE", Decimal("92253123")), \
             patch.object(main.cfg, "GRID_UPPER_PRICE", Decimal("111137221")), \
             patch.object(main.cfg, "GRID_SLOT_COUNT", 10), \
             patch.object(main.cfg, "GRID_TOTAL_BUDGET_KRW", Decimal("2000000")), \
             patch.object(main.cfg, "GRID_TP_MODEL", "k"), \
             patch.object(main.cfg, "GRID_TP_K_BASE", Decimal("9.0")), \
             patch.object(main.cfg, "GRID_TP_K_FLOOR", Decimal("7.0")), \
             patch.object(main.cfg, "MAX_TOTAL_BUDGET_KRW", Decimal("2000000")), \
             patch("main.build_exchange", return_value=exchange), \
             patch("main.build_grid_repository", return_value=repository):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main.run_grid_init(
                    lower_price=Decimal("92253123"),
                    upper_price=Decimal("111137221"),
                    slot_count=10,
                    total_budget=Decimal("2000000"),
                    current_price=None,
                )

        self.assertEqual(result, 1)
        repository.save.assert_not_called()
        self.assertIn("기존 PostgreSQL 그리드 스냅샷이 있습니다", stdout.getvalue())
        self.assertIn("상태: 실패", stdout.getvalue())
