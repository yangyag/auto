# Mobile API 사용 문서

React Native Android 앱에서 호출할 FastAPI 서버 문서다. 서버는 봇과 별도 프로세스로 실행되고 PostgreSQL을 공유 상태 저장소로 사용한다.

## 배포 상태

- API URL: `http://<EC2_PUBLIC_IP>:8086`
- 로컬 확인 URL: `http://127.0.0.1:8086`
- FastAPI 서비스: `auto-api.service`
- 명령 워커 서비스: `auto-command-worker.service`
- OpenAPI: `GET /openapi.json`
- Swagger UI: `GET /docs`

현재 user systemd로 설치되어 있다.
`loginctl show-user "$USER" -p Linger` 값은 `Linger=yes`여야 로그아웃 후에도 user service가 유지된다.
현재 8086 포트는 직접 HTTP로 열려 있다. 운영 앱에 배포할 때는 도메인/Caddy/Nginx를 붙여 HTTPS로 종단하는 구성이 더 안전하다.

```bash
systemctl --user status auto-api.service auto-command-worker.service
systemctl --user restart auto-api.service auto-command-worker.service
journalctl --user -u auto-api.service -f
journalctl --user -u auto-command-worker.service -f
```

서비스 파일 원본은 다음 경로에 있다.

- `deploy/systemd/user/auto-api.service`
- `deploy/systemd/user/auto-command-worker.service`

## 환경 변수

`.env`에서 읽는다.

```dotenv
MOBILE_API_USERNAME=admin
MOBILE_API_PASSWORD=<strong-password>
MOBILE_API_JWT_SECRET=<random-secret>
# 선택: 설정하면 로그인/위험 명령에 TOTP 코드가 필요하다.
MOBILE_API_TOTP_SECRET=<base32-secret>
```

Upbit 체결 기반 PnL API는 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`가 필요하다. 키가 비어 있으면 `/v1/pnl/realized`는 `503`을 반환한다.

## 인증 흐름

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

## React Native 예시

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

모든 `/v1/*` 읽기 API는 `Authorization: Bearer <access_token>` 헤더가 필요하다.

```bash
curl -s http://127.0.0.1:8086/v1/bot/status \
  -H "Authorization: Bearer <access_token>"

curl -s http://127.0.0.1:8086/v1/market/price \
  -H "Authorization: Bearer <access_token>"

curl -s http://127.0.0.1:8086/v1/grid/state \
  -H "Authorization: Bearer <access_token>"

curl -s http://127.0.0.1:8086/v1/grid/summary \
  -H "Authorization: Bearer <access_token>"

curl -s http://127.0.0.1:8086/v1/orders/pending \
  -H "Authorization: Bearer <access_token>"

curl -s 'http://127.0.0.1:8086/v1/orders/recent?limit=50' \
  -H "Authorization: Bearer <access_token>"

curl -s 'http://127.0.0.1:8086/v1/pnl/realized?period=d' \
  -H "Authorization: Bearer <access_token>"

curl -s http://127.0.0.1:8086/v1/config \
  -H "Authorization: Bearer <access_token>"
```

`/v1/market/price`는 fresh heartbeat 가격을 우선 사용하고, 없으면 Upbit public REST 가격을 반환한다. `source` 필드로 구분한다.

## 명령 API

명령 API는 즉시 실행하지 않고 `commands` 테이블에 큐잉한다. `auto-command-worker.service`가 큐에서 하나씩 가져와 실행한다.

봇 중지:

```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/bot/stop \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

봇 시작:

```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/bot/start \
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

손절 상태 해제:

```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/reset-stop-loss \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"force":false,"totp_code":"123456"}'
```

명령 상태 조회:

```bash
curl -s http://127.0.0.1:8086/v1/commands/<command_id> \
  -H "Authorization: Bearer <access_token>"
```

위험 명령은 PostgreSQL advisory lock과 기존 운영 스크립트의 안전장치를 그대로 사용한다. 동시에 같은 종류의 명령은 하나만 `queued/running` 상태가 될 수 있다.
