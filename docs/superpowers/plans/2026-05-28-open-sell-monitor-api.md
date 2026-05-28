# Open Sell Monitor API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/upbit_open_sell_monitor.py` 의 핵심 로직을 `GET /v1/monitor/open-sells` 엔드포인트로 노출하여 Mobile App에서 호출 가능하게 한다.

**Architecture:** 기존 PnL API 패턴을 그대로 따른다. Service → Router → Schema 3계층. Service는 스크립트 함수를 import하여 JSON 응답으로 가공하고, Router는 JWT 인증 후 Service를 호출한다. 신규 파일 3개, 기존 파일 1개 수정.

**Tech Stack:** FastAPI, Pydantic, Python 3.11+, JWT Bearer 인증

---

## File Structure

| 파일 | 역할 |
|------|------|
| `app/api/schemas/monitor.py` (신규) | 요청/응답 Pydantic 모델 |
| `app/api/services/monitor_service.py` (신규) | `upbit_open_sell_monitor.py` 의 함수를 import하여 API 응답 가공 |
| `app/api/routers/monitor.py` (신규) | `GET /v1/monitor/open-sells` 엔드포인트 |
| `app/api/main.py` (수정) | monitor 라우터 등록 |

---

### Task 1: 응답 스키마 정의

**Files:**
- Create: `app/api/schemas/monitor.py`

- [ ] **Step 1: 스키마 파일 작성**

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.api.schemas.common import DecimalModel


class OpenSellRowSchema(DecimalModel):
    slot_index: Optional[int]
    qty: Decimal
    buy_unit_cost: Optional[Decimal]
    sell_limit_price: Decimal
    current_price: Decimal
    unrealized_at_current: Optional[Decimal]
    gap_to_fill_krw: Decimal


class OpenSellSummarySchema(DecimalModel):
    total_count: int
    matched_count: int
    unmatched_count: int
    profit_count: int
    loss_count: int
    total_unrealized_krw: Decimal


class OpenSellDiagnosticSchema(DecimalModel):
    open_orders: int
    matched: int
    unmatched: int
    lookback_days: int


class OpenSellMonitorResponse(DecimalModel):
    market: str
    current_price: Decimal
    generated_at: datetime
    rows: list[OpenSellRowSchema]
    summary: OpenSellSummarySchema
    diagnostic: OpenSellDiagnosticSchema
```

- [ ] **Step 2: 문법 오류 확인**

```bash
cd /home/yangyag/auto && .venv/bin/python -c "from app.api.schemas.monitor import OpenSellMonitorResponse; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/schemas/monitor.py
git commit -m "open sell monitor API 스키마 추가"
```

---

### Task 2: 서비스 계층 구현

**Files:**
- Create: `app/api/services/monitor_service.py`

- [ ] **Step 1: 서비스 파일 작성**

```python
from __future__ import annotations

import time
import warnings
from datetime import datetime
from decimal import Decimal

import requests

import app.config.settings as cfg
from app.api.schemas.monitor import (
    OpenSellDiagnosticSchema,
    OpenSellMonitorResponse,
    OpenSellRowSchema,
    OpenSellSummarySchema,
)
from scripts import upbit_realized_pnl as pnl
from scripts.upbit_actual_assets import _prepare_valid_orders, get_with_retry
from scripts.upbit_open_sell_monitor import (
    _compile_reset_pattern,
    _compile_slot_pattern,
    build_open_sell_rows,
    fetch_open_orders,
    fetch_remaining_buy_queues,
    match_open_sells_to_buy_lots,
)

try:
    from jwt.warnings import InsecureKeyLengthWarning
except ImportError:
    InsecureKeyLengthWarning = Warning

warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
warnings.filterwarnings(
    "ignore",
    message=r"The HMAC key is .* below the minimum recommended length of 64 bytes for SHA512\\.",
    category=Warning,
)

DEFAULT_LOOKBACK_DAYS = 120


def get_open_sell_monitor_data(
    *,
    market: str = pnl.DEFAULT_MARKET,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    bot_key: str | None = None,
    reset_sell_uuids: list[str] | None = None,
) -> OpenSellMonitorResponse:
    if not cfg.API_KEY or not cfg.API_SECRET:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY is not configured")

    if lookback_days <= 0:
        raise RuntimeError("lookback_days must be >= 1")

    bot_key = bot_key or cfg.STATE_BOT_KEY
    slot_pattern = _compile_slot_pattern(bot_key)
    reset_sell_uuids = reset_sell_uuids or []

    current_price_data = requests.get(
        f"{pnl.BASE_URL}/v1/ticker",
        params={"markets": market},
        timeout=10,
    )
    current_price_data.raise_for_status()
    ticker_list = current_price_data.json()
    current_price = pnl._to_decimal(ticker_list[0]["trade_price"])

    open_orders = fetch_open_orders(cfg.API_KEY, cfg.API_SECRET, market)
    time.sleep(pnl.RATE_LIMIT_SLEEP_SEC)

    queues_by_slot = fetch_remaining_buy_queues(
        api_key=cfg.API_KEY,
        api_secret=cfg.API_SECRET,
        market=market,
        lookback_days=lookback_days,
        reset_sell_uuids=set(reset_sell_uuids),
        bot_key=bot_key,
        slot_pattern=slot_pattern,
    )

    buy_cost_map = match_open_sells_to_buy_lots(open_orders, queues_by_slot, slot_pattern)
    rows = build_open_sell_rows(open_orders, buy_cost_map, current_price, slot_pattern)

    matched = sum(1 for r in rows if r.buy_unit_cost is not None)
    unmatched = len(rows) - matched

    profit_count = 0
    loss_count = 0
    total_unrealized = Decimal("0")
    for row in rows:
        if row.unrealized_at_current is not None:
            total_unrealized += row.unrealized_at_current
            if row.unrealized_at_current >= 0:
                profit_count += 1
            else:
                loss_count += 1

    schema_rows = [
        OpenSellRowSchema(
            slot_index=row.slot_index,
            qty=row.qty,
            buy_unit_cost=row.buy_unit_cost,
            sell_limit_price=row.sell_limit_price,
            current_price=row.current_price,
            unrealized_at_current=row.unrealized_at_current,
            gap_to_fill_krw=row.gap_to_fill_krw,
        )
        for row in rows
    ]

    return OpenSellMonitorResponse(
        market=market,
        current_price=current_price,
        generated_at=datetime.now(pnl.KST),
        rows=schema_rows,
        summary=OpenSellSummarySchema(
            total_count=len(rows),
            matched_count=matched,
            unmatched_count=unmatched,
            profit_count=profit_count,
            loss_count=loss_count,
            total_unrealized_krw=total_unrealized,
        ),
        diagnostic=OpenSellDiagnosticSchema(
            open_orders=len(open_orders),
            matched=matched,
            unmatched=unmatched,
            lookback_days=lookback_days,
        ),
    )
