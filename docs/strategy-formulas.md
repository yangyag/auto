# Strategy Formulas

auto 자동매매 봇의 전략 동작에 쓰이는 수식과 판정 조건을 코드 기준으로 정리

Σ 16 섹션
📐 로그 간격 그리드
📦 KRW · BTC 단위
🐍 app/strategy + app/core

𝓥핵심 변수

P
:   현재 평가 가격

Bi
:   buy\_price (KRW)

Si
:   sell\_price (KRW)

Qi
:   planned\_qty (BTC)

Hi
:   held\_qty (BTC)

📦사용 모듈

전략
:   app/strategy/grid\_strategy.py

그리드
:   app/core/grid.py

설정
:   app/core/grid\_properties.py

가드
:   app/strategy/breakout\_guard.py

엔트리
:   app/main.py

⚖단위 규칙

가격
:   KRW (정수, 호가 단위)

수량
:   BTC, step 0.00000001

주문 금액
:   step 1 KRW

정규화
:   Fnorm(x)

내림
:   Fstep(x, s)

🔧핵심 상수

kbase
:   TP\_K\_BASE

kfloor
:   TP\_K\_FLOOR

pstep
:   GRID\_STEP\_PCT

nbelow
:   ACTIVE\_WINDOW\_BELOW…

nabove
:   ACTIVE\_WINDOW\_ABOVE…

이 문서는 전략 동작에 쓰이는 수식과 판정 조건만 코드 기준으로 정리한다. 수식 안에는 긴 설정 키 문자열을 직접 넣지 않고, 아래 기호 표의 매핑으로 치환한다.

📚 기준 구현

- `app/strategy/grid_strategy.py`
- `app/core/grid.py`
- `app/core/grid_properties.py`
- `app/strategy/breakout_guard.py`
- `app/main.py`

## 기호

수식에 등장하는 모든 기호와 매핑된 설정 키 / 함수다.

| 기호 | 의미 | 설정 키 · 함수 | 단위 / 비고 |
| --- | --- | --- | --- |
| Pprev | 직전 전략 평가 가격 | — | KRW |
| P | 현재 전략 평가 가격 | — | KRW |
| Bi | i번 슬롯의 `buy_price` | — | KRW |
| Si | i번 슬롯의 저장된 `sell_price` | — | KRW |
| Qi | i번 슬롯의 `planned_qty` | — | BTC |
| Hi | i번 슬롯의 `held_qty` | — | BTC |
| L | 그리드 하단 가격 | — | KRW |
| U | 그리드 상단 가격 | — | KRW |
| N | 슬롯 수 | — | 정수 |
| I | 가격 구간 수 | — | 정수, I = N − 1 |
| Fnorm(x) | 업비트 KRW 호가 단위 정규화 | `normalize_price(x)` | KRW → KRW |
| Fstep(x, s) | 지정 step s 단위 내림 | `floor_step(x, s)` | — |
| GN | 그리드 슬롯 수 직접 지정 | `GRID_COUNT` | 정수 |
| pstep | 그리드 간격 (%) | `GRID_STEP_PCT` | % |
| kbase | 기본 TP 배수 | `TP_K_BASE` | — |
| kfloor | 최소 TP 배수 | `TP_K_FLOOR` | — |
| Btotal | 총예산 | `TOTAL_BUDGET_KRW` | KRW |
| nbelow | 현재가 이하 활성 슬롯 수 | `ACTIVE_WINDOW_BELOW_CURRENT_SLOTS` | 정수 |
| nabove | 현재가 위 재진입 활성 슬롯 수 | `ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS` | 정수 |
| Bmaxop | 최대 운영 예산 | `MAX_OPERATING_BUDGET_KRW` | KRW |
| Tstale | 직전 가격 stale 임계 (초) | `STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS` | seconds |
| Amin | 최소 주문 금액 | `MIN_KRW_ORDER_AMOUNT` | KRW |
| fupbit | 업비트 수수료율 | `UPBIT_FEE_RATE` | 비율 |
| Abuffer | 수수료 버퍼 | `FEE_BUFFER_KRW` | KRW |
| Areserve | 잔고 최소 유보 | `MIN_BALANCE_RESERVE` | KRW |
| M | 브레이크아웃 가드 연속 캔들 수 | `BREAKOUT_GUARD_CONSECUTIVE_CANDLES` | 정수 |

