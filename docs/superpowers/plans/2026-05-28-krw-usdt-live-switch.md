# KRW-USDT Live Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the local live grid configuration from `KRW-BTC` to `KRW-USDT` with a separate bot key and a 1430-1530 KRW, 10,000,000 KRW grid.

**Architecture:** Keep existing code defaults backward compatible, but allow runtime market selection through `.env`. The database grid is rebuilt from `grid.properties` under the new `STATE_BOT_KEY`, so prior BTC state remains separate.

**Tech Stack:** Python, unittest, PostgreSQL-backed state scripts, dotenv-compatible `.env` loading.

---

## File Structure

- Modify `app/config/settings.py`: load `SYMBOL` from the environment with `KRW-BTC` as the default.
- Modify `tests/test_settings_env.py`: add a regression test proving `.env` can override `SYMBOL`.
- Modify `.env_sample`: document `SYMBOL=KRW-BTC` for new installs.
- Modify `.env`: set `SYMBOL=KRW-USDT` and `STATE_BOT_KEY=krw-usdt-live-local`.
- Modify `grid.properties`: set the USDT grid range, keep the existing budget/TP values, and set a valid `band_multiple` stop-loss margin for the narrower USDT range.
- Use `scripts/apply_grid_properties_to_postgres.py`: rebuild the PostgreSQL grid for the new bot key.

---

### Task 1: Make `SYMBOL` Environment-Configurable

**Files:**
- Modify: `tests/test_settings_env.py`
- Modify: `app/config/settings.py`
- Modify: `.env_sample`

- [ ] **Step 1: Write the failing test**

Add this test method to `tests/test_settings_env.py`:

```python
    def test_settings_loads_symbol_from_env_file(self):
        project_root = Path(__file__).resolve().parents[1]
        settings_source = (project_root / "app" / "config" / "settings.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "app" / "config").mkdir(parents=True)
            (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "settings.py").write_text(settings_source, encoding="utf-8")
            (tmp_path / ".env").write_text("SYMBOL=KRW-USDT\n", encoding="utf-8")

            env = os.environ.copy()
            env.pop("SYMBOL", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import sys
                        sys.path.insert(0, r'__TMPDIR__')
                        import app.config.settings as settings
                        print(settings.SYMBOL)
                        """.replace("__TMPDIR__", str(r"__TMPDIR__"))
                    ),
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "KRW-USDT")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_settings_env.SettingsEnvLoadingTest.test_settings_loads_symbol_from_env_file -v`

Expected: FAIL because `settings.SYMBOL` is still hard-coded to `KRW-BTC`.

- [ ] **Step 3: Write minimal implementation**

Change `app/config/settings.py` from:

```python
SYMBOL = "KRW-BTC"
```

to:

```python
SYMBOL = os.getenv("SYMBOL", "KRW-BTC")
```

Add this line to `.env_sample` near the Upbit credentials:

```bash
SYMBOL=KRW-BTC
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_settings_env.SettingsEnvLoadingTest.test_settings_loads_symbol_from_env_file -v`

Expected: PASS.

---

### Task 2: Set Local USDT Operating Inputs

**Files:**
- Modify: `.env`
- Modify: `grid.properties`

- [ ] **Step 1: Update `.env`**

Set the operating market and separated bot key:

```bash
SYMBOL=KRW-USDT
STATE_BOT_KEY=krw-usdt-live-local
```

- [ ] **Step 2: Update `grid.properties`**

Set the grid boundaries, set a 10,000,000 KRW budget, and use the smallest practical `band_multiple` adjustment that passes the existing stop-loss validation for `1430~1530`:

```properties
MIN_BUY_PRICE=1430
MAX_BUY_PRICE=1530
TOTAL_BUDGET_KRW=10000000
GRID_STEP_PCT=0.2
STOP_LOSS_BAND_MULTIPLE=1.55
```

- [ ] **Step 3: Verify local settings load correctly**

Run:

```bash
.venv/bin/python - <<'PY'
import app.config.settings as cfg
print(cfg.SYMBOL)
print(cfg.STATE_BOT_KEY)
PY
```

Expected output:

```text
KRW-USDT
krw-usdt-live-local
```

- [ ] **Step 4: Verify grid properties generate valid rows**

Run:

```bash
.venv/bin/python - <<'PY'
from app.core.grid_properties import build_grid_rows_from_property_spec, load_grid_property_spec
spec = load_grid_property_spec("grid.properties")
rows = build_grid_rows_from_property_spec(spec)
print(len(rows))
print(rows[0].buy_price)
print(rows[-1].buy_price)
print(spec.total_budget_krw)
PY
```

Expected: row count greater than 1, top buy price `1530`, bottom buy price `1430`, total budget `10000000`.

---

### Task 3: Rebuild the Local PostgreSQL Grid and Verify

**Files:**
- Uses: `scripts/apply_grid_properties_to_postgres.py`
- Uses: `scripts/show_grid_state.py`

- [ ] **Step 1: Confirm the trading bot is not running**

Run:

```bash
test -f .auto-trading.pid && cat .auto-trading.pid || true
ps -eo pid,args | grep '[p]ython.*/main.py' || true
```

Expected: no active `python ... main.py` bot process.

- [ ] **Step 2: Rebuild the PostgreSQL grid for the new bot key**

Run:

```bash
.venv/bin/python scripts/apply_grid_properties_to_postgres.py --force
```

Expected: `상태: 성공`, `symbol: KRW-USDT`, `top_buy_price: 1530`, `bottom_buy_price: 1430`.

- [ ] **Step 3: Inspect the saved grid**

Run:

```bash
.venv/bin/python scripts/show_grid_state.py
```

Expected: output references `postgres:auto_trading/krw-usdt-live-local`, `심볼: KRW-USDT`, and a 1430-1530 grid.

---

### Task 4: Final Verification

**Files:**
- Test: `tests/test_settings_env.py`
- Test: `tests/test_grid_properties.py`

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_settings_env tests.test_grid_properties -v
```

Expected: all tests pass.

- [ ] **Step 2: Check final diff**

Run:

```bash
git status --short
git diff -- app/config/settings.py tests/test_settings_env.py .env_sample grid.properties docs/superpowers/plans/2026-05-28-krw-usdt-live-switch.md
```

Expected: only the intended files are modified or added. `.env` may be modified locally but remains ignored by git.