```

- [ ] **Step 2: 문법 오류 확인**

```bash
cd /home/yangyag/auto && .venv/bin/python -c "from app.api.services.monitor_service import get_open_sell_monitor_data; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/services/monitor_service.py
git commit -m "open sell monitor 서비스 계층 추가"
```

---

### Task 3: 라우터 정의

**Files:**
- Create: `app/api/routers/monitor.py`

- [ ] **Step 1: 라우터 파일 작성**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.api.schemas.monitor import OpenSellMonitorResponse
from app.api.services.monitor_service import get_open_sell_monitor_data

router = APIRouter(
    prefix="/v1/monitor",
    tags=["monitor"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/open-sells", response_model=OpenSellMonitorResponse)
def open_sells(
    market: str = Query(default="KRW-BTC"),
    lookback_days: int = Query(default=120, ge=1),
    bot_key: str | None = Query(default=None),
    reset_sell_uuid: list[str] = Query(default=[]),
) -> OpenSellMonitorResponse:
    try:
        return get_open_sell_monitor_data(
            market=market,
            lookback_days=lookback_days,
            bot_key=bot_key,
            reset_sell_uuids=reset_sell_uuid,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
```

- [ ] **Step 2: 문법 오류 확인**

```bash
cd /home/yangyag/auto && .venv/bin/python -c "from app.api.routers.monitor import router; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/routers/monitor.py
git commit -m "open sell monitor 라우터 추가"
```

---

### Task 4: main.py에 라우터 등록

**Files:**
- Modify: `app/api/main.py`

- [ ] **Step 1: main.py 수정**

변경 전 5-7라인:
```python
from app.api.errors import install_error_handlers
from app.api.routers import auth, commands, grid, health, ops, orders, pnl, runtime
```

변경 후:
```python
from app.api.errors import install_error_handlers
from app.api.routers import auth, commands, grid, health, monitor, ops, orders, pnl, runtime
```

변경 전 (router 등록 부분):
```python
    app.include_router(commands.router)
    return app
```

변경 후:
```python
    app.include_router(commands.router)
    app.include_router(monitor.router)
    return app
```

- [ ] **Step 2: FastAPI 앱 로드 확인**

```bash
cd /home/yangyag/auto && .venv/bin/python -c "from app.api.main import app; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/main.py
git commit -m "main.py에 monitor 라우터 등록"
```

---

### Task 5: EC2 배포 및 테스트

**Files:**
- (변경 없음 - 배포 및 검증 단계)

- [ ] **Step 1: EC2에 코드 동기화**

```bash
ssh ubuntu@<EC2_IP> "cd /home/ubuntu/auto && git pull"
```

- [ ] **Step 2: API 서비스 재시작**

```bash
ssh ubuntu@<EC2_IP> "systemctl --user restart auto-api.service"
```

- [ ] **Step 3: 서비스 상태 확인**

```bash
ssh ubuntu@<EC2_IP> "systemctl --user status auto-api.service && ss -ltnp | grep :8086"
```

- [ ] **Step 4: 헬스 체크**

```bash
ssh ubuntu@<EC2_IP> "curl -s http://127.0.0.1:8086/health"
```
예상: `{"status":"ok"}`

- [ ] **Step 5: 로그인 후 토큰 획득**

```bash
TOKEN=$(ssh ubuntu@<EC2_IP> "curl -s http://127.0.0.1:8086/v1/auth/login -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"<PASSWORD>\"}' | jq -r '.access_token'")
```

- [ ] **Step 6: open-sells 엔드포인트 호출**

```bash
ssh ubuntu@<EC2_IP> "curl -s http://127.0.0.1:8086/v1/monitor/open-sells -H 'Authorization: Bearer $TOKEN' | jq ."
```
예상: JSON 응답 (market, current_price, rows, summary, diagnostic 포함)

- [ ] **Step 7: Swagger 문서 확인**

```bash
ssh ubuntu@<EC2_IP> "curl -s http://127.0.0.1:8086/openapi.json | jq '.paths.\"/v1/monitor/open-sells\"'"
```
예상: 엔드포인트 정의 출력
