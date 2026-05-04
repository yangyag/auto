# Strategy Review — 2026-05-04

세 명의 리뷰 에이전트(`reviewer-arch`, `reviewer-formula`, `devil`)가 토론을 거쳐 합의한 이슈 목록이다. devil(악마의 변호인)이 두 라운드의 반박 끝에 인정한 항목만 합의로 남겼고, 반박을 통과하지 못한 항목은 부록에 분리했다.

검토 범위: `README.md`, `docs/strategy-formulas.md`, `app/main.py`, `app/strategy/*`, `app/core/*`, `app/storage/*`, `app/exchange/*`, `scripts/*`.

---

## 합의 항목

### A1 [high] `apply_grid_properties_to_postgres.py --force` 가 optimistic concurrency 와 advisory lock 을 모두 우회

- 위치
  - `scripts/apply_grid_properties_to_postgres.py:119-125` 가 `GridSnapshot(metadata=RepositoryMetadata())` (`version=None`) 으로 `save` 호출.
  - `app/storage/postgres_grid_repository.py:74` 의 `expected_version is not None and current_version != expected_version` 분기는 `expected_version=None` 일 때 검사 자체를 스킵.
  - `PostgresRuntimeLock` 미획득.
- 위험: 운영봇이 살아 있을 때 누군가 `--force` 실행하면, 봇의 in-memory 그리드 version 과 무관하게 `grid_slots` 행을 통째로 DELETE/INSERT 한다. 봇이 다음 cycle 에 `has_changed` 로 재로드해 holding 슬롯 메타데이터(`filled_at`, `held_qty`)가 날아가거나, 봇이 자기 in-memory 로 다시 덮어써 ladder 변경이 무효화될 수 있다. `reset_krw_btc_live.py` 권장 경로 안에서도 호출되지만 그 자체에 봇 부재 강제 검증 없음.
- 권고: 스크립트 시작 시 `PostgresRuntimeLock.acquire` 시도, 실패하면 abort.

### A3 [high] 봇 시작 경로에 거래소↔DB pending order cross-check 부재 (submit crash gap)

- 위치
  - `app/main.py:submit_orders 216-225` 는 (1) `place_order` → uuid 수령, (2) `pending_orders[uuid]=order`, (3) `repo.add` 순서.
  - 재시작 시 `app/main.py:911-918` 가 `list_open()` 만 보고 in-memory `pending_orders` 를 채움.
  - 거래소 ↔ DB cross-check 경로는 `scripts/reset_krw_btc_live.py` 만 보유, 일반 `run()` 경로엔 없음.
- 위험: (1)~(3) 사이 process crash / DB 단절 시 업비트엔 identifier 가 박힌 라이브 주문이 있고 DB `orders` 에는 없다. 재시작 후 `filter_pending_slot_orders` / `_pending_sell_slot_indexes` 가 이를 인지 못 하므로 같은 슬롯에 second BUY 또는 중복 TP SELL 가능. DB 와 거래소의 단일 직렬 경로가 깨지는 가장 현실적 경로.
- 권고: `run()` 초기화에 거래소-DB cross-check 를 reset 경로와 동일 형태로 추가 (open uuid 비교 후 DB 에 없는 거래소 주문은 보강 추가 또는 cancel).

### A2 [med] `adjust_budget_live.py` 가 `PostgresRuntimeLock` 미획득 + `input()` 대기 동안 race window

- 위치: `scripts/adjust_budget_live.py:177-264`. `list_open_buys()` 두 번 검사 + `grid_repo.save(metadata=snapshot.metadata)` 의 version 체크는 silent overwrite 는 막지만, `PostgresRuntimeLock` 은 어디서도 잡지 않음.
- 위험
  - `input()` 대기 동안 봇이 SELL 체결 반영 → 사용자에게 표시된 "역산된 implicit total budget" 등 stale 리포트 기반 의사결정.
  - `ValueError` abort 후 재실행 race.
  - 봇 부재 강제 가드 없음 → 운영가이드(`./stop.sh` 권장)에만 의존.
- 권고: A1 과 동일하게 advisory lock acquire 추가.

### F1 [high] 상승 재진입 burst guard 의 스코프 모호 / 코드 어긋남

