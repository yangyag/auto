# auto

Python 기반 그리드 자동매매 시스템이다. 현재 기준 구현은 업비트 `KRW-BTC`와 PostgreSQL 상태 저장소를 전제로 하며, 가격의 절대값이 아니라 poll 구간에서 `buy_price`와 `sell_price`를 어떻게 교차했는지로 매수와 매도를 판단한다. 주문이 접수됐다고 바로 상태를 바꾸지 않고, 업비트 재조회 결과가 `done`으로 확인될 때만 그리드 상태를 갱신한다.

## 전략 개요
- 그리드는 빈 슬롯과 보유 슬롯의 집합으로 운영된다.
- 빈 슬롯은 하락 교차에서 매수 후보가 되고, 보유 슬롯은 목표 매도 가격 이상에서 매도 후보가 된다.
- 같은 poll 안에 여러 `buy_price`를 함께 통과하면 여러 슬롯이 동시에 매수 후보가 될 수 있다.
- 신규 매수는 단순 가격 조건만으로 생성되지 않고, 활성 윈도우, inventory-target gate, 브레이크아웃 가드를 함께 통과해야 한다.
- 매도 기준은 저장된 `sell_price` 하나로 고정되지 않고, Phase 6 이후에는 보유 기간에 따라 압축되는 `effective_sell_price`를 사용할 수 있다.

## 상태 모델
- `held_qty > 0` 인 슬롯은 보유 중 슬롯이다.
- `held_qty = 0` 이고 `planned_qty > 0` 인 슬롯은 빈 슬롯이다.
- `planned_qty`는 다음 복원 시점의 목표 수량 의미를 유지할 수 있다.
- `filled_at` 는 holding 슬롯 age 추적용 메타데이터다. BUY 체결 시 기록되고 SELL 체결 시 비워진다.
- pending/open 주문은 별도 저장되며, Phase 7부터 업비트 `uuid`와 nullable `identifier`를 함께 보관한다. 현재 reconciliation 주키는 여전히 `uuid` 다.

## 매수 로직
빈 슬롯의 기본 매수 조건은 `previous_price > buy_price >= current_price` 다. 첫 가격 스냅샷에서는 신규 매수를 만들지 않고, 이후 poll 부터 하락 교차한 empty 슬롯만 매수 후보가 된다.

Phase 4부터는 가격 조건만 맞는다고 바로 사지 않는다.
- 활성 윈도우는 `previous_price` 기준으로 계산한다.
- 기본값은 현재가 아래 최근접 `48` 슬롯과 위쪽 재진입 후보 `4` 슬롯이다.
- pending BUY 슬롯은 활성 윈도우 안에 있어도 신규 매수 제출 대상에서 제외된다.
- 현재 구현은 더 먼 empty 슬롯으로 backfill 하지 않는 보수적 계약이다.

inventory-target gate 도 함께 적용된다.
- `q_current = Σ(buy_price * held_qty) / MAX_OPERATING_BUDGET_KRW`
- `z = (ln(P) - ln(L)) / (ln(U) - ln(L))`
- `q_target(z) = q_min + (q_max - q_min) * (1 - z)^gamma`
- 허용 조건은 `q_current < q_target(z) - epsilon`

즉 현재 판의 매수는 "가격이 닿았는가"만이 아니라 "지금 구간에서 이 정도 재고를 더 들고 가도 되는가"를 함께 본다.

## 상승 재진입 옵션
상승 구간의 단일 슬롯 상향 돌파 매수는 옵션 기능이다.

- 조건은 `previous_price < buy_price <= current_price`
- 정확히 `1`개 empty 슬롯 상향 돌파일 때만 후보가 된다
- 업비트 `ord_type=price` 시장가 예산매수를 쓴다
- `UPWARD_BUY_ENABLED=True` 일 때만 켜지고 기본값은 `OFF` 다

기본 운영 전략은 이 기능을 꺼 둔 보수적 경로다.

## 매도 로직과 Age TP
보유 슬롯은 현재가가 런타임 `effective_sell_price` 이상이면 매도 후보가 된다. 기본값은 저장된 `sell_price`지만, `k` 기반 holding 슬롯은 `filled_at` 경과 시간에 따라 더 낮아질 수 있다.

Phase 6 age TP 압축 규칙:
- 48시간 이후: `k - 0.5`
- 7일 이후: `k - 1.0`
- 최저치는 `k_floor`

중요한 점:
- 압축은 런타임 매도 판정에서만 적용된다.
- 저장된 `sell_price` 자체를 덮어쓰지는 않는다.
- 현재 런타임 `GRID_TP_K_BASE` / `GRID_TP_K_FLOOR` 가 DB 그리드를 만들 때 쓴 값과 일치해야 의도한 폭으로 동작한다.

## 브레이크아웃 가드
전략은 최근 완료된 `BREAKOUT_GUARD_CANDLE_UNIT` 분 캔들 종가가 `BREAKOUT_GUARD_CONSECUTIVE_CANDLES` 개 연속으로 밴드 밖에 있으면 신규 매수를 모두 제거한다. 이미 보유한 슬롯의 매도는 계속 허용한다.

