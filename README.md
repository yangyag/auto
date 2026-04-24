# auto

Python 기반 그리드 자동매매 시스템이다. 구현은 업비트 `KRW-BTC`와 PostgreSQL 상태 저장소를 전제로 하며, 가격의 절대값이 아니라 전략 평가 사이클 사이에서 `buy_price`와 `sell_price`를 어떻게 교차했는지로 매수와 매도를 판단한다. 기본 현재가 루프는 업비트 public `ticker` WebSocket 이벤트를 기다리되, 전략 평가는 최소 3초 간격으로만 실행한다. WebSocket을 사용할 수 없거나 이벤트가 없으면 기존 5초 REST polling 으로 fallback 한다. 주문이 접수됐다고 바로 상태를 바꾸지 않고, 업비트 재조회 결과가 `done`으로 확인될 때만 그리드 상태를 갱신한다. BUY 체결이 확인되면 해당 슬롯의 TP 지정가 SELL 주문을 즉시 생성해 pending 으로 관리한다.

## 파일 구성 및 역할

이 시스템은 기능별로 모듈화되어 있으며, 각 폴더의 주요 `.py` 파일 역할은 다음과 같다.

| 분류 | 파일 | 역할 설명 |
| :--- | :--- | :--- |
| **Root** | `main.py` | 프로그램 진입점. CLI 커맨드(run, init-grid 등) 처리 및 WebSocket 이벤트 기반 메인 루프 실행 |
| **core/** | `grid.py` | 그리드 슬롯의 상태(`GridState`) 관리 및 업데이트 로직 |
| | `grid_builder.py` | 설정된 속성값에 따라 신규 그리드 슬롯(`GridRow`)을 생성 및 분배 |
| | `grid_properties.py` | 그리드 범위, 예산 가중치 등 그리드 명세(`GridPropertySpec`) 정의 |
| | `models.py` | 그리드 행, 주문 정보, 주문 상태 등 공용 데이터 모델 및 Enum 정의 |
| **strategy/** | `grid_strategy.py` | 매수/매도 진입 판정, 재고 게이트 적용 등 핵심 트레이딩 전략 로직 |
| | `breakout_guard.py` | 캔들 데이터를 분석하여 급등락 시 신규 매수를 차단하는 가드 로직 |
| | `recenter_preview.py` | 현재가를 기준으로 그리드 재배치(Recenter) 시뮬레이션 및 결과 계산 |
| **storage/** | `postgres_grid_repository.py` | PostgreSQL을 이용한 그리드 상태(슬롯별 수량, 가격 등)의 영속성 관리 |
| | `postgres_order_repository.py` | 체결 대기 중인 주문(Pending Orders)의 DB CRUD 처리 |
| | `factory.py` | 설정에 따라 적절한 저장소(Repository) 인스턴스를 생성하는 팩토리 |
| | `interfaces.py` | 저장소 계층의 일관성을 위한 추상 인터페이스 정의 |
| | `postgres_common.py` | DB 연결 설정 및 트랜잭션 관리를 위한 공통 유틸리티 |
| **exchange/** | `crypto.py` | 업비트(Upbit) REST API와 선택적 WebSocket 캐시를 연동하여 실제 주문 제출 및 상태 조회 구현 |
| | `upbit_ws.py` | 업비트 WebSocket ticker/candle/myAsset/myOrder 캐시와 현재가 이벤트 대기 기능 |
| | `base.py` | 거래소 연동을 위한 공통 추상 클래스(`BaseExchange`) 정의 |
| **scripts/** | `reset_krw_btc_live.py` | 운영 중인 그리드를 초기화하고 자산을 정리하여 재시작하는 운영 스크립트 |
| | `show_grid_state.py` | 현재 DB에 저장된 그리드와 주문의 상태를 요약해서 터미널에 출력 |
| | `apply_grid_properties_to_postgres.py` | `grid.properties` 파일의 설정을 DB의 그리드 테이블에 강제 반영 |
| | `adjust_budget_live.py` | 현재 DB 그리드의 가격 구조와 보유 수량은 유지한 채 `planned_qty`만 재계산하여 예산을 보수적으로 증액/감액 |
| **utils/** | `upbit_market.py` | 업비트 마켓의 최소 주문 단위, 호가 단위 등 시장 정보 관리 |
| | `grid_reporting.py` | 수익률, 재고 현황 등 그리드 운영 성과 리포팅 유틸리티 |
| | `decimal_utils.py` | 정밀한 수치 계산을 위한 Decimal 변환 및 절사(Truncate) 도구 |
| | `logger.py` | KST 기준 로그 포맷팅 및 파일/콘솔 로깅 설정 |
| **config/** | `settings.py` | `.env` 환경 변수 로드 및 시스템 전역 설정 값 관리 |

## 전략 개요
- 그리드는 빈 슬롯과 보유 슬롯의 집합으로 운영된다.
- 빈 슬롯은 하락 교차에서 매수 후보가 되고, 보유 슬롯은 목표 매도 가격 이상에서 매도 후보가 된다.
- 같은 평가 사이클 안에 여러 `buy_price`를 함께 통과하면 여러 슬롯이 동시에 매수 후보가 될 수 있다.
- 신규 매수는 단순 가격 조건만으로 생성되지 않고, 활성 윈도우, inventory-target gate, 브레이크아웃 가드를 함께 통과해야 한다.
- BUY 체결이 확정되면 해당 슬롯의 TP 지정가 SELL 주문을 즉시 제출하고, 이미 열린 SELL pending 주문이 있으면 같은 슬롯에 중복 매도를 만들지 않는다.
- 매도 기준은 저장된 `sell_price` 하나로 고정되지 않고, 보유 기간에 따라 압축되는 `effective_sell_price`를 사용할 수 있다.

## 상태 모델
- `held_qty > 0` 인 슬롯은 보유 중 슬롯이다.
- `held_qty = 0` 이고 `planned_qty > 0` 인 슬롯은 빈 슬롯이다.
- `planned_qty`는 다음 복원 시점의 목표 수량 의미를 유지할 수 있다.
- `filled_at` 는 holding 슬롯 age 추적용 메타데이터다. BUY 체결 시 기록되고 SELL 체결 시 비워진다.
- pending/open 주문은 별도 저장되며, 업비트 `uuid`와 nullable `identifier`를 함께 보관한다. reconciliation 주키는 여전히 `uuid` 다.
- 보유 슬롯은 가능하면 항상 대응하는 TP SELL pending 주문을 하나씩 갖는 구조를 기본으로 한다.

## 매수 로직
빈 슬롯의 기본 매수 조건은 `previous_price > buy_price >= current_price` 다. 첫 가격 스냅샷에서는 신규 매수를 만들지 않고, 이후 전략 평가 사이클부터 하락 교차한 empty 슬롯만 매수 후보가 된다.

가격 조건만 맞는다고 바로 사지 않는다.
- 활성 윈도우는 `previous_price` 기준으로 계산한다.
- 기본값은 현재가 아래 최근접 `48` 슬롯과 위쪽 재진입 후보 `8` 슬롯이다.
- pending BUY 슬롯은 활성 윈도우 안에 있어도 신규 매수 제출 대상에서 제외된다.
- 구현은 더 먼 empty 슬롯으로 backfill 하지 않는 보수적 계약이다.

inventory-target gate 도 함께 적용된다.
- `q_current = Σ(buy_price * held_qty) / MAX_OPERATING_BUDGET_KRW`
- `z = (ln(P) - ln(L)) / (ln(U) - ln(L))`
- `q_target(z) = q_min + (q_max - q_min) * (1 - z)^gamma`
- 허용 조건은 `q_current < q_target(z) - epsilon`

즉 매수는 "가격이 닿았는가"만이 아니라 "지금 구간에서 이 정도 재고를 더 들고 가도 되는가"를 함께 본다.

## 상승 재진입 옵션
상승 구간의 단일 슬롯 상향 돌파 매수는 옵션 기능이다.

- 조건은 `previous_price < buy_price <= current_price`
- 정확히 `1`개 empty 슬롯 상향 돌파일 때만 후보가 된다
- 업비트 `ord_type=price` 시장가 예산매수를 쓴다
- `UPWARD_BUY_ENABLED=True` 일 때 켜지고, 기본값은 `ON` 이다

기본 경로는 이 기능을 켜 둔 상승 재진입 경로다.

## 현재가 루프와 WebSocket 전환
운영 기본값은 현재가 `ticker` WebSocket 이벤트 루프다.

- `UPBIT_WS_PUBLIC_ENABLED=True`: public ticker WebSocket 캐시를 켠다.
- `UPBIT_WS_EVENT_LOOP_ENABLED=True`: 메인 루프가 새 ticker 이벤트를 기다렸다가 전략 평가 사이클을 실행한다.
- `UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=3`: ticker 이벤트가 더 자주 와도 전략 평가는 최소 3초 간격으로 제한한다.
- `PRICE_POLL_INTERVAL=5`: WebSocket 의존성 누락, 시작 실패, 연결 오류, 이벤트 없음, stale tick 상황에서 REST 현재가 조회 fallback 주기로 사용한다.

WebSocket callback/thread 는 가격 이벤트만 메모리 캐시에 저장한다. pending 주문, 그리드 상태, DB 저장, 주문 제출은 모두 `main.py`의 단일 실행 경로에서 직렬로 처리한다. 따라서 이벤트 폭주가 있어도 주문 판단은 backlog를 순차 처리하지 않고 최신 가격으로 coalesce 된다.

## 매도 로직과 Age TP
BUY 체결이 확인되면 해당 슬롯의 `effective_sell_price` 기준 지정가 SELL 주문을 즉시 제출한다. 따라서 기본 매도 경로는 “현재가를 보고 그때 SELL을 새로 만든다”보다 “체결 직후 TP SELL을 미리 걸어둔다”에 가깝다. 보유 슬롯에 열린 SELL pending 주문이 없을 때만 누락된 TP 주문을 보강한다.

`effective_sell_price` 기본값은 저장된 `sell_price`지만, `k` 기반 holding 슬롯은 `filled_at` 경과 시간에 따라 더 낮아질 수 있다.

Age TP 압축 규칙:
- 48시간 이후: `k - 0.5`
- 7일 이후: `k - 1.0`
- 최저치는 `k_floor`

중요한 점:
- 압축은 런타임 매도 판정에서만 적용된다.
- 저장된 `sell_price` 자체를 덮어쓰지는 않는다.
- 런타임 `GRID_TP_K_BASE=9.0` / `GRID_TP_K_FLOOR=7.0` 가 DB 그리드를 만들 때 쓴 값과 일치해야 의도한 폭으로 동작한다.
- 이미 제출된 SELL pending 주문의 가격은 Age TP 변화에 맞춰 자동 재호가하지 않는다. 압축은 새 SELL 주문을 만들 때만 반영한다.

## 브레이크아웃 가드
전략은 최근 완료된 `BREAKOUT_GUARD_CANDLE_UNIT` 분 캔들 종가가 `BREAKOUT_GUARD_CONSECUTIVE_CANDLES` 개 연속으로 밴드 밖에 있으면 신규 매수를 모두 제거한다. 이미 보유한 슬롯의 매도는 계속 허용한다.

판정 밴드는 설정 상수보다 PostgreSQL 그리드의 실제 `buy_price` 최상단과 최하단을 기준으로 본다. 초기화 경로와 무관하게 저장된 런타임 그리드 기준으로 판정한다.

캔들 조회 실패 시 기본값은 `BREAKOUT_GUARD_FAIL_OPEN=False` 이다. 즉 데이터가 불안정하면 신규 매수를 막는 fail-close 쪽으로 동작한다.

## 주문 제출과 상태 반영
주문 제출 경로는 아래 순서다.

1. `GET /v1/orders/chance`
2. `POST /v1/orders/test`
3. `POST /v1/orders`

실주문 body 에만 `identifier` 를 넣고, `orders/test` body 에는 넣지 않는다. 주문 생성 성공은 체결 완료와 다르다. 상태 저장소는 업비트 `GET /v1/order` 재조회 결과가 `done`일 때만 갱신한다. `wait` 와 `watch` 상태 주문은 pending 으로 유지한다.

체결/취소 처리 규칙:
- BUY 체결 확인 후 슬롯을 holding 으로 반영하고 즉시 TP SELL pending 주문을 생성한다.
- `cancelled` 이면서 `executed_volume > 0` 인 BUY는 부분 체결로 보고 holding 반영 후 TP SELL을 생성한다.
- `cancelled` 이면서 `executed_volume > 0` 인 SELL은 부분 매도로 보고 남은 `held_qty`를 유지한 뒤 잔여 수량 기준 TP SELL을 다시 건다.

rate limit 대응은 `Remaining-Req` 기반 제한과 `429`, 짧은 `418` 차단에 대한 bounded backoff 로만 다룬다. `POST /v1/orders` timeout 또는 network 오류처럼 체결 여부가 모호한 경우는 자동 재시도하지 않는다.

## 그리드 생성 경로
- `main.py init-grid`는 슬롯 개수 기반이다.
- `grid.properties`는 `MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `TOTAL_BUDGET_KRW`와 `GRID_COUNT` 또는 `GRID_STEP_PCT` 중 정확히 하나를 받는다.
- `TOTAL_BUDGET_KRW`를 상단/중단/하단 `0.7x / 1.0x / 1.3x` 가중치로 정규화 배분한다.
- 각 슬롯 `planned_qty`는 `slot_budget / buy_price` 기준 소수 BTC 단위 내림으로 계산한다.

`GRID_COUNT`는 슬롯 수를 직접 고정할 때 쓰고, `GRID_STEP_PCT`는 기존 슬롯 간격을 비율로 그대로 복원할 때 쓴다.

운영 중 예산이나 그리드를 다시 세팅할 때는 단순히 DB 그리드만 덮어쓰지 말고, 가능하면 `scripts/reset_krw_btc_live.py` 경로를 사용한다.

- 대상: `KRW-BTC` 라이브 운영 환경
- 실행 위치: EC2 `cd /home/ubuntu/auto`
- 실행 명령: `.venv/bin/python scripts/reset_krw_btc_live.py`
- 수행 순서: `./stop.sh` -> 업비트 `KRW-BTC` 미체결 주문 취소 -> BTC 전량 시장가 매도 -> `grid.properties` 기준 DB 그리드 재반영 -> 상태 출력 -> `./run.sh`

즉 다음번에 `TOTAL_BUDGET_KRW` 같은 금액만 바꿔도, 라이브 재초기화는 이 스크립트를 실행하는 것을 기본 경로로 본다. `scripts/apply_grid_properties_to_postgres.py --force` 는 DB 반영만 필요할 때 쓰는 하위 경로다.

보유 물량을 청산하지 않고 빈 슬롯의 매수 대기 금액만 보수적으로 조정하려면 `scripts/adjust_budget_live.py` 를 쓴다.

- 목적: 현재 DB의 `buy_price` ladder, `held_qty`, `sell_price`, `filled_at` 는 유지하고 `planned_qty`만 새 총예산 기준으로 다시 계산
- 적용 범위: 빈 슬롯은 즉시 새 `planned_qty`가 반영되고, 보유 슬롯은 현재 보유 수량을 유지한 채 다음 복원 시점부터 새 `planned_qty` 의미를 사용
- 안전장치: DB ladder 연속성/내림차순 검증, open BUY 주문 차단, BTC 수량 step 내림, 업비트 최소 주문 금액 검사, `target_budget < current_inventory_cost` 경고와 `--force` 요구
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
- `UPBIT_WS_CANDLE_ENABLED`, `UPBIT_WS_ASSET_ENABLED`, `UPBIT_WS_ORDER_ENABLED`: 캔들/자산/주문 상태 WebSocket 캐시 사용 여부를 제어한다. 주문 생성과 취소는 계속 REST만 사용한다. `UPBIT_WS_ORDER_ENABLED=true` 여도 주문 상태의 terminal 판정은 반드시 `GET /v1/order` REST 재조회 기준이며, WS myOrder 캐시는 관측/힌트 용도다.

## 참고 문서
- [docs/UPBIT_API_REFERENCE.md](docs/UPBIT_API_REFERENCE.md)
