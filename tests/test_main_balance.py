import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import main
from core.models import Order, OrderExecutionType, OrderSide
from exchange.crypto import UpbitAPIError


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

    def test_run_grid_init_writes_grid_file(self):
        exchange = Mock()
        exchange.get_current_price.return_value = Decimal("112000000")

        with TemporaryDirectory() as tmpdir, \
             patch.object(main.cfg, "EXCHANGE_TYPE", "crypto"), \
             patch.object(main.cfg, "SYMBOL", "KRW-BTC"), \
             patch.object(main.cfg, "GRID_LOWER_PRICE", Decimal("92253123")), \
             patch.object(main.cfg, "GRID_UPPER_PRICE", Decimal("111137221")), \
             patch.object(main.cfg, "GRID_SLOT_COUNT", 10), \
             patch.object(main.cfg, "GRID_FIRST_BUY_AMOUNT_KRW", Decimal("200000")), \
             patch.object(main.cfg, "GRID_SELL_PERCENT", Decimal("5")), \
             patch.object(main.cfg, "MAX_TOTAL_BUDGET_KRW", Decimal("2000000")), \
             patch("main.build_exchange", return_value=exchange):
            grid_path = Path(tmpdir) / "grid.txt"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main.run_grid_init(
                    grid_file=str(grid_path),
                    lower_price=Decimal("92253123"),
                    upper_price=Decimal("111137221"),
                    slot_count=10,
                    first_buy_amount=Decimal("200000"),
                    sell_percent=Decimal("5"),
                    current_price=None,
                )

            self.assertEqual(result, 0)
            self.assertTrue(grid_path.exists())
            text = grid_path.read_text(encoding="utf-8")
            self.assertIn("Grid3 KRW-BTC", text)
            self.assertIn("매도 퍼센트: 5%", stdout.getvalue())
            self.assertIn("고정 수량: 0.00183341 BTC", stdout.getvalue())
            self.assertIn("상태: 성공", stdout.getvalue())

    def test_run_grid_init_allows_current_price_below_top_buy_level(self):
        exchange = Mock()
        exchange.get_current_price.return_value = Decimal("105817000")

        with TemporaryDirectory() as tmpdir, \
             patch.object(main.cfg, "EXCHANGE_TYPE", "crypto"), \
             patch.object(main.cfg, "SYMBOL", "KRW-BTC"), \
             patch.object(main.cfg, "GRID_LOWER_PRICE", Decimal("92253123")), \
             patch.object(main.cfg, "GRID_UPPER_PRICE", Decimal("111137221")), \
             patch.object(main.cfg, "GRID_SLOT_COUNT", 10), \
             patch.object(main.cfg, "GRID_FIRST_BUY_AMOUNT_KRW", Decimal("200000")), \
             patch.object(main.cfg, "GRID_SELL_PERCENT", Decimal("5")), \
             patch.object(main.cfg, "MAX_TOTAL_BUDGET_KRW", Decimal("2000000")), \
             patch("main.build_exchange", return_value=exchange):
            grid_path = Path(tmpdir) / "grid.txt"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main.run_grid_init(
                    grid_file=str(grid_path),
                    lower_price=Decimal("92253123"),
                    upper_price=Decimal("111137221"),
                    slot_count=10,
                    first_buy_amount=Decimal("200000"),
                    sell_percent=Decimal("5"),
                    current_price=None,
                )

        self.assertEqual(result, 0)
        self.assertIn("상태: 성공", stdout.getvalue())
