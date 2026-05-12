# Mobile API 설계 (FastAPI)

React Native (Android) 앱에서 사용할 API 서버 설계 문서. 기존 Python 봇 프로세스와 별도로 동작하며, PostgreSQL을 공유 상태 저장소로 사용한다.

## 1. 프로세스 토폴로지

```
[ React Native (Android) ]
            │ HTTPS + JWT
            ▼
   [ FastAPI 프로세스 ]  ─────┐
            │                 │ DB만 공유 (직접 호출 X)
            ▼                 ▼
       PostgreSQL  ◄────  [ 봇 프로세스 (app/main.py) ]
```

- **별도 프로세스** (uvicorn). 봇 메인 루프와 같은 머신/같은 DB를 쓰되 import는 공유하고 함수 호출/메모리 공유는 하지 않음. 봇이 죽어도 API는 살아 있고, API가 무거워져도 트레이딩 루프 cycle에 영향 없음.
- DB가 SSOT (Single Source of Truth). 그리드/주문/명령 모두 PostgreSQL 경유.
- `app/config/settings.py`, `app/storage/*`, `app/utils/*`는 그대로 재사용.

## 2. 폴더 구조

```
app/
  api/
    __init__.py
    main.py            # FastAPI 인스턴스, 라우터 등록, lifespan(repo wiring)
    deps.py            # Depends: repository, current_user, settings
    auth.py            # JWT 발급/검증
    errors.py          # 공통 예외 -> HTTP 매핑
    routers/
      health.py        # GET /health, /version
      grid.py          # GET /v1/grid/state, /v1/grid/summary
      orders.py        # GET /v1/orders/pending, /v1/orders/recent
      market.py        # GET /v1/market/price (WS cache 우선, fallback REST)
      pnl.py           # GET /v1/pnl/realized?period=d|w|m|y|all
      config.py        # GET /v1/config (read-only 핵심 설정)
      bot.py           # GET /v1/bot/status (pid/heartbeat)
      commands.py      # POST /v1/commands/*  (쓰기/위험 명령)
    schemas/           # pydantic v2 모델 (요청/응답 DTO)
      grid.py
      order.py
      pnl.py
      command.py
    services/          # 기존 app/* 코드를 호출하는 얇은 application layer
      grid_service.py     # show_grid_state.py 로직 함수화하여 재사용
      pnl_service.py      # scripts/upbit_realized_pnl.py 본체 함수화 후 호출
      command_service.py  # 위험 명령 큐잉/실행 상태 관리
db/migrations/
  20260512_add_commands.sql   # 명령 큐 테이블 (아래 §5)
```

스크립트(`scripts/*.py`)는 그대로 두되, 내부 로직을 함수로 추출해 API 서비스에서 같은 함수를 호출한다. CLI 진입점과 HTTP 진입점이 같은 함수를 공유하면 검증/유지보수가 쉬워진다.

## 3. 엔드포인트 (v1)

### 읽기 위주

| Method | Path | 용도 | 데이터 소스 |
|---|---|---|---|
| GET | `/health` | liveness | 자체 |
| GET | `/v1/bot/status` | 봇 alive/lag | DB heartbeat row 또는 pid lock |
| GET | `/v1/market/price` | 최신가/24h 변동 | upbit WS cache → REST fallback |
| GET | `/v1/grid/state` | 전체 슬롯 + recenter preview | `GridStateRepository.load()` |
| GET | `/v1/grid/summary` | 보유량/총 KRW 원가/평단/breakout/stop_loss 요약 | 위 snapshot 가공 |
| GET | `/v1/orders/pending` | DB pending 주문 | `PendingOrderRepository.list_open()` |
| GET | `/v1/orders/recent?limit=50` | 최근 체결/취소 (로그 또는 별도 테이블) | 추가 테이블 권장 |
| GET | `/v1/pnl/realized?period=d\|w\|m\|y\|all` | 일/주/월/년/누적 실현손익 | `upbit_realized_pnl` 함수 재사용 |
| GET | `/v1/config` | 핵심 설정 (read-only) | `app.config.settings` 화이트리스트 |

### 쓰기 (위험 명령은 별도 영역)

| Method | Path | 동작 |
|---|---|---|
| POST | `/v1/commands/bot/stop` | `stop.sh` 트리거 (큐잉) |
| POST | `/v1/commands/bot/start` | `run.sh` 트리거 (큐잉) |
| POST | `/v1/commands/reset` | `reset_krw_btc_live.py` 트리거 |
| POST | `/v1/commands/adjust-budget` | body `{target_budget}` → `adjust_budget_live.py` |
| GET | `/v1/commands/{id}` | 명령 상태/로그 조회 |

## 4. 인증/권한

