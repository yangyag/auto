# 그리드 전략 개선 Phase 계획

[docs/gpt.md](gpt.md) 의 제안을 현재 코드 구조와 PostgreSQL 저장 계약에 맞게 다시 재구성한 구현 계획서다.

핵심 원칙은 두 가지다.

1. `docs/gpt.md` 의 방향성은 유지하되, 현재 코드에서 바로 넣을 수 있는 작업과 저장 계약/주문 엔진을 바꿔야 하는 작업을 분리한다.
2. 실거래 경로를 건드리는 순서는 항상 **안전장치 → 재고 관리 → 주문 수 최적화 → 저장 계약 확장 → 업비트 엔진 개편** 으로 간다.

각 Phase 는 [AGENTS.md](../AGENTS.md) 의 파이프라인(`Planner -> Generator -> Evaluator`)을 따른다.

## 전체 구조 한눈에

| Phase | 기간(추정) | 핵심 목표 | 포함 제안 |
|-------|-----------|-----------|-----------|
| 0 | 반나절 | 안전한 출발점 고정 | 상승 매수 OFF, 용어/초기화 경로 정리 |
| 1 | 2일 | 재고 과다 방지 기준 도입 | 제안 1 (`q_target(z)`) |
| 2 | 1~2일 | 신규 그리드 자금 배분 개선 | 제안 3 (하단 가중), 단 초기화 경로 분리 유지 |
| 3 | 2일 | 추세장 신규 매수 차단 | 제안 7 중 브레이크아웃 가드 |
| 4 | 2~3일 | 주문 수와 자금 집중도 최적화 | 제안 4 (활성 윈도우) |
| 5 | 3~4일 | 익절 로직을 그리드 간격 기준으로 전환 | 제안 2 (`k` 기반 TP) |
| 6 | 4~5일 | 오래 묶인 재고와 재중심화 규칙 도입 | 제안 6 + 제안 7 중 재중심화 |
| 7 | 3~5일 | 업비트 REST 경로 강화 | `orders/chance`, `orders/test`, `identifier`, rate limiter/backoff |
| 8 | 1주+ | 이벤트 기반 주문 엔진 전환 | WebSocket `myOrder`/`myAsset`, `cancel_and_new` |

---

## 선행 용어와 계약

이 문서를 구현하기 전에 아래 용어를 먼저 고정한다.

### 1. 초기화 경로는 두 개이며, 같은 개념이 아니다

- `python3 main.py init-grid`
  - [core/grid_builder.py](../core/grid_builder.py) 기준
  - `GRID_FIRST_BUY_AMOUNT_KRW` 또는 `--first-buy-amount` 기준
  - 첫 슬롯 기준 고정 수량을 모든 슬롯에 동일하게 사용한다
- `scripts/apply_grid_properties_to_postgres.py`
  - `grid.properties` 기준
  - 총예산 `BUY_AMOUNT_KRW * GRID_COUNT` 를 가중 배분한 `slot_budget / buy_price` 로 각 슬롯 `planned_qty` 가 달라진다

따라서 `config/settings.py::GRID_SLOT_COUNT` 와 `grid.properties::GRID_COUNT` 를 단순히 같은 값으로 맞추는 작업은 금지한다.
Phase 0 의 목표는 “숫자 동기화”가 아니라 “의미 분리와 운영 기준 고정”이다.

### 2. 재고 비율 `q` 의 분모를 별도 설정으로 둔다

Phase 1 부터는 아래 값을 별도 설정으로 도입한다.

- `MAX_OPERATING_BUDGET_KRW`
  - 전략이 현재 가격대에서 허용하는 최대 운영 자본
  - 기존 `MAX_TOTAL_BUDGET_KRW` 와 다를 수 있다

Phase 1 의 기본 정의는 아래처럼 둔다.

- `q_current = 현재 보유 슬롯의 (buy_price * held_qty) 합 / MAX_OPERATING_BUDGET_KRW`
- 즉, 우선은 평가손익 기반 mark-to-market 이 아니라 슬롯 원가 기준 재고비율로 시작한다

