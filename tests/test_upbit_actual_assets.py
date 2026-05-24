import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

import scripts.upbit_actual_assets as actual_assets


class UpbitActualAssetsTest(unittest.TestCase):
    def test_parser_defaults_to_120_day_lookback(self):
        args = actual_assets.build_parser().parse_args([])

        self.assertEqual(args.lookback_days, 120)

    def test_summary_uses_bot_lot_cost_separately_from_upbit_average_cost(self):
        accounts = [
            {
                "currency": "KRW",
                "balance": "1000",
                "locked": "50",
            },
            {
                "currency": "BTC",
                "balance": "0.01",
                "locked": "0.02",
                "avg_buy_price": "100000000",
            },
        ]
        queues_by_slot = {
            1: [
                {"qty": Decimal("0.01"), "unit_cost": Decimal("110000000")},
            ],
            2: [
                {"qty": Decimal("0.02"), "unit_cost": Decimal("120000000")},
            ],
        }

        summary = actual_assets.build_actual_asset_summary(
            accounts=accounts,
            market="KRW-BTC",
            current_price=Decimal("130000000"),
            queues_by_slot=queues_by_slot,
        )

        self.assertEqual(summary.krw_total, Decimal("1050"))
        self.assertEqual(summary.base_total, Decimal("0.03"))
        self.assertEqual(summary.upbit_avg_cost_krw, Decimal("3000000.00"))
        self.assertEqual(summary.bot_lot_cost_krw, Decimal("3500000.00"))
        self.assertEqual(summary.bot_book_total_krw, Decimal("3501050.00"))
        self.assertEqual(summary.mark_to_market_total_krw, Decimal("3901050.00"))
        self.assertEqual(summary.avg_cost_gap_krw, Decimal("500000.00"))
        self.assertTrue(summary.quantity_matches)

    def test_summary_flags_quantity_mismatch(self):
        accounts = [
            {"currency": "KRW", "balance": "0", "locked": "0"},
            {
                "currency": "BTC",
                "balance": "0.03",
                "locked": "0",
                "avg_buy_price": "100000000",
            },
        ]
        queues_by_slot = {
            1: [{"qty": Decimal("0.02"), "unit_cost": Decimal("110000000")}],
        }

        summary = actual_assets.build_actual_asset_summary(
            accounts=accounts,
            market="KRW-BTC",
            current_price=Decimal("130000000"),
            queues_by_slot=queues_by_slot,
        )

        self.assertFalse(summary.quantity_matches)
        self.assertEqual(summary.quantity_gap, Decimal("-0.01"))

    def test_get_with_retry_retries_429_response(self):
        first_response = Mock()
        first_response.status_code = 429
        first_response.json.return_value = {"error": {"name": "too_many_requests"}}

        second_response = Mock()
        second_response.status_code = 200
        second_response.json.return_value = [{"currency": "KRW", "balance": "1000"}]

        with patch.object(
            actual_assets.requests,
            "get",
            side_effect=[first_response, second_response],
        ) as request_get, patch.object(actual_assets.time, "sleep") as sleep:
            data = actual_assets.get_with_retry("key", "s" * 64, "/v1/accounts", {})

        self.assertEqual(data, [{"currency": "KRW", "balance": "1000"}])
        self.assertEqual(request_get.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
