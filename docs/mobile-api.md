# Mobile API 사용 문서

React Native Android 앱에서 자동매매 상태를 조회하고 운영 명령을 요청하기 위한 FastAPI 서버 문서다.

🚀 FastAPI · Port 8086
🔐 JWT · Bearer
⚙ auto-api.service
⚡ auto-command-worker.service

🌐Base URL

외부
:   http://<EC2\_PUBLIC\_IP>:8086

EC2 내부
:   http://127.0.0.1:8086

OpenAPI
:   GET /openapi.json

Swagger
:   GET /docs

🔑인증

방식
:   Bearer JWT

헤더
:   Authorization: Bearer <access\_token>

만료
:   access 15분 (900s)

갱신
:   refresh\_token

📦Content Type

요청
:   application/json

응답
:   application/json

인코딩
:   UTF-8

HTML 점검
:   GET /ops

⚠에러 응답

형식
:   FastAPI HTTPException

본문
:   {"detail": "..."}

2xx
:   200201

4xx/5xx
:   401409503

## 한 줄 요약

`./run.sh`는 트레이딩 봇만 실행한다. 모바일 앱용 API는 `auto-api.service`, 앱에서 요청한 명령을 실제로 실행하는 워커는 `auto-command-worker.service`로 따로 실행된다.

📌 분리된 3개의 프로세스

트레이딩 봇 / FastAPI 서버 / 명령 워커가 각각 독립 실행되며 PostgreSQL을 통해 상태를 공유한다.

## 구현 위치

| 경로 | 역할 |
| --- | --- |
| `app/api/main.py` | FastAPI 인스턴스 생성, 라우터 등록 |
| `app/api/routers/` | 인증, 상태 조회, 그리드, 주문, 손익, 명령 API 라우터 |
| `app/api/schemas/` | API 요청/응답 Pydantic 모델 |
| `app/api/services/` | 기존 봇 저장소/스크립트 로직을 HTTP 응답으로 가공하는 서비스 계층 |
| `app/api/command_worker.py` | `commands` 테이블에 쌓인 운영 명령 실행 |
| `db/migrations/004_mobile_api.sql` | 모바일 API용 heartbeat, 명령, refresh token 테이블 |
| `deploy/systemd/user/auto-api.service` | FastAPI 서버 user systemd unit |
| `deploy/systemd/user/auto-command-worker.service` | 명령 워커 user systemd unit |

## 전체 실행 구조

운영 서버에는 역할이 다른 프로세스가 3개 있다.

| 역할 | 실행 방식 | 하는 일 | 꺼져 있으면 |
| --- | --- | --- | --- |
| 트레이딩 봇 | `./run.sh` | 가격을 보고 실제 그리드 매수/매도 로직을 실행한다. | 자동매매가 멈춘다. |
| 모바일 API | `auto-api.service` | React Native 앱이 호출하는 HTTP API 서버다. 8086 포트로 열린다. | 앱에서 상태 조회/로그인이 안 된다. |
| 명령 워커 | `auto-command-worker.service` | 앱에서 요청한 시작/중지/reset 같은 명령을 큐에서 꺼내 실행한다. | 앱에서 명령을 넣어도 실행되지 않고 큐에 남는다. |

흐름은 아래와 같다.

text

```
React Native 앱
  -> FastAPI 서버(auto-api.service, 8086)
  -> PostgreSQL
  <- 트레이딩 봇(./run.sh로 실행되는 main.py)

위험 명령:
React Native 앱
  -> FastAPI 서버
  -> commands 테이블에 큐 저장
  -> 명령 워커(auto-command-worker.service)
  -> stop.sh/run.sh/reset 스크립트 실행
```

📌 메모리 분리

FastAPI가 트레이딩 봇을 메모리에서 직접 호출하지 않는다. 둘은 PostgreSQL을 통해 상태를 공유한다. 그래서 API를 재시작해도 봇 루프가 바로 죽지 않고, 봇이 꺼져 있어도 API 서버 자체는 살아 있을 수 있다.