이 정의를 먼저 고정해야 `q_target(z)` 가 구현 중 흔들리지 않는다.

### 3. 저장 계약을 바꾸는 작업은 뒤로 미룬다

아래 항목은 PostgreSQL 스키마와 export/show 스크립트까지 함께 바꿔야 한다.

- `filled_at` 기반 age 관리
- `identifier`, `time_in_force`, `smp_type` 저장
- `prevented`, partial fill, replace 이력 저장
- WebSocket 이벤트 기반 상태머신

이 작업은 Phase 6 이후로만 들어간다.

### 4. 실거래 검증은 마지막까지 금지한다

- 기본 검증은 `python3 -c "import main"` 와 `python3 -m unittest discover -s tests -v`
- `python3 main.py` 무한 루프 실행은 사용자가 명시적으로 요청한 경우만

---

## Phase 0 — 안전한 출발점 고정

**목표**: 다음 Phase 들이 같은 전제를 보도록 설정과 용어를 먼저 고정한다.

### 작업 항목

- 상승 1칸 돌파 매수를 config 플래그로 분리하고 기본값을 `OFF` 로 둔다
- `init-grid` 경로와 `grid.properties` 경로의 차이를 문서에 명시한다
- 운영 자본 관련 설정 이름과 의미를 고정한다
  - `MAX_TOTAL_BUDGET_KRW`: 전체 그리드 배정 한도 검사
  - `MAX_OPERATING_BUDGET_KRW`: 재고 비율 계산용 운영 자본 상한

### 영향 파일

- `config/settings.py`
- `strategy/grid_strategy.py`
- `README.md`
- `AGENTS.md`

### 완료 조건

- 기본값에서 상승 매수 경로가 비활성화된다
- 문서에 두 초기화 경로의 차이가 명확히 적힌다
- `MAX_TOTAL_BUDGET_KRW` 와 `MAX_OPERATING_BUDGET_KRW` 의 의미가 혼동되지 않는다
- `python3 -c "import main"` 통과
- `python3 -m unittest discover -s tests -v` 통과

### 리스크

- 기존 테스트가 상승 매수 경로를 당연시하면 수정이 필요하다
- 용어만 바꾸고 실제 체크 로직을 안 바꾸면 이후 Phase 에서 다시 혼선이 난다

---

## Phase 1 — 목표 재고곡선 도입

**목표**: “가격대별 적정 보유량” 기준을 먼저 넣어 과재고를 막는다.

### 핵심 개념

- 밴드 내 현재 가격 위치
  - `z = (ln(P) - ln(L)) / (ln(U) - ln(L))`
- 목표 재고 비율
  - `q_target(z) = q_min + (q_max - q_min) * (1 - z) ^ gamma`
- 신규 매수 허용 조건
  - `q_current < q_target(z) - epsilon`

### 기본값

- `q_min = 0.10`
- `q_max = 0.85`
- `gamma = 1.5`
- `epsilon = 0.03`

### 작업 항목

- `GridState` 에 아래 계산 메서드 추가
  - `band_position_z()`
  - `current_inventory_ratio()`
  - `target_inventory_ratio()`
- 하락 교차 매수와 향후 모든 신규 매수는 `q_target(z)` 게이트를 통과해야만 생성한다
- 기본값이 과도하게 보수적이지 않은지 테스트를 추가한다

### 영향 파일

- `config/settings.py`
- `core/grid.py`
- `strategy/grid_strategy.py`
- `tests/`

### 완료 조건

- 상단 근처에서 과재고 상태면 하락 교차가 나와도 신규 매수가 차단된다
- 하단 근처에서 재고가 부족하면 기존 하락 교차 매수는 정상 동작한다
- PostgreSQL 스키마 변경 없음

### 리스크