- **단일 운영자 모델**: 사용자가 본인 한 명. 회원가입/패스워드 리셋 흐름은 불필요.
- 로그인: `POST /v1/auth/login` (username + password + TOTP) → JWT (access 15min) + refresh token (rotating, 30d).
- 시크릿/패스워드 해시(argon2)/TOTP secret은 환경변수 또는 별도 `auth_users` 테이블.
- **위험 명령**(`/v1/commands/reset`, `adjust-budget`)은 access token 외에 **즉시 TOTP 재확인**을 요구. 모바일 분실/세션 탈취 방어용.
- IP allowlist는 옵션 (모바일은 망 바뀌므로 강제하긴 어려움). 대신 rate limit + 명령 로그.
- CORS는 모바일이라 사실상 불필요. WebView로 안 띄울 거면 origin 화이트리스트 비활성화 가능.

## 5. 위험 명령 실행 모델

API가 절대 `subprocess.run`을 동기로 깔고 응답을 기다리지 않는다. 명령 큐 패턴이 필요하다.

```
commands 테이블 (PostgreSQL)
  id (uuid), kind (reset|adjust_budget|bot_start|bot_stop),
  params (jsonb), status (queued|running|succeeded|failed),
  requested_by, requested_at, started_at, finished_at,
  log (text), result (jsonb)
```

흐름:
1. `POST /v1/commands/reset` → row INSERT (`status=queued`) → `{id}` 즉시 반환 (202 Accepted).
2. 별도 워커 (`app/api/command_worker.py`, systemd unit 분리)가 `SELECT ... FOR UPDATE SKIP LOCKED` 로 큐 polling → 실행 → stdout/stderr 캡처 → status/log 업데이트.
3. 클라이언트는 `GET /v1/commands/{id}` 폴링 또는 SSE 스트림.

**왜 봇 프로세스가 직접 처리하지 않나**: `reset`은 `./stop.sh`로 봇을 죽이고 시작하는 절차다. 봇이 자기 자신을 죽이게 만들면 신호 처리/재기동 책임이 모호해진다. 워커가 외부에서 관리하는 게 안전.

**동시성 가드**: `kind` 별로 동시에 한 건만. `commands` 테이블에 partial unique index (`status in ('queued','running')`) 걸어 중복 큐잉 차단.

## 6. 봇과의 상태 통신

봇이 자기 살아있음을 알리는 heartbeat row를 주기적으로 업데이트:

```
bot_heartbeat (singleton row)
  bot_key, last_heartbeat_at, current_price, last_cycle_ts,
  breakout_guard_active, stop_loss_active, stop_loss_level
```

API의 `/v1/bot/status`, `/v1/grid/summary`는 이걸 읽어서 "최근 N초 안에 갱신됐는가" 로 health 판정. 봇 본체 코드에는 cycle 끝에 UPSERT 한 줄 추가만 하면 됨 (`app/main.py` 메인 루프 후미).

## 7. 실시간 푸시 (선택)

초기엔 클라이언트 폴링으로 시작 (2~5초 간격이면 충분). 나중에 필요해지면:

- `GET /v1/stream/ticker` (SSE): WS cache 변경 시 푸시.
- `GET /v1/stream/orders` (SSE): pending/체결 이벤트 푸시.

SSE를 먼저 권하는 이유: FastAPI 단방향이라 구현이 단순하고 모바일에서 fetch streaming으로 잘 받는다. WebSocket은 양방향 명령까지 보낼 거 아니면 과하다.

## 8. 의존성과 패키지

`requirements.txt`에 추가:
```
fastapi
uvicorn[standard]
pydantic              # v2
python-jose[cryptography]   # JWT
passlib[argon2]
pyotp                 # TOTP
```

기존 코드에는 영향 없음. `app/api`만 import.

## 9. 운영 구동

- `systemd` 또는 `docker-compose.yml`에 서비스 두 개 분리:
  - `auto-bot.service`: 기존 `./run.sh`
  - `auto-api.service`: `uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1`
  - `auto-command-worker.service`: 명령 큐 워커
- 외부 노출은 Caddy/Nginx로 TLS 종단 + reverse proxy. ACME 자동 갱신.
- `workers 1`로 두는 이유: 단일 사용자 + 모바일 트래픽 미미 + repository는 thread-safe 아니므로 굳이 멀티프로세스 가성비 없음.

## 10. 우선순위 (단계적으로)

1. **MVP**: auth (JWT만, TOTP 후행) → `/health` → `/v1/grid/state`, `/grid/summary` → `/v1/orders/pending` → `/v1/market/price`.
2. **읽기 확장**: `/v1/pnl/realized`, `/v1/bot/status` (heartbeat 테이블 추가).
3. **명령 큐**: `commands` 테이블 + 워커 → `bot/stop`, `bot/start`.
4. **위험 명령**: `reset`, `adjust-budget` + TOTP 강제.
5. **실시간**: SSE ticker/orders.

이 정도면 봇 본체에 추가되는 코드는 heartbeat UPSERT 한 군데뿐이고, 나머지는 모두 `app/api/` 와 새 테이블에 격리된다.