## 가장 자주 쓰는 운영 명령

EC2에서 작업할 때는 먼저 프로젝트 폴더로 이동한다.

bash

```
cd /home/ubuntu/auto
```

### 트레이딩 봇만 재시작

bash

```
./stop.sh
./run.sh
```

### 모바일 API와 명령 워커 재시작

bash

```
systemctl --user restart auto-api.service auto-command-worker.service
```

### 전체 상태 확인

bash

```
ps -ef | grep '/home/ubuntu/auto/main.py' | grep -v grep
systemctl --user status auto-api.service auto-command-worker.service
ss -ltnp | grep :8086
```

### 로그 확인

bash

```
journalctl --user -u auto-api.service -f
journalctl --user -u auto-command-worker.service -f
tail -f logs/trading-$(date +%F).log
```

## 배포 상태

- API URL: `http://<EC2_PUBLIC_IP>:8086`
- EC2 내부 확인 URL: `http://127.0.0.1:8086`
- 브라우저 점검 화면: `GET /ops`
- FastAPI 서비스: `auto-api.service`
- 명령 워커 서비스: `auto-command-worker.service`
- OpenAPI: `GET /openapi.json`
- Swagger UI: `GET /docs`

⚠ Linger 설정

현재 user systemd로 설치되어 있다. `loginctl show-user "$USER" -p Linger` 값은 `Linger=yes`여야 SSH 접속이 끊겨도 user service가 유지된다.

⚠ HTTPS 권장

현재 8086 포트는 직접 HTTP로 열려 있다. 실제 모바일 앱에 장기간 사용할 때는 도메인/Caddy/Nginx를 붙여 HTTPS로 종단하는 구성이 더 안전하다.

서비스 파일 원본:

- `deploy/systemd/user/auto-api.service`
- `deploy/systemd/user/auto-command-worker.service`

## 브라우저 점검 화면

간단히 눈으로 API 상태를 확인하려면 브라우저에서 아래 주소를 연다.

text

```
http://<EC2_PUBLIC_IP>:8086/ops
```

이 화면은 FastAPI가 직접 내려주는 HTML이다. HTML과 API가 같은 서버/같은 포트에서 열리므로 CORS 문제가 없다.

### 화면에서 할 수 있는 일

- API 상태 확인
- 아이디/비밀번호 로그인
- 봇 상태 조회
- 그리드 요약 조회
- 그리드 전체 조회: 슬롯별 매수가, 계획 매수 BTC/KRW, 보유 BTC/KRW, 매도가, 미체결 주문
- 현재가 조회
- 미체결 주문 조회
- 오늘/이번주/이번달/올해/전체 실현손익 조회

📌 조회 전용

이 화면에는 reset, 예산 조정, 봇 중지 같은 위험 명령 버튼을 넣지 않았다. 운영 상태를 바꾸지 않고 조회만 해보는 용도다.

## 환경 변수

환경 변수는 `/home/ubuntu/auto/.env`에서 읽는다.

### 모바일 API 자체에 필요한 값

dotenv

```
MOBILE_API_USERNAME=admin
MOBILE_API_PASSWORD=<strong-password>
MOBILE_API_JWT_SECRET=<random-secret>
```

### 선택 값

dotenv

```
# 설정하면 로그인/위험 명령에 TOTP 코드가 필요하다.
MOBILE_API_TOTP_SECRET=<base32-secret>
```

### Upbit 관련 값

dotenv

```
UPBIT_ACCESS_KEY=<upbit-access-key>
UPBIT_SECRET_KEY=<upbit-secret-key>
```

⚠ Upbit 키 필수 엔드포인트

