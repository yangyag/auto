# Mobile API 사용 문서

React Native Android 앱에서 자동매매 상태를 조회하고 운영 명령을 요청하기 위한 FastAPI 서버 문서입니다.

---

## 📌 API 인프라 요약

### 🌐 Base URL
- **외부 접속**: `http://<EC2_PUBLIC_IP>:8086`
- **EC2 내부 전용**: `http://127.0.0.1:8086`
- **OpenAPI 명세**: `GET /openapi.json`
- **Swagger UI 문서**: `GET /docs`

### 🔑 인증 방식
- **인증 메커니즘**: `Bearer JWT`
- **인증 헤더**: `Authorization: Bearer <access_token>`
- **만료 시간**: Access Token 15분 (900s)
- **토큰 갱신**: `refresh_token` 사용

### 📦 요청 & 응답
- **Content Type**: `application/json` (UTF-8 인코딩)
- **HTML 모니터링 콘솔**: `GET /ops`
- **오류 응답**: FastAPI HTTPException 규격 (`{"detail": "에러메시지"}`)
- **상태 코드**: 성공 `2xx` / 실패 `4xx`, `5xx` (401, 409, 503 등)

---

## 한 줄 요약

[run.sh](file:///C:/dev/mobileAuto/auto/run.sh)는 트레이딩 봇만 백그라운드로 실행합니다. 모바일 앱 연동용 API 서버는 `auto-api.service`, 앱의 제어 요청을 실행하는 작업 큐 백그라운드 워커는 `auto-command-worker.service` 서비스로 각각 분리하여 관리됩니다.

> [!NOTE]
> **프로세스 분리 운영**: 트레이딩 봇, FastAPI API 서버, 명령 백그라운드 워커는 프로세스가 완벽하게 분리되어 독립적으로 동작하며, PostgreSQL 데이터베이스 상태를 공유하여 통신합니다. 이 구조 덕분에 API 서버를 재시작해도 가동 중인 자동매매 봇은 영향을 받지 않습니다.

---

## 구현 소스 및 배포 위치

| 경로 | 역할 |
| :--- | :--- |
| [main.py](file:///C:/dev/mobileAuto/auto/app/api/main.py) | FastAPI 인스턴스 초기화 및 API 라우터 일괄 등록 |
| [routers/](file:///C:/dev/mobileAuto/auto/app/api/routers) | 인증, 상태 조회, 그리드 제어, 주문 정보, 손익 및 제어 명령 라우터 구현부 |
| [schemas/](file:///C:/dev/mobileAuto/auto/app/api/schemas) | API 요청/응답 검증용 Pydantic 스키마 모델 |
| [services/](file:///C:/dev/mobileAuto/auto/app/api/services) | 기존 봇 모듈 및 조회 스크립트 결과를 HTTP 응답에 맞춰 가공하는 서비스 계층 |
| [command_worker.py](file:///C:/dev/mobileAuto/auto/app/api/command_worker.py) | 데이터베이스 `commands` 테이블 큐에 등록된 운영 제어 스크립트 실행기 |
| [004_mobile_api.sql](file:///C:/dev/mobileAuto/auto/db/migrations/004_mobile_api.sql) | 모바일 API 하트비트, 명령 저장용 큐, Refresh Token 관리용 마이그레이션 SQL |
| [auto-api.service](file:///C:/dev/mobileAuto/auto/deploy/systemd/user/auto-api.service) | FastAPI 서버 구동용 User Systemd 유닛 서비스 설정 파일 |
| [auto-command-worker.service](file:///C:/dev/mobileAuto/auto/deploy/systemd/user/auto-command-worker.service) | 명령 워커 구동용 User Systemd 유닛 서비스 설정 파일 |

---

## 프로세스 실행 관계도

운영 환경에서는 각기 목적이 다른 3개의 백그라운드 프로세스가 실행됩니다.

| 프로세스 유형 | 구동 커맨드 / 서비스 | 주요 역할 | 중단 시 영향 |
| :--- | :--- | :--- | :--- |
| **트레이딩 봇** | [run.sh](file:///C:/dev/mobileAuto/auto/run.sh) | 실시간 시세를 모니터링하여 그리드 주문 실행 | 자동매매 전면 중단 |
| **모바일 API** | `auto-api.service` | 앱이 호출하는 HTTP 백그라운드 API 서버 (Port: 8086) | 모바일 앱을 통한 정보 조회 및 로그인 불가 |
| **명령 워커** | `auto-command-worker.service` | 앱에서 요청하여 commands 테이블에 적재된 제어 명령 실행 | 앱 제어 불가 (명령어들이 큐에 대기 상태로 남음) |

```
[React Native 앱]
       │ (HTTP 호출)
       ▼
[FastAPI 서버 (auto-api.service, Port 8086)]
       │
       ▼ (상태 공유)
[PostgreSQL Database] ◀──▶ [트레이딩 봇 (run.sh 기반 main.py)]
       │
       ▼ (위험 명령 큐 적재 확인)
[명령 워커 (auto-command-worker.service)]
       │
       ▼ (실제 스크립트 수행)
[stop.sh / run.sh / 리셋 가동]
```

---

## 자주 쓰는 운영 명령어

EC2 접속 후 작업 폴더로 이동합니다.
```bash
cd /home/ubuntu/auto
```

### 트레이딩 봇 프로세스만 재시작
```bash
./stop.sh
./run.sh
```

### 모바일 API 및 명령 워커 프로세스 재시작
```bash
systemctl --user restart auto-api.service auto-command-worker.service
```

### 관련 프로세스 가동 여부 일괄 확인
```bash
ps -ef | grep '/home/ubuntu/auto/main.py' | grep -v grep
systemctl --user status auto-api.service auto-command-worker.service
ss -ltnp | grep :8086
```

### 각 프로세스별 실시간 로그 출력
```bash
# API 서버 로그
journalctl --user -u auto-api.service -f

# 명령 워커 로그
journalctl --user -u auto-command-worker.service -f

# 자동매매 봇 트레이딩 로그
tail -f logs/trading-$(date +%F).log
```

> [!IMPORTANT]
> **Systemd Linger 설정**: 
> 현재 서비스들은 User Systemd 기반으로 빌드되어 있습니다. SSH 콘솔 접속이 끊긴 후에도 백그라운드 서비스가 유지되기 위해서는 사용자 계정에 Linger 기능이 반드시 활성화되어 있어야 합니다 (`loginctl show-user "$USER" -p Linger` 실행 결과가 `Linger=yes` 여야 합니다).

---

## 1. 인증(Auth) API 규격

### 1-1. 로그인 (`/v1/auth/login`)
아이디와 비밀번호(및 설정 시 TOTP 코드)로 인증하여 JWT 토큰 쌍을 발급받습니다.

- **HTTP Method**: `POST`
- **Request Body 필드**:
  | 필드명 | 타입 | 필수 여부 | 설명 |
  | :--- | :---: | :---: | :--- |
  | `username` | string | 필수 | 관리자 아이디 (`MOBILE_API_USERNAME`) |
  | `password` | string | 필수 | 관리자 비밀번호 (`MOBILE_API_PASSWORD`) |
  | `totp_code` | string | 조건부 | TOTP 보안 활성화 시 입력 필수 |

- **요청 예시 (cURL)**:
  ```bash
  curl -s http://127.0.0.1:8086/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{
      "username": "admin",
      "password": "YOUR_STRONG_PASSWORD",
      "totp_code": "123456"
    }'
  ```

- **응답 예시 (JSON)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1Ni...",
    "refresh_token": "rfr_ey...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```

### 1-2. 토큰 갱신 (`/v1/auth/refresh`)
만료된 Access Token을 재발급받습니다.

- **HTTP Method**: `POST`
- **Request Body 필드**:
  | 필드명 | 타입 | 필수 여부 | 설명 |
  | :--- | :---: | :---: | :--- |
  | `refresh_token` | string | 필수 | 로그인 시 발급받은 Refresh Token 값 |

- **요청 예시 (cURL)**:
  ```bash
  curl -s http://127.0.0.1:8086/v1/auth/refresh \
    -H 'Content-Type: application/json' \
    -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
  ```

### 1-3. 로그아웃 (`/v1/auth/logout`)
전달된 Refresh Token을 데이터베이스에서 삭제하여 무효화합니다.

- **HTTP Method**: `POST`
- **요청 예시 (cURL)**:
  ```bash
  curl -s http://127.0.0.1:8086/v1/auth/logout \
    -H 'Content-Type: application/json' \
    -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
  ```

---

## 2. 조회(Read-Only) API 규격

모든 조회 API는 `Authorization: Bearer <access_token>` 헤더가 필요합니다.

### 2-1. 봇 상태 조회 (`GET /v1/bot/status`)
봇의 라이브 여부, 최종 하트비트 시각, 손절/브레이크아웃 가드 적용 여부를 반환합니다.
```bash
curl -s http://127.0.0.1:8086/v1/bot/status \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2-2. 실시간 시세 조회 (`GET /v1/market/price`)
봇이 남긴 최근 가격 하트비트 시각이 정상 범위 내이면 해당 캐시 시세를 반환하고, 부재 시 업비트 Public API를 직접 조회하여 결과를 응답합니다.
```bash
curl -s http://127.0.0.1:8086/v1/market/price \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2-3. 전체 그리드 상태 조회 (`GET /v1/grid/state`)
현재 활성화되어 있는 모든 그리드 슬롯의 매수가, 계획 물량, 체결 재고, 매도가 등의 명세를 리스트로 가져옵니다.

- **Slot 응답 데이터 필드 정보**:
  | 필드명 | 타입 | 상세 설명 |
  | :--- | :---: | :--- |
  | `buy_price` | number | 슬롯의 최초 기준 매수 단가 |
  | `planned_qty` / `planned_buy_krw` | number | 매수 대기 상태의 수량(BTC) 및 투입 목표 예산(KRW) |
  | `held_qty` / `inventory_cost_krw` | number | 이미 체결되어 보유 중인 재고 수량(BTC) 및 획득 원가(KRW) |
  | `sell_price` / `effective_sell_price` | number | 기준 매도 타깃가 및 봇 로직(Age TP 등)이 가미된 최종 매도 단가 |
  | `pending_order` | object | 미체결 대기 상태의 주문 정보 객체 (없을 시 `null`) |

```bash
curl -s http://127.0.0.1:8086/v1/grid/state \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2-4. 그리드 요약 정보 (`GET /v1/grid/summary`)
체결된 슬롯 개수, 총 재고 평가 원장, 평단가 등의 요약 값을 반환합니다.

> [!WARNING]
> **자산 원장 평가 기준 유의**: 
> 모바일 앱이나 API 요약 데이터는 업비트 계정상의 `avg_buy_price` 평단을 직접 사용하지 않고, 봇 데이터베이스의 매수/매도 FIFO 매칭 큐 원장 데이터를 표준으로 반환합니다. 따라서 업비트 MTS 화면상의 평가액과 미세한 차이가 발생할 수 있으며, 종합 정밀 자산 내역은 운영 서버의 `scripts/upbit_actual_assets.py`를 수행하여 비교 점검하는 것이 가장 정확합니다.

```bash
curl -s http://127.0.0.1:8086/v1/grid/summary \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2-5. 미체결 주문 목록 (`GET /v1/orders/pending`)
봇이 거래소에 주문을 제출하여 현재 대기 중인 활성 주문들을 반환합니다.
```bash
curl -s http://127.0.0.1:8086/v1/orders/pending \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2-6. 최근 거래 내역 (`GET /v1/orders/recent`)
데이터베이스에 누적된 과거 체결/주문 데이터 목록을 최신순으로 가져옵니다.

- **Query Parameters**:
  | 파라미터 | 타입 | 기본값 | 용도 |
  | :--- | :---: | :---: | :--- |
  | `limit` | int | `50` | 조회할 최근 데이터의 개수 제한 |

```bash
curl -s "http://127.0.0.1:8086/v1/orders/recent?limit=50" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2-7. 실현 손익 요약 (`GET /v1/pnl/realized`)
업비트 거래 정보를 스캔해 수수료가 차감된 순 실현 이익 내역을 기간별로 정제하여 가져옵니다. (업비트 API 연동 활성화 필수)

- **Query Parameters**:
  | 파라미터 | 타입 | 필수 여부 | 상세 값 범위 |
  | :--- | :---: | :---: | :--- |
  | `period` | enum | 필수 | `d` (오늘) / `w` (이번주) / `m` (이번달) / `y` (올해) / `all` (전체) |

```bash
curl -s "http://127.0.0.1:8086/v1/pnl/realized?period=d" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 2-8. 매도 대기 실시간 현황 (`GET /v1/monitor/open-sells`)
체결 대기 중인 모든 SELL 주문과 봇의 실제 매수 슬롯 원가를 정합하여 미실현 손익 구조를 한눈에 볼 수 있도록 가공해 반환합니다.

- **Query Parameters**:
  | 파라미터 | 타입 | 기본값 | 용도 |
  | :--- | :---: | :---: | :--- |
  | `market` | string | `KRW-BTC` | 분석 대상 업비트 마켓 코드 |
  | `lookback_days` | int | `120` | 과거 매수 이력 매칭을 위한 큐 추적 윈도우 기간 (일 단위) |
  | `bot_key` | string | (기본 봇 키) | 특정 봇 식별 고유 접두사 |
  | `reset_sell_uuid` | array | — | 과거 강제 리셋 매도 주문 UUID 목록 (다중 지정 가능) |

- **응답 예시 (JSON)**:
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

---

## 3. 제어(Commands) API 규격

제어 명령 API는 봇 프로세스를 기동/정지하거나 예산을 개편하는 등 위험도가 높으므로 실행 큐(`commands` 테이블)에 적재된 뒤 비동기 워커가 안전 검증을 수행하며 처리합니다.

### 3-1. 봇 작동 중지 (`POST /v1/commands/bot/stop`)
[stop.sh](file:///C:/dev/mobileAuto/auto/stop.sh)를 백그라운드 호출하여 봇을 안전하게 정지시킵니다.
```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/bot/stop \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

### 3-2. 봇 작동 시작 (`POST /v1/commands/bot/start`)
[run.sh](file:///C:/dev/mobileAuto/auto/run.sh)를 실행하여 봇을 백그라운드로 기동합니다.
```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/bot/start \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

### 3-3. 라이브 리셋 (`POST /v1/commands/reset`)
가동 봇을 정지하고, 모든 미체결 매매를 취소한 뒤, 보유 코인을 전량 시장가 청산 및 그리드를 초기화하는 고위험 명령입니다.

- **Request Body 필드**:
  | 필드명 | 타입 | 필수 여부 | 설명 |
  | :--- | :---: | :---: | :--- |
  | `totp_code` | string | 조건부 | TOTP 보안 활성화 시 필수 |
  | `confirmation` | string | 필수 | 오작동 예방용 고정 텍스트 문구 `"RESET"` 입력 |

```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/reset \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456","confirmation":"RESET"}'
```

### 3-4. 가동 예산 조정 (`POST /v1/commands/adjust-budget`)
기존 가격대 및 체결 재고는 유지한 상태로 미체결 대기 슬롯들의 계획 매수량만 조정된 예산에 맞춰 업데이트합니다.

- **Request Body 필드**:
  | 필드명 | 타입 | 필수 여부 | 설명 |
  | :--- | :---: | :---: | :--- |
  | `target_budget` | string | 필수 | 개편할 절대 총예산 금액 (원화 단위 정수) |
  | `force` | bool | 선택 | 강제 적용 여부 |
  | `confirmation` | string | 필수 | 오작동 예방용 고정 텍스트 문구 `"ADJUST_BUDGET"` 입력 |

```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/adjust-budget \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "target_budget": "2400000",
    "force": false,
    "totp_code": "123456",
    "confirmation": "ADJUST_BUDGET"
  }'
```

### 3-5. 손절 상태 해제 (`POST /v1/commands/reset-stop-loss`)
활성화된 L1/L2 손절 가드 락 상태를 초기화하여 정상 거래 가능 모드로 복구합니다.
```bash
curl -s -X POST http://127.0.0.1:8086/v1/commands/reset-stop-loss \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"totp_code":"123456"}'
```

### 3-6. 적재 명령 가동 상태 조회 (`GET /v1/commands/{id}`)
큐에 전달한 비동기 작업의 진행 및 성공 여부를 확인합니다.
*(반환 상태 값: `queued` / `running` / `succeeded` / `failed`)*
```bash
curl -s http://127.0.0.1:8086/v1/commands/YOUR_COMMAND_ID \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## 🛠 장애 대응 및 점검 가이드

### 1. 앱 연동 장애 (조회/통신이 전혀 안 될 때)
- API 서버 구동 로그 및 포트 대기 확인:
  ```bash
  systemctl --user status auto-api.service
  ss -ltnp | grep :8086
  curl -s http://127.0.0.1:8086/health
  ```

### 2. 로그인 인증 불가 시
- `.env` 내 모바일 인증 계정 정보 정합성 확인 후 API 재기동:
  ```bash
  awk -F= '/^MOBILE_API_/ {print $1"=<set>"}' .env
  systemctl --user restart auto-api.service
  ```

### 3. 모바일에서 손익 정보(PnL) 조회 실패 시
- 업비트 API 키 주입 여부 확인 및 수동 손익 조회 테스트:
  ```bash
  awk -F= '/^(UPBIT_ACCESS_KEY|UPBIT_SECRET_KEY)=/ {print $1"=<set>"}' .env
  .venv/bin/python scripts/upbit_realized_pnl.py --period d
  ```

### 4. 제어 명령어가 앱에서 작동하지 않을 때 (명령 락 현상)
- 명령 실행기 워커 구동 여부 및 PostgreSQL 명령어 큐 적재 데이터 확인:
  ```bash
  systemctl --user status auto-command-worker.service
  journalctl --user -u auto-command-worker.service -n 50 --no-pager
  
  # 데이터베이스 내 commands 큐 최종 적재 10건 현황 확인
  docker exec auto-postgres psql -U auto -d auto \
    -c "SELECT id, kind, status, requested_at, error FROM auto_trading.commands ORDER BY requested_at DESC LIMIT 10"
  ```
