# Bug Report: previous_price stale 비교로 인한 BUY 폭발 (2026-04-28)

## 요약
DB 단절로 봇 cycle이 약 4시간 17분 동안 크래시 루프에 빠진 뒤, DB가 복구되자마자 첫 정상 cycle에서 메모리에 남아 있던 stale `previous_price`(단절 이전 값)와 현재가를 비교하면서 같은 poll 안에 BUY 4건이 동시에 fan-out 되어 시장가 근처에 일괄 체결됐다. 시간 기반 stale 가드(Option A)로 막을 수 있다.

## 증상 / 영향
- 운영 환경: EC2 `KRW-BTC` 라이브 봇.
- 사고 시각: KST 2026-04-28 02:17:40~43.
- 영향: 슬롯 47/48/49/50 BUY 4건이 1~2초 안에 모두 시장가 근처(약 114,348,000 KRW)에 체결. 의도된 그리드 가격(115,197K / 114,966K / 114,735K / 114,505K)이 아닌 단일 현재가 부근에 집중. 즉 그리드 분산 매수 의미가 깨졌다.
- 자금 손실 자체는 없으나(매수가 ≤ 슬롯 limit), 슬롯 분산이 무너져 이후 TP SELL 효율과 재고 관리 가정이 흔들린다.

## 타임라인 (KST)
| 시각 | 사건 |
|---|---|
| (전일) ~22:00 | `auto-postgres` 컨테이너 종료 (Exit 255, OOM 아님, RestartPolicy=no). 정확한 trigger 미확인. |
| 22:00 ~ 02:17 | 봇 프로세스 alive, 매 cycle `psycopg.OperationalError: Connection refused`로 크래시. `previous_price`는 메모리에 그대로 (마지막 성공 cycle 값 = 115,502,000). |
| 02:17:34 | 마지막 ERROR (DB 여전히 down). |
| 02:17:39 | DB 복구 직후 첫 정상 cycle 시작 (`docker start auto-postgres` 직후). |
| 02:17:40 | 첫 정상 poll: `현재가 114,348,000`. |
| 02:17:40 | strategy가 `115,502,000 -> 114,348,000` 한 tick 비교로 인식 → 슬롯 47~50의 buy_price가 모두 그 사이에 위치 → BUY 4건 동시 제출. |
| 02:17:42~43 | 4건 모두 1~2초 안에 체결 (지정가가 시장가 위쪽이라 즉시 매칭). |
| 02:17:42~44 | 각 슬롯 TP SELL 자동 생성 및 접수. |

## 증거 (log 발췌)
출처: EC2 `/home/ubuntu/auto/logs/asdf.log` (사용자가 사고 직후 별도 복사).

```
02:17:34 [ERROR] connection failed                                   ← 마지막 에러
02:17:39 [ORDER_LIMIT] 일일 주문 카운터 리셋                            ← 정상 cycle 시작
02:17:40 현재가: 114,348,000.0                                       ← 첫 정상 poll
02:17:40 매수 교차 조건 충족(하락) → 슬롯47: 115,502,000 -> 114,348,000 / buy 115,197,000
02:17:40                              → 슬롯48: 115,502,000 -> 114,348,000 / buy 114,966,000
02:17:40                              → 슬롯49: 115,502,000 -> 114,348,000 / buy 114,735,000
02:17:40                              → 슬롯50: 115,502,000 -> 114,348,000 / buy 114,505,000
02:17:40~41 BUY 4건 접수
02:17:42~43 BUY 4건 모두 체결
```

핵심은 strategy 로그의 `115,502,000 -> 114,348,000` 표시. 한 tick에 1,154,000원 떨어진 것으로 인식했지만 실제로는 4시간 17분의 갭이 메모리에 그대로 보존된 결과다.

## 근본 원인
`GridStrategy.previous_price`는 프로세스 메모리에 살아 있고, 평가가 정상 종료된 cycle 끝에서만 갱신된다 (`strategy/grid_strategy.py:53`). DB 단절로 `refresh_grid_state_if_changed`(`main.py`)에서 매 cycle 예외가 던져지면 `evaluate_with_pending` 자체에 도달하지 못하므로 `previous_price`는 단절 직전 값 그대로 남는다. 이후 DB가 복구되어 cycle이 다시 정상적으로 evaluate에 도달하면, 봇은 그 사이의 시간 갭을 인지하지 못한 채 (단절 전 값) → (현재가) 비교를 한 tick의 정상적인 가격 변화로 처리한다. 이때 두 값 사이에 끼어 있는 모든 빈 슬롯이 `previous > buy_price >= current` 매수 교차 조건을 동시에 만족해 BUY 다수가 한 cycle에 fan-out 된다.