`/v1/pnl/realized`는 Upbit의 private 주문 조회 API를 사용하므로 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`가 필요하다. 키가 비어 있으면 503을 반환한다.

### WebSocket 설정 (선택)

WebSocket 설정은 코드 기본값이 있지만, 운영 의도를 분명히 남기려면 `.env`에 명시해도 된다.

dotenv

```
UPBIT_WS_PUBLIC_ENABLED=true
UPBIT_WS_PRICE_MAX_AGE_SECONDS=10
UPBIT_WS_EVENT_LOOP_ENABLED=true
UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=3
UPBIT_WS_CANDLE_ENABLED=false
UPBIT_WS_CANDLE_MAX_AGE_SECONDS=60
UPBIT_WS_ASSET_ENABLED=false
UPBIT_WS_ASSET_MAX_AGE_SECONDS=30
UPBIT_WS_ORDER_ENABLED=false
UPBIT_WS_ORDER_MAX_AGE_SECONDS=10
```

`.env`를 수정한 뒤에는 해당 값을 읽는 프로세스를 재시작해야 한다.

bash

```
# 봇 설정 변경 반영
./stop.sh
./run.sh

# API/worker 설정 변경 반영
systemctl --user restart auto-api.service auto-command-worker.service
```

## 인증 흐름

앱은 먼저 로그인해서 `access_token`과 `refresh_token`을 받는다.

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `access_token` | string | 응답 | API 호출 때 `Authorization` 헤더에 넣는다. 유효 시간은 15분이다. |
| `refresh_token` | string | 응답 | access token을 새로 받을 때 쓴다. 앱의 보안 저장소에 저장한다. |
| `totp_code` | string | 조건부 | `MOBILE_API_TOTP_SECRET`을 설정한 경우에만 필요하다. |

POST
/v1/auth/login
로그인 (access + refresh 발급)

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "admin",
    "password": "<password>",
    "totp_code": "123456"
  }'
```

#### Response

json

```
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

POST
/v1/auth/refresh
access\_token 재발급

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
```

POST
/v1/auth/logout
refresh\_token 무효화

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/auth/logout \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
```

## React Native 호출 예시

토큰은 Android Keystore 기반 secure storage에 저장한다. 예시는 `react-native-keychain` 사용 형태다.

ts

```
import * as Keychain from 'react-native-keychain';

const API_BASE = 'http://<EC2_PUBLIC_IP>:8086';

export async function login(username: string, password: string, totpCode?: string) {
  const res = await fetch(`${API_BASE}/v1/auth/login`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username, password, totp_code: totpCode}),
  });
  if (!res.ok) throw new Error(await res.text());
  const tokens = await res.json();
  await Keychain.setGenericPassword('auto-mobile-api', JSON.stringify(tokens));
  return tokens;
}

