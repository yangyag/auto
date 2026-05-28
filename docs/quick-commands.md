# auto 빠른 명령어 모음

자주 쓰는 운영 명령을 한곳에서 빠르게 복사 · 실행하기 위한 cheat sheet

📂 /home/yangyag/auto
🐍 .venv/bin/python
⚡ Copy-ready
🔍 Filter by keyword

**·** 명령
**·** 섹션

📂기준 위치

로컬
:   cd /home/yangyag/auto

EC2
:   cd /home/ubuntu/auto

▶봇 제어

실행
:   ./run.sh

종료
:   ./stop.sh

재시작
:   ./stop.sh && ./run.sh

📜로그

오늘
:   logs/trading-$(date +%F).log

최신
:   ./tail-latest-log.sh

최저가
:   scripts/check\_daily\_low.py

🛠그리드

반영
:   apply\_grid\_properties\_to\_postgres.py

상태
:   show\_grid\_state.py

설정
:   grid.properties

## 제일 자주 쓸 명령 4개

실전에서 가장 빈도 높은 4개 명령. 다른 모든 섹션의 압축본이다.

grid그리드 반영

`grid.properties` 기준으로 DB 그리드를 다시 만든다.

bash

```
python3 scripts/apply_grid_properties_to_postgres.py --force
```

state현재 상태 보기

DB의 슬롯/재고/계획매수금액 요약을 출력한다.

bash

```
python3 scripts/show_grid_state.py
```

log로그 확인

오늘 날짜의 운영 로그를 실시간 추적한다.

bash

```
tail -f logs/trading-$(date +%F).log
```

bot재시작

봇을 안전하게 종료한 뒤 곧바로 다시 띄운다.

bash

```
./stop.sh && ./run.sh
```

📌 기준 위치

모든 명령은 기본적으로 작업 디렉터리에서 실행한다.

bash

```
cd /home/yangyag/auto
```

## 현재 봇 실행 / 종료 / 상태

run실행

백그라운드로 봇을 띄운다.

bash

```
./run.sh
```

stop종료

백그라운드 봇을 정상 종료한다.

bash

```
./stop.sh
```

check실행 중인지 확인

PID 파일과 프로세스 패턴 둘 다 점검한다.

bash

```
test -f .auto-trading.pid && cat .auto-trading.pid || true
ps -eo pid,args | grep '[p]ython.*/home/yangyag/auto/main.py'
```

## 로그 보기

tail오늘 로그 마지막 50줄

`$(date +%F)` 로 오늘 날짜 로그 파일을 잡는다.

bash

```
tail -n 50 logs/trading-$(date +%F).log
```

follow실시간 로그 보기

`-f` 로 파일 끝에 붙어 추적한다.

bash

```
tail -f logs/trading-$(date +%F).log
```

latest최신 날짜 로그 추적

날짜를 직접 입력하지 않아도 최신 파일을 자동 선택한다.

bash

```
./tail-latest-log.sh
```

scan날짜별 최저 현재가

매수 라인 도달 여부를 빠르게 가늠할 때 쓴다. EC2에서는 `.venv/bin/python` 으로 실행.

bash

```
python3 scripts/check_daily_low.py
```

📌 동작

`scripts/check_daily_low.py` 는 `logs/trading-YYYY-MM-DD.log` 파일들을 모두 스캔해서 날짜별 최저 현재가를 출력한다.

## 업비트 잔고 확인

balance주문 가능 KRW 잔고 1회 조회

한 번 호출하고 종료한다.

bash

```
python3 main.py balance
```

⚠ 평균매수가 착시

`main.py balance` 는 주문 가능 KRW 잔고만 보여준다. 업비트 `/v1/accounts` 의 `avg_buy_price * BTC 보유수량` 은 계정 전체 평균매수가 기준 원가이며, 봇이 관리하는 슬롯별 잔여 매수원가와 다를 수 있다.