README의 콜드스타트 가드("첫 가격 스냅샷에서는 신규 매수를 만들지 않는다", `strategy/grid_strategy.py:41-43`)는 이 케이스를 보호하지 않는다. 가드는 "프로세스 새로 시작" 케이스만 잡고, "프로세스는 살아 있는데 DB만 끊겼다 복구된" 케이스는 해당 없음 분기로 흘러간다.

추가로 하강 경로 `_make_buy_orders`에는 한 tick에 다중 슬롯 가로지름을 막는 가드가 없다. 상승 경로 `_make_upward_buy_order`에는 비대칭으로 이미 다중 돌파 시 전체 스킵 가드가 있다 (`strategy/grid_strategy.py:137-143`). 하강에도 같은 보호가 있었다면 본 사고의 영향이 줄었을 가능성이 있다.

## 제안 조치: Option A — 시간 기반 stale 가드

### 핵심 아이디어
`GridStrategy`에 `previous_price_at` 필드를 추가하고, `evaluate_with_pending` 진입부에서 직전 평가 이후 경과 시간이 임계값을 초과하면 신규 BUY 평가를 통째로 스킵한다. 효과는 콜드스타트 가드와 동일: `previous_price`/`previous_price_at`을 현재 값으로 baseline 갱신만 하고, 다음 poll부터 정상 비교를 재개한다. SELL 평가는 영향받지 않는다.

### 임계값 결정 근거
EC2 `logs/asdf.log` 12분 분량 165 샘플 측정 (사고 직후 정상 운영 구간):

| 통계 | 값(초) |
|---|---|
| min / median / mean / max | 4 / 4 / 4.42 / 8 |
| p90 / p95 / p99 | 6 / 7 / 8 |
| > 30s 횟수 | 0 |

→ **30초 임계값**이면 worst observed 대비 3.75배 마진. PRICE_POLL_INTERVAL(5초) 대비 6배 마진. WebSocket 이벤트 루프(min_interval=3s)가 도입된 현 코드 베이스에서도 측정 데이터에 포함되므로 그대로 유효.

### 시간 소스: `time.monotonic()`
시계 역행/NTP 보정 면역. 프로세스 메모리에만 살아 있으므로 직렬화·재시작 보존이 필요 없는 본 용도에 정확히 맞는다. `datetime.now()`를 쓰면 NTP 보정으로 음수 elapsed가 발생해 가드가 무력화될 위험이 있다.

### 변경 파일 (총 4개)
- `config/settings.py`: 상수 1줄 추가.
- `strategy/grid_strategy.py`: `import time`, `previous_price_at` 필드, `evaluate_with_pending` 진입부 stale 분기.
- `tests/test_grid_strategy.py`: 테스트 3개 추가.
- `README.md`: "## 매수 로직" 섹션에 stale 가드 단락, "## 핵심 설정 의미" 섹션에 새 상수 한 줄.

### 코드 스펙 (4월 28일 작업 기준, 현 origin/main과는 cherry-pick 충돌 가능)

`config/settings.py`:
```python
PRICE_POLL_INTERVAL = 5      # 가격 조회 간격 (초)
STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS = 30  # previous_price 메모리 stale 판정 임계값 (초)
```

`strategy/grid_strategy.py`:
```python
import time
# ...
class GridStrategy:
    def __init__(self, grid_state, exchange, symbol):
        ...
        self.previous_price: Decimal | None = None
        self.previous_price_at: float | None = None  # time.monotonic() 기준

    def evaluate_with_pending(self, current_price, pending_slot_indexes=None):
        effective_pending_slots = pending_slot_indexes or set()
        now = time.monotonic()

        if self.previous_price is None:
            self.previous_price = current_price
            self.previous_price_at = now
            return [], self._make_sell_orders(current_price)

        if self.previous_price_at is not None:
            elapsed = now - self.previous_price_at
            if elapsed > cfg.STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS:
                logger.info(
                    f"매수 평가 스킵(stale previous_price) → "
                    f"prev={self.previous_price} cur={current_price} elapsed={elapsed:.1f}s"
                )
                self.previous_price = current_price
                self.previous_price_at = now
                return [], self._make_sell_orders(current_price)

        active_slot_indexes = self._resolve_active_buy_window_slot_indexes(self.previous_price)
        buy_orders = self._make_buy_orders(
            self.previous_price, current_price, effective_pending_slots, active_slot_indexes,
        )
        sell_orders = self._make_sell_orders(current_price)
        self.previous_price = current_price
        self.previous_price_at = now
        return buy_orders, sell_orders
```

