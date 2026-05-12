# Mobile API 사용 문서

React Native Android 앱에서 자동매매 상태를 조회하고 운영 명령을 요청하기 위한 FastAPI 서버 문서다.

이 문서는 운영자가 헷갈리기 쉬운 실행 구조, 환경 변수, API 호출 방법, 장애 확인 순서를 함께 정리한다.

## 한 줄 요약

`./run.sh`는 트레이딩 봇만 실행한다. 모바일 앱용 API는 `auto-api.service`, 앱에서 요청한 명령을 실제로 실행하는 워커는 `auto-command-worker.service`로 따로 실행된다.

## 전체 실행 구조

운영 서버에는 역할이 다른 프로세스가 3개 있다.

| 역할 | 실행 방식 | 하는 일 | 꺼져 있으면 |
|---|---|---|---|
| 트레이딩 봇 | `./run.sh` | 가격을 보고 실제 그리드 매수/매도 로직을 실행한다. | 자동매매가 멈춘다. |
| 모바일 API | `auto-api.service` | React Native 앱이 호출하는 HTTP API 서버다. 8086 포트로 열린다. | 앱에서 상태 조회/로그인이 안 된다. |
| 명령 워커 | `auto-command-worker.service` | 앱에서 요청한 시작/중지/reset 같은 명령을 큐에서 꺼내 실행한다. | 앱에서 명령을 넣어도 실행되지 않고 큐에 남는다. |

흐름은 아래와 같다.

```text
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

FastAPI가 트레이딩 봇을 메모리에서 직접 호출하지 않는다. 둘은 PostgreSQL을 통해 상태를 공유한다. 그래서 API를 재시작해도 봇 루프가 바로 죽지 않고, 봇이 꺼져 있어도 API 서버 자체는 살아 있을 수 있다.

## 가장 자주 쓰는 운영 명령

EC2에서 작업할 때는 먼저 프로젝트 폴더로 이동한다.

```bash
cd /home/ubuntu/auto
```

트레이딩 봇만 재시작:

```bash
./stop.sh
./run.sh
```

모바일 API와 명령 워커 재시작:

```bash
systemctl --user restart auto-api.service auto-command-worker.service
```

전체 상태 확인:

```bash
ps -ef | grep '/home/ubuntu/auto/main.py' | grep -v grep
systemctl --user status auto-api.service auto-command-worker.service
ss -ltnp | grep :8086
```

로그 확인:

```bash
journalctl --user -u auto-api.service -f
journalctl --user -u auto-command-worker.service -f
tail -f logs/trading-$(date +%F).log
```

## 배포 상태

- API URL: `http://<EC2_PUBLIC_IP>:8086`
- EC2 내부 확인 URL: `http://127.0.0.1:8086`
- FastAPI 서비스: `auto-api.service`
- 명령 워커 서비스: `auto-command-worker.service`
- OpenAPI: `GET /openapi.json`
- Swagger UI: `GET /docs`

현재 user systemd로 설치되어 있다. `loginctl show-user "$USER" -p Linger` 값은 `Linger=yes`여야 SSH 접속이 끊겨도 user service가 유지된다.

현재 8086 포트는 직접 HTTP로 열려 있다. 실제 모바일 앱에 장기간 사용할 때는 도메인/Caddy/Nginx를 붙여 HTTPS로 종단하는 구성이 더 안전하다.

서비스 파일 원본:

- `deploy/systemd/user/auto-api.service`
- `deploy/systemd/user/auto-command-worker.service`

## 환경 변수

환경 변수는 `/home/ubuntu/auto/.env`에서 읽는다.

모바일 API 자체에 필요한 값:

```dotenv
MOBILE_API_USERNAME=admin
MOBILE_API_PASSWORD=<strong-password>
MOBILE_API_JWT_SECRET=<random-secret>
```

선택 값:

```dotenv
# 설정하면 로그인/위험 명령에 TOTP 코드가 필요하다.
MOBILE_API_TOTP_SECRET=<base32-secret>
```

Upbit 관련 값:

```dotenv
UPBIT_ACCESS_KEY=<upbit-access-key>
UPBIT_SECRET_KEY=<upbit-secret-key>
```

`/v1/pnl/realized`는 Upbit의 private 주문 조회 API를 사용하므로 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`가 필요하다. 키가 비어 있으면 `503`을 반환한다.

WebSocket 설정은 코드 기본값이 있지만, 운영 의도를 분명히 남기려면 `.env`에 명시해도 된다.

```dotenv
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

```bash
# 봇 설정 변경 반영
./stop.sh
./run.sh

# API/worker 설정 변경 반영
systemctl --user restart auto-api.service auto-command-worker.service
```

## 인증 흐름

앱은 먼저 로그인해서 `access_token`과 `refresh_token`을 받는다.

- `access_token`: API 호출 때 `Authorization` 헤더에 넣는다. 유효 시간은 15분이다.
- `refresh_token`: access token을 새로 받을 때 쓴다. 앱의 보안 저장소에 저장한다.
- `totp_code`: `MOBILE_API_TOTP_SECRET`을 설정한 경우에만 필요하다.

로그인:

```bash
curl -s http://127.0.0.1:8086/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "admin",
    "password": "<password>",
    "totp_code": "123456"
  }'
```

응답:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

토큰 갱신:

```bash
curl -s http://127.0.0.1:8086/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
```

로그아웃:

```bash
curl -s http://127.0.0.1:8086/v1/auth/logout \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
```

## React Native 호출 예시

