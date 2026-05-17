# auto

Python 기반 그리드 자동매매 시스템이다. 구현은 업비트 `KRW-BTC`와 PostgreSQL 상태 저장소를 전제로 하며, 매수는 전략 평가 사이클 사이에서 `buy_price`를 어떻게 교차했는지로 판단하고, 매도는 보유 슬롯의 `effective_sell_price` 도달 여부로 판단한다. 기본 현재가 루프는 업비트 public `ticker` WebSocket 이벤트를 기다리되, 전략 평가는 최소 3초 간격으로만 실행한다. WebSocket을 사용할 수 없거나 이벤트가 없으면 기존 5초 REST polling 으로 fallback 한다. 주문이 접수됐다고 바로 상태를 바꾸지 않고, 업비트 재조회 결과가 `done`으로 확인될 때만 그리드 상태를 갱신한다. BUY 체결이 확인되면 해당 슬롯의 TP 지정가 SELL 주문을 즉시 생성해 pending 으로 관리한다.

> **쉽게 말하면**: 그리드(여러 가격대 슬롯) 를 설정해두고 — **"가격이 매수 라인을 지나쳐 내려가면 사고, 보유 슬롯의 목표 매도 가격 이상이면 판다"**. 매수 쪽 핵심은 "지금 가격이 얼마냐" 가 아니라 "직전 체크 시점과 비교해서 어느 라인을 **건너갔냐**" 다. 그래야 같은 슬롯을 여러 번 체결하거나 가격 변동을 놓치는 일이 없다.

## 먼저 읽기

이 README는 프로그램의 전체 구조와 핵심 로직을 설명하는 기준 문서다. 초보 운영자가 매일 봐야 하는 내용은 아래 **초보 운영자 빠른 시작**부터 확인하면 된다.

- 처음 설치하거나 `.env`, PostgreSQL, 가상환경을 준비해야 하면 [docs/setup.html](docs/setup.html)를 먼저 본다.
- EC2 접속, 배포, 운영 서버 기준은 [docs/operations.html](docs/operations.html)를 본다.
- 명령어만 빠르게 찾고 싶으면 [docs/quick-commands.html](docs/quick-commands.html)를 본다.
- 전략 수식과 세부 판정 조건은 [docs/strategy-formulas.html](docs/strategy-formulas.html)를 본다.

## 초보 운영자 빠른 시작

기준 작업 위치는 로컬에서 `cd /home/yangyag/auto`, EC2 운영 서버에서 `cd /home/ubuntu/auto` 다. 아래 명령은 프로젝트 루트에서 실행한다.

> **운영 원칙**: 실거래 주문이 발생할 수 있는 봇 루프는 명시적으로 필요할 때만 실행한다. 단순 확인은 `show_grid_state.py`, `balance`, 로그 조회처럼 읽기 전용 명령부터 사용한다.

### 1. 지금 봇이 실행 중인지 확인

```bash
test -f .auto-trading.pid && cat .auto-trading.pid || true
ps -eo pid,args | grep '[p]ython.*/main.py'
```

PID가 나오고 `main.py` 프로세스가 보이면 실행 중이다. PID 파일만 있고 프로세스가 없으면 이전 실행 흔적일 수 있으니 로그를 같이 확인한다.

### 2. 로그 확인

```bash
./tail-latest-log.sh
```

직접 오늘 로그만 보고 싶으면:

```bash
tail -n 50 logs/trading-$(date +%F).log
```

### 3. 현재 그리드 상태 확인

```bash
.venv/bin/python scripts/show_grid_state.py
```

이 명령은 DB에 저장된 슬롯, 보유 수량, pending 주문, 손절 상태 요약을 확인하는 읽기 전용 점검 명령이다.

### 4. 업비트 주문 가능 잔고 확인

```bash
.venv/bin/python main.py balance
```

### 5. 봇 시작 / 종료

시작:

```bash
PYTHON_BIN=.venv/bin/python ./run.sh
```

종료:

```bash
./stop.sh
```

실행 후에는 `./tail-latest-log.sh` 로 로그가 계속 쌓이는지 확인한다.

### 6. 실현 손익 확인

```bash
.venv/bin/python scripts/upbit_realized_pnl.py
```

오늘/이번주/이번달만 보려면:

```bash
.venv/bin/python scripts/upbit_realized_pnl.py --period d
.venv/bin/python scripts/upbit_realized_pnl.py --period w
.venv/bin/python scripts/upbit_realized_pnl.py --period m
```

## grid.properties 수정 후 기본 흐름