export async function apiGet(path: string) {
  const stored = await Keychain.getGenericPassword();
  if (!stored) throw new Error('not logged in');

  const {access_token} = JSON.parse(stored.password);
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {Authorization: `Bearer ${access_token}`},
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

## 읽기 API

읽기 API는 상태를 보여줄 뿐, 주문을 만들거나 봇을 멈추지 않는다. 모두 `Authorization: Bearer <access_token>` 헤더가 필요하다.

| API | 앱에서 보여줄 내용 | 비고 |
| --- | --- | --- |
| `GET /v1/bot/status` | 봇 alive 여부, 마지막 heartbeat, 손절/브레이크아웃 상태 | 봇이 꺼져 있으면 API는 살아 있어도 `is_alive=false`가 될 수 있다. |
| `GET /v1/market/price` | 현재가 | 봇 heartbeat 가격이 fresh하면 우선 사용하고, 없으면 Upbit public REST를 사용한다. |
| `GET /v1/grid/state` | 전체 그리드 슬롯 목록 | 각 슬롯의 매수가, 계획 매수 BTC/KRW, 보유 BTC/KRW, 매도가, pending 주문을 확인한다. |
| `GET /v1/grid/summary` | 그리드 요약 | 보유 슬롯 수, 총 재고, 원가, 평균 매수가 등을 보여준다. |
| `GET /v1/orders/pending` | DB 기준 미체결 주문 | 봇이 관리하는 open 주문 목록이다. |
| `GET /v1/orders/recent?limit=50` | 최근 주문 이력 | DB에 기록된 주문 기준이다. |
| `GET /v1/pnl/realized?period=d` | 오늘 실현손익 | `d/w/m/y/all` 기간을 지원한다. Upbit 키가 필요하다. |
| `GET /v1/monitor/open-sells` | 매도 대기 주문 현황 | 슬롯별 매수원가, 미실현손익, 도달까지 거리를 보여준다. |
| `GET /v1/config` | 앱에 보여줘도 되는 핵심 설정 | secret은 반환하지 않는다. |

GET
/v1/bot/status
봇 alive, heartbeat, 손절/브레이크아웃 상태

봇이 꺼져 있으면 API는 살아 있어도 `is_alive=false`가 될 수 있다.

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/bot/status \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/market/price
현재가 (heartbeat 우선, fallback Upbit REST)

봇 heartbeat 가격이 fresh하면 우선 사용하고, 없으면 Upbit public REST를 사용한다.

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/market/price \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/grid/state
전체 그리드 슬롯 목록

각 슬롯의 매수가, 계획 매수 BTC/KRW, 보유 BTC/KRW, 매도가, pending 주문을 확인한다.

#### Slot 필드

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `buy_price` | number | 해당 슬롯의 매수 기준 가격 |
| `planned_qty`, `planned_buy_krw` | number | 아직 비어 있는 슬롯에서 매수할 목표 BTC 수량과 KRW 금액 |
| `held_qty`, `inventory_cost_krw` | number | 이미 매수되어 보유 중인 BTC 수량과 원가 |
| `sell_price`, `effective_sell_price` | number | 기본 매도 기준 가격과 Age TP 등이 반영된 실제 매도 기준 가격 |
| `pending_order` | object | null | 해당 슬롯에 아직 완료되지 않은 주문이 있으면 주문 정보 |

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/grid/state \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/grid/summary
그리드 요약 (보유 슬롯, 재고, 평균 매수가 등)

보유 슬롯 수, 총 재고, 원가, 평균 매수가 등을 보여준다.

⚠ 원가 기준

모바일 API나 앱에서 원금성 지표를 만들 때 업비트 `avg_buy_price` 를 봇 슬롯 원가로 대체하지 않는다. 업비트 평균매수가는 계정 전체 BTC 평균이고, 그리드 봇의 원가는 슬롯별 BUY/SELL 매칭 결과다.

낮은 슬롯이 먼저 매도되고 높은 슬롯이 남는 구간에서는 `주문 가능 KRW + avg_buy_price * BTC 수량` 이 봇 장부 기준 원금과 다르게 보일 수 있다. 봇 기준 원금/잔여 원가는 그리드 슬롯 상태와 실현손익 매칭 로직의 잔여 BUY 큐를 기준으로 해석하며, 운영 서버에서는 `scripts/upbit_actual_assets.py` 를 바로 실행해 확인한다.

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/grid/summary \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/orders/pending
DB 기준 미체결 주문 목록

봇이 관리하는 open 주문 목록이다.

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/orders/pending \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/orders/recent?limit=50
최근 주문 이력

DB에 기록된 주문 기준이다.

#### Query

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `limit` | int | 선택 | 가져올 행 수 (기본 50) |

#### Request

bash

```
curl -s "http://127.0.0.1:8086/v1/orders/recent?limit=50" \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/pnl/realized?period=d
실현손익 (Upbit private API)

`d/w/m/y/all` 기간을 지원한다. Upbit 키가 필요하다.

#### Query

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `period` | enum | 필수 | `d` / `w` / `m` / `y` / `all` |

#### Status

200 정상
401 토큰 없음/만료
503 Upbit 키 누락

#### Request

bash

```
curl -s "http://127.0.0.1:8086/v1/pnl/realized?period=d" \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/config
앱에 보여줘도 되는 핵심 설정 (secret 제외)

secret은 반환하지 않는다.

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/config \
  -H "Authorization: Bearer <access_token>"
```

GET
/v1/monitor/open-sells
매도 대기 주문 현황 (슬롯별 매수원가 + 미실현손익)

현재 미체결 매도 주문을 봇 슬롯별 실제 매수원가와 매칭해, 각 슬롯의 매수원가, 매도지정가, 현재가 기준 미실현손익, 체결까지 남은 거리를 보여준다.

#### Query

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `market` | string | 선택 | 업비트 마켓 코드 (기본: `KRW-BTC`) |
| `lookback_days` | int | 선택 | BUY 큐 계산용 주문 조회 기간 (기본: `120`) |
| `bot_key` | string | 선택 | identifier bot key prefix (기본: `cfg.STATE_BOT_KEY`) |
| `reset_sell_uuid` | string[] | 선택 | 과거 reset SELL uuid 지정 (반복 가능) |

#### Status

200 정상
401 토큰 없음/만료
503 Upbit 키 누락

#### Response

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

#### Request

```bash
curl -s "http://127.0.0.1:8086/v1/monitor/open-sells" \
  -H "Authorization: Bearer <access_token>"
```

lookback을 늘려 재확인:

```bash
curl -s "http://127.0.0.1:8086/v1/monitor/open-sells?lookback_days=180" \
  -H "Authorization: Bearer <access_token>"
```

## 명령 API

명령 API는 실제 운영에 영향을 줄 수 있다. 그래서 바로 실행하지 않고 먼저 `commands` 테이블에 저장한다. `auto-command-worker.service`가 큐에서 하나씩 꺼내 실행한다.

| API | 실제로 하는 일 | 주의 |
| --- | --- | --- |
| `POST /v1/commands/bot/stop` | `stop.sh` 실행 | 트레이딩 봇이 멈춘다. |
| `POST /v1/commands/bot/start` | `run.sh` 실행 | 트레이딩 봇을 다시 켠다. |
| `POST /v1/commands/reset` | `scripts/reset_krw_btc_live.py` 실행 | 미체결 취소, BTC 청산, 그리드 재반영 경로라 매우 위험하다. |
| `POST /v1/commands/adjust-budget` | `scripts/adjust_budget_live.py` 실행 | 빈 슬롯 planned\_qty를 목표 예산에 맞춰 조정한다. |
| `POST /v1/commands/reset-stop-loss` | `main.py reset-stop-loss` 실행 | 손절 상태를 해제한다. |
| `GET /v1/commands/{id}` | 명령 진행 상태 확인 | `queued/running/succeeded/failed`를 본다. |

⚠ 위험 명령 확인 문구

- reset: `"confirmation": "RESET"`
- adjust-budget: `"confirmation": "ADJUST_BUDGET"`

POST
/v1/commands/bot/stop
stop.sh 실행 (봇 정지)

트레이딩 봇이 멈춘다.

#### Request

bash

```
curl -s -X POST http://127.0.0.1:8086/v1/commands/bot/stop \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

POST
/v1/commands/bot/start
run.sh 실행 (봇 재시작)

트레이딩 봇을 다시 켠다.

#### Request

bash

```
curl -s -X POST http://127.0.0.1:8086/v1/commands/bot/start \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

POST
/v1/commands/reset
라이브 reset (매우 위험)

미체결 취소, BTC 청산, 그리드 재반영 경로라 매우 위험하다. 확인 문구 `"RESET"` 필수.

#### Body 필드

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `totp_code` | string | 조건부 | TOTP secret 설정 시 필수 |
| `confirmation` | string | 필수 | 고정 문자열 `"RESET"` |

#### Request

bash

```
curl -s -X POST http://127.0.0.1:8086/v1/commands/reset \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456","confirmation":"RESET"}'
```

POST
/v1/commands/adjust-budget
빈 슬롯 planned\_qty 재계산

빈 슬롯 planned\_qty를 목표 예산에 맞춰 조정한다. 확인 문구 `"ADJUST_BUDGET"` 필수.

#### Body 필드

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `target_budget` | string | 필수 | 절대 총예산 (KRW) |
| `force` | bool | 선택 | 강제 적용 여부 |
| `totp_code` | string | 조건부 | TOTP secret 설정 시 필수 |
| `confirmation` | string | 필수 | 고정 문자열 `"ADJUST_BUDGET"` |

#### Request

bash

```
curl -s -X POST http://127.0.0.1:8086/v1/commands/adjust-budget \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{
    "target_budget": "2400000",
    "force": false,
    "totp_code": "123456",
    "confirmation": "ADJUST_BUDGET"
  }'
