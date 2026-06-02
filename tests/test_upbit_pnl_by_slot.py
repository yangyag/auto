import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import scripts.upbit_pnl_by_slot as by_slot


KST = by_slot.KST


def _today_kst_at(seconds: int) -> datetime:
    """오늘 KST 표시 윈도우 안에 드는 _time_key (period='d' 필터 통과)."""
    today = datetime.now(KST).date()
    base = datetime(today.year, today.month, today.day, 10, 0, 0, tzinfo=KST)
    return base + timedelta(seconds=seconds)


def _order(*, uuid, side, slot, qty, funds, fee="0", seconds=0):
    """슬롯 identifier 를 가진 체결 주문(전처리 완료 형태).

    identifier 의 side 토큰은 buy/sell (체결 side bid/ask 와 구분).
    """
    side_token = "buy" if side == "bid" else "sell"
    identifier = f"{by_slot.cfg.STATE_BOT_KEY}-{side_token}-{slot}-1000-{uuid}hex"
    return {
        "uuid": uuid,
        "side": side,
        "state": "done",
        "identifier": identifier,
        "executed_volume": qty,
        "executed_funds": funds,
        "paid_fee": fee,
        "created_at": _today_kst_at(seconds).isoformat(),
        "_time_key": _today_kst_at(seconds),
    }


def _run_main(argv, sorted_orders, grid_snapshot=None):
    """네트워크(fetch_closed_orders)·전처리(prepare_sorted_orders)·DB(load_grid_snapshot)를 모킹하고 main 실행."""
    patches = [
        patch.object(by_slot.cfg, "API_KEY", "test-key"),
        patch.object(by_slot.cfg, "API_SECRET", "test-secret"),
        patch.object(by_slot.cfg, "STATE_BOT_KEY", by_slot.cfg.STATE_BOT_KEY or "krw-btc-live"),
        # raw_orders 는 어차피 prepare_sorted_orders 모킹으로 무시되지만 네트워크 차단.
        patch.object(by_slot, "fetch_closed_orders", return_value=list(sorted_orders)),
        patch.object(by_slot, "prepare_sorted_orders", return_value=list(sorted_orders)),
    ]

    grid_patch = None
    if grid_snapshot is _UNSET:
        # DB 미연결을 흉내: load_grid_snapshot 이 예외를 던지면 buy_price 는 '-'.
        grid_patch = patch(
            "app.api.services.grid_service.load_grid_snapshot",
            side_effect=RuntimeError("no db"),
        )
    elif grid_snapshot is not None:
        grid_patch = patch(
            "app.api.services.grid_service.load_grid_snapshot",
            return_value=grid_snapshot,
        )

    if grid_patch is not None:
        patches.append(grid_patch)

    for p in patches:
        p.start()
    try:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = by_slot.main(argv)
        return exit_code, buffer.getvalue()
    finally:
        for p in reversed(patches):
            p.stop()


_UNSET = object()


def _grid_snapshot(price_by_index: dict[int, str]):
    rows = [
        SimpleNamespace(index=idx, buy_price=Decimal(price))
        for idx, price in price_by_index.items()
    ]
    return SimpleNamespace(rows=rows)