그리드 봇은 슬롯별로 BUY/SELL 을 매칭한다. 낮은 가격 슬롯이 먼저 팔리고 높은 가격 슬롯이 남으면, `주문 가능 KRW + 업비트 평균매수가 기준 BTC 원가` 는 봇 장부 원금보다 낮거나 높게 보일 수 있다. BTC 보유 중 실제 장부 기준 합계는 `scripts/upbit_actual_assets.py` 로 확인한다.

## 실제 전체 자산 확인

업비트 계정 잔고와 봇 슬롯별 잔여 BUY 원가를 함께 조회하는 read-only 점검 명령이다. 파일에 실행 권한이 있으므로 가상환경이 준비된 프로젝트 루트에서 바로 실행한다.

assets기본 120일 조회

평소에는 옵션 없이 실행한다.

bash

```
scripts/upbit_actual_assets.py
```

lookback더 오래 조회

수량 불일치가 표시될 때만 늘린다.

bash

```
scripts/upbit_actual_assets.py --lookback-days 180
```

📌 출력 해석

`KRW + 봇 슬롯별 잔여 매수원가` 는 매수 당시 슬롯 장부 기준 합계이고, `KRW + 현재 평가액` 은 현재가 기준 평가 합계다. `Upbit 평균매수가 기준 원가` 는 계정 전체 평균이라 봇 장부 원가와 다를 수 있다.

## 매도 대기 주문 실시간 현황

현재 걸려있는 모든 미체결 매도 주문을 봇 슬롯별 실제 매수원가와 매칭해, 현재가 기준 미실현 손익을 한눈에 보여주는 read-only 점검 명령이다.

업비트는 평균매수가 하나만 보여주지만, 이 스크립트는 각 슬롯의 실제 매수원가를 기준으로 한다.

monitor기본 실행

현재 열려있는 모든 매도 대기 주문과 슬롯별 손익을 출력한다.

bash

```
.venv/bin/python scripts/upbit_open_sell_monitor.py
```

bot-key다른 봇 키 지정

로컬 STATE\_BOT\_KEY가 거래소 identifier prefix와 다를 때.

bash

```
.venv/bin/python scripts/upbit_open_sell_monitor.py --bot-key krw-btc-live
```

lookback조회 기간 늘리기

매수원가 매칭이 안 될 때 lookback을 늘려 재확인.

bash

```
.venv/bin/python scripts/upbit_open_sell_monitor.py --lookback-days 180
```

📌 API / 브라우저로도 확인 가능

EC2 운영 서버에서는 CLI 외에 아래 방법으로도 동일한 매도 대기 현황을 조회할 수 있다.

- 브라우저 점검 화면: `http://<EC2_IP>:8086/ops` → **매도 대기** 버튼
- Mobile API: `GET /v1/monitor/open-sells` (JWT 인증 필요, [docs/mobile-api.md](mobile-api.md) 참조)

### 출력 컬럼 설명

| 컬럼 | 의미 |
| --- | --- |
| `slot` | 그리드 슬롯 번호. `-` 이면 봇 identifier가 없는 수동 주문 |
| `qty(BTC)` | 매도 대기 중인 BTC 수량 |
| `매수원가` | 해당 슬롯의 실제 BUY 체결 원가 (봇 기준). `-` 이면 매칭 실패 |
| `매도지정가` | 현재 걸려있는 SELL 지정가 |
| `현재가` | 업비트 현재 시세 |
| `미실현손익` | (현재가 - 매수원가) × 수량. 양수=수익권, 음수=손실권 |
| `도달까지` | 매도지정가 - 현재가. 체결까지 얼마나 남았는지 |

📌 진단 정보

하단 진단 줄에서 `matched`/`unmatched` 비율을 확인한다. `unmatched`가 있으면 수동 주문이거나 `--lookback-days`가 부족한 것이다.

⚠ 업비트 평균매수가와의 차이

