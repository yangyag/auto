# USDT Open Sell Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/upbit_open_sell_monitor.py` default and output labels follow the configured market, especially `KRW-USDT`.

**Architecture:** Keep the read-only Upbit fetch, FIFO matching, and unrealized PnL math unchanged. Reuse `scripts.upbit_realized_pnl.market_base_currency()` to derive the displayed quantity unit from the selected market.

**Tech Stack:** Python, unittest, argparse, existing Upbit monitor scripts.

---

## File Structure

- Create `tests/test_upbit_open_sell_monitor.py`: parser and output-label regression tests.
- Modify `scripts/upbit_open_sell_monitor.py`: neutral base quantity formatter and dynamic quantity label.
- Modify `README.md`: explain current `SYMBOL` behavior and explicit BTC lookup for open sell monitor.
- Modify `docs/quick-commands.md`: update open sell monitor quick commands.

---

### Task 1: Parser Default And Quantity Label Tests

**Files:**
- Create: `tests/test_upbit_open_sell_monitor.py`

- [x] **Step 1: Write failing tests**

Add:

```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_upbit_open_sell_monitor -v
```

Expected: first test may pass if default already follows `pnl.DEFAULT_MARKET`; second test fails because header still uses `qty(BTC)`.

---

### Task 2: Dynamic Base Quantity Label

**Files:**
- Modify: `scripts/upbit_open_sell_monitor.py`
- Test: `tests/test_upbit_open_sell_monitor.py`

- [x] **Step 1: Implement minimal label change**

Change `_fmt_btc()` into a neutral helper while keeping a compatibility alias:

```python
def _fmt_asset_qty(value: Decimal) -> str:
    return f"{value:.8f}"


def _fmt_btc(value: Decimal) -> str:
    return _fmt_asset_qty(value)
```

In `print_open_sell_summary()`, derive:

```python
base_currency = pnl.market_base_currency(market)
```

Change the header from:

```python
f"{'slot':>5}  {'qty(BTC)':>12}  {'매수원가':>14}  "
```

to:

```python
f"{'slot':>5}  {f'qty({base_currency})':>12}  {'매수원가':>14}  "
```

Change the row formatter call from `_fmt_btc(row.qty)` to `_fmt_asset_qty(row.qty)`.

- [x] **Step 2: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_upbit_open_sell_monitor -v
```

Expected: PASS.

---

### Task 3: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/quick-commands.md`

- [x] **Step 1: Update README**

In the open sell monitor section, state that the default target is current `SYMBOL`/`STATE_BOT_KEY`. Change the BTC historical example to:

```bash
.venv/bin/python scripts/upbit_open_sell_monitor.py --market KRW-BTC --bot-key krw-btc-live
```

- [x] **Step 2: Update quick commands**

In `docs/quick-commands.md`, state that quantity labels follow the selected market base asset. Change the BTC historical example to:

```bash
.venv/bin/python scripts/upbit_open_sell_monitor.py --market KRW-BTC --bot-key krw-btc-live
```

- [x] **Step 3: Check docs diff**

Run:

```bash
git diff -- README.md docs/quick-commands.md
```

Expected: only open sell monitor wording changes.

---

### Task 4: Final Verification

**Files:**
- Test: `tests/test_upbit_open_sell_monitor.py`
- Test: broader focused suite

- [x] **Step 1: Run new monitor tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_upbit_open_sell_monitor -v
```

Expected: PASS.

- [x] **Step 2: Run focused script tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_upbit_open_sell_monitor tests.test_upbit_realized_pnl tests.test_upbit_actual_assets -v
```

Expected: PASS.

- [x] **Step 3: Run script help**

Run:

```bash
.venv/bin/python scripts/upbit_open_sell_monitor.py --help
```

Expected: `--market` help shows current configured default market.

- [x] **Step 4: Check status and diff**

Run:

```bash
git status --short
git diff -- scripts/upbit_open_sell_monitor.py tests/test_upbit_open_sell_monitor.py README.md docs/quick-commands.md docs/superpowers/plans/2026-05-28-usdt-open-sell-monitor.md
```

Expected: only intended files changed.