```

POST
/v1/commands/reset-stop-loss
손절 상태 해제 (main.py reset-stop-loss)

손절 상태를 해제한다.

#### Request

bash

```
curl -s -X POST http://127.0.0.1:8086/v1/commands/reset-stop-loss \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

GET
/v1/commands/{id}
명령 진행 상태 확인

상태 값: queued running succeeded failed

#### Request

bash

```
curl -s http://127.0.0.1:8086/v1/commands/<command_id> \
  -H "Authorization: Bearer <access_token>"
```

📌 동시성 안전장치

위험 명령은 PostgreSQL advisory lock과 기존 운영 스크립트의 안전장치를 그대로 사용한다. 동시에 같은 종류의 명령은 하나만 `queued/running` 상태가 될 수 있다.

## 문제 해결 순서

### 앱에서 아무 API도 안 될 때

bash

```
cd /home/ubuntu/auto
systemctl --user status auto-api.service
ss -ltnp | grep :8086
curl -s http://127.0.0.1:8086/health
```

### 로그인이 안 될 때

bash

```
cd /home/ubuntu/auto
awk -F= '/^MOBILE_API_/ {print $1"=<set>"}' .env
systemctl --user restart auto-api.service
```

### PnL API가 실패할 때

bash

```
cd /home/ubuntu/auto
awk -F= '/^(UPBIT_ACCESS_KEY|UPBIT_SECRET_KEY)=/ {print $1"=<set>"}' .env
.venv/bin/python scripts/upbit_realized_pnl.py --period d
```