- `q_current` 를 원가 기준으로 볼지 평가금액 기준으로 볼지 흔들리면 테스트가 불안정해진다
- `MAX_OPERATING_BUDGET_KRW` 가 비어 있으면 재고 게이트가 형식만 있고 의미가 없어진다

---

## Phase 2 — 하단 가중 배분

상태: 완료 (2026-04-19)

**목표**: 신규 그리드 생성 시 자금을 하단 슬롯에 더 배치한다.

### 핵심 개념

- 상단 1/3: `0.7x`
- 중단 1/3: `1.0x`
- 하단 1/3: `1.3x`

### 구현 범위

이 Phase 에서는 **`grid.properties` 경로를 우선 적용 대상** 으로 한다.

- 이유:
  - 이 경로는 원래도 슬롯별 `planned_qty` 가 달라질 수 있다
  - 반대로 `main.py init-grid` 는 “첫 슬롯 기준 고정 수량”이라는 별도 계약을 가진다

`main.py init-grid` 의 고정 수량 계약을 바꾸는 작업은 별도 결정 없이는 하지 않는다.

### 작업 항목

- `grid.properties` 기반 생성에서 슬롯 위치별 가중치를 반영한다
- 최소 주문 금액(5,000 KRW) 미달 슬롯이 생기면 생성 단계에서 막는다
- 필요하면 가중치가 적용된 총예산 요약을 스크립트 출력에 추가한다

### 운영 확인 포인트

- `python3 scripts/apply_grid_properties_to_postgres.py --force`
  - `planned_buy_budget_total`
  - `top_slot_planned_buy_budget`
  - `bottom_slot_planned_buy_budget`
- `python3 scripts/show_grid_state.py`
  - 슬롯별 `planned_krw` 열
  - 총 계획매수금액 요약

하단 가중이 정상 적용되면 일반적으로 `bottom_slot_planned_buy_budget > top_slot_planned_buy_budget` 이다.

### 영향 파일

- `core/grid_properties.py`
- `scripts/apply_grid_properties_to_postgres.py`
- `scripts/export_postgres_grid.py`
- `scripts/show_grid_state.py`
- `docs/`
- `tests/`

### 완료 조건

- 동일 총예산 `BUY_AMOUNT_KRW * GRID_COUNT` 을 유지한 채 하단 슬롯 쪽 `slot_budget` 과 `planned_qty` 가 기존 flat baseline 보다 커지도록 생성된다
- 상단 슬롯이 최소 주문 금액 미달이면 명시적으로 실패한다
- `main.py init-grid` 계약은 그대로 유지된다

### 구현 결과

- `grid.properties` 경로에서만 `BUY_AMOUNT_KRW` 를 슬롯 평균 예산으로 재해석했다
- 상단/중단/하단 가중치 `0.7 / 1.0 / 1.3` 을 실제 슬롯 수에 맞춰 정규화해 총예산을 유지한다
- `apply`/`export`/`show` 스크립트는 `planned_buy_budget_total`, `top_slot_planned_buy_budget`, `bottom_slot_planned_buy_budget` 을 같은 계산식으로 출력한다
- 검증 기준은 `.venv/bin/python -c "import main"` 와 `.venv/bin/python -m unittest discover -s tests -v` 를 사용한다

### 리스크

- 두 초기화 경로를 섞어서 해석하면 운영자가 같은 전략이라고 오해할 수 있다
- 기존 운영 DB 그리드에 소급 적용하면 계약이 바뀌므로, 신규 생성부터만 적용해야 한다

---

## Phase 3 — 브레이크아웃 가드

상태: 완료 (2026-04-19)

**목표**: 추세장에서는 “더 받지 않는 것”을 먼저 구현한다.

### 핵심 개념

- 완료된 15분 종가가 밴드 밖에서 4개 연속 나오면
  - 신규 매수 중지
  - 기존 포지션 청산만 허용

### 구현 원칙

