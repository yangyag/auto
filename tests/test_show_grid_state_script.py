import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import scripts.show_grid_state as show_grid_state
from app.core.grid_properties import build_sell_price_from_k
from app.core.models import GridRow
from app.storage.interfaces import GridSnapshot, RepositoryMetadata


class ShowGridStateScriptTest(unittest.TestCase):
    def _make_phase6_row(
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

    def test_main_prints_postgres_grid_snapshot(self):
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(
                GridRow(1, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1")),
                GridRow(2, Decimal("90"), Decimal("0.25"), Decimal("94.5"), Decimal("0.5")),
            ),
            metadata=RepositoryMetadata(version=7, revision="rev-7"),
        )

        fake_repository = type("FakeRepository", (), {"load": lambda self: snapshot})()

        with patch.object(show_grid_state.cfg, "PGSCHEMA", "auto_trading"), patch.object(
            show_grid_state.cfg,
            "STATE_BOT_KEY",
            "krw-btc-live",
        ), patch.object(
            show_grid_state,
            "build_grid_repository",
            return_value=fake_repository,
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = show_grid_state.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("상태: 성공", output)
        self.assertIn("백엔드: postgres", output)
        self.assertIn("소스: postgres:auto_trading/krw-btc-live", output)
        self.assertIn("심볼: KRW-BTC", output)
        self.assertIn("행 수: 2", output)
        self.assertIn("총 보유량: 0.25", output)
        self.assertIn("계획 매수 예산 합계: 145", output)
        self.assertIn("상단 슬롯 계획 매수 예산: 100", output)
        self.assertIn("하단 슬롯 계획 매수 예산: 45", output)
        self.assertIn("슬롯 | 매수가 | 보유량 | 매도가 | 계획량 | 계획_원화 | 상태", output)
        self.assertIn(
            "1) buy=             100 held=               0 sell=             105 planned=               1 planned_krw=             100 status=비어있음",
            output,
        )
        self.assertIn(
            "2) buy=              90 held=            0.25 sell=            94.5 planned=             0.5 planned_krw=              45 status=보유중",
            output,
        )

    def test_main_uses_repository_loader_for_postgres_backend(self):
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(GridRow(1, Decimal("100"), Decimal("0.1"), Decimal("105"), Decimal("1")),),
            metadata=RepositoryMetadata(version=7, revision="rev-7"),
        )

        fake_repository = type("FakeRepository", (), {"load": lambda self: snapshot})()

        with patch.object(show_grid_state.cfg, "PGSCHEMA", "auto_trading"), patch.object(
            show_grid_state.cfg,
            "STATE_BOT_KEY",
            "krw-btc-live",
        ), patch.object(
            show_grid_state,
            "build_grid_repository",
            return_value=fake_repository,
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = show_grid_state.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("백엔드: postgres", output)
        self.assertIn("소스: postgres:auto_trading/krw-btc-live", output)
        self.assertIn("심볼: KRW-BTC", output)
        self.assertIn("행 수: 1", output)
        self.assertIn("총 보유량: 0.1", output)
        self.assertIn("계획 매수 예산 합계: 100", output)
        self.assertIn("상단 슬롯 계획 매수 예산: 100", output)
        self.assertIn("하단 슬롯 계획 매수 예산: 100", output)
        self.assertIn(
            "1) buy=             100 held=             0.1 sell=             105 planned=               1 planned_krw=             100 status=보유중",
            output,
        )

    def test_main_prints_phase6_age_tp_metadata_for_holding_rows(self):
        filled_at = datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc)
        top_sell_price = build_sell_price_from_k(
            Decimal("100"),
            lower_price=Decimal("90"),
            upper_price=Decimal("100"),
            price_interval_count=2,
            tp_k=Decimal("11.0"),
            tp_k_floor=Decimal("8.0"),
        )
        bottom_sell_price = build_sell_price_from_k(
            Decimal("90"),
            lower_price=Decimal("90"),
            upper_price=Decimal("100"),
            price_interval_count=2,
            tp_k=Decimal("11.0"),
            tp_k_floor=Decimal("8.0"),
        )
        snapshot = GridSnapshot(
            symbol="KRW-BTC",
            rows=(
                self._make_phase6_row(
                    index=1,
                    buy_price="100",
                    held_qty="0.1",
                    sell_price=str(top_sell_price),
                    planned_qty="1",
                    filled_at=filled_at,
                ),
                self._make_phase6_row(
                    index=2,
                    buy_price="90",
                    held_qty="0",
                    sell_price=str(bottom_sell_price),
                    planned_qty="1",
                    filled_at=None,
                ),
            ),
            metadata=RepositoryMetadata(version=7, revision="rev-7"),
        )
        fake_repository = type("FakeRepository", (), {"load": lambda self: snapshot})()

        class _FixedDateTime:
            @classmethod
            def now(cls, tz=None):
                current = datetime(2026, 4, 20, 1, 0, tzinfo=timezone.utc)
                if tz is None:
                    return current
                return current.astimezone(tz)

        with patch.object(show_grid_state.cfg, "PGSCHEMA", "auto_trading"), patch.object(
            show_grid_state.cfg,
            "STATE_BOT_KEY",
            "krw-btc-live",
        ), patch.object(
            show_grid_state.cfg,
            "GRID_TP_K_BASE",
            Decimal("11.0"),
        ), patch.object(
            show_grid_state.cfg,
            "GRID_TP_K_FLOOR",
            Decimal("8.0"),
        ), patch.object(
            show_grid_state,
            "build_grid_repository",
            return_value=fake_repository,
        ), patch.object(
            show_grid_state,
            "datetime",
            _FixedDateTime,
            create=True,
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = show_grid_state.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("filled_at=2026-04-18T00:00:00+00:00", output)
        self.assertIn("tp_age_step=-0.5", output)
        self.assertIn("effective_tp_k=10.5", output)

    def test_main_prints_recenter_preview_without_applying_it(self):
        preview = {
            "status": "blocked",
            "can_apply": False,
            "blockers": [
                "breakout_duration_below_24h",
                "open_buy_orders_present",
            ],
            "proposed_lower_price": Decimal("95"),
            "proposed_upper_price": Decimal("135"),
        }
        snapshot = SimpleNamespace(
            symbol="KRW-BTC",
            rows=(
                GridRow(1, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1")),
            ),
            metadata=SimpleNamespace(version=7, revision="rev-7", recenter_preview=preview),
            recenter_preview=preview,
        )
        fake_repository = type("FakeRepository", (), {"load": lambda self: snapshot})()

        with patch.object(show_grid_state.cfg, "PGSCHEMA", "auto_trading"), patch.object(
            show_grid_state.cfg,
            "STATE_BOT_KEY",
            "krw-btc-live",
        ), patch.object(
            show_grid_state,
            "build_grid_repository",
            return_value=fake_repository,
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = show_grid_state.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("리센터 미리보기: blocked", output)
        self.assertIn("리센터 적용 가능: 아니오", output)
        self.assertIn(
            "리센터 차단 항목: breakout_duration_below_24h, open_buy_orders_present",
            output,
        )
        self.assertIn("리센터 제안 밴드: 95 -> 135", output)


if __name__ == "__main__":
    unittest.main()
