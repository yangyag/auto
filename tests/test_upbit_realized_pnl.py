import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO

import scripts.upbit_realized_pnl as pnl


KST = pnl.KST


def _order(
    *,
    uuid: str,
    side: str,
    identifier: str | None,
    qty: str,
    funds: str,
    fee: str = "0",
    seconds: int = 0,
    state: str = "done",
    remaining_volume: str | None = None,
    volume: str | None = None,
    cancelled_tp_sell_candidate: bool = False,
) -> dict:
    order = {
        "uuid": uuid,
        "side": side,
        "state": state,
        "identifier": identifier,
        "executed_volume": qty,
        "executed_funds": funds,
        "paid_fee": fee,
        "_time_key": datetime(2026, 1, 1, 0, 0, tzinfo=KST) + timedelta(seconds=seconds),
    }
    if remaining_volume is not None:
        order["remaining_volume"] = remaining_volume
    if volume is not None:
        order["volume"] = volume
    if cancelled_tp_sell_candidate:
        order["_cancelled_tp_sell_candidate"] = True
    return order


def _identifier(side: str, slot: int, suffix: str) -> str:
    return f"{pnl.cfg.STATE_BOT_KEY}-{side}-{slot}-1000-{suffix}"


class UpbitRealizedPnlTest(unittest.TestCase):
    def test_normal_slot_matching_is_unchanged(self):
        orders = [
            _order(
                uuid="buy-1",
                side="bid",
                identifier=_identifier("buy", 1, "aaa"),
                qty="0.01",
                funds="1000000",
                fee="500",
                seconds=1,
            ),
            _order(
                uuid="sell-1",
                side="ask",
                identifier=_identifier("sell", 1, "bbb"),
                qty="0.005",
                funds="600000",
                fee="300",
                seconds=2,
            ),
        ]

        realized, unmatched, unparseable_buys, unparseable_sells, queues, reset_residuals = (
            pnl.run_fifo(orders)
        )

        self.assertEqual(len(realized), 1)
        self.assertEqual(realized[0]["slot"], 1)
        self.assertEqual(realized[0]["matched_qty"], Decimal("0.005"))
        self.assertEqual(realized[0]["realized_pnl"], Decimal("99450.000"))
        self.assertEqual(unmatched, [])
        self.assertEqual(unparseable_buys, [])
        self.assertEqual(unparseable_sells, [])
        self.assertEqual(queues[1][0]["qty"], Decimal("0.005"))
        self.assertEqual(reset_residuals, [])

    def test_reset_sell_matches_multiple_slot_queues_fifo(self):
        orders = [
            _order(
                uuid="buy-slot-2",
                side="bid",
                identifier=_identifier("buy", 2, "aaa"),
                qty="0.01",
                funds="1000000",
                seconds=1,
            ),
            _order(
                uuid="buy-slot-1",
                side="bid",
                identifier=_identifier("buy", 1, "bbb"),
                qty="0.03",
                funds="3600000",
                seconds=2,
            ),
            _order(
                uuid="reset-sell",
                side="ask",
                identifier=f"{pnl.cfg.STATE_BOT_KEY}-reset-sell-1000-abc123abc123",
                qty="0.04",
                funds="5000000",
                fee="4000",
                seconds=3,
            ),
        ]

        realized, unmatched, _buys, _sells, queues, reset_residuals = pnl.run_fifo(orders)

        self.assertEqual([line["slot"] for line in realized], [2, 1])
        self.assertEqual([line["matched_qty"] for line in realized], [Decimal("0.01"), Decimal("0.03")])
        self.assertEqual([line["realized_pnl"] for line in realized], [Decimal("249000.00"), Decimal("147000.00")])
        self.assertEqual(unmatched, [])
        self.assertFalse(any(entries for entries in queues.values()))
        self.assertEqual(reset_residuals, [])

    def test_reset_sell_uuid_marks_historical_sell_once(self):
        orders = [
            _order(
                uuid="buy-1",
                side="bid",
                identifier=_identifier("buy", 1, "aaa"),
                qty="0.01",
                funds="1000000",
                seconds=1,
            ),
            _order(
                uuid="historical-reset",
                side="ask",
                identifier="manual-sell",
                qty="0.01",
                funds="1200000",
                fee="1000",
                seconds=2,
            ),
        ]

        realized, unmatched, _buys, unparseable_sells, queues, reset_residuals = pnl.run_fifo(
            orders,
            {"historical-reset"},
        )

        self.assertEqual(len(realized), 1)
        self.assertEqual(realized[0]["sell_uuid"], "historical-reset")
        self.assertEqual(realized[0]["realized_pnl"], Decimal("199000"))
        self.assertEqual(unmatched, [])
        self.assertEqual(unparseable_sells, [])
        self.assertFalse(any(entries for entries in queues.values()))
        self.assertEqual(reset_residuals, [])

    def test_reset_sell_less_than_queued_quantity_discards_pre_reset_residual(self):
        orders = [
            _order(
                uuid="buy-1",
                side="bid",
                identifier=_identifier("buy", 1, "aaa"),
                qty="0.05",
                funds="5000000",
                seconds=1,
            ),
            _order(
                uuid="reset-sell",
                side="ask",
                identifier=f"{pnl.cfg.STATE_BOT_KEY}-reset-sell-1000-abc123abc123",
                qty="0.02",
                funds="2400000",
                seconds=2,
            ),
            _order(
                uuid="post-reset-sell",
                side="ask",
                identifier=_identifier("sell", 1, "bbb"),
                qty="0.03",
                funds="3600000",
                seconds=3,
            ),
        ]

        realized, unmatched, _buys, _sells, queues, reset_residuals = pnl.run_fifo(orders)

        self.assertEqual(len(realized), 1)
        self.assertEqual(realized[0]["sell_uuid"], "reset-sell")
        self.assertEqual(realized[0]["matched_qty"], Decimal("0.02"))
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched[0]["sell_uuid"], "post-reset-sell")
        self.assertEqual(unmatched[0]["unmatched_qty"], Decimal("0.03"))
        self.assertFalse(any(entries for entries in queues.values()))
        self.assertEqual(len(reset_residuals), 1)
        self.assertEqual(reset_residuals[0]["residual_qty"], Decimal("0.03"))
        self.assertEqual(reset_residuals[0]["residual_cost"], Decimal("3000000.0"))

    def test_reset_sell_prefers_recent_cancelled_tp_sell_slots(self):
        orders = [
            _order(
                uuid="old-cheap-buy",
                side="bid",
                identifier=_identifier("buy", 42, "old"),
                qty="0.01",
                funds="1000000",
                seconds=1,
            ),
            _order(
                uuid="target-buy-23",
                side="bid",
                identifier=_identifier("buy", 23, "aaa"),
                qty="0.01",
                funds="1200000",
                seconds=2,
            ),
            _order(
                uuid="target-buy-24",
                side="bid",
                identifier=_identifier("buy", 24, "bbb"),
                qty="0.02",
                funds="2400000",
                seconds=3,
            ),
            _order(
                uuid="cancelled-sell-23",
                side="ask",
                identifier=_identifier("sell", 23, "ccc"),
                qty="0",
                funds="0",
                state="cancel",
                remaining_volume="0.01",
                volume="0.01",
                seconds=4,
                cancelled_tp_sell_candidate=True,
            ),
            _order(
                uuid="cancelled-sell-24",
                side="ask",
                identifier=_identifier("sell", 24, "ddd"),
                qty="0",
                funds="0",
                state="cancel",
                remaining_volume="0.02",
                volume="0.02",
                seconds=5,
                cancelled_tp_sell_candidate=True,
            ),
            _order(
                uuid="reset-sell",
                side="ask",
                identifier=f"{pnl.cfg.STATE_BOT_KEY}-reset-sell-1000-abc123abc123",
                qty="0.03",
                funds="3300000",
                seconds=6,
            ),
        ]

        realized, unmatched, _buys, _sells, queues, reset_residuals = pnl.run_fifo(orders)

        self.assertEqual([line["slot"] for line in realized], [23, 24])
        self.assertEqual([line["matched_qty"] for line in realized], [Decimal("0.01"), Decimal("0.02")])
        self.assertEqual([line["realized_pnl"] for line in realized], [Decimal("-100000"), Decimal("-200000")])
        self.assertEqual(unmatched, [])
        self.assertFalse(any(entries for entries in queues.values()))
        self.assertEqual(len(reset_residuals), 1)
        self.assertEqual(reset_residuals[0]["slot"], 42)
        self.assertEqual(reset_residuals[0]["residual_qty"], Decimal("0.01"))

    def test_non_slot_market_sell_with_cancelled_tp_sells_is_inferred_reset(self):
        orders = [
            _order(
                uuid="old-cheap-buy",
                side="bid",
                identifier=_identifier("buy", 42, "old"),
                qty="0.01",
                funds="1000000",
                seconds=1,
            ),
            _order(
                uuid="target-buy-31",
                side="bid",
                identifier=_identifier("buy", 31, "aaa"),
                qty="0.01",
                funds="1190000",
                seconds=2,
            ),
            _order(
                uuid="cancelled-sell-31",
                side="ask",
                identifier=_identifier("sell", 31, "bbb"),
                qty="0",
                funds="0",
                state="cancel",
                remaining_volume="0.01",
                volume="0.01",
                seconds=3,
                cancelled_tp_sell_candidate=True,
            ),
            _order(
                uuid="upbit-market-sell",
                side="ask",
                identifier="upbit-generated",
                qty="0.01",
                funds="1200000",
                seconds=4,
            ),
        ]

        realized, unmatched, _buys, unparseable_sells, queues, reset_residuals = pnl.run_fifo(orders)

        self.assertEqual(len(realized), 1)
        self.assertEqual(realized[0]["sell_uuid"], "upbit-market-sell")
        self.assertEqual(realized[0]["slot"], 31)
        self.assertEqual(realized[0]["realized_pnl"], Decimal("10000"))
        self.assertEqual(unmatched, [])
        self.assertEqual(unparseable_sells, [])
        self.assertFalse(any(entries for entries in queues.values()))
        self.assertEqual(len(reset_residuals), 1)
        self.assertEqual(reset_residuals[0]["slot"], 42)

    def test_realized_section_reports_order_count_and_trade_count_separately(self):
        realized_lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("100"),
                "matched_qty": Decimal("0.001"),
                "sell_uuid": "sell-1",
                "sell_trade_count": 2,
                "slot": 1,
            },
            {
                "time_key": datetime(2026, 5, 5, 11, 0, tzinfo=KST),
                "realized_pnl": Decimal("200"),
                "matched_qty": Decimal("0.002"),
                "sell_uuid": "sell-2",
                "sell_trade_count": 1,
                "slot": 2,
            },
        ]

        out = StringIO()
        with redirect_stdout(out):
            pnl._print_realized_section(realized_lines, ["daily"])

        output = out.getvalue()
        self.assertIn("매도주문수", output)
        self.assertIn("체결건수", output)
        self.assertIn("26-05-05", output)
        self.assertIn("         2        3", output)

    def test_realized_section_deduplicates_split_lines_for_one_sell_order(self):
        realized_lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("100"),
                "matched_qty": Decimal("0.001"),
                "sell_uuid": "reset-sell",
                "sell_trade_count": 1,
                "slot": 1,
            },
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("200"),
                "matched_qty": Decimal("0.002"),
                "sell_uuid": "reset-sell",
                "sell_trade_count": 1,
                "slot": 2,
            },
        ]

        out = StringIO()
        with redirect_stdout(out):
            pnl._print_realized_section(realized_lines, ["daily"])

        self.assertIn("         1        1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
