import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import scripts.upbit_open_sell_monitor as monitor


class UpbitOpenSellMonitorTest(unittest.TestCase):
    def test_parser_defaults_market_to_current_config_symbol(self):
        with patch.object(monitor.pnl, "DEFAULT_MARKET", "KRW-USDT"):
            args = monitor.build_parser().parse_args([])

        self.assertEqual(args.market, "KRW-USDT")

    def test_summary_uses_market_base_currency_quantity_label(self):
        rows = [
            monitor.OpenSellRow(
                slot_index=1,
                qty=Decimal("12.5"),
                buy_unit_cost=Decimal("1440"),
                sell_limit_price=Decimal("1450"),
                current_price=Decimal("1445"),
                unrealized_at_current=Decimal("62.5"),
                gap_to_fill_krw=Decimal("5"),
            )
        ]

        out = StringIO()
        with redirect_stdout(out):
            monitor.print_open_sell_summary(
                rows=rows,
                market="KRW-USDT",
                current_price=Decimal("1445"),
                lookback_days=120,
            )

        output = out.getvalue()
        self.assertIn("qty(USDT)", output)
        self.assertNotIn("qty(BTC)", output)


if __name__ == "__main__":
    unittest.main()