업비트 `avg_buy_price`는 계정 전체 평균이므로, 낮은 슬롯이 먼저 팔리고 높은 슬롯이 남으면 실제 각 슬롯의 매수원가와 다르게 보인다. 이 스크립트는 그 착시를 제거하고 슬롯별 실제 원가로 보여준다.

## grid.properties 기반으로 DB 그리드 반영

apply기본 properties 사용

`grid.properties` 작성 후 실행할 명령.

bash

```
python3 scripts/apply_grid_properties_to_postgres.py --force
```

custom다른 properties 파일

`--properties-file` 플래그로 경로 지정.

bash

```
python3 scripts/apply_grid_properties_to_postgres.py --properties-file my-grid.properties --force
```

📌 init-grid 와 차이

`main.py init-grid` 는 슬롯 개수 기반이고, `grid.properties` 는 `GRID_COUNT` 또는 `GRID_STEP_PCT` 중 정확히 하나를 쓴다.

### 이 명령이 사용하는 입력

- `grid.properties`
- 현재 `.env` 의 `STATE_BOT_KEY`
- 현재 `.env` 의 PostgreSQL 접속정보

### Phase 2 하단 가중 배분 확인 항목

- `planned_buy_budget_total`
- `top_slot_planned_buy_budget`
- `bottom_slot_planned_buy_budget`

✅ 검증 기준

하단 가중이 적용된 새 그리드라면 보통 `bottom_slot_planned_buy_budget > top_slot_planned_buy_budget` 이어야 한다.

## 현재 그리드 슬롯 상태 바로 보기

state현재 DB 상태 출력

슬롯별 buy/held/sell/planned/status 와 요약을 출력한다.

bash

```
python3 scripts/show_grid_state.py
```

### 입력

- `.env` 의 `STATE_BOT_KEY`
- `.env` 의 `PGSCHEMA`
- PostgreSQL 접속정보

출력에는 조회 source, 슬롯별 `buy/held/sell/planned/planned_krw/status`, 총재고, 상단/하단/총 계획매수금액 요약이 포함된다.

## 실현 손익 조회 (KRW-BTC)

업비트 API 기준 read-only 분석. 봇 주문 `identifier` 의 슬롯 번호를 기준으로 같은 슬롯 안에서만 BUY/SELL 을 FIFO 매칭해 수수료 차감 순손익을 산출한다.

bash

```
.venv/bin/python scripts/upbit_realized_pnl.py [--period d|w|m|y] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--reset-sell-uuid UUID] [--lookback DAYS]
```

📌 기본 동작

옵션이 없으면 기본 최근 90일을 일/주/월/년/전체 섹션으로 모두 출력하고, lookback 30일을 사용한다. 업비트 `GET /v1/orders/closed` 와 `/v1/order` 만 사용한다.

글로벌 FIFO 가 아니며, 매칭되지 않는 매도(윈도우 시작 이전 매수분, identifier 패턴 불일치 등)는 별도 라인으로 분리한다. 기간은 2자리 연도 형식으로 표시하며, 주간 기간은 `26-04-20 ~ 26-04-26` 처럼 출력한다.

실현손익 표의 `매도주문수` 는 SELL 주문 UUID 기준이고, `체결건수` 는 업비트 `/v1/order` 의 `trades` 배열 기준 fill 수다.

⚠ 실현손익과 총자산 비교

실현손익은 이미 매도된 슬롯의 확정 손익이다. 총 보유자산이나 원금 장부와 비교할 때는 현재 남아 있는 BTC의 원가 기준을 분리해서 본다. 업비트 평균매수가 기준 잔여 원가와 봇 슬롯별 잔여 BUY 원가는 같은 값이 아닐 수 있다.

전량 매도 후에는 KRW 잔고로 최종 정산되지만, BTC 보유 중에는 `avg_buy_price` 기준 합계가 봇의 슬롯 장부를 그대로 대표하지 않는다. 의심되면 이 스크립트의 `잔여 매수` 섹션을 확인하고, 필요한 경우 lookback 을 충분히 늘려 잔여 BUY 큐가 안정적으로 수렴하는지 비교한다.