class UpbitPnlBySlotCliTest(unittest.TestCase):
    def test_main_prints_both_sections_with_slot_and_sell_detail(self):
        orders = [
            _order(uuid="buy1", side="bid", slot=1, qty="0.01", funds="1000000", fee="500", seconds=1),
            _order(uuid="sell1", side="ask", slot=1, qty="0.005", funds="600000", fee="300", seconds=2),
            _order(uuid="buy2", side="bid", slot=2, qty="0.02", funds="2000000", seconds=3),
            _order(uuid="sell2", side="ask", slot=2, qty="0.02", funds="2400000", seconds=4),
        ]
        snapshot = _grid_snapshot({1: "100000000", 2: "95000000"})

        exit_code, output = _run_main(["--period", "d"], orders, grid_snapshot=snapshot)

        self.assertEqual(exit_code, 0)
        # 2개 섹션 헤더
        self.assertIn(by_slot.SLOT_PNL_TITLE, output)
        self.assertIn(by_slot.SELL_DETAIL_TITLE, output)
        # 슬롯별 섹션 컬럼/합계행
        self.assertIn("그리드매수가(참고)", output)
        self.assertIn("매도주문수", output)
        self.assertIn("실현손익(KRW)", output)
        self.assertIn("합계", output)
        # 매도별 상세 섹션 컬럼
        self.assertIn("체결시각(KST)", output)
        self.assertIn("sell_uuid", output)
        # 양 슬롯이 모두 등장
        self.assertIn("sell1", output)
        self.assertIn("sell2", output)
        # 그리드 참고가 주의 문구
        self.assertIn("현재 그리드 기준 참고가", output)

    def test_slot_section_shows_grid_buy_price_from_snapshot(self):
        orders = [
            _order(uuid="buy1", side="bid", slot=1, qty="0.01", funds="1000000", seconds=1),
            _order(uuid="sell1", side="ask", slot=1, qty="0.01", funds="1200000", seconds=2),
        ]
        snapshot = _grid_snapshot({1: "123456789"})

        exit_code, output = _run_main(["--period", "d"], orders, grid_snapshot=snapshot)

        self.assertEqual(exit_code, 0)
        # _fmt_krw 천단위 콤마 포맷
        self.assertIn("123,456,789", output)

    def test_base_currency_label_uses_market_base(self):
        orders = [
            _order(uuid="buy1", side="bid", slot=1, qty="1", funds="1000", seconds=1),
            _order(uuid="sell1", side="ask", slot=1, qty="1", funds="1100", seconds=2),
        ]

        exit_code, output = _run_main(
            ["--period", "d", "--market", "KRW-USDT"],
            orders,
            grid_snapshot=_grid_snapshot({}),
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("매도수량(USDT)", output)
        self.assertNotIn("매도수량(BTC)", output)

    def test_missing_grid_snapshot_renders_dash_and_does_not_crash(self):
        orders = [
            _order(uuid="buy1", side="bid", slot=1, qty="0.01", funds="1000000", seconds=1),
            _order(uuid="sell1", side="ask", slot=1, qty="0.01", funds="1200000", seconds=2),
        ]

        # DB 미연결 (load_grid_snapshot 예외) → 죽지 않고 buy_price 컬럼 '-'
        exit_code, output = _run_main(["--period", "d"], orders, grid_snapshot=_UNSET)

        self.assertEqual(exit_code, 0)
        self.assertIn(by_slot.SLOT_PNL_TITLE, output)
        self.assertIn(by_slot.SELL_DETAIL_TITLE, output)
        # 실현손익 라인은 정상 출력되되 그리드매수가는 '-'
        self.assertIn("sell1", output)

    def test_no_realized_lines_prints_empty_placeholders(self):
        # BUY 만 있고 매칭되는 SELL 없음 → realized 없음
        orders = [
            _order(uuid="buy1", side="bid", slot=1, qty="0.01", funds="1000000", seconds=1),
        ]

        exit_code, output = _run_main(["--period", "d"], orders, grid_snapshot=_grid_snapshot({}))

        self.assertEqual(exit_code, 0)
        self.assertIn(by_slot.SLOT_PNL_TITLE, output)
        self.assertIn("(실현손익 없음)", output)
        self.assertIn(by_slot.SELL_DETAIL_TITLE, output)
        self.assertIn("(매도 내역 없음)", output)

    def test_missing_api_credentials_returns_error_exit_code(self):
        with patch.object(by_slot.cfg, "API_KEY", ""), patch.object(
            by_slot.cfg, "API_SECRET", ""
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = by_slot.main(["--period", "d"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
