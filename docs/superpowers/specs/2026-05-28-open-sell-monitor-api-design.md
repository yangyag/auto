# Open Sell Monitor API — Design Spec

## Purpose

`scripts/upbit_open_sell_monitor.py` 의 핵심 로직을 FastAPI 엔드포인트로 노출.
Mobile App에서 JWT 인증 후 호출 가능하게 한다.

## Pattern

기존 `pnl_service.py` + `routers/pnl.py` 패턴을 그대로 따른다:
- **Service layer**: `app/api/services/monitor_service.py` — 스크립트의 함수를 import하여 API 응답으로 가공
- **Schema layer**: `app/api/schemas/monitor.py` — Pydantic 응답 모델
- **Router layer**: `app/api/routers/monitor.py` — `GET /v1/monitor/open-sells`
- **Registration**: `app/api/main.py` 에 라우터 등록

## Endpoint

```
GET /v1/monitor/open-sells
```

### Query Parameters

| 이름 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `market` | string | 선택 | KRW-BTC | 업비트 마켓 코드 |
| `lookback_days` | int | 선택 | 120 | BUY 큐 계산용 주문 조회 기간 |
| `bot_key` | string | 선택 | cfg.STATE_BOT_KEY | identifier bot key prefix |
| `reset_sell_uuid` | string[] | 선택 | [] | 과거 reset SELL uuid |

### Response (200)

```json
{
  "market": "KRW-BTC",
  "current_price": "152000000",
  "generated_at": "2026-05-28T14:30:00+09:00",
  "rows": [
    {
      "slot_index": 3,
      "qty": "0.00100",
      "buy_unit_cost": "148500000",
      "sell_limit_price": "153000000",
      "current_price": "152000000",
      "unrealized_at_current": "3500",
      "gap_to_fill_krw": "1000000"
    }
  ],
  "summary": {
    "total_count": 5,
    "matched_count": 4,
    "unmatched_count": 1,
    "profit_count": 3,
    "loss_count": 1,
    "total_unrealized_krw": "5000"
  },
  "diagnostic": {
    "open_orders": 5,
    "matched": 4,
    "unmatched": 1,
    "lookback_days": 120
  }
}
```

### Errors

- `401` — JWT 인증 실패
- `503` — Upbit 키 미설정 / API 호출 실패

## Implementation Steps

1. `app/api/schemas/monitor.py` — 응답 스키마 정의
2. `app/api/services/monitor_service.py` — 스크립트 로직 래핑
3. `app/api/routers/monitor.py` — 엔드포인트 정의
4. `app/api/main.py` — 라우터 등록
5. EC2 배포 및 테스트

## Non-Goals

- CLI 스크립트 자체를 수정하지 않음
- POST/명령 API가 아닌 순수 읽기 전용
- WebSocket 지원 없음