- 이 Phase 에서는 **재중심화는 하지 않는다**
- 저장소에 추가 상태를 넣지 않고, 최근 완료 15분 캔들 조회 결과만으로 판정한다

### 작업 항목

- 업비트 15분 캔들 조회 추가
- 현재 밴드 이탈 여부 판정
- 신규 매수만 차단하는 가드 추가
- 로그에 가드 ON/OFF 상태를 남긴다
- 캔들 조회 실패 시에는 fail-open 으로 기존 매수/매도 흐름을 유지하고 경고 로그를 남긴다

### 영향 파일

- `exchange/crypto.py`
- `exchange/base.py`
- `exchange/stock.py`
- `main.py`
- `strategy/breakout_guard.py`
- `config/settings.py`
- `tests/`

### 완료 조건

- 완료된 15분 종가 4개가 밴드 밖에 연속 존재하면 신규 매수가 발생하지 않는다
- 보유 슬롯 매도는 계속 가능하다
- 가드 해제 시 신규 매수가 다시 동작한다
- 캔들 API 오류가 나도 런타임은 중단하지 않고 기존 주문 흐름을 유지한다

### 구현 결과

- 업비트 `GET /v1/candles/minutes/15` 호출을 `exchange/crypto.py`에 추가했다
- 진행 중인 캔들은 제외하고, 최근 완료 캔들 종가만 가드 판정에 사용한다
- 브레이크아웃 판정은 `strategy/breakout_guard.py`의 순수 계산 로직으로 분리했다
- 가드는 현재 설정 상수 대신 PostgreSQL에 저장된 런타임 그리드의 실제 `buy_price` 상단/하단을 기준으로 판정한다
- 가드가 켜지면 신규 매수만 제거하고, 매도 후보와 pending 체결 반영 흐름은 그대로 둔다
- 캔들 조회 실패 기본값은 fail-open 이며, 경고 로그만 남기고 기존 매수/매도 흐름을 유지한다
- 검증은 `.venv/bin/python -m unittest tests.test_crypto_exchange tests.test_breakout_guard tests.test_main_balance tests.test_order_sync -v` 와 PostgreSQL 통합 테스트로 확인한다

### 리스크

- 가드 상태를 로그로 남기지 않으면 운영 중 왜 매수가 멈췄는지 파악이 어렵다

---

## Phase 4 — 활성 윈도우

**목표**: 전체 그리드는 유지하되 실제 매수 후보는 현재가 근처에만 집중한다.

### 핵심 개념

- 전체 레벨은 유지
- 실제 활성 매수 후보:
  - 현재가 아래 최근접 `36~48` 슬롯
  - 현재가 위 `0~4` 슬롯은 재진입 후보로만 사용

### 작업 항목

- 현재 가격 기준 활성 슬롯 범위를 계산한다
- 비활성 empty 슬롯은 교차가 나와도 주문 후보로 만들지 않는다
- pending 슬롯과 보유 슬롯은 기존 규칙과 충돌하지 않게 정리한다

### 영향 파일

- `strategy/grid_strategy.py`
- `core/grid.py`
- `config/settings.py`
- `tests/`

### 완료 조건

- 같은 가격 구간에서 주문 후보 수가 줄어든다
- 급락 시 현재가 아래 근접 구간에만 신규 매수 후보가 생긴다
- 보유 슬롯 매도 로직은 기존과 동일하다

### 리스크

- 슬롯 범위 계산이 잘못되면 중요한 하단 슬롯이 비활성화될 수 있다
- 상승 재진입 슬롯을 Phase 0 에서 꺼둔 상향 매수 규칙과 혼동하지 않게 해야 한다

---

## Phase 5 — `k` 기반 TP 전환

**목표**: `SELL_PERCENT` 고정 모델 대신 “몇 칸 반등하면 팔지”로 TP 를 관리한다.

### 핵심 개념

- `delta = ln(U / L) / (N - 1)`
- `sell_percent_i = exp(k_i * delta) - 1`
- 기본값
  - `k_base = 11.0`
  - `k_floor = 8.0`

