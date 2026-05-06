# 자동 손절 처리 설계 문서

## 요구사항

- 현재가가 그리드 최하단(`min_buy_price`) 아래로 내려갔을 때 단계별 자동 대응
- 소폭 하락(~10%)은 그리드 정상 운영 유지
- 대폭 하락 시 자동 손절 실행
- 사용자 수면 중 폭락에도 자동 대응 (모니터링 + 자동 실행)
- 정확한 손절 임계값은 고정값이 아닌 설정 파라미터로 노출

---

## 임계값 설계 — 결론

### 참조 기준점: `min_buy_price`

그리드 전략은 레인지 회귀(mean-reverting) 베팅이므로 `min_buy_price` 아래로 내려간다는 것은 운영자가 명시적으로 선언한 "정상 범위 이탈"을 의미한다. 모든 손절 임계는 이 값을 기준으로 계산한다.

### 두 가지 임계값 모델

#### 모델 A: 밴드 폭 배수 (권장)

```
P_stop = min_buy_price × (1 - k × (1 - min_buy_price / max_buy_price))
```

- 그리드 폭이 달라져도 "레인지 가정이 얼마나 깨졌는가"를 일관되게 측정
- 현재 그리드(L=110M, U=126.34M, 밴드 폭 ≈14.86%) 기준:
  - `k=1.5` → 손절가 약 88.65M (L 대비 -19.4%)
  - `k=2.0` → 손절가 약 87.3M (L 대비 -20.6%)

#### 모델 B: 고정 % (백테스트/비교용)

```
P_stop = min_buy_price × (1 - X / 100)
```

BTC 통계 기반 참고값:

| 임계 | BTC 변동성 분위 | 특성 |
|---|---|---|
| -10% | ~90th percentile (단주간) | 일상 조정. 매수 차단만 적합, 직접 손절은 과민 |
| -20% | ~95~98th percentile | 강한 약세 추세 진입 신호. 분기 0~1회 |
| -30% | ~99th percentile | 사이클 변곡점. 연 0~1회 |

두 모델 모두 **현재 그리드에서 -20% ≈ band_multiple=1.5**로 수렴한다.

---

## 3단계 손절 구조

| 단계 | 트리거 (min_buy_price 기준) | 컨펌 조건 (15분봉 종가) | 추가 시간 | 액션 |
|---|---|---|---|---|
| **L0** | -10% 이하 | 4개 연속 | 없음 | 신규 매수 차단만. 보유분/TP 매도 유지. 가역. |
| **L1** | -20% 이하 | 4개 연속 | armed 후 1시간 | 보유 BTC 50% 지정가 매도. 매수 영구 차단(수동 해제 전까지). |
| **L2** | -30% 이하 | 2개 연속 | armed 후 30분 | 잔여 100% 분할 청산. 봇 종료 + 24시간 재시작 잠금. |

### 컨펌 비대칭 근거

- **L1은 1시간 여유**: -20%는 BTC 1시간 이내 회복 사례가 존재. 성급한 손절 방지.
- **L2는 30분으로 빠르게**: -30% 이후 30분 내 회복은 역사적으로 극히 드물고, 회복하더라도 재하락 확률이 높음. 추가 손실 비용 > 컨펌 대기 비용.

### 오손절 방지

- **단일 틱(웹소켓 1이벤트) 트리거 절대 금지**: 업비트 호가 공백/스푸핑으로 1초 스파이크 후 즉시 회복하는 케이스 존재
- **분봉 종가 N개 연속** 방식이 필수: 캔들 종가 = 매수자/매도자 합의 가격, wick/플래시크래시 영향 제거
- 기존 `BreakoutGuard`의 "N개 연속 캔들 종가" 패턴 재사용

---

## 구현 위치

### 삽입 지점

`run_trading_cycle()` 내, **현재가 확정 직후 / BreakoutGuard 호출 직전** (main.py:716 근처)

```python
logger.info(f"현재가: {current_price}")

stop_loss_decision = evaluate_stop_loss(exchange, grid_state, current_price)
if stop_loss_decision.triggered:
    result = execute_stop_loss(...)
    return TradingCycleResult(..., stop_loss_triggered=True)

breakout_guard_status = fetch_breakout_guard_status(...)
```

이유:
- 현재가 확정 후, pending 주문 정리 완료 후 시점
- 별도 스레드 X → DB 정합성(pending_orders, grid_state 동시 접근) 문제 회피
- WS 이벤트 루프 / REST 폴링 루프 양쪽 모두 `run_trading_cycle`을 거치므로 동일 적용

