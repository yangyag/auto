# USDT Realized PnL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/upbit_realized_pnl.py` default to the configured live market and print quantity labels using the market base currency.

**Architecture:** Keep the existing Upbit fetch and slot FIFO matching logic unchanged. Move market selection to runtime parser construction from `cfg.SYMBOL`, and pass a derived base-currency label into report printing functions instead of hard-coding `BTC`.

**Tech Stack:** Python, unittest, Upbit REST read-only script, existing `app.config.settings`.

---

## File Structure

- Modify `scripts/upbit_realized_pnl.py`: dynamic default market, base-currency helper, neutral quantity formatter aliases, and report label parameters.
- Modify `tests/test_upbit_realized_pnl.py`: TDD coverage for dynamic default market and USDT/BTC output labels.
- Modify `README.md`: update realized PnL description from fixed `KRW-BTC` to current `SYMBOL`.
- Modify `docs/quick-commands.md`: update the quick command section for current-market default and explicit BTC lookup.

---

### Task 1: Dynamic Default Market

**Files:**
- Modify: `tests/test_upbit_realized_pnl.py`
- Modify: `scripts/upbit_realized_pnl.py`

- [x] **Step 1: Write failing tests**

Add these tests to `tests/test_upbit_realized_pnl.py`:

```python
    def test_parser_defaults_market_to_current_config_symbol(self):
        with patch.object(pnl.cfg, "SYMBOL", "KRW-ETH"):
            args = pnl.build_parser().parse_args([])

        self.assertEqual(args.market, "KRW-ETH")

    def test_market_base_currency_parses_quote_base_market(self):
        self.assertEqual(pnl.market_base_currency("KRW-USDT"), "USDT")
        self.assertEqual(pnl.market_base_currency("krw-btc"), "BTC")
```

Also add `patch` to the existing import line:

```python
from unittest.mock import patch
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_upbit_realized_pnl.UpbitRealizedPnlTest.test_parser_defaults_market_to_current_config_symbol \
  tests.test_upbit_realized_pnl.UpbitRealizedPnlTest.test_market_base_currency_parses_quote_base_market -v
```

Expected: fails because `build_parser()` uses fixed `DEFAULT_MARKET`, and `market_base_currency()` does not exist.

- [x] **Step 3: Implement minimal code**

In `scripts/upbit_realized_pnl.py`, add:

```python
def default_market() -> str:
    return cfg.SYMBOL


def market_base_currency(market: str) -> str:
    if "-" not in market:
        return market.upper()
    return market.split("-", 1)[1].upper()
```

Change parser `--market` default from `DEFAULT_MARKET` to `default_market()`, and help text to use `default_market()`.

- [x] **Step 4: Run tests to verify they pass**

Run the same two-test command from Step 2.

Expected: PASS.

---

### Task 2: Base-Currency Quantity Labels

**Files:**
- Modify: `tests/test_upbit_realized_pnl.py`
- Modify: `scripts/upbit_realized_pnl.py`

- [x] **Step 1: Write failing output-label tests**

Add these tests to `tests/test_upbit_realized_pnl.py`:

```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_upbit_realized_pnl.UpbitRealizedPnlTest.test_realized_section_uses_base_currency_quantity_label \
  tests.test_upbit_realized_pnl.UpbitRealizedPnlTest.test_unmatched_section_uses_base_currency_quantity_label -v
```

Expected: errors because print functions do not accept `base_currency`, or failures because headers still use `BTC`.

- [x] **Step 3: Implement label parameters**

Update `_print_realized_section()` and `_print_unmatched_section()` signatures:

```python
def _print_realized_section(..., base_currency: str = "BTC") -> None:
```

```python
def _print_unmatched_section(..., base_currency: str = "BTC") -> None:
```

Change headers from `매도수량(BTC)` to:

```python
f" {'실현손익(KRW)':>18} {f'매도수량({base_currency})':>18}"
```

and:

```python
header = f"{'기간':<23} {'건수':>8} {'매도순대금(KRW)':>18} {f'매도수량({base_currency})':>18}"
```

- [x] **Step 4: Run tests to verify they pass**

Run the same two-test command from Step 2.

Expected: PASS.

---

### Task 3: Propagate Base Currency Through Main Output

**Files:**
- Modify: `tests/test_upbit_realized_pnl.py`
- Modify: `scripts/upbit_realized_pnl.py`

- [x] **Step 1: Write integration-style print test**

Add this test to `tests/test_upbit_realized_pnl.py`:

```python
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
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_upbit_realized_pnl.UpbitRealizedPnlTest.test_print_report_uses_market_base_currency_in_all_quantity_sections -v
```

Expected: error because `print_report_sections()` does not exist.

- [x] **Step 3: Extract report printing helper**

Create `print_report_sections()` in `scripts/upbit_realized_pnl.py` near the output functions. It should derive:

```python
base_currency = market_base_currency(market)
```

and call existing output section functions, passing `base_currency` to realized and unmatched sections.

Then replace the repeated print-section calls at the end of `main()` with a call to `print_report_sections(...)`.

- [x] **Step 4: Run test to verify it passes**

Run the same single-test command from Step 2.

Expected: PASS.

---

### Task 4: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/quick-commands.md`

- [x] **Step 1: Update docs**

Change the `upbit_realized_pnl.py` descriptions from fixed `KRW-BTC` to current `SYMBOL` based behavior. Include explicit BTC historical lookup:

```bash
STATE_BOT_KEY=krw-btc-live .venv/bin/python scripts/upbit_realized_pnl.py --market KRW-BTC
```

- [x] **Step 2: Check docs diff**

Run:

```bash
git diff -- README.md docs/quick-commands.md
```

Expected: only realized PnL wording changes.

---

### Task 5: Final Verification

**Files:**
- Test: `tests/test_upbit_realized_pnl.py`
- Test: broader focused suite

- [x] **Step 1: Run realized PnL tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_upbit_realized_pnl -v
```

Expected: PASS.

- [x] **Step 2: Run focused settings/script tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_upbit_realized_pnl tests.test_settings_env -v
```

Expected: PASS.

- [x] **Step 3: Run script help**

Run:

```bash
.venv/bin/python scripts/upbit_realized_pnl.py --help
```

Expected: `--market` help shows current configured default market.

- [x] **Step 4: Check diff**

Run:

```bash
git status --short
git diff -- scripts/upbit_realized_pnl.py tests/test_upbit_realized_pnl.py README.md docs/quick-commands.md docs/superpowers/plans/2026-05-28-usdt-realized-pnl.md
```

Expected: only intended files changed.