- 위치: `docs/strategy-formulas.md:246` ↔ `app/strategy/grid_strategy.py:144-160`
- 사실
  - `crossed_up_rows` 는 (1) `is_empty` (2) `not pending` (3) `active_slot_indexes` 통과 (4) `previous_price < buy_price <= current_price` 까지 모두 필터링한 뒤 `len > 1` burst guard 가 적용된다.
  - 갭상승으로 N개 슬롯이 동시에 상향 돌파해도, 그 중 active window 안에 1개만 들어 있으면 burst guard 가 발동하지 않고 시장가 매수가 나간다.
- 운영 의도와의 어긋남
  - `docs/strategy-formulas.md:246` 의 "정확히 1개 empty 슬롯만 상향 교차한다" 표현이 "전체 그리드 기준" 인지 "active 후보 기준" 인지 명시되어 있지 않다.
  - `README.md:106` 의 "한 번에 여러 칸을 튀어오르면 추세장이라 판단해서 건너뛴다" 라는 운영 의도는 전체 그리드 기준 burst guard 다. 코드는 이 의도를 표현하지 못한다.
- 권고
  - doc 에 "전체 그리드 기준" / "active 후보 기준" 중 어느 쪽인지 명시.
  - 운영 의도가 전자라면 코드의 `len > 1` 검사를 active_window/pending 필터링 이전 단계로 이동.

### F2 [med] 가격교차 SELL 경로의 `A_min` 검사 누락

- 위치: `docs/strategy-formulas.md:381-383` ↔ `app/strategy/grid_strategy.py:_make_sell_orders 195-216`
- 사실
  - doc 은 매도 조건의 일부로 `S_i^eff * H_i >= A_min` 명시.
  - 코드의 `_make_sell_orders` 는 `current_price >= effective_sell_price` 만 보고 `Order` 생성. `A_min` 가드는 `build_tp_sell_order_for_slot:244-249` (TP 보강 경로) 에만 있어 가격교차 경로 우선 발화 시 우회된다.
  - `check_risk` (`app/main.py:519-547`) 도 BUY 측 최소금액만 검사한다.
- 발생 조건: 부분매도 체결로 잔여 `H_i` 가 작아져 `effective_sell_price * H_i < 5000 KRW` 인 슬롯.
- 운영 영향
  - 거래소가 `minimum_total` 위반으로 cancel 응답 → `main.py` 의 `is_cancelled` 분기로 떨어져 pending 에서 빠지지만 grid 의 is_holding 은 그대로 유지.
  - 다음 cycle 에 `_pending_sell_slot_indexes` 가 비어 있으니 동일 슬롯에 SELL 재시도 → 가격이 `effective_sell_price` 위에 머무는 동안 매 cycle 호출 낭비, rate limit 소모, 로그 노이즈.
  - 영구 손실은 없으나 운영 가시성/리소스 손해.
- 권고: `_make_sell_orders` 에 `A_min` 가드 추가, 또는 `check_risk` 의 SELL 분기에 `A_min` 검사 추가.

---

## Doc 보강 권고 (합의 목록 외, 운영 가시성/SOP)

- **A4**: `app/main.py:836-874` 의 price-event 루프 throttle 후 추가 wait 로 한 cycle 이 최대 ~2x `min_interval` (기본 6s) 늦어질 수 있음. README 의 "최소 3초 간격" 은 floor 표현이라 위반은 아니지만 운영자 시각에서 ceiling 동작 미명시.
- **A5**: `scripts/reset_krw_btc_live.py` 가 `stop.sh` 후 cancel/liquidate/apply 를 진행하지만 `PostgresRuntimeLock` 으로 봇 부재를 강제 검증하지 않음. 기존 advisory lock 자산을 활용하지 않는 비대칭 설계. 패치 cheap, 발생 빈도 low.
- **A7**: `app/main.py:138-141, 163-166` 의 `order.quantity = status.executed_volume` in-memory mutate 후 `mark_filled` 가 `quantity` SQL 갱신을 안 함. `orders` 테이블엔 처음 add 한 quantity 가 남고 `GridState.held_qty` 만 갱신 → 사고 분석 가시성 저하. 손해 시나리오는 없음.
- **F4**: 상승 매수 `spend_amount` 의 사전 가드는 `app/main.py:check_risk:532` 의 `MIN_KRW_ORDER_AMOUNT` 가 흡수한다 (`app/core/models.py:67-70` 의 `Order.required_krw` 가 시장가 매수 시 `spend_amount` 반환). doc 에 "사전 검증은 `check_risk` 의 `MIN_KRW_ORDER_AMOUNT` 가 담당" 한 줄 보강 권장.
- **F6**: `scripts/adjust_budget_live.py` 의 `r_lower` 가 현재가에 의존해 같은 `X` 입력에서도 implicit 총예산이 시장 위치에 따라 달라진다. doc/코드는 일관 ("하단 매수합 목표" 정의의 직접 귀결) 이지만 운영자 가이드에 비단조성을 명시 권장.