## 그리드 슬롯 수

### (1) `GRID_COUNT`를 직접 지정

N = GN

[식 1]

I = N − 1

[식 2]

### (2) `GRID_STEP_PCT`를 지정

Δlog = ln(U / L)

[식 3]

δlog = ln(1 + pstep / 100)

[식 4]

Iraw = Δlogδlog

[식 5]

후보 구간 수:

𝓘cand = { ⌊Iraw⌋, ⌈Iraw⌉ }

[식 6]

각 후보의 오차:

E(j) = | Δlogj − δlog |

[식 7]

𝓘cand 안에서 E(j)가 가장 작은 후보를 I로 선택한다. 오차가 같으면 더 큰 I를 선택한다.

N = I + 1

[식 8]

🔢 워크드 예시 · pstep = 1%, U = 100,000,000, L = 80,000,000

Δlog = ln(100,000,000 / 80,000,000) = ln(1.25) ≈ 0.22314

δlog = ln(1 + 0.01) ≈ 0.00995

Iraw ≈ 0.22314 / 0.00995 ≈ 22.42

𝓘cand = { 22, 23 }

E(22) = | 0.22314 / 22 − 0.00995 | ≈ 0.00019

E(23) = | 0.22314 / 23 − 0.00995 | ≈ 0.00025

→ I = 22, N = 23

## 매수 가격 사다리

상단에서 하단으로 내려가는 로그 간격 사다리다.

ℓ = ln(U / L)N − 1

[식 9]

g = eℓ

[식 10]

B0 = U

[식 11]

Bi = Fnorm( Ugi ),   0 < i < N − 1

[식 12]

BN−1 = L

[식 13]

⚠ 중복 호가 실패

호가 단위 적용 후 Bi가 중복되면 그리드 생성은 실패한다.

유도 메모 — 왜 로그 간격인가

ℓ는 인접한 두 buy 가격 사이의 로그 거리다. Bi+1 / Bi = 1/g = e−ℓ로 일정하므로, 호가가 작은 하단도 같은 비율로 촘촘해진다. 결과적으로 각 슬롯의 매수 후 다음 슬롯까지의 하락폭(%)이 일정해진다.

## 신규 TP 가격

`k` 모델은 고정 퍼센트가 아니라 그리드 로그 간격을 k배 적용하는 모델이다.

keff = kbase

[식 14]

Siraw = Bi · eℓ · keff

[식 15]

Si = Fnorm(Siraw)

[식 16]

#### 검증 조건

Si > Bi

[식 17]

kbase ≥ kfloor > 0

[식 18]

## 예산 가중치

슬롯 인덱스는 상단이 0, 하단이 N − 1이다.

bi = min( ⌊ 3iN − 1 ⌋, 2 )

[식 19]

wi =
0.7bi = 0
1.0bi = 1
1.3bi = 2

[식 20]

W = Σi=0N−1 wi

[식 21]

슬롯별 예산 배분:

Bslot, i = Btotal · wiW

[식 22]

Qi = Fstep( Bslot, iBi, 0.00000001 BTC )

[식 23]

🔢 워크드 예시 · N = 10

bi = min(⌊3i/9⌋, 2) → 인덱스 0..9에 대해: 0, 0, 0, 1, 1, 1, 2, 2, 2, 2

가중치: 상위 3슬롯 0.7, 중간 3슬롯 1.0, 하위 4슬롯 1.3

W = 3 × 0.7 + 3 × 1.0 + 4 × 1.3 = 2.1 + 3.0 + 5.2 = 10.3

하단(i = 9)의 슬롯 예산 비율 = 1.3 / 10.3 ≈ 12.6% — 더 싼 가격대에 더 많은 KRW를 배정.

## 현재 재고 원가와 총 배정 금액