### 기간 옵션

| 옵션 | 의미 |
| --- | --- |
| `--period d` | 오늘 |
| `--period w` | 이번주(월요일~오늘) |
| `--period m` | 이번달(1일~오늘) |
| `--period y` | 이번년(1월 1일~오늘) |
| `--from YYYY-MM-DD --to YYYY-MM-DD` | 직접 지정 기간 1개 합산 출력 |

⚠ 옵션 충돌

`--period` 와 `--from/--to` 는 같이 쓰지 않는다. 특정 날짜/기간을 직접 지정할 때만 `--from/--to` 를 사용한다.

### --lookback 파라미터

실현손익을 정확히 계산하려면 조회 기간 이전의 BUY 주문도 포함해야 한다. `--lookback` 은 표시 시작일 이전으로 추가 조회할 기간(일)이다.

- **API 호출 범위(fetch):** `표시 시작일 - lookback ~ 표시 종료일` (모든 BUY/SELL 조회)
- **출력 범위(display):** `--period` 또는 `--from/--to` 로 정한 기간 (이 범위의 SELL만 표시)
- **매칭 대상:** fetch 범위 전체에서 FIFO 매칭 수행 (표시 범위 외 SELL도 과거 BUY 매칭에 사용)

기본값은 30일이며, 실제 운영 데이터 분석 결과 30일부터 실현손익이 수렴하는 것을 확인했다.

⚠ 경고 메커니즘

fetch 범위 경계(`--from` 이후 1일)에 BUY 가 조회되면 "lookback 부족 위험" 경고를 출력한다. 이는 lookback 이 부족하여 더 오래된 BUY 를 누락했을 가능성을 의미하므로, 권장 값으로 재실행하면 정확도가 향상된다.

**한계:** 경고는 fetch\_start ~ +1일 사이 BUY 존재 여부 휴리스틱이므로, 일부 케이스에서 경고 없이도 lookback 이 실제로 부족할 수 있다. 의심되면 안전하게 lookback 을 더 늘려서 재실행하는 것이 권장된다.

📌 일별 버킷팅 기준

실현손익 표의 일별 그룹핑은 SELL 주문의 `_time_key`(= 업비트 `/v1/order` 의 `trades` 배열에서 최대 `created_at`, KST 시각)를 기준으로 한다. SELL 주문 생성 시각이 아니라 실제 체결 완료 시각을 의미하므로, 매도 다중 체결이나 시간대가 다른 매도 건들을 정확히 분류할 수 있다.

### 사용 예

all전체 조회

최근 90일 일/주/월/년/전체 섹션 출력.

bash

```
.venv/bin/python scripts/upbit_realized_pnl.py
```

d오늘 손익만

`--period d`

bash

```
.venv/bin/python scripts/upbit_realized_pnl.py --period d
```

w이번주 손익만

`--period w` (월요일~오늘)

bash

```
.venv/bin/python scripts/upbit_realized_pnl.py --period w
```

m이번달 손익만

`--period m` (1일~오늘)

bash

```
.venv/bin/python scripts/upbit_realized_pnl.py --period m
```

range직접 지정 기간 + lookback 45일

기간 1개 합산 출력 + 안전 마진.

bash

```
.venv/bin/python scripts/upbit_realized_pnl.py --from 2026-05-01 --to 2026-05-31 --lookback 45
```

safe경고 시 안전 마진 재실행

lookback 부족 경고가 나올 때.

bash

```
.venv/bin/python scripts/upbit_realized_pnl.py --from 2026-05-01 --to 2026-05-31 --lookback 60
```

📌 reset 청산 매칭

`reset_krw_btc_live.py` 로 발생한 reset 전량 시장가 매도는 `{STATE_BOT_KEY}-reset-sell-...` identifier 로 자동 인식된다. reset 직전에 취소된 봇 TP SELL 주문들이 있으면 해당 슬롯/수량을 우선 사용해 청산 손익을 매칭한다.