`grid.properties`는 그리드 가격 범위, 총예산, 슬롯 간격, TP 기준을 정하는 운영 입력 파일이다. 라이브 운영 중 값을 바꿀 때는 먼저 봇을 멈춘 뒤 반영한다.

```bash
./stop.sh
.venv/bin/python scripts/apply_grid_properties_to_postgres.py --force
.venv/bin/python scripts/show_grid_state.py
PYTHON_BIN=.venv/bin/python ./run.sh
```

> **쉽게 말하면**: `grid.properties`를 저장했다고 봇 DB 상태가 자동으로 바뀌지는 않는다. `apply_grid_properties_to_postgres.py --force` 를 실행해야 현재 `.env`의 `STATE_BOT_KEY` 기준 DB 그리드에 반영된다.

주의할 점:

- 이 경로는 DB 그리드를 강제로 반영하는 경로다.
- 이미 운영 중인 포지션을 정리하고 완전히 새 그리드로 시작하려면 아래의 라이브 리셋 경로를 검토한다.
- 기존 보유 물량은 유지하고 빈 슬롯 계획 수량만 조정하려면 예산 조정 경로를 사용한다.

## 위험 명령

아래 명령들은 운영 상태를 크게 바꿀 수 있으므로 실행 전에 [docs/operations.html](docs/operations.html)와 [docs/quick-commands.html](docs/quick-commands.html)의 해당 절차를 먼저 확인한다.

### 라이브 리셋

```bash
.venv/bin/python scripts/reset_krw_btc_live.py
```

이 명령은 `KRW-BTC` 미체결 주문을 취소하고, BTC를 전량 시장가 매도한 뒤, `grid.properties` 기준으로 DB 그리드를 다시 반영한다. 재시작은 자동으로 하지 않으므로 결과 확인 후 직접 `./run.sh` 를 실행한다.

### 라이브 예산 조정

```bash
.venv/bin/python scripts/adjust_budget_live.py --target-budget <KRW>
```

이 명령은 현재 그리드 가격 구조와 보유 수량은 유지하고 `planned_qty`만 목표 예산 기준으로 다시 계산한다. 이미 보유한 BTC를 즉시 줄이지 않으므로, 목표 예산이 현재 재고 원가보다 작아도 실제 예산 회수는 이후 매도 체결을 기다려야 한다.

### 손절 상태 해제

```bash
.venv/bin/python main.py reset-stop-loss
```