현재 보유 재고 원가:

Cinventory = Σi ∈ ℋ Bi Hi

[식 24]

총 배정 금액:

Ballocated = Σi ∈ ℋ Bi Hi + Σi ∈ ℰ Bi Qi

[식 25]

여기서 ℋ는 holding 슬롯 집합, ℰ는 empty 슬롯 집합이다.

## 매수 교차 조건

하락 매수 후보:

Pprev > Bi ≥ P

[식 26]

#### 추가 조건

- 슬롯 i가 empty 상태다.
- 슬롯 i에 pending 주문이 없다.
- 슬롯 i가 active buy window 안에 있다.
- inventory target gate를 통과한다.
- breakout guard가 비활성이다.

⚠ 첫 스냅샷 처리

첫 가격 스냅샷에서는 Pprev 기준선만 저장하고 신규 매수를 만들지 않는다.

## 상승 재진입 조건

상승 매수 후보:

P > Pprev

[식 27]

Pprev < Bi ≤ P

[식 28]

#### 추가 조건

- `UPWARD_BUY_ENABLED`가 true다.
- 전체 그리드 기준 burst guard: active/pending 필터 적용 전, 전체 그리드에서 교차하는 empty 슬롯이 **정확히 1개**다.
- 슬롯 i에 pending 주문이 없다.
- 슬롯 i가 active buy window 안에 있다.
- inventory target gate를 통과한다.
- breakout guard가 비활성이다.

시장가 예산매수 금액:

Aspend = Fstep( Bi Qi, 1 KRW )

[식 29]

사전 검증은 `app/main.py`의 `check_risk`가 `MIN_KRW_ORDER_AMOUNT`로 흡수한다 (`app/core/models.py`의 `Order.required_krw`가 시장가 매수 시 `spend_amount` 반환).

## 활성 매수 윈도우

기준 가격은 Pprev다.

𝓑≤ = { i ∈ ℰ : Bi ≤ Pprev }

[식 30]

𝓑> = { i ∈ ℰ : Bi > Pprev }

[식 31]

#### 정렬 기준

- 𝓑≤: Bi 내림차순, `slot_index` 오름차순
- 𝓑>: Bi 오름차순, `slot_index` 오름차순

활성 슬롯 집합:

𝓐 = firstn≤(𝓑≤) ∪ firstn>(𝓑>)

[식 32]

여기서:

n≤ = nbelow

[식 33]

n> = nabove

[식 34]

📌 윈도우 비활성

활성 윈도우가 꺼져 있으면 모든 empty 슬롯을 활성 후보로 본다.

## Inventory Target Gate

운영 예산 분모:

Bop =
BmaxopBmaxop > 0
BallocatedBmaxop ≤ 0

[식 35]

현재 재고 비율은 같은 평가 사이클에서 이미 승인된 매수 후보까지 반영한 projected inventory 기준이다.

qcurrent = CprojectedBop

[식 36]

로그 밴드 위치:

zraw = ln(P) − ln(L)ln(U) − ln(L)

[식 37]

z = clamp(zraw, 0, 1)

[식 38]

목표 재고 비율:

qtarget(z) = qmin + (qmax − qmin)(1 − z)γ

[식 39]

qtarget(z) = clamp(qtarget(z), qmin, qmax)

[식 40]

통과 조건:

θ = max(qtarget(z) − ε, 0)

[식 41]

gpass = ( qcurrent < θ )

[식 42]

해석 메모 — z 와 qtarget의 관계

z는 로그 가격대 안에서 현재가의 위치다. z = 0 은 하단(L), z = 1 은 상단(U).

(1 − z)γ 항이 있으므로 가격이 낮을수록 qtarget은 qmax에 가까워지고, 높을수록 qmin에 가까워진다. → "쌀 때 더 많이 들고, 비쌀 때 줄여라."

## Stale Previous Price Guard

직전 평가 이후 경과 시간이 임계값을 초과하면 그 cycle의 신규 매수 평가는 스킵한다.

telapsed = tmonotonicNow − tpreviousPrice

[식 43]