토큰은 Android Keystore 기반 secure storage에 저장한다. 예시는 `react-native-keychain` 사용 형태다.

```ts
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
|---|---|---|
| `GET /v1/bot/status` | 봇 alive 여부, 마지막 heartbeat, 손절/브레이크아웃 상태 | 봇이 꺼져 있으면 API는 살아 있어도 `is_alive=false`가 될 수 있다. |
| `GET /v1/market/price` | 현재가 | 봇 heartbeat 가격이 fresh하면 우선 사용하고, 없으면 Upbit public REST를 사용한다. |
| `GET /v1/grid/state` | 전체 그리드 슬롯 목록 | 각 슬롯의 매수가, 매도가, 보유 수량, pending 주문을 확인한다. |
| `GET /v1/grid/summary` | 그리드 요약 | 보유 슬롯 수, 총 재고, 원가, 평균 매수가 등을 보여준다. |
| `GET /v1/orders/pending` | DB 기준 미체결 주문 | 봇이 관리하는 open 주문 목록이다. |
| `GET /v1/orders/recent?limit=50` | 최근 주문 이력 | DB에 기록된 주문 기준이다. |
| `GET /v1/pnl/realized?period=d` | 오늘 실현손익 | `d/w/m/y/all` 기간을 지원한다. Upbit 키가 필요하다. |
| `GET /v1/config` | 앱에 보여줘도 되는 핵심 설정 | secret은 반환하지 않는다. |

예시:

```bash
curl -s http://127.0.0.1:8086/v1/grid/summary \
  -H "Authorization: Bearer <access_token>"
```

## 명령 API

명령 API는 실제 운영에 영향을 줄 수 있다. 그래서 바로 실행하지 않고 먼저 `commands` 테이블에 저장한다. `auto-command-worker.service`가 큐에서 하나씩 꺼내 실행한다.

| API | 실제로 하는 일 | 주의 |
|---|---|---|
| `POST /v1/commands/bot/stop` | `stop.sh` 실행 | 트레이딩 봇이 멈춘다. |
| `POST /v1/commands/bot/start` | `run.sh` 실행 | 트레이딩 봇을 다시 켠다. |
| `POST /v1/commands/reset` | `scripts/reset_krw_btc_live.py` 실행 | 미체결 취소, BTC 청산, 그리드 재반영 경로라 매우 위험하다. |
| `POST /v1/commands/adjust-budget` | `scripts/adjust_budget_live.py` 실행 | 빈 슬롯 planned_qty를 목표 예산에 맞춰 조정한다. |
| `POST /v1/commands/reset-stop-loss` | `main.py reset-stop-loss` 실행 | 손절 상태를 해제한다. |
| `GET /v1/commands/{id}` | 명령 진행 상태 확인 | `queued/running/succeeded/failed`를 본다. |

위험도가 큰 명령은 확인 문구가 필요하다.

- reset: `"confirmation": "RESET"`
- adjust-budget: `"confirmation": "ADJUST_BUDGET"`

봇 중지:

```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/bot/stop \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

라이브 reset:

```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/reset \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456","confirmation":"RESET"}'
```

예산 조정:

```bash
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

명령 상태 조회:

```bash
curl -s http://127.0.0.1:8086/v1/commands/<command_id> \
  -H "Authorization: Bearer <access_token>"
```

위험 명령은 PostgreSQL advisory lock과 기존 운영 스크립트의 안전장치를 그대로 사용한다. 동시에 같은 종류의 명령은 하나만 `queued/running` 상태가 될 수 있다.

## 문제 해결 순서

앱에서 아무 API도 안 될 때:

```bash
cd /home/ubuntu/auto
systemctl --user status auto-api.service
ss -ltnp | grep :8086
curl -s http://127.0.0.1:8086/health
```

로그인이 안 될 때:

```bash
cd /home/ubuntu/auto
awk -F= '/^MOBILE_API_/ {print $1"=<set>"}' .env
systemctl --user restart auto-api.service
```

PnL API가 실패할 때:

```bash
cd /home/ubuntu/auto
awk -F= '/^(UPBIT_ACCESS_KEY|UPBIT_SECRET_KEY)=/ {print $1"=<set>"}' .env
.venv/bin/python scripts/upbit_realized_pnl.py --period d
```

앱에서 봇 시작/중지 명령이 실행되지 않을 때:

```bash
cd /home/ubuntu/auto
systemctl --user status auto-command-worker.service
journalctl --user -u auto-command-worker.service -n 100 --no-pager
docker exec auto-postgres psql -U auto -d auto \
  -c "SELECT id, kind, status, requested_at, error FROM auto_trading.commands ORDER BY requested_at DESC LIMIT 10"
```

API는 되는데 봇이 죽어 있는 것 같을 때:

```bash
cd /home/ubuntu/auto
ps -ef | grep '/home/ubuntu/auto/main.py' | grep -v grep
tail -n 100 logs/trading-$(date +%F).log
```

## 안전 기준

- `GET` API는 조회용이다. 주문을 만들거나 봇을 멈추지 않는다.
- `POST /v1/commands/*` API는 운영 상태를 바꿀 수 있다.
- reset 계열 명령은 실제 자산과 주문에 영향을 주므로 앱 UI에서 별도 확인 절차를 둔다.
- 모바일 앱에는 Upbit 키를 넣지 않는다. Upbit 키는 EC2의 `.env`에만 둔다.
- 지금 8086은 HTTP다. 실제 외부 앱에서 장기간 쓰려면 HTTPS reverse proxy를 붙이는 것을 권장한다.