### 구현 원칙

기존 보유 슬롯의 `sell_price` 를 자동으로 전부 재계산하지 않는다.

안전한 기본 정책은 아래 순서다.

1. 신규 생성 그리드와 empty 슬롯부터 `k` 기반 적용
2. 기존 holding 슬롯은 현재 `sell_price` 유지
3. holding 슬롯 재계산은 별도 마이그레이션/재배치 절차 없이는 금지

### 작업 항목

- `k` 기반 sell 가격 계산 함수 추가
- 설정값 추가
- 신규 그리드 생성 경로에 `k` 모델 반영
- 기존 `SELL_PERCENT` 와의 호환 또는 폐기 계획 문서화

### 영향 파일

- `core/grid_properties.py`
- `core/grid_builder.py`
- `config/settings.py`
- `README.md`
- `tests/`

### 완료 조건

- 신규 생성 그리드의 `sell_price` 가 `k` 기준으로 계산된다
- 기존 보유 슬롯의 `sell_price` 는 뜻하지 않게 변하지 않는다
- `SELL_PERCENT` 를 쓰는 경로가 남아 있다면 문서에 명확히 드러난다

### 리스크

- 기존 보유 슬롯까지 일괄 재계산하면 즉시 매도 사고가 날 수 있다
- `grid.properties` 경로와 `init-grid` 경로의 계산식이 또 다시 벌어질 수 있다

---

## Phase 6 — age 기반 TP 와 재중심화

**목표**: 오래 묶인 재고를 더 빨리 돌리고, 밴드 재설정은 엄격한 조건에서만 허용한다.

### 핵심 개념

- age 기반 TP 압축
  - 48시간 경과: `k - 0.5`
  - 7일 경과: `k - 1.0`
  - 단 `k_floor` 아래로는 내려가지 않음
- 재중심화 조건
  - 브레이크아웃 24시간 이상 지속
  - `inventory_ratio <= 0.20`
  - open buy 주문 없음

### 구현 원칙

- 이 Phase 부터는 저장 계약 확장이 필요하다
- 재중심화는 곧바로 완전 자동으로 넣지 않는다
  - 1차: preview/plan 생성
  - 2차: guarded apply

### 작업 항목

- `GridRow` 또는 별도 inventory 메타데이터에 `filled_at` 추가
- age 계산 및 `k` 압축 로직 추가
- 재중심화 preview 로직 작성
- 조건 충족 시에만 apply 가능한 경로 설계

### 영향 파일

- `db/migrations/`
- `core/models.py`
- `core/grid.py`
- `storage/postgres_grid_repository.py`
- `scripts/export_postgres_grid.py`
- `scripts/show_grid_state.py`
- `tests/`

### 완료 조건

- age 데이터가 DB 에 안전하게 저장/복구된다
- 오래 묶인 보유 슬롯의 TP 만 단계적으로 낮아진다
- 재중심화 preview 와 apply 가 구분되어 있다
- 조건 미충족 상태에서는 재중심화가 절대 실행되지 않는다

### 리스크

- 과거 보유 슬롯의 `filled_at` 이 없으면 age 계산 기준이 흔들린다
- 재중심화 apply 가 open order 와 충돌하면 상태 저장소와 거래소 상태가 어긋날 수 있다

---

## Phase 7 — 업비트 REST 경로 강화

**목표**: WebSocket 전환 전, REST 만으로도 주문 실패와 운영 리스크를 줄인다.

### 작업 항목

- `GET /v1/orders/chance` 연동
  - 최소 주문 금액
  - 수수료
  - 주문 가능 상태 조회
- `POST /v1/orders/test` 프리플라이트 체크
- 주문 식별용 `identifier` 생성 및 저장
- `Remaining-Req` 기반 자체 rate limiter 추가
- 429/418 대응 백오프 + jitter 재시도 추가

### 구현 원칙