### 총 평가액과 장부 원금이 다르게 보일 때

bash

```
cd /home/ubuntu/auto
scripts/upbit_actual_assets.py
# 수량 불일치가 표시될 때만:
scripts/upbit_actual_assets.py --lookback-days 180
```

`--lookback-days` 기본값은 120일이다. 평소에는 옵션 없이 실행하고, 오래된 BUY가 누락된 것으로 보일 때만 늘린다.

### 앱에서 봇 시작/중지 명령이 실행되지 않을 때

bash

```
cd /home/ubuntu/auto
systemctl --user status auto-command-worker.service
journalctl --user -u auto-command-worker.service -n 100 --no-pager
docker exec auto-postgres psql -U auto -d auto \
  -c "SELECT id, kind, status, requested_at, error FROM auto_trading.commands ORDER BY requested_at DESC LIMIT 10"
```

### API는 되는데 봇이 죽어 있는 것 같을 때

bash

```
cd /home/ubuntu/auto
ps -ef | grep '/home/ubuntu/auto/main.py' | grep -v grep
tail -n 100 logs/trading-$(date +%F).log
```

## 안전 기준

✅ 읽기 API

`GET` API는 조회용이다. 주문을 만들거나 봇을 멈추지 않는다.

⚠ 명령 API

`POST /v1/commands/*` API는 운영 상태를 바꿀 수 있다.

🚫 reset 계열

reset 계열 명령은 실제 자산과 주문에 영향을 주므로 앱 UI에서 별도 확인 절차를 둔다.

🔐 Upbit 키 보호

모바일 앱에는 Upbit 키를 넣지 않는다. Upbit 키는 EC2의 `.env`에만 둔다.

⚠ HTTPS 권장

지금 8086은 HTTP다. 실제 외부 앱에서 장기간 쓰려면 HTTPS reverse proxy를 붙이는 것을 권장한다.
