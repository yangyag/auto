import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
import io

from app.core.models import GridRow, Order, OrderSide
from app.storage.interfaces import GridSnapshot
from app.storage.postgres_grid_repository import PostgresGridRepository
from app.storage.postgres_order_repository import PostgresOrderRepository
from scripts.adjust_budget_live import main
from tests.postgres_test_utils import (
    PostgresIntegrationTestCase,
    apply_test_schema,
    drop_test_schema,
    postgres_test_config,
)
from app.utils.decimal_utils import BTC_QUANTITY_STEP, quantize_to_step


class TestAdjustBudgetLiveScript(PostgresIntegrationTestCase):
    PRICES = (
        Decimal("110000000"),
        Decimal("100000000"),
        Decimal("90000000"),
    )
    SELL_PRICES = (
        Decimal("121000000"),
        Decimal("110000000"),
        Decimal("99000000"),
    )
    WEIGHTS = (
        Decimal("0.7"),
        Decimal("1.0"),
        Decimal("1.3"),
    )

    def setUp(self):
        self.config = postgres_test_config()
        apply_test_schema(self.config.PGSCHEMA)
        self.grid_repo = PostgresGridRepository.from_config(self.config)
        self.order_repo = PostgresOrderRepository.from_config(self.config)
        self.save_grid(self.build_rows_for_budget(Decimal("3000000")))

    def tearDown(self):
        drop_test_schema(self.config.PGSCHEMA)

    def expected_quantities(self, total_budget: Decimal) -> tuple[Decimal, ...]:
        weight_sum = sum(self.WEIGHTS, Decimal("0"))
        quantities = []
        for price, weight in zip(self.PRICES, self.WEIGHTS):
            slot_budget = (total_budget * weight) / weight_sum
            quantities.append(quantize_to_step(slot_budget / price, BTC_QUANTITY_STEP))
        return tuple(quantities)

    def build_rows_for_budget(
        self,
        total_budget: Decimal,
        *,
        held_quantities: tuple[Decimal, ...] | None = None,
    ) -> tuple[GridRow, ...]:
        held_quantities = held_quantities or (
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        )
        planned_quantities = self.expected_quantities(total_budget)
        return tuple(
            GridRow(
                index=index,
                buy_price=price,
                held_qty=held_qty,
                sell_price=sell_price,
                planned_qty=planned_qty,
            )
            for index, (price, sell_price, held_qty, planned_qty) in enumerate(
                zip(self.PRICES, self.SELL_PRICES, held_quantities, planned_quantities),
                start=1,
            )
        )

    def save_grid(self, rows: tuple[GridRow, ...]) -> None:
        self.grid_repo.save(GridSnapshot(symbol="KRW-BTC", rows=rows))

    def run_script(self, args, *, current_price: Decimal = Decimal("120000000")):
        """스크립트 실행 및 결과 캡처. current_price 가 모든 슬롯 buy_price 보다 높으면 lower_budget 이 곧 total_budget 이 된다."""
        output = io.StringIO()
        full_args = args + ["--bot-key", self.config.STATE_BOT_KEY]
        with patch("sys.stdout", new=output), patch("sys.stdin", io.StringIO("y\n")):
            try:
                with patch("app.config.settings.PGHOST", self.config.PGHOST), \
                     patch("app.config.settings.PGPORT", self.config.PGPORT), \
                     patch("app.config.settings.PGDATABASE", self.config.PGDATABASE), \
                     patch("app.config.settings.PGUSER", self.config.PGUSER), \
                     patch("app.config.settings.PGPASSWORD", self.config.PGPASSWORD), \
                     patch("app.config.settings.PGSCHEMA", self.config.PGSCHEMA), \
                     patch("app.config.settings.STATE_BOT_KEY", self.config.STATE_BOT_KEY), \
                     patch("scripts.adjust_budget_live.fetch_current_price", return_value=current_price):
                    exit_code = main(full_args)
            except SystemExit as e:
                exit_code = e.code
        return exit_code, output.getvalue()

    def test_increase_budget_success(self):
        # 300만 -> 600만 증액. 과거 정수 quantize 버그라면 여기서 planned_qty가 0이 됐어야 한다.
        exit_code, output = self.run_script(["--target-lower-budget", "6000000"])

        self.assertEqual(exit_code, 0)
        self.assertIn("상태: 성공", output)

        loaded = self.grid_repo.load()
        expected_quantities = self.expected_quantities(Decimal("6000000"))
        self.assertEqual(tuple(row.planned_qty for row in loaded.rows), expected_quantities)
        self.assertEqual(loaded.rows[0].planned_qty, Decimal("0.01272727"))
        self.assertGreater(loaded.rows[0].planned_qty, Decimal("0"))
        self.assertGreater(loaded.rows[1].planned_qty, Decimal("0"))
        self.assertGreater(loaded.rows[2].planned_qty, Decimal("0"))

    def test_fail_if_open_buy_exists(self):
        # 오픈된 BUY 주문 추가
        original = self.grid_repo.load()
        self.order_repo.add(
            Order(
                slot_index=1,
                side=OrderSide.BUY,
                price=self.PRICES[0],
                quantity=Decimal("0.001"),
                symbol="KRW-BTC",
                order_id="uuid-1",
            )
        )

        exit_code, output = self.run_script(["--target-lower-budget", "6000000"])

        self.assertEqual(exit_code, 1)
        self.assertIn("에러: 현재 열려 있는 BUY 주문이 1개 있습니다.", output)
        self.assertEqual(self.grid_repo.load(), original)

    def test_warn_and_require_force_if_budget_less_than_inventory(self):
        # Slot 1 held_qty=0.01 BTC -> inventory cost = 1,100,000 KRW
        self.save_grid(
            self.build_rows_for_budget(
                Decimal("3000000"),
                held_quantities=(Decimal("0.01"), Decimal("0"), Decimal("0")),
            )
        )
        original = self.grid_repo.load()

        exit_code, output = self.run_script(["--target-lower-budget", "500000"])

        self.assertEqual(exit_code, 1)
        self.assertIn("[경고] 역산된 총 예산이 현재 보유 중인 인벤토리 가치보다 작습니다!", output)
        self.assertIn("강제 진행하려면 --force 옵션을 사용하세요.", output)
        self.assertEqual(self.grid_repo.load(), original)

    def test_force_execution_if_budget_less_than_inventory(self):
        self.save_grid(
            self.build_rows_for_budget(
                Decimal("3000000"),
                held_quantities=(Decimal("0.01"), Decimal("0"), Decimal("0")),
            )
        )

        exit_code, output = self.run_script(["--target-lower-budget", "500000", "--force"])

        self.assertEqual(exit_code, 0)
        self.assertIn("상태: 성공", output)

        loaded = self.grid_repo.load()
        self.assertEqual(tuple(row.planned_qty for row in loaded.rows), self.expected_quantities(Decimal("500000")))
        self.assertEqual(loaded.rows[0].planned_qty, Decimal("0.00106060"))
        self.assertEqual(loaded.rows[0].held_qty, Decimal("0.01"))

    def test_fail_if_grid_inconsistent(self):
        # 가격 순서가 잘못된 그리드 강제 주입
        self.save_grid(
            (
                GridRow(1, Decimal("90000000"), Decimal("0"), Decimal("99000000"), Decimal("0.01")),
                GridRow(2, Decimal("100000000"), Decimal("0"), Decimal("110000000"), Decimal("0.01")),
            )
        )
        original = self.grid_repo.load()

        exit_code, output = self.run_script(["--target-lower-budget", "6000000"])

        self.assertEqual(exit_code, 1)
        self.assertIn("에러: buy_price가 내림차순이 아닙니다", output)
        self.assertEqual(self.grid_repo.load(), original)

    def test_fail_if_slot_index_has_gap(self):
        self.save_grid(
            (
                GridRow(1, Decimal("110000000"), Decimal("0"), Decimal("121000000"), Decimal("0.01")),
                GridRow(3, Decimal("90000000"), Decimal("0"), Decimal("99000000"), Decimal("0.01")),
            )
        )
        original = self.grid_repo.load()

        exit_code, output = self.run_script(["--target-lower-budget", "6000000"])

        self.assertEqual(exit_code, 1)
        self.assertIn("에러: 슬롯 인덱스 불일치", output)
        self.assertEqual(self.grid_repo.load(), original)

    def test_fail_if_slot_notional_below_upbit_minimum(self):
        original = self.grid_repo.load()

        exit_code, output = self.run_script(["--target-lower-budget", "10000"])

        self.assertEqual(exit_code, 1)
        self.assertIn("업비트 최소 주문 금액보다 작습니다", output)
        self.assertEqual(self.grid_repo.load(), original)

    def test_fail_if_planned_qty_quantizes_to_zero(self):
        original = self.grid_repo.load()

        exit_code, output = self.run_script(["--target-lower-budget", "1"])

        self.assertEqual(exit_code, 1)
        self.assertIn("planned_qty가 0 이하가 됩니다", output)
        self.assertEqual(self.grid_repo.load(), original)

    def test_preserve_filled_at_on_success(self):
        filled_at = datetime(2026, 4, 23, 0, 0, tzinfo=timezone.utc)
        self.save_grid(
            (
                GridRow(1, self.PRICES[0], Decimal("0.01"), self.SELL_PRICES[0], self.expected_quantities(Decimal("3000000"))[0], filled_at=filled_at),
                GridRow(2, self.PRICES[1], Decimal("0"), self.SELL_PRICES[1], self.expected_quantities(Decimal("3000000"))[1]),
                GridRow(3, self.PRICES[2], Decimal("0"), self.SELL_PRICES[2], self.expected_quantities(Decimal("3000000"))[2]),
            )
        )

        exit_code, output = self.run_script(["--target-lower-budget", "6000000", "--force"])

        self.assertEqual(exit_code, 0)
        self.assertIn("상태: 성공", output)
        loaded = self.grid_repo.load()
        self.assertEqual(loaded.rows[0].filled_at, filled_at)

if __name__ == "__main__":
    unittest.main()