판정 밴드는 설정 상수보다 현재 PostgreSQL 그리드의 실제 `buy_price` 최상단과 최하단을 기준으로 본다. `grid.properties` 경로와 `init-grid` 경로가 섞여 있어도 저장된 런타임 그리드 기준으로 판정한다.

캔들 조회 실패 시 기본값은 `BREAKOUT_GUARD_FAIL_OPEN=True` 이다. 즉 경고를 남기고 기존 매수/매도 흐름을 유지한다.

## 주문 제출과 상태 반영
Phase 7 기준 주문 제출 경로는 아래 순서다.

1. `GET /v1/orders/chance`
2. `POST /v1/orders/test`
3. `POST /v1/orders`

실주문 body 에만 `identifier` 를 넣고, `orders/test` body 에는 넣지 않는다. 주문 생성 성공은 체결 완료와 다르다. 상태 저장소는 업비트 `GET /v1/order` 재조회 결과가 `done`일 때만 갱신한다. `wait` 와 `watch` 상태 주문은 pending 으로 유지한다.

rate limit 대응은 `Remaining-Req` 기반 제한과 `429`, 짧은 `418` 차단에 대한 bounded backoff 로만 다룬다. `POST /v1/orders` timeout 또는 network 오류처럼 체결 여부가 모호한 경우는 자동 재시도하지 않는다.

## 그리드 생성 경로
이 저장소에는 서로 다른 두 개의 초기화 계약이 있다.

코드 기반 `init-grid`:
- 첫 슬롯 `buy_price` 기준 `GRID_FIRST_BUY_AMOUNT_KRW` 만큼 살 수 있는 BTC 수량을 모든 슬롯의 고정 수량으로 사용한다.
- 총예산 배분이 아니라 첫 슬롯 기준 고정 수량 모델이다.

`grid.properties` 기반 경로:
- `MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `BUY_AMOUNT_KRW`, `GRID_COUNT`를 읽는다.
- 총예산 `BUY_AMOUNT_KRW * GRID_COUNT`를 상단/중단/하단 `0.7x / 1.0x / 1.3x` 가중치로 정규화 배분한다.
- 각 슬롯 `planned_qty`는 `slot_budget / buy_price` 기준 소수 BTC 단위 내림으로 계산한다.

두 경로는 같은 초기화 계약이 아니므로 숫자를 단순 동기화하면 안 된다.

## 기존 전략 vs 현재 전략
운영자가 "예전 판과 지금 판이 무엇이 달라졌는가"를 빠르게 이해하기 위한 요약이다.

| 항목 | 예전 운영 기준 | 현재 운영 기준 |
|------|----------------|----------------|
| 그리드 범위 예시 | `91,623,000 ~ 127,886,000` | `98,000,000 ~ 121,000,000` |
| 슬롯 수 | `122` | `96` |
| 슬롯 예산 | 거의 균등, 슬롯당 약 `50,000 KRW` | 상단 약 `17,500 KRW`, 중단 약 `25,000 KRW`, 하단 약 `32,500 KRW` |
| 매도 기준 | 레거시 `SELL_PERCENT=3.2` 고정형 | 기본 `TP_MODEL=k`, `TP_K_BASE=11.0`, `TP_K_FLOOR=8.0` |
| 상승 추격 매수 | 포함 가능, 더 공격적 | 기본 `OFF` |
| 하락 매수 범위 | 하락 중 교차한 empty 슬롯을 넓게 매수 | 활성 윈도우 안의 근접 슬롯 위주 매수 |
| 재고 제어 | 약함 | `q_target(z)` inventory gate 적용 |
| 추세장 대응 | 약함 | 브레이크아웃 가드로 신규 매수 차단 |
| 주문 제출 | 실주문 중심 | `orders/chance` -> `orders/test` -> 실주문 |

현재 판의 성격은 공격적 수익 극대화보다 자본 점유와 추세 리스크를 더 강하게 제어하는 쪽에 가깝다.

## 핵심 설정 의미
- `MAX_TOTAL_BUDGET_KRW`: 전체 그리드 총배정금액 한도 검사에 사용한다.
- `MAX_OPERATING_BUDGET_KRW`: 재고 비율 `q_current` 계산 분모다.
- `UPWARD_BUY_ENABLED`: 상승 1칸 돌파 시장가 예산매수 토글이다.
- `ACTIVE_WINDOW_BELOW_CURRENT_SLOTS`, `ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS`: 빈 슬롯 매수 후보 범위를 제어한다.
- `BREAKOUT_GUARD_ENABLED`, `BREAKOUT_GUARD_CANDLE_UNIT`, `BREAKOUT_GUARD_CONSECUTIVE_CANDLES`: 추세장 신규 매수 차단 규칙을 제어한다.
- `GRID_TP_MODEL`, `GRID_TP_K_BASE`, `GRID_TP_K_FLOOR`: 신규 생성 그리드의 TP 규칙과 Phase 6 age TP 압축 기준을 결정한다.

## 참고 문서
- [docs/UPBIT_API_REFERENCE.md](docs/UPBIT_API_REFERENCE.md)