코드 반영 전 발생한 과거 reset 매도처럼 identifier 가 없는 청산 주문도 직전 취소 TP SELL 수량으로 일부 자동 추론되며, 자동 추론이 애매한 경우는 `--reset-sell-uuid <UUID>` 를 반복 지정해서 reset 청산 경계로 포함한다.

## 손절 관련 명령

### 손절 해제 (reset-stop-loss)

#### L1 매수 차단 해제

L1 손절이 발동된 후 매수 차단을 해제하려면:

L1로컬 / venv 활성

기본 호출.

bash

```
python3 main.py reset-stop-loss
```

EC2venv 없이 절대 경로

SSH 직후 activate 생략하고 즉시 실행.

bash

```
/home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py reset-stop-loss
```

✅ 역할

- L1 청산 이후 남은 포지션의 TP 매도는 그대로 유지
- L1 매수 영구 차단 상태를 해제
- `stop_loss_active` 상태를 false 로 복구
- 새로운 매수 신호에서 다시 매수 가능하게 복구

#### L2 강제 해제 (--force)

L2 24시간 잠금을 강제 해제하려면 `--force` 옵션을 사용한다.

L2강제 해제

긴급용. 24시간 대기 없이 즉시 봇 재시작 필요시.

bash

```
python3 main.py reset-stop-loss --force
```

⚠ 역할 및 주의

- `STOP_LOSS_RESTART_LOCKOUT_HOURS` 미경과 상태에서도 24시간 잠금 강제 해제
- L2 이후 모든 포지션이 청산되었으므로 새 그리드 생성 후 매수 재개 가능
- `--force` 없이 호출 시, `STOP_LOSS_RESTART_LOCKOUT_HOURS` 미경과 상태면 **exit 2** 반환
- L2 이후는 `init-grid --force` 로 새 그리드 생성 필수

### 손절 상태 확인

현재 손절 상태는 `scripts/show_grid_state.py` 의 상단 출력에 포함된다.

bash

```
python3 scripts/show_grid_state.py
```

출력에서 다음을 확인한다:

- `stop_loss_active`: 현재 손절 발동 상태 (True/False)
- `armed_at`: 가장 최근 손절 armed 시간
- 각 슬롯의 `status` 컬럼 (L1/L2 발동시 일부 슬롯은 청산 상태)

### 손절 파라미터 변경

손절 매개변수는 `grid.properties` 또는 환경변수로 제어된다.

변경 후 봇 재시작:

bash

```
./stop.sh
# grid.properties 또는 .env 수정
PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh
```

#### 변경 가능한 파라미터

| 파라미터 | 의미 |
| --- | --- |
| `STOP_LOSS_MODE` | 활성화/비활성화 모드 (`band_multiple` / `fixed_pct` / `off`) |
| `STOP_LOSS_BAND_MULTIPLE` | 그리드 폭 배수 (1.0 ~ 2.0) |
| `STOP_LOSS_*_CONSECUTIVE_CLOSES` | 컨펌 캔들 개수 |
| `STOP_LOSS_*_ARM_HOLD_SECONDS` | 대기 시간 |
| `STOP_LOSS_L1_LIQUIDATE_RATIO` | L1 청산 비율 |
| `STOP_LOSS_WEBHOOK_URL` | 외부 알림 Webhook URL (비어있으면 미발송) |
| `STOP_LOSS_NOTIFICATION_ENABLED` | 외부 알림 활성화/비활성화 (True/False) |

📌 참고