---

## 합의 목록에서 제외된 항목 (devil 반박, 양쪽 수용)

- **A6**: `OrderStatus.is_filled` / `is_cancelled` 가 mutually exclusive (`app/core/models.py:106`) 로 보장됨. round-off 케이스 사실상 발생 X.
- **F3**: 정상 그리드 `N >= 2` 에서 거의 발생 안 함.
- **F5**: 두 step 동시 정합 사실상 불가, 압축 적용 = 매도 빨라짐 = 불리 X.
- **F7**: reviewer-formula 본인이 코드 OK 표시.

---

## 검증 완료 (정합 OK, 보고용 기록)

`reviewer-formula` 가 docs/코드 일치를 확인한 항목:

- 그리드 슬롯 수: `I_raw` 의 floor/ceil 후보 동률 시 큰 `I` 선택 (`app/core/grid_properties.py:76-78`).
- 매수 가격 사다리: `B_0=U`, `B_{N-1}=L`, 중간 normalize, 중복 시 `ValueError` (`app/core/grid_properties.py:236-247`).
- 매수 교차 `P_prev > B_i` and `P <= B_i` (`app/strategy/grid_strategy.py:88`) ↔ doc `P_prev > B_i >= P` 동치.
- 상승 교차 `P_prev < B_i <= P` (`app/strategy/grid_strategy.py:149`).
- 첫 가격 스냅샷에서 `P_prev` 만 저장하고 BUY 미생성 (`app/strategy/grid_strategy.py:45-48`), SELL 은 진행.
- Stale guard: `monotonic` 시계 사용 (`app/strategy/grid_strategy.py:43,52`), SELL 영향 없음 (line 59).
- 예산 가중치 배분 0.7/1.0/1.3 인덱스 → 밴드 매핑 (`app/core/grid_properties.py:209-219`), `L = ∅` → `ValueError` (`app/core/grid_properties.py:275-279`).
- 양자화 단조성: `planned_qty = floor(B_slot / B_i, 1e-8 BTC)`. 하단 매수합 ≤ `B_lower` 보장.
- inventory target gate: `q_target = q_min + (q_max - q_min)*(1-z)^gamma`, `threshold = max(q_target - epsilon, 0)`, `pass = q_current < threshold` (`app/core/grid.py:158-185`, `app/strategy/grid_strategy.py:269-287`).
- `B_op` 분모: `MAX_OPERATING_BUDGET_KRW > 0` 이면 그것, 아니면 `total_allocated_budget` (`app/core/grid.py:377-384`, `app/strategy/grid_strategy.py:276`).
- projected inventory 누적: `current_inventory_cost` 부터 시작, 승인 BUY 마다 `buy_price * planned_qty` 더함 (`app/strategy/grid_strategy.py:81, 116, 193`).
- Age TP 경계 48h/7d: `a >= 7d → -1.0`, `48h <= a < 7d → -0.5`, `a < 48h → 0` (`app/core/grid.py:233-237`).
- `k_eff = max(k_base - d(a), k_floor)` (`app/core/grid.py:239`).
- Age TP 압축 가격 불변량 `B_i < S~_i < S_i`: floor 정규화로 등호 케이스 발생 시 폴백 (`app/core/grid.py:266-277`).
- breakout guard: `M` 개 연속 종가 모두 `> U` (상단) 또는 모두 `< L` (하단) (`app/strategy/breakout_guard.py:40-54`). fail-open/close 정책 (`app/main.py:376-396`).
- 매수 필요 KRW: `A_estimated = A_required*(1+f) + buffer`, 잔고 `>= A_estimated + reserve`, 다중 BUY 시 `balance -= estimated_required` (`app/main.py:241-245, 519-547`). 누적 검증 산술적 정확.
- 라이브 예산 조정 (`scripts/adjust_budget_live.py:84-137`): 보유 슬롯 `H_i` 유지, ladder 유지, `planned_qty` 만 재계산, `lower_ratio` 재계산, version 체크 활성. 양자화 단조성 보존.
