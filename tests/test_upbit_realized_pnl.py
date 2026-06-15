import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

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
    def test_parser_defaults_market_to_current_config_symbol(self):
        with patch.object(pnl.cfg, "SYMBOL", "KRW-ETH"):
            args = pnl.build_parser().parse_args([])

        self.assertEqual(args.market, "KRW-ETH")

    def test_market_base_currency_parses_quote_base_market(self):
        self.assertEqual(pnl.market_base_currency("KRW-USDT"), "USDT")
        self.assertEqual(pnl.market_base_currency("krw-btc"), "BTC")

    def test_default_report_window_shows_recent_90_days_all_sections(self):
        args = pnl.build_parser().parse_args([])

        window = pnl.resolve_report_window(args, date(2026, 5, 11))

        self.assertEqual(window.from_date, date(2026, 2, 10))
        self.assertEqual(window.to_date, date(2026, 5, 11))
        self.assertEqual(window.periods_to_show, ["daily", "weekly", "monthly", "yearly", "all"])
        self.assertEqual(window.mode_label, "전체")

    def test_period_presets_resolve_to_current_ranges(self):
        today = date(2026, 5, 13)

        daily = pnl.resolve_report_window(pnl.build_parser().parse_args(["--period", "d"]), today)
        weekly = pnl.resolve_report_window(pnl.build_parser().parse_args(["--period", "w"]), today)
        monthly = pnl.resolve_report_window(pnl.build_parser().parse_args(["--period", "m"]), today)
        yearly = pnl.resolve_report_window(pnl.build_parser().parse_args(["--period", "y"]), today)

        self.assertEqual((daily.from_date, daily.to_date, daily.periods_to_show), (today, today, ["daily"]))
        self.assertEqual((weekly.from_date, weekly.to_date, weekly.periods_to_show), (date(2026, 5, 11), today, ["weekly"]))
        self.assertEqual((monthly.from_date, monthly.to_date, monthly.periods_to_show), (date(2026, 5, 1), today, ["monthly"]))
        self.assertEqual((yearly.from_date, yearly.to_date, yearly.periods_to_show), (date(2026, 1, 1), today, ["yearly"]))

    def test_last_week_period_preset_resolves_to_previous_monday_through_sunday(self):
        today = date(2026, 6, 15)

        short_alias = pnl.resolve_report_window(
            pnl.build_parser().parse_args(["--period", "lw"]),
            today,
        )
        long_alias = pnl.resolve_report_window(
            pnl.build_parser().parse_args(["--period", "last-week"]),
            today,
        )

        self.assertEqual(
            (short_alias.from_date, short_alias.to_date, short_alias.periods_to_show, short_alias.mode_label),
            (date(2026, 6, 8), date(2026, 6, 14), ["weekly"], "지난주"),
        )
        self.assertEqual(long_alias, short_alias)

    def test_custom_date_range_outputs_single_range_section(self):
        args = pnl.build_parser().parse_args(["--from", "2026-05-01", "--to", "2026-05-11"])

        window = pnl.resolve_report_window(args, date(2026, 5, 13))

        self.assertEqual(window.from_date, date(2026, 5, 1))
        self.assertEqual(window.to_date, date(2026, 5, 11))
        self.assertEqual(window.periods_to_show, ["range"])
        self.assertEqual(pnl.group_key(datetime(2026, 5, 5, tzinfo=KST), "range"), "조회범위")

    def test_period_cannot_be_combined_with_custom_range(self):
        args = pnl.build_parser().parse_args(["--period", "d", "--from", "2026-05-01"])

        with self.assertRaises(ValueError):
            pnl.resolve_report_window(args, date(2026, 5, 13))

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

    def test_realized_section_uses_base_currency_quantity_label(self):
        realized_lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("100"),
                "matched_qty": Decimal("12.5"),
                "sell_uuid": "sell-1",
                "sell_trade_count": 1,
                "slot": 1,
            },
        ]

        out = StringIO()
        with redirect_stdout(out):
            pnl._print_realized_section(realized_lines, ["daily"], base_currency="USDT")

        output = out.getvalue()
        self.assertIn("매도수량(USDT)", output)
        self.assertNotIn("매도수량(BTC)", output)

    def test_unmatched_section_uses_base_currency_quantity_label(self):
        unmatched_lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "unmatched_proceeds": Decimal("1000"),
                "unmatched_qty": Decimal("7.25"),
                "sell_uuid": "sell-1",
                "slot": 1,
            },
        ]

        out = StringIO()
        with redirect_stdout(out):
            pnl._print_unmatched_section(unmatched_lines, ["daily"], base_currency="USDT")

        output = out.getvalue()
        self.assertIn("매도수량(USDT)", output)
        self.assertNotIn("매도수량(BTC)", output)

    def test_group_realized_by_slot_sums_pnl_qty_and_counts_distinct_sells(self):
        lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("100"),
                "matched_qty": Decimal("0.01"),
                "sell_uuid": "sell-a",
                "slot": 2,
            },
            {
                "time_key": datetime(2026, 5, 5, 11, 0, tzinfo=KST),
                "realized_pnl": Decimal("50"),
                "matched_qty": Decimal("0.02"),
                "sell_uuid": "sell-a",
                "slot": 2,
            },
            {
                "time_key": datetime(2026, 5, 5, 12, 0, tzinfo=KST),
                "realized_pnl": Decimal("-30"),
                "matched_qty": Decimal("0.005"),
                "sell_uuid": "sell-b",
                "slot": 2,
            },
            {
                "time_key": datetime(2026, 5, 5, 13, 0, tzinfo=KST),
                "realized_pnl": Decimal("999"),
                "matched_qty": Decimal("0.1"),
                "sell_uuid": "sell-c",
                "slot": 1,
            },
        ]

        groups = pnl.group_realized_by_slot(lines)

        # slot 오름차순 정렬
        self.assertEqual([g["slot"] for g in groups], [1, 2])

        slot1 = groups[0]
        self.assertEqual(slot1["realized_pnl_krw"], Decimal("999"))
        self.assertEqual(slot1["matched_qty"], Decimal("0.1"))
        self.assertEqual(slot1["order_count"], 1)

        slot2 = groups[1]
        # 합계: 100 + 50 + (-30)
        self.assertEqual(slot2["realized_pnl_krw"], Decimal("120"))
        # 합계: 0.01 + 0.02 + 0.005
        self.assertEqual(slot2["matched_qty"], Decimal("0.035"))
        # distinct sell_uuid: sell-a, sell-b → 2
        self.assertEqual(slot2["order_count"], 2)

    def test_group_realized_by_slot_returns_empty_for_no_lines(self):
        self.assertEqual(pnl.group_realized_by_slot([]), [])

    def test_group_realized_by_slot_pnl_sum_is_decimal_typed(self):
        lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("100"),
                "matched_qty": Decimal("0.01"),
                "sell_uuid": "sell-a",
                "slot": 7,
            },
        ]

        groups = pnl.group_realized_by_slot(lines)

        self.assertIsInstance(groups[0]["realized_pnl_krw"], Decimal)
        self.assertIsInstance(groups[0]["matched_qty"], Decimal)

    def test_realized_to_sell_lines_orders_by_time_then_sell_uuid(self):
        lines = [
            {
                "time_key": datetime(2026, 5, 5, 12, 0, tzinfo=KST),
                "realized_pnl": Decimal("30"),
                "matched_qty": Decimal("0.003"),
                "sell_uuid": "sell-late",
                "sell_trade_count": 1,
                "slot": 3,
            },
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("10"),
                "matched_qty": Decimal("0.001"),
                "sell_uuid": "sell-b",
                "sell_trade_count": 1,
                "slot": 1,
            },
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("20"),
                "matched_qty": Decimal("0.002"),
                "sell_uuid": "sell-a",
                "sell_trade_count": 1,
                "slot": 2,
            },
        ]

        sells = pnl.realized_to_sell_lines(lines)

        # 같은 시각이면 sell_uuid 오름차순(tie-break), 이후 시각 오름차순
        self.assertEqual(
            [s["sell_uuid"] for s in sells],
            ["sell-a", "sell-b", "sell-late"],
        )

    def test_realized_to_sell_lines_projects_only_detail_fields(self):
        lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("10"),
                "matched_qty": Decimal("0.001"),
                "sell_uuid": "sell-a",
                "sell_trade_count": 2,
                "slot": 5,
            },
        ]

        sells = pnl.realized_to_sell_lines(lines)

        self.assertEqual(len(sells), 1)
        line = sells[0]
        self.assertEqual(
            set(line.keys()),
            {"time_key", "slot", "matched_qty", "realized_pnl", "sell_uuid"},
        )
        self.assertEqual(line["slot"], 5)
        self.assertEqual(line["matched_qty"], Decimal("0.001"))
        self.assertEqual(line["realized_pnl"], Decimal("10"))
        self.assertEqual(line["sell_uuid"], "sell-a")

    def test_group_and_sell_lines_consume_run_fifo_output(self):
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

        realized_lines, *_ = pnl.run_fifo(orders)

        groups = pnl.group_realized_by_slot(realized_lines)
        sells = pnl.realized_to_sell_lines(realized_lines)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["slot"], 1)
        self.assertEqual(groups[0]["order_count"], 1)
        self.assertEqual(groups[0]["matched_qty"], Decimal("0.005"))
        self.assertEqual(groups[0]["realized_pnl_krw"], Decimal("99450.000"))

        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["sell_uuid"], "sell-1")
        self.assertEqual(sells[0]["slot"], 1)

    def test_print_report_uses_market_base_currency_in_all_quantity_sections(self):
        realized_lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "realized_pnl": Decimal("100"),
                "matched_qty": Decimal("12.5"),
                "sell_uuid": "sell-1",
                "sell_trade_count": 1,
                "slot": 1,
            },
        ]
        unmatched_lines = [
            {
                "time_key": datetime(2026, 5, 5, 10, 0, tzinfo=KST),
                "unmatched_proceeds": Decimal("1000"),
                "unmatched_qty": Decimal("7.25"),
                "sell_uuid": "sell-2",
                "slot": 1,
            },
        ]

        out = StringIO()
        with redirect_stdout(out):
            pnl.print_report_sections(
                realized_lines=realized_lines,
                unmatched_lines=unmatched_lines,
                unparseable_buys=[],
                unparseable_sells=[],
                outside_sell_orders=[],
                queues_by_slot={},
                reset_residuals=[],
                sorted_orders=[],
                display_start_dt=datetime(2026, 5, 5, tzinfo=KST),
                display_end_dt=datetime(2026, 5, 5, 23, 59, 59, tzinfo=KST),
                fetch_start_dt=datetime(2026, 5, 1, tzinfo=KST),
                lookback_days=30,
                periods=["daily"],
                market="KRW-USDT",
            )

        output = out.getvalue()
        self.assertIn("매도수량(USDT)", output)
        self.assertNotIn("매도수량(BTC)", output)


if __name__ == "__main__":
    unittest.main()