자세한 설명은 [docs/operations.md](operations.md#stoploss) 의 손절 운영 가이드를 참조한다.

## 테스트

all전체 테스트

`tests/` 하위 모두 실행, verbose.

bash

```
python3 -m unittest discover -s tests -v
```

propsproperties 관련만

grid\_properties + apply\_grid\_properties\_script

bash

```
python3 -m unittest tests.test_grid_properties tests.test_apply_grid_properties_script -v
```

pgpostgres 관련만

grid / order repository + runtime\_lock

bash

```
python3 -m unittest tests.test_postgres_grid_repository tests.test_postgres_order_repository tests.test_postgres_runtime_lock -v
```

state상태 조회 스크립트만

show\_grid\_state 동작 검증.

bash

```
python3 -m unittest tests.test_show_grid_state_script -v
```

## 설정 확인

### 현재 상태 저장 backend 확인

bash

```
python3 - <<'PY'
import app.config.settings as cfg
print(cfg.STATE_BOT_KEY)
print(cfg.PGHOST, cfg.PGPORT, cfg.PGDATABASE, cfg.PGUSER, cfg.PGSCHEMA)
PY
```

### 현재가 WebSocket 이벤트 루프 설정 확인

bash

```
python3 - <<'PY'
import app.config.settings as cfg
print("UPBIT_WS_PUBLIC_ENABLED=", cfg.UPBIT_WS_PUBLIC_ENABLED)
print("UPBIT_WS_EVENT_LOOP_ENABLED=", cfg.UPBIT_WS_EVENT_LOOP_ENABLED)
print("UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=", cfg.UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS)
print("PRICE_POLL_INTERVAL=", cfg.PRICE_POLL_INTERVAL)
PY
```

📌 기본값

기본값은 public ticker WebSocket 이벤트 루프 사용, 전략 평가 최소 3초 간격, 장애 시 5초 REST polling fallback 이다.

## grid.properties 예시

properties

```
MIN_BUY_PRICE=91623000
MAX_BUY_PRICE=127886000
TOTAL_BUDGET_KRW=4000000
GRID_STEP_PCT=1.770527625862
TP_MODEL=k
TP_K_BASE=9.0
TP_K_FLOOR=7.0
```

### 각 키의 의미

| 키 | 의미 |
| --- | --- |
| `MIN_BUY_PRICE` | 최하단 슬롯 buy\_price |
| `MAX_BUY_PRICE` | 최상단 슬롯 buy\_price |
| `TOTAL_BUDGET_KRW` | 그리드 전체에 배정할 총예산 |
| `GRID_COUNT` | 슬롯 개수 |
| `GRID_STEP_PCT` | 슬롯 간격 비율 |
| `TP_MODEL` | TP 계산 모드, 현재 운영 기준은 `k` |
| `TP_K_BASE` | 기본 TP `k` |
| `TP_K_FLOOR` | Age TP 최저 `k` |

⚠ 주의

- `grid.properties` 는 `GRID_COUNT` 또는 `GRID_STEP_PCT` 중 정확히 하나만 둔다.
- `MIN_BUY_PRICE`, `MAX_BUY_PRICE` 는 업비트 호가 단위에 맞는 값으로 넣어야 한다.
- 안 맞으면 스크립트가 에러를 낸다.

## KRW-BTC 라이브 리셋 후 새 그리드 반영

reset전량 청산 + 그리드 재반영

한 번에 정지/취소/매도/그리드 반영/상태 출력까지.

bash

```
.venv/bin/python scripts/reset_krw_btc_live.py
```

### 이 명령이 수행하는 순서

1. `./stop.sh`
2. 업비트 `KRW-BTC` 미체결 주문 취소
3. BTC 전량 시장가 매도
4. `grid.properties` 기준 DB 그리드 재반영
5. 상태 출력

⚠ 재시작은 자동이 아니다

재시작은 자동으로 하지 않는다. 결과 확인 후 필요하면 직접 실행한다.

bash

```
./run.sh
```

📌 reset identifier 자동 인식

전량 시장가 매도 주문에는 reset 전용 identifier 가 붙으므로, 이후 `scripts/upbit_realized_pnl.py` 에서 옵션 없이 reset 청산 손익에 포함된다.