핵심 invariant:
- 콜드스타트 / stale / 정상 세 분기 모두에서 `previous_price`와 `previous_price_at`이 동시 갱신.
- `>` strict 비교 (정확히 임계값 = 정상 처리).
- stale 분기에서도 SELL은 정상 평가 (`_make_sell_orders`는 `previous_price`를 안 씀).

### 테스트 계획 (3개)
1. `test_stale_previous_price_skips_buy_and_runs_sell` — 임계값 + 1초 흐른 뒤 evaluate, 매수 교차 조건 만족 셋업. BUY 차단, SELL 진행, 로그 메시지, previous_price 갱신 확인.
2. `test_stale_threshold_boundary_just_below_runs_normally` — 임계값 - 0.5초만 흐른 경우 정상 매수 진행.
3. `test_previous_price_at_updated_on_every_branch` — 콜드스타트/정상/stale 세 분기 모두에서 두 필드가 함께 갱신되는 invariant.

`time.monotonic` 모킹 방식: `unittest.mock.patch("strategy.grid_strategy.time.monotonic", side_effect=...)`.

## 잔여 리스크 / 미보호 케이스
Option A로 막히지 않는 케이스:
- **임계값 미만의 짧은 단절(예: 15초) + 그 사이 큰 가격 변동.** 가드 통과 후 stale 비교가 그대로 일어남.
- **outage 무관, 정상 운영 중 한 cycle 안에 다중 슬롯을 가로지르는 빠른 하락(플래시 크래시 등).** 본 가드는 전혀 작용하지 않음.
- 즉 상승 경로의 다중 돌파 가드(`_make_upward_buy_order`)와 하강 경로의 비대칭은 본 변경 후에도 그대로 남는다.

후속 검토 항목 (별도 결정):
- **Option B (변화량 캡)**: 하강 경로에도 한 cycle 변화율 임계값(예: 0.5%) 또는 다중 교차 슬롯 수 캡을 추가. 임계값 결정에 운영 데이터(정상 cycle 변화율 분포) 측정 필요.
- 다중 하강 교차 자체에 슬롯 수 cap (`crossed_down_count > N` 시 가장 깊은 1개만 발주).

## 운영/배포 메모
- 사고 직후 임시 조치: `docker update --restart unless-stopped auto-postgres` 적용 완료 (postgres 종료 시 자동 재기동). `RestartPolicy=no`였던 상태에서 변경됨. 컨테이너 재기동만으론 본 BUG가 재현 가능 → Option A 적용이 근본 조치.
- 배포 절차: AGENTS.md "Git / 배포 기준" 절차 그대로 (`./stop.sh` → `git pull --ff-only` → `.venv/bin/python -c "import main"` → `./run.sh`). GridStrategy는 main.py 시작 시 새로 생성되므로 `previous_price_at`은 None부터 시작 → 첫 cycle은 콜드스타트 분기 → 안전한 마이그레이션.

## 작업 컨텍스트 / 참고
- 본 보고서 작성 시점에 4월 28일 작업한 패치는 `backup/stale-guard-ed0d625` 브랜치에 보존 중. main은 `origin/main`(`bc92200`)과 동일.
- 4월 28일 패치는 commit `e16cbd0`(당시 로컬 head) 기준으로 작성됨. 이후 origin/main에 WebSocket 이벤트 루프, WS 캐시, myOrder 캐시, throttle 후 stale 가격 가드(`ada952c`) 등 8개 커밋이 추가됨. `ada952c`는 본 보고서가 다루는 inter-cycle stale `previous_price`와는 다른 문제(intra-cycle WS throttle 후 stale `current_price`)를 다룬다 — 보완 관계, 중복 아님.
- 다음 작업 순서 권장:
  1. 새 main.py(`run_price_event_loop_iteration` 등) 흐름에서 `evaluate_with_pending` 호출 경로가 동일한지 확인.
  2. 측정 데이터(p99 8초)가 이벤트 루프 도입 후에도 유효한지 추가 샘플로 재확인 (현재 측정은 ada952c 적용된 EC2 로그 기반이므로 실제로는 이미 새 구조 데이터).
  3. 백업 브랜치에서 cherry-pick 또는 fresh 재적용. `tests/test_grid_strategy.py`/`config/settings.py`/`strategy/grid_strategy.py`는 8커밋 사이에 손대지 않음(README만 충돌 가능).