### 임계값 계산 함수

```python
def _resolve_stop_loss_threshold(
    grid_state, *, mode: str, band_multiple: Decimal, fixed_pct: Decimal,
) -> Decimal | None:
    bounds = _resolve_runtime_band_bounds(grid_state)
    if bounds is None:
        return None
    lower, upper = bounds
    if mode == "off":
        return None
    if mode == "band_multiple":
        band_drop_ratio = Decimal("1") - lower / upper
        return lower * (Decimal("1") - band_multiple * band_drop_ratio)
    if mode == "fixed_pct":
        return lower * (Decimal("1") - fixed_pct / Decimal("100"))
    raise ValueError(f"unknown STOP_LOSS_MODE={mode}")
```

가드 조건:
- `threshold <= lower * 0.5` → 오설정 차단 (L 대비 -50% 미만 불허)
- `threshold >= lower * 0.9` → 오설정 차단 (L 대비 -10% 이내는 그리드 정상 구간 침범)

### 손절 실행 순서

1. 기존 미체결 주문 전부 취소 (시장가 매도와 충돌 방지)
2. `is_holding` 슬롯별 시장가 매도 (`MARKET_SELL_BY_VOLUME`, 이미 모델/어댑터 구현됨)
3. 즉시 reconcile → grid_state 반영 + 영속화
4. L2는 봇 종료 + `liquidated_at` DB 기록

---

## 설정 파라미터

`grid.properties` 또는 환경변수로 노출:

```
# 손절 모드: band_multiple (권장) | fixed_pct | off
STOP_LOSS_MODE=band_multiple

# band_multiple 모드
STOP_LOSS_BAND_MULTIPLE=1.5        # k 값. 범위: 1.0 ~ 2.0

# fixed_pct 모드 (백테스트/비교용)
STOP_LOSS_L0_PCT=10
STOP_LOSS_L1_PCT=20
STOP_LOSS_L2_PCT=30

# 컨펌 캔들
STOP_LOSS_CANDLE_UNIT=15           # 분봉 단위
STOP_LOSS_L0_CONSECUTIVE_CLOSES=4
STOP_LOSS_L1_CONSECUTIVE_CLOSES=4
STOP_LOSS_L2_CONSECUTIVE_CLOSES=2

# 시간 컨펌 윈도우
STOP_LOSS_L1_ARM_HOLD_SECONDS=3600   # 1시간
STOP_LOSS_L2_ARM_HOLD_SECONDS=1800   # 30분

# 청산 비율
STOP_LOSS_L1_LIQUIDATE_RATIO=0.5     # L1에서 50% 청산

# L2 이후 재시작 잠금
STOP_LOSS_RESTART_LOCKOUT_HOURS=24
```

유효성 검사: L0 < L1 < L2 순서 강제. 임계값이 그리드 폭보다 작으면 시작 시 경고.

---

## 손절 후 봇 상태

| 단계 | 봇 상태 | 재개 조건 |
|---|---|---|
| L0 | 정상 운영 (매수 차단만) | 가격이 L0 임계 위로 회복 시 자동 해제 |
| L1 | 매수 영구 차단, TP 매도는 유지 | 수동 해제 (`reset-stop-loss` CLI) |
| L2 | 봇 종료 + 24시간 재시작 잠금 | 사용자가 새 그리드를 `init-grid --force`로 재구성 |

L2 이후 자동 재진입 금지: 데드캣 바운스 함정 방지.

---

## 알림

- 로그: `logger.error("[STOP_LOSS] ...")` — ERROR 레벨로 CloudWatch/journalctl 연동
- DB: `stop_loss_events` 테이블 신설 권장 (`trigger_at`, `stage`, `lower_price`, `current_price`, `threshold`, `sold_slots`, `total_qty`)
- 외부 알림(옵션): `STOP_LOSS_WEBHOOK_URL` ENV로 Slack/Telegram 연동. 손절 진입/완료/실패 3건 발송. 실패해도 손절 본 흐름 차단하지 않도록 `try/except`

---

## 구현 단계 (PR 분리 권고)

1. `grid.properties` / `settings.py` 파라미터 추가 + `GridPropertySpec` 확장
2. `evaluate_stop_loss()` + 단위 테스트
3. `execute_stop_loss()` + 통합 테스트
4. 정지 모드 영속화 (`GridStateRuntime.stop_loss_active`) + `reset-stop-loss` CLI
5. 외부 알림 옵션 (`app/utils/notifier.py`)