sskip = ( telapsed > Tstale )

[식 44]

이 경우:

Pprev ← P

[식 45]

tpreviousPrice ← tmonotonicNow

[식 46]

✅ SELL 평가

SELL 평가는 계속 수행한다.

## 매도 조건

보유 슬롯의 매도 후보:

P ≥ Sieff

[식 47]

TP 주문 생성 최소 금액 조건:

Sieff Hi ≥ Amin

[식 48]

## Age TP 압축

보유 시간:

a = tnowUtc − tfilledUtc

[식 49]

`k` 압축량:

d(a) =
1.0a ≥ 7 days
0.548 hours ≤ a < 7 days
0.0a < 48 hours

[식 50]

유효 k:

keff = max( kbase − d(a), kfloor )

[식 51]

압축 매도 가격:

gbase = ln( Si / Bi )

[식 52]

gcompressed = gbase · keffkbase

[식 53]

Si = Fnorm( Bi · egcompressed )

[식 54]

최종 매도 가격:

Sieff =
SiBi < Si < Si
Siotherwise

[식 55]

🔢 워크드 예시 · kbase = 2.0, kfloor = 1.0, a = 72h

a = 72h → 48h ≤ a < 7d 이므로 d(a) = 0.5

keff = max(2.0 − 0.5, 1.0) = 1.5

예: Bi = 90,000,000, Si = 91,800,000

gbase = ln(91,800,000 / 90,000,000) ≈ 0.01980

gcompressed = 0.01980 × (1.5 / 2.0) ≈ 0.01485

e0.01485 ≈ 1.01497 → 압축 매도가 ≈ 91,347,300 (정규화 전)

Bi < 압축가 < Si 이므로 Sieff = 압축 매도가

⚠ 적용 조건

Age TP는 `k` 모델로 생성된 그리드이고 holding 슬롯에 `filled_at`이 있을 때만 적용된다.

## 브레이크아웃 가드

최근 완료 캔들 종가 Cj를 최신순으로 M개 본다.

상단 이탈:

oupper = ⋀j=1M ( Cj > U )

[식 56]

하단 이탈:

olower = ⋀j=1M ( Cj < L )

[식 57]

가드 활성:

bguard = oupper ∨ olower

[식 58]

🚫 가드 활성화 시

가드가 활성화되면 신규 BUY 후보는 제거하고 SELL 후보는 유지한다.

📌 입력 실패 처리

캔들 조회 실패, 캔들 부족, invalid band 같은 입력 실패는 `app/main.py`의 failure policy에서 fail-open / fail-close로 처리한다.

## 매수 필요 KRW 추정

BUY 주문 원금:

#### 시장가 예산매수

Arequired = Aspend

[식 59]

#### 지정가 BUY

Arequired = Porder Qorder

[식 60]

수수료와 버퍼를 포함한 필요 금액:

Aestimated = Arequired(1 + fupbit) + Abuffer

[식 61]

잔고 통과 조건:

Aavailable ≥ Aestimated + Areserve

[식 62]

📌 사이클 내 누적 차감

같은 cycle에서 여러 BUY를 검사할 때는 통과한 주문의 Aestimated를 가용 잔고에서 선반영 차감한다.

🔢 워크드 예시 · 지정가 BUY 100,000 KRW

Arequired = 100,000 KRW

fupbit = 0.0005, Abuffer = 100 KRW

Aestimated = 100,000 × 1.0005 + 100 = 100,150 KRW

Areserve = 10,000 KRW 라면 가용 잔고는 ≥ 110,150 KRW 이어야 통과.

## 라이브 예산 조정

`scripts/adjust_budget_live.py --target-budget X`는 기존 ladder와 보유 수량을 유지하고 Qi만 다시 계산한다.

Btotal ← X

[식 63]

슬롯별 예산 재배분:

Bslot, i = Btotal · wiW

[식 64]

Qinew = Fstep( Bslot, iBi, 0.00000001 BTC )

[식 65]

✅ 유지되는 값

보유 슬롯의 Hi, Si, `filled_at`은 유지한다.