L1 손절 이후 매수 차단을 해제할 때 사용한다. L2 24시간 잠금을 강제로 해제해야 하는 상황은 `--force`가 필요하므로 [docs/operations.html](docs/operations.html#stoploss)를 먼저 확인한다.

## 문제가 생기면 먼저 볼 것

문제가 생겼을 때는 임의로 재시작하거나 리셋하기 전에 아래 순서로 확인한다.

1. 최신 로그: `./tail-latest-log.sh`
2. DB 그리드 상태: `.venv/bin/python scripts/show_grid_state.py`
3. 업비트 잔고: `.venv/bin/python main.py balance`
4. 설정 파일: 프로젝트 루트 `.env` 또는 EC2 `/home/ubuntu/auto/.env`
5. PostgreSQL 접속 정보: `.env`의 `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSCHEMA`

로그에 손절, 브레이크아웃 가드, 주문 실패, PostgreSQL 연결 실패가 보이면 관련 세부 문서를 먼저 확인한다. 실거래 주문이 걸릴 수 있는 명령은 원인을 파악한 뒤 실행한다.

## 파일 구성 및 역할

루트의 업무 폴더는 `app/`, `scripts/`, `db/`, `docs/`, `tests/`로 제한한다.
운영 코드는 `app/` 패키지 아래에 모여 있고, 기존 운영 명령 호환을 위해 루트 `main.py`, 루트 호환 alias 모듈, `scripts/` 경로는 유지한다.
각 폴더의 주요 `.py` 파일 역할은 다음과 같다.

| 분류 | 파일 | 역할 설명 |
| :--- | :--- | :--- |
| **Root** | `main.py` | 기존 `python3 main.py ...` 명령을 유지하는 호환 진입점 |
| | `core.py`, `strategy.py`, `exchange.py`, `storage.py`, `config.py`, `utils.py` | 예전 루트 패키지 import 경로를 `app/` 하위 패키지로 연결하는 호환 alias |
| **app/** | `main.py` | 프로그램 진입점 구현. 인자 없는 실행은 봇 루프, CLI subcommand는 `balance`, `init-grid` 처리 |
| **app/core/** | `grid.py` | 그리드 슬롯의 상태(`GridState`) 관리 및 업데이트 로직 |
| | `grid_builder.py` | 설정된 속성값에 따라 신규 그리드 슬롯(`GridRow`)을 생성 및 분배 |
| | `grid_properties.py` | 그리드 범위, 예산 가중치 등 그리드 명세(`GridPropertySpec`) 정의 |
| | `models.py` | 그리드 행, 주문 정보, 주문 상태 등 공용 데이터 모델 및 Enum 정의 |
| **app/strategy/** | `grid_strategy.py` | 매수/매도 진입 판정, 재고 게이트 적용 등 핵심 트레이딩 전략 로직 |
| | `breakout_guard.py` | 캔들 데이터를 분석하여 급등락 시 신규 매수를 차단하는 가드 로직 |
| | `stop_loss.py` | 현재가가 그리드 최하단 아래로 내려갔을 때 단계별 자동 손절 실행 |
| | `recenter_preview.py` | 현재가를 기준으로 그리드 재배치(Recenter) 시뮬레이션 및 결과 계산 |
| **app/storage/** | `postgres_grid_repository.py` | PostgreSQL을 이용한 그리드 상태(슬롯별 수량, 가격 등)의 영속성 관리 |
| | `postgres_order_repository.py` | 체결 대기 중인 주문(Pending Orders)의 DB CRUD 처리 |
| | `factory.py` | 설정에 따라 적절한 저장소(Repository) 인스턴스를 생성하는 팩토리 |
| | `interfaces.py` | 저장소 계층의 일관성을 위한 추상 인터페이스 정의 |
| | `postgres_common.py` | DB 연결 설정 및 트랜잭션 관리를 위한 공통 유틸리티 |
| **app/exchange/** | `crypto.py` | 업비트(Upbit) REST API와 선택적 WebSocket 캐시를 연동하여 실제 주문 제출 및 상태 조회 구현 |
| | `upbit_ws.py` | 업비트 WebSocket ticker/candle/myAsset/myOrder 캐시와 현재가 이벤트 대기 기능 |
| | `base.py` | 거래소 연동을 위한 공통 추상 클래스(`BaseExchange`) 정의 |
| | `stock.py` | 주식 거래소 연동용 stub. `EXCHANGE_TYPE=stock` 일 때 로드되는 `BaseExchange` 구현 뼈대이며 현재는 `NotImplementedError` 만 던진다 (KIS API 등 실 연동 시 교체 예정) |
| **scripts/** | `reset_krw_btc_live.py` | 운영 중인 그리드와 자산을 정리하고 새 그리드를 반영하는 운영 스크립트. 봇 재시작은 자동으로 하지 않는다 |
| | `show_grid_state.py` | 현재 DB에 저장된 그리드와 주문의 상태를 요약해서 터미널에 출력 |
| | `check_daily_low.py` | `logs/trading-YYYY-MM-DD.log` 파일들을 스캔해 날짜별 최저 현재가를 출력. 매수 라인 도달 여부 빠른 점검용 |
| | `apply_grid_properties_to_postgres.py` | `grid.properties` 파일의 설정을 DB의 그리드 테이블에 강제 반영 |
| | `adjust_budget_live.py` | 현재 DB 그리드의 가격 구조와 보유 수량은 유지한 채 `planned_qty`만 재계산하여 예산을 보수적으로 증액/감액. `--target-budget` (절대 총액) 으로 지정 |
| | `upbit_realized_pnl.py` | 업비트 `GET /v1/orders/closed` + `/v1/order` 로 KRW-BTC 실현 손익을 산출. 옵션 없이 실행하면 최근 90일을 일/주/월/년/전체로 모두 출력하고, `--period d/w/m/y` 로 오늘/이번주/이번달/이번년만 조회한다. 직접 지정 기간은 `--from/--to` 로 1개 범위를 합산 출력한다. 봇 주문 identifier의 슬롯 번호를 기준으로 같은 슬롯 안에서만 FIFO 매칭한다 (수수료 차감, read-only 분석). lookback 마진(기본 30일)으로 과거 BUY를 포함해 정확한 매칭을 보장한다. reset 청산 매도는 reset identifier 또는 직전 취소 TP SELL 수량으로 자동 인식하며, 과거 reset 주문은 `--reset-sell-uuid`로 지정 가능. 일별 버킷팅은 SELL `_time_key`(=최대 체결 시각, KST) 기준 |
| **app/utils/** | `upbit_market.py` | 업비트 마켓의 최소 주문 단위, 호가 단위 등 시장 정보 관리 |
| | `grid_reporting.py` | 수익률, 재고 현황 등 그리드 운영 성과 리포팅 유틸리티 |
| | `decimal_utils.py` | 정밀한 수치 계산을 위한 Decimal 변환 및 절사(Truncate) 도구 |
| | `logger.py` | KST 기준 로그 포맷팅 및 파일/콘솔 로깅 설정 |
| **app/config/** | `settings.py` | `.env` 환경 변수 로드 및 시스템 전역 설정 값 관리 |

## 전략 개요

> **한 줄 요약**: 가격대를 여러 슬롯으로 촘촘히 나눠두고, 가격이 어떤 빈 슬롯의 매수가를 **아래로 지나치면 사고**, 보유 슬롯은 목표 매도 가격 이상이면 판다. 매수/매도 차익을 슬롯마다 누적한다.

- 그리드는 빈 슬롯과 보유 슬롯의 집합으로 운영된다.
- 빈 슬롯은 하락 교차에서 매수 후보가 되고, 보유 슬롯은 목표 매도 가격 이상에서 매도 후보가 된다.
- 같은 평가 사이클 안에 여러 `buy_price`를 함께 통과하면 여러 슬롯이 동시에 매수 후보가 될 수 있다.
- 신규 매수는 단순 가격 조건만으로 생성되지 않고, 활성 윈도우, inventory-target gate, 브레이크아웃 가드를 함께 통과해야 한다.
- BUY 체결이 확정되면 해당 슬롯의 TP 지정가 SELL 주문을 즉시 제출하고, 이미 열린 SELL pending 주문이 있으면 같은 슬롯에 중복 매도를 만들지 않는다.
- 매도 기준은 저장된 `sell_price` 하나로 고정되지 않고, 보유 기간에 따라 압축되는 `effective_sell_price`를 사용할 수 있다.

수학적 판정 조건과 계산식은 [docs/strategy-formulas.html](docs/strategy-formulas.html)에 별도로 정리했다.

> **쉽게 말하면**: "가격이 닿았다고 무조건 사지 않는다" 가 핵심. 세 가지 필터가 더 붙어 있다 —  
> ① **활성 윈도우**: 현재가에서 너무 멀리 떨어진 슬롯은 스킵 (극단에 쌓지 않음)  
> ② **inventory-target gate**: 지금 재고가 이미 많으면 추가 매수 안 함 (과매수 방지)  
> ③ **브레이크아웃 가드**: 급등/급락 추세면 신규 매수 전체 차단 (추세 이탈 보호)

## 상태 모델

> **쉽게 말하면**: 각 슬롯은 두 상태 중 하나 — "**이미 BTC 보유 중**" 또는 "**아직 매수 대기 중**". 보유 중 슬롯은 다음에 팔 SELL 주문을 미리 걸어두는 것이 기본이다.

- `held_qty > 0` 인 슬롯은 보유 중 슬롯이다.
- `held_qty = 0` 이고 `planned_qty > 0` 인 슬롯은 빈 슬롯이다.
- `planned_qty`는 다음 복원 시점의 목표 수량 의미를 유지할 수 있다.
- `filled_at` 는 holding 슬롯 age 추적용 메타데이터다. BUY 체결 시 기록되고 SELL 체결 시 비워진다.
- pending/open 주문은 별도 저장되며, 업비트 `uuid`와 nullable `identifier`를 함께 보관한다. reconciliation 주키는 여전히 `uuid` 다.
- 보유 슬롯은 가능하면 항상 대응하는 TP SELL pending 주문을 하나씩 갖는 구조를 기본으로 한다.

## 매수 로직
빈 슬롯은 직전 평가 가격에서 현재가로 내려오며 매수선을 하락 교차했을 때 매수 후보가 된다. 첫 가격 스냅샷에서는 신규 매수를 만들지 않고, 이후 전략 평가 사이클부터 하락 교차한 empty 슬롯만 매수 후보가 된다. 정확한 불등식은 [Strategy Formulas](docs/strategy-formulas.html#buy-cross)에 정리되어 있다.

> **쉽게 말하면**: 단순히 "현재가 < 매수가" 가 아니라 **"방금 그 매수가 선을 가로지르며 내려왔다"** 를 요구한다. 예) 매수가 1억인 슬롯 — 직전 가격 1억 50만, 지금 9,999만 → 라인을 지나쳤으니 매수 후보 ✅. 직전 가격도 이미 9,500만이었다면 이미 아래라 후보 ❌.

가격 조건만 맞는다고 바로 사지 않는다.
- 활성 윈도우는 `previous_price` 기준으로 계산한다.
- 기본값은 현재가 아래 최근접 `48` 슬롯과 위쪽 재진입 후보 `8` 슬롯이다.
- 같은 슬롯에 pending 주문이 있으면 활성 윈도우 안에 있어도 신규 매수 제출 대상에서 제외된다.
- 구현은 더 먼 empty 슬롯으로 backfill 하지 않는 보수적 계약이다.

> **쉽게 말하면**: 현재가 근처 슬롯들만 매수 대상. 멀리 있는 슬롯은 그 가격에 진짜 도달한 뒤에 다뤄진다 (먼 곳으로 미리 채우지 않는다).

inventory-target gate 도 함께 적용된다. 현재 보유 재고 원가가 현재 밴드 위치에서 허용되는 목표 재고 비율보다 낮을 때만 신규 매수를 허용한다. `q_current`, `z`, `q_target` 계산식과 통과 조건은 [Strategy Formulas](docs/strategy-formulas.html#inventory-gate)에 정리되어 있다.

> **쉽게 말하면**: 가격이 바닥 쪽이면 공격적으로 더 사고, 천장 쪽이면 수비적으로 덜 산다. 같은 가격에 매수 라인이 닿아도 이미 많이 실렸으면 쉰다.

즉 매수는 "가격이 닿았는가"만이 아니라 "지금 구간에서 이 정도 재고를 더 들고 가도 되는가"를 함께 본다.

추가로 시간 기반 stale 가드가 매수 평가 진입부를 막는다. 직전 평가 이후 `STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS` 초보다 더 흘렀으면 그 cycle 의 신규 매수 평가를 통째로 스킵하고 `previous_price` 만 현재가로 baseline 재설정한다. SELL 평가는 영향받지 않는다. 시간 측정은 `time.monotonic()` 기준이라 NTP 보정/시계 역행에 면역이다.

> **쉽게 말하면**: DB 단절·네트워크 장애 등으로 봇이 한참 멈췄다 깨어났을 때, 메모리에 박제돼 있던 옛 가격과 현재가를 한 tick으로 비교해 매수 라인을 한꺼번에 가로지르는 사고를 막는 가드다. "오랫동안 평가가 멎어 있던 직후의 첫 비교는 신뢰하지 않고 한 cycle 쉰다." 콜드스타트 가드의 시간 기반 확장판.

## 상승 재진입 옵션
상승 구간의 단일 슬롯 상향 돌파 매수는 옵션 기능이다.

- 직전 가격에서 현재가로 올라오며 정확히 `1`개 empty 슬롯의 매수선을 상향 교차할 때만 후보가 된다
- 업비트 `ord_type=price` 시장가 예산매수를 쓴다
- `UPWARD_BUY_ENABLED=True` 일 때 켜지고, 기본값은 `ON` 이다
- 정확한 판정식은 [Strategy Formulas](docs/strategy-formulas.html#upward-reentry)에 정리되어 있다.

기본 경로는 이 기능을 켜 둔 상승 재진입 경로다.

> **쉽게 말하면**: 기본 매수는 "내려올 때" 타지만, 이 옵션은 **"올라올 때"** 도 한 슬롯 정도는 담는다. 바닥 찍고 반등하는 국면에서 완전히 배제되지 않도록. 단 **정확히 한 칸만** 넘는 경우에 한정 — 한 번에 여러 칸을 튀어오르면 추세 장이라 판단해서 건너뛴다.

## 현재가 루프와 WebSocket 전환
운영 기본값은 현재가 `ticker` WebSocket 이벤트 루프다.

- `UPBIT_WS_PUBLIC_ENABLED=True`: public ticker WebSocket 캐시를 켠다.
- `UPBIT_WS_EVENT_LOOP_ENABLED=True`: 메인 루프가 새 ticker 이벤트를 기다렸다가 전략 평가 사이클을 실행한다.
- `UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=3`: ticker 이벤트가 더 자주 와도 전략 평가는 최소 3초 간격으로 제한한다. throttle 후 wait 발생 시 한 cycle은 최대 약 2배 더 늦을 수 있다.
- `PRICE_POLL_INTERVAL=5`: WebSocket 의존성 누락, 시작 실패, 연결 오류, 이벤트 없음, stale tick 상황에서 REST 현재가 조회 fallback 주기로 사용한다.

WebSocket callback/thread 는 가격 이벤트만 메모리 캐시에 저장한다. pending 주문, 그리드 상태, DB 저장, 주문 제출은 모두 `app/main.py`의 단일 실행 경로에서 직렬로 처리한다. 따라서 이벤트 폭주가 있어도 주문 판단은 backlog를 순차 처리하지 않고 최신 가격으로 coalesce 된다.

> **쉽게 말하면**: WS 가 1초에 수십 틱을 쏟아내도 봇이 **각 틱마다 주문 판단을 반복하지 않는다.** 캐시에는 "가장 최근 가격" 하나만 덮어쓰고, 전략 평가는 최소 3초 간격에 한 번씩 최신가 기준으로만 실행한다. 이벤트가 쌓여 밀리거나 옛 가격으로 뒤늦게 판단할 일이 없다.

## 매도 로직과 Age TP
BUY 체결이 확인되면 해당 슬롯의 `effective_sell_price` 기준 지정가 SELL 주문을 즉시 제출한다. 따라서 기본 매도 경로는 “현재가를 보고 그때 SELL을 새로 만든다”보다 “체결 직후 TP SELL을 미리 걸어둔다”에 가깝다. 보유 슬롯에 열린 SELL pending 주문이 없을 때만 누락된 TP 주문을 보강한다.

`effective_sell_price` 기본값은 저장된 `sell_price`지만, `k` 기반 holding 슬롯은 `filled_at` 경과 시간에 따라 더 낮아질 수 있다.

Age TP 압축 규칙과 `effective_sell_price` 계산식은 [Strategy Formulas](docs/strategy-formulas.html#age-tp)에 정리되어 있다.

> **쉽게 말하면**: `k` 는 고정 퍼센트가 아니라 그리드 로그 간격 기준의 TP 폭이다. 그 가격에 도달하지 못하고 오래 들고 있으면 점점 낮은 TP 폭을 허용하되, `k_floor` 밑으로는 내리지 않는다. "안 팔리고 쥐고만 있지 말자" 는 취지다.

중요한 점:
- 압축은 런타임 매도 판정에서만 적용된다.
- 저장된 `sell_price` 자체를 덮어쓰지는 않는다.
- 런타임 `GRID_TP_K_BASE=9.0` / `GRID_TP_K_FLOOR=7.0` 가 DB 그리드를 만들 때 쓴 값과 일치해야 의도한 폭으로 동작한다.
- 이미 제출된 SELL pending 주문의 가격은 Age TP 변화에 맞춰 자동 재호가하지 않는다. 압축은 새 SELL 주문을 만들 때만 반영한다.

## 브레이크아웃 가드
전략은 최근 완료된 `BREAKOUT_GUARD_CANDLE_UNIT` 분 캔들 종가가 `BREAKOUT_GUARD_CONSECUTIVE_CANDLES` 개 연속으로 밴드 밖에 있으면 신규 매수를 모두 제거한다. 이미 보유한 슬롯의 매도는 계속 허용한다.

판정 밴드는 설정 상수보다 PostgreSQL 그리드의 실제 `buy_price` 최상단과 최하단을 기준으로 본다. 초기화 경로와 무관하게 저장된 런타임 그리드 기준으로 판정한다.

캔들 조회 실패 시 기본값은 `BREAKOUT_GUARD_FAIL_OPEN=False` 이다. 즉 데이터가 불안정하면 신규 매수를 막는 fail-close 쪽으로 동작한다.

> **쉽게 말하면**: 가격이 그리드 밴드를 **확실히 벗어나서 추세 이탈 중이면 신규 매수 중단**, 이미 보유한 건 계속 팔기는 허용. 예) 기본값 기준 15분 캔들 4개가 연속으로 그리드 천장 위에서 마감 → "그리드가 따라잡기엔 너무 튀었다" → 매수 멈춤. 캔들 데이터를 아예 못 가져오는 경우도 **매수를 막는 쪽 (fail-close)** 이 기본값 — "잘 모르면 안 사는 게 안전" 원칙.

## 주문 제출과 상태 반영
주문 제출 경로는 아래 순서다.

1. `GET /v1/orders/chance`
2. `POST /v1/orders/test`
3. `POST /v1/orders`

> **쉽게 말하면** (각 단계의 역할):
> 1. **chance**: 이 주문 가능한지 사전 확인 (잔고 충분? 최소 주문 금액 통과? 호가 단위 맞음?)
> 2. **orders/test**: 실제 주문 전에 업비트에게 "이 파라미터로 돼?" 라고 dry-run 검증 (실제 주문은 안 나감)
> 3. **orders**: 실제 주문 제출
>
> 즉 실주문 보내기 전에 **두 번 먼저 체크** 하는 구조. 엉뚱한 주문으로 실패/블록당하지 않으려는 보수적 경로다.

실주문 body 에만 `identifier` 를 넣고, `orders/test` body 에는 넣지 않는다. 주문 생성 성공은 체결 완료와 다르다. 상태 저장소는 업비트 `GET /v1/order` 재조회 결과가 `done`일 때만 갱신한다. `wait` 와 `watch` 상태 주문은 pending 으로 유지한다. `cancel` 이더라도 `executed_volume > 0` 인 경우는 부분 체결로 별도 반영한다.

> **쉽게 말하면**: "주문 넣었다 = 체결됐다" 가 아니다. 주문은 접수만 됐을 뿐. 실제로 `GET /v1/order` 로 다시 조회해서 **업비트가 "done" 이라고 답할 때만** 그리드 상태를 "보유" 로 바꾼다. `wait`/`watch` 주문은 pending 으로 남겨 다음 주기에 reconciliation 으로 정리한다. 단, 실주문 `POST /v1/orders` 호출 자체가 타임아웃/네트워크 오류로 실패해 `uuid`를 받지 못한 경우 현재 구현은 pending 주문으로 저장하지 못하고 실패로 기록한다.

체결/취소 처리 규칙:
- BUY 체결 확인 후 슬롯을 holding 으로 반영하고 즉시 TP SELL pending 주문을 생성한다.
- `cancelled` 이면서 `executed_volume > 0` 인 BUY는 부분 체결로 보고 holding 반영 후 TP SELL을 생성한다.
- `cancelled` 이면서 `executed_volume > 0` 인 SELL은 부분 매도로 보고 남은 `held_qty`를 유지한 뒤 잔여 수량 기준 TP SELL을 다시 건다.

rate limit 대응은 `Remaining-Req` 기반 제한과 `429`, 짧은 `418` 차단에 대한 bounded backoff 로만 다룬다. `POST /v1/orders` timeout 또는 network 오류처럼 체결 여부가 모호한 경우는 자동 재시도하지 않는다. 이 경우 `uuid`가 없으므로 pending reconciliation 대상에도 자동 등록되지 않는다.

봇 시작 시에는 거래소에 열려 있지만 DB의 pending 주문 저장소에는 없는 `KRW-BTC` 미체결 주문을 조회해 취소한다. DB를 기준으로 관리하지 않는 외부/수동 주문과 섞여 중복 상태가 생기는 것을 막기 위한 부팅 가드다.

## 그리드 생성 경로
- `main.py init-grid`는 슬롯 개수 기반이다.
- `grid.properties`는 `MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `TOTAL_BUDGET_KRW`와 `GRID_COUNT` 또는 `GRID_STEP_PCT` 중 정확히 하나를 받는다.
- `TOTAL_BUDGET_KRW`를 상단/중단/하단 `0.7x / 1.0x / 1.3x` 가중치로 정규화 배분한다.
- 각 슬롯 `planned_qty`는 `slot_budget / buy_price` 기준 소수 BTC 단위 내림으로 계산한다.

> **쉽게 말하면**: 같은 총예산을 슬롯에 **균등 배분하지 않는다**. 상단(비싼 구간)은 0.7배로 적게, 하단(싼 구간)은 1.3배로 많이 분배한다. 바닥에 떨어졌을 때 더 많이 담을 수 있도록 자금을 아래쪽으로 기울여두는 구조.

`GRID_COUNT`는 슬롯 수를 직접 고정할 때 쓰고, `GRID_STEP_PCT`는 기존 슬롯 간격을 비율로 그대로 복원할 때 쓴다.

운영 중 예산이나 그리드를 다시 세팅할 때는 단순히 DB 그리드만 덮어쓰지 말고, 가능하면 `scripts/reset_krw_btc_live.py` 경로를 사용한다.

- 대상: `KRW-BTC` 라이브 운영 환경
- 실행 위치: EC2 `cd /home/ubuntu/auto`
- 실행 명령: `.venv/bin/python scripts/reset_krw_btc_live.py`
- 수행 순서: `./stop.sh` -> 업비트 `KRW-BTC` 미체결 주문 취소 -> BTC 전량 시장가 매도 -> `grid.properties` 기준 DB 그리드 재반영 -> 상태 출력
- 재시작은 자동으로 하지 않는다. 결과 확인 후 필요하면 직접 `./run.sh` 를 실행한다.
- reset 전량 시장가 매도에는 `{STATE_BOT_KEY}-reset-sell-...` identifier를 붙인다. `scripts/upbit_realized_pnl.py` 는 이 주문을 reset 청산 경계로 자동 인식하고, reset 직전 취소된 TP SELL 슬롯을 우선 사용해 청산 손익을 매칭한다.

즉 다음번에 `TOTAL_BUDGET_KRW` 같은 금액만 바꿔도, 라이브 재초기화는 이 스크립트를 실행하는 것을 기본 경로로 본다. `scripts/apply_grid_properties_to_postgres.py --force` 는 DB 반영만 필요할 때 쓰는 하위 경로다.

보유 물량을 청산하지 않고 빈 슬롯의 매수 대기 금액만 보수적으로 조정하려면 `scripts/adjust_budget_live.py` 를 쓴다.

- 목적: 현재 DB의 `buy_price` ladder, `held_qty`, `sell_price`, `filled_at` 는 유지하고 `planned_qty`만 새 총예산 기준으로 다시 계산
- 적용 범위: 빈 슬롯은 즉시 새 `planned_qty`가 반영되고, 보유 슬롯은 현재 보유 수량을 유지한 채 다음 복원 시점부터 새 `planned_qty` 의미를 사용
- 입력 옵션:
  - `--target-budget <KRW>` (필수): 그리드 전체 총 예산을 절대값으로 지정.
- 안전장치: DB ladder 연속성/내림차순 검증, open BUY 주문 차단(확정 전후 2회), BTC 수량 step 내림, 업비트 최소 주문 금액 검사, `target_budget < current_inventory_cost` 경고와 `--force` 요구, 사용자 `y/n` 확정 후에만 DB 저장.
- 권장 절차: `./stop.sh` -> open BUY 없음 확인 -> `.venv/bin/python scripts/adjust_budget_live.py --target-budget <KRW>` -> `./run.sh`
- 주의: 이 스크립트는 soft adjust 경로다. 이미 보유한 물량을 즉시 줄이지 않으므로, 목표 예산이 현재 인벤토리 원가보다 작아도 실제 예산 회수는 매도 이후에 완료된다.

## 핵심 설정 의미
- `GRID_TOTAL_BUDGET_KRW` / `--total-budget` / `TOTAL_BUDGET_KRW`: `init-grid`와 `grid.properties`가 공유하는 총예산 입력값이다. `init-grid`는 슬롯 수 기반이다.
- `MAX_TOTAL_BUDGET_KRW`: 전체 그리드 총배정금액 한도 검사에 사용한다.
- `MAX_OPERATING_BUDGET_KRW`: 재고 비율 `q_current` 계산 분모다.
- `UPBIT_FEE_RATE`, `FEE_BUFFER_KRW`: 매수 필요 KRW 추정에 반영하는 수수료/안전 버퍼다.
- `UPWARD_BUY_ENABLED`: 상승 1칸 돌파 시장가 예산매수 토글이다.
- `ACTIVE_WINDOW_BELOW_CURRENT_SLOTS`, `ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS`: 빈 슬롯 매수 후보 범위를 제어한다.
- `BREAKOUT_GUARD_ENABLED`, `BREAKOUT_GUARD_CANDLE_UNIT`, `BREAKOUT_GUARD_CONSECUTIVE_CANDLES`: 추세장 신규 매수 차단 규칙을 제어한다.
- `GRID_TP_MODEL`, `GRID_TP_K_BASE=9.0`, `GRID_TP_K_FLOOR=7.0`: 신규 생성 그리드의 TP 규칙과 Age TP 압축 기준을 결정한다.
- `UPBIT_WS_PUBLIC_ENABLED`, `UPBIT_WS_EVENT_LOOP_ENABLED`, `UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS`: 현재가 WebSocket 이벤트 루프와 최소 전략 평가 간격을 제어한다.
- `STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS=30`: cycle 사이 경과 시간이 이 값을 초과하면 그 cycle 의 신규 매수 평가를 스킵하고 `previous_price` 만 baseline 재설정한다. DB 단절 후 stale `previous_price` 와 현재가 한 tick 비교로 BUY 다수가 fan-out 되는 사고 방지용.
- `UPBIT_WS_CANDLE_ENABLED`, `UPBIT_WS_ASSET_ENABLED`, `UPBIT_WS_ORDER_ENABLED`: 캔들/자산/주문 상태 WebSocket 캐시 사용 여부를 제어한다. 주문 생성과 취소는 계속 REST만 사용한다. `UPBIT_WS_ORDER_ENABLED=true` 여도 주문 상태의 terminal 판정은 반드시 `GET /v1/order` REST 재조회 기준이며, WS myOrder 캐시는 관측/힌트 용도다.

## 참고 문서
- [docs/setup.html](docs/setup.html)
- [docs/operations.html](docs/operations.html)
- [docs/quick-commands.html](docs/quick-commands.html)
- [docs/mobile-api.html](docs/mobile-api.html)
- [docs/strategy-formulas.html](docs/strategy-formulas.html)
- [docs/UPBIT_API_REFERENCE.html](docs/UPBIT_API_REFERENCE.html)