- 이 Phase 에서는 여전히 REST polling 기반 reconciliation 을 유지한다
- `identifier` 는 도입하되, `uuid` 와 함께 저장해 과도기 호환을 유지한다

### 영향 파일

- `exchange/crypto.py`
- `core/models.py`
- `storage/postgres_order_repository.py`
- `db/migrations/`
- `main.py`
- `tests/`

### 완료 조건

- `orders/test` 실패 시 실주문이 발행되지 않는다
- 주문 저장소에 `uuid` 와 `identifier` 가 함께 남는다
- 429/418 발생 시 즉시 실패만 하지 않고 통제된 재시도를 한다

### 리스크

- `orders/test` 와 실주문 사이의 시차는 여전히 존재한다
- `identifier` 를 저장소에 넣지 않고 메모리에서만 관리하면 프로세스 재시작 시 끊긴다

---

## Phase 8 — 이벤트 기반 주문 엔진 전환

**목표**: private WebSocket 을 단일 진실원천으로 쓰는 주문 상태머신으로 전환한다.

### 작업 항목

- private WebSocket `myOrder`, `myAsset` 구독
- 주문 상태 처리 전환
  - `wait`
  - `trade`
  - `done`
  - `cancel`
  - `prevented`
- `cancel_and_new` 기반 리프라이싱/재배치
- `orders/open` 주기적 reconciliation 로 누락 이벤트 보정

### 구현 원칙

- `myOrder` 를 주 상태 경로로 쓰되, REST 는 보정 경로로 남긴다
- `post_only` 기본화 여부는 전략 성격을 다시 검토한 뒤 결정한다
  - 현재 “교차 후 바로 체결 기대” 로직에는 단순 치환이 불가능하다

### 영향 파일

- `exchange/crypto.py`
- `main.py`
- `core/models.py`
- `storage/postgres_order_repository.py`
- `db/migrations/`
- `tests/`

### 완료 조건

- 프로세스 재시작 후에도 open order / partial fill / prevented 상태를 복구할 수 있다
- WebSocket 단절/재연결 시 재구독과 상태 보정이 동작한다
- `cancel_and_new` 로 재배치한 주문의 연결 관계가 저장소에 남는다

### 리스크

- 가장 광범위한 Phase 다
- 반드시 별도 설계 문서와 시뮬레이션 테스트를 먼저 작성한 뒤 진입한다

---

## 구현 순서 요약

실제 착수 순서는 아래를 권장한다.

1. Phase 0
2. Phase 1
3. Phase 3
4. Phase 4
5. Phase 2
6. Phase 5
7. Phase 6
8. Phase 7
9. Phase 8

이 순서를 권장하는 이유는 다음과 같다.

- 과재고를 막는 재고 게이트가 슬롯 가중보다 먼저 들어가야 한다
- 브레이크아웃 가드는 추세장 손상을 줄이는 즉효 장치다
- 활성 윈도우는 저장 계약 변경 없이 주문 수를 줄일 수 있다
- 하단 가중은 신규 그리드 생성 품질 개선이므로 운영 중 엔진 변경보다 뒤에 둬도 된다
- Upbit 엔진 개편은 마지막까지 미룬다

---

## 공통 규칙

- 모든 Phase 는 `Planner -> Generator -> Evaluator` 순서로 진행한다
- 비파괴 검증(`python3 -c "import main"`, `python3 -m unittest`) 이 먼저다
- `python3 main.py` 실거래 루프는 사용자가 명시적으로 요청한 경우에만 실행한다
- PostgreSQL 저장 계약을 바꾸면 저장소 구현과 export/show 스크립트를 함께 수정한다
- 리스크 정책 변경은 `config/settings.py` 와 `main.py::check_risk()` 를 함께 본다
- 업비트 주문 파라미터가 불명확하면 공식 문서와 `docs/UPBIT_API_REFERENCE.md` 를 우선 기준으로 삼는다
- 커밋 메시지는 한글로 작성한다
