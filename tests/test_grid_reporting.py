import unittest
from decimal import Decimal

from core.models import GridRow
from utils.grid_reporting import planned_buy_budget, summarize_planned_buy_budget


class GridReportingTest(unittest.TestCase):
    def test_planned_buy_budget_multiplies_price_and_planned_qty(self):
        row = GridRow(1, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1.25"))

        self.assertEqual(planned_buy_budget(row), Decimal("125"))

    def test_summarize_planned_buy_budget_uses_total_top_and_bottom_slots(self):
        rows = (
            GridRow(1, Decimal("100"), Decimal("0"), Decimal("105"), Decimal("1")),
            GridRow(2, Decimal("90"), Decimal("0"), Decimal("94.5"), Decimal("2")),
            GridRow(3, Decimal("80"), Decimal("0"), Decimal("84"), Decimal("3")),
        )

        summary = summarize_planned_buy_budget(rows)

        self.assertEqual(summary.total, Decimal("520"))
        self.assertEqual(summary.top_slot, Decimal("100"))
        self.assertEqual(summary.bottom_slot, Decimal("240"))

    def test_summarize_planned_buy_budget_returns_zeroes_for_empty_rows(self):
        summary = summarize_planned_buy_budget([])

        self.assertEqual(summary.total, Decimal("0"))
        self.assertEqual(summary.top_slot, Decimal("0"))
        self.assertEqual(summary.bottom_slot, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
