# Strategy Formulas

[auto](file:///C:/dev/mobileAuto/auto) 자동매매 봇의 전략 동작에 사용되는 수식과 판정 조건을 실제 파이썬 코드 구현을 기준으로 정리한 기술 문서입니다.

---

## 📌 전략 인프라 요약

### 📐 핵심 전략 모듈
- **전략 평가 엔진**: [grid_strategy.py](file:///C:/dev/mobileAuto/auto/app/strategy/grid_strategy.py)
- **그리드 구조 연산**: [grid.py](file:///C:/dev/mobileAuto/auto/app/core/grid.py)
- **그리드 속성 파싱**: [grid_properties.py](file:///C:/dev/mobileAuto/auto/app/core/grid_properties.py)
- **이탈 가드 (Breakout Guard)**: [breakout_guard.py](file:///C:/dev/mobileAuto/auto/app/strategy/breakout_guard.py)
- **전체 제어 진입점**: [main.py](file:///C:/dev/mobileAuto/auto/app/main.py)

### ⚖ 수량 및 가격 단위 규칙
- **가격 (Price)**: KRW 기준 (정수, 업비트 호가 단위 정규화 반영)
- **수량 (Quantity)**: BTC 단위 (최소 소수점 8자리, Step `0.00000001` 지정)
- **주문 금액**: 최소 원화 1원 단위
- **호가 단위 정규화**: $F_{norm}(x)$ (업비트 가격 규칙에 맞춤)
- **소수점 단위 내림**: $F_{step}(x, s)$ (지정 단위 $s$ 기준 내림 연산)

---

## 기호 설명 및 환경변수 매핑

수식에 등장하는 변수 및 봇 설정 변수의 매핑 인덱스 테이블입니다.

| 기호 | 용도 및 의미 | 매핑된 설정 변수 / 함수 | 단위 및 비고 |
| :--- | :--- | :--- | :---: |
| $P$ | 현재 전략 평가 주기 시세 | — | KRW |
| $P\_{prev}$ | 직전 평가 주기 시세 | — | KRW |
| $B\_i$ | $i$번 그리드 슬롯의 매수 기준가 | `buy_price` | KRW |
| $S\_i$ | $i$번 그리드 슬롯의 매도 기준가 | `sell_price` | KRW |
| $S\_i^{eff}$ | 이익 실현(TP)이 적용된 최종 매도가 | `effective_sell_price` | KRW |
| $Q\_i$ | $i$번 슬롯의 목표 매수량 | `planned_qty` | BTC |
| $H\_i$ | $i$번 슬롯의 체결 재고량 | `held_qty` | BTC |
| $L$ | 그리드 최하단 한계 가격 | `MIN_BUY_PRICE` | KRW |
| $U$ | 그리드 최상단 한계 가격 | `MAX_BUY_PRICE` | KRW |
| $N$ | 그리드 슬롯 총 개수 | `GRID_COUNT` | 정수 |
| $I$ | 그리드 가격 구간 개수 | $I = N - 1$ | 정수 |
| $p\_{step}$ | 슬롯 간의 고정 간격 비율 (%) | `GRID_STEP_PCT` | % |
| $k\_{base}$ | 기준 이익 실현(TP) 배수 | `TP_K_BASE` | 실수 (가중치) |
| $k\_{floor}$ | 최하단 이익 실현(TP) 제한 배수 | `TP_K_FLOOR` | 실수 (가중치) |
| $B\_{total}$ | 봇 구동 가용 총예산 | `TOTAL_BUDGET_KRW` | KRW |
| $B\_{maxop}$ | 최대 가용 예산 제한값 | `MAX_OPERATING_BUDGET_KRW` | KRW |
| $n\_{below}$ | 현재가 이하 활성화할 슬롯 수 | `ACTIVE_WINDOW_BELOW_CURRENT_SLOTS` | 정수 |
| $n\_{above}$ | 현재가 위 활성화할 재진입 슬롯 수 | `ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS` | 정수 |
| $T\_{stale}$ | 직전 시세 갱신 지연 감지 임계점 | `STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS` | 초 (Seconds) |
| $A\_{min}$ | 업비트 최소 주문 가능 금액 | `MIN_KRW_ORDER_AMOUNT` | KRW (기본 5,000) |
| $f\_{upbit}$ | 업비트 거래 수수료율 | `UPBIT_FEE_RATE` | 비율 (기본 0.0005) |
| $A\_{buffer}$ | 주문 예비 수수료 버퍼 | `FEE_BUFFER_KRW` | KRW |
| $A\_{reserve}$ | 계정 최소 안전 유보금 | `MIN_BALANCE_RESERVE` | KRW |
| $M$ | 브레이크아웃 가드 분석 캔들 개수 | `BREAKOUT_GUARD_CONSECUTIVE_CANDLES` | 정수 |

---

## 1. 그리드 슬롯 수 연산

그리드의 가격 계단 개수($N$)를 결정하는 방식은 두 가지가 있습니다.

### (1) `GRID_COUNT` 값을 직접 고정 주입하는 경우

$$N = G\_N \tag{식 1}$$

$$I = N - 1 \tag{식 2}$$

### (2) `GRID_STEP_PCT` (슬롯 간격 비율)를 지정하는 경우
그리드 범위 내의 총 로그 변동률과 지정 간격의 로그 변동률을 비교하여 최적의 정수 구간 수 $I$를 산출합니다.

$$\Delta\_{log} = \ln\left(\frac{U}{L}\right) \tag{식 3}$$

$$\delta\_{log} = \ln\left(1 + \frac{p\_{step}}{100}\right) \tag{식 4}$$

$$I\_{raw} = \frac{\Delta\_{log}}{\delta\_{log}} \tag{식 5}$$

구간 수는 정수여야 하므로 올림과 내림을 후보군으로 잡습니다:

$$\mathcal{I}\_{cand} = \{ \lfloor I\_{raw} \rfloor, \lceil I\_{raw} \rceil \} \tag{식 6}$$

각 정수 후보 $j \in \mathcal{I}\_{cand}$에 대해 실제 계산되는 격자 간격과 목표 간격 간의 절대 오차 $E(j)$를 구합니다:

$$E(j) = \left| \frac{\Delta\_{log}}{j} - \delta\_{log} \right| \tag{식 7}$$

오차 $E(j)$를 최소화하는 정수를 최종 구간 수 $I$로 채택하며, 오차가 같을 경우 안전마진 확보를 위해 더 큰 값을 선택합니다. 슬롯 수 $N$은 다음과 같습니다:

$$N = I + 1 \tag{식 8}$$

---

## 2. 매수 가격 사다리 구성

상단 경계($U$)에서 하단 경계($L$)로 내려가는 로그 간격 사다리를 생성합니다.

$$\ell = \frac{\ln(U / L)}{N - 1} \tag{식 9}$$

$$g = e^\ell \tag{식 10}$$

$$B\_0 = U \tag{식 11}$$

$$B\_i = F\_{norm}\left( \frac{U}{g^i} \right), \quad 0 < i < N - 1 \tag{식 12}$$

$$B\_{N-1} = L \tag{식 13}$$

> [!WARNING]
> **중복 호가 생성 예방**: 
> 업비트 호가 정규화 함수 $F_{norm}$을 거친 후, 인접한 슬롯 가격 $B\_i$와 $B\_{i+1}$이 동일한 가격으로 수렴(중복)하면 그리드 생성 스크립트는 안전을 위해 실패 처리됩니다.

---

## 3. 이익 실현 (Take-Profit) 매도 가격 결정

`k` 모델은 단순 고정 비율이 아닌, 그리드 슬롯 간의 로그 거리인 $\ell$을 바탕으로 하여 $k$배수 영역에 매도를 등록합니다.

$$k\_{eff} = k\_{base} \tag{식 14}$$

$$S\_{i, raw} = B\_i \cdot e^{\ell \cdot k\_{eff}} \tag{식 15}$$

$$S\_i = F\_{norm}(S\_{i, raw}) \tag{식 16}$$

정상 등록 검증 조건:

$$S\_i > B\_i \tag{식 17}$$

$$k\_{base} \ge k\_{floor} > 0 \tag{식 18}$$

---

## 4. 슬롯별 예산 가중치 배분

하단으로 내려갈수록 더 큰 예산을 투입하는 **하단 가중 분배 방식**을 적용합니다. 슬롯 인덱스 $i$는 상단이 $0$, 최하단이 $N-1$입니다.

$$b\_i = \min\left( \left\lfloor \frac{3i}{N-1} \right\rfloor, 2 \right) \tag{식 19}$$

각 구간 변수 $b\_i$에 따른 매칭 가중치 $w\_i$:

$$w\_i = \begin{cases} 0.7 & \text{if } b\_i = 0 \quad (\text{상단 } 1/3) \\\\ 1.0 & \text{if } b_i = 1 \quad (\text{중단 } 1/3) \\\\ 1.3 & \text{if } b_i = 2 \quad (\text{하단 } 1/3) \end{cases} \tag{식 20}$$

전체 그리드 가중치 합산 $W$:

$$W = \sum\_{i=0}^{N-1} w\_i \tag{식 21}$$

슬롯별 할당 예산 $B\_{slot, i}$ 및 목표 매수량 $Q\_i$:

$$B\_{slot, i} = B\_{total} \cdot \frac{w\_i}{W} \tag{식 22}$$

$$Q\_i = F\_{step}\left( \frac{B\_{slot, i}}{B\_i}, 0.00000001 \text{ BTC} \right) \tag{식 23}$$

---

## 5. 현재 보유 재고 및 가용 자산 연산

현재 가동 중인 봇의 재고 원가($C\_{inventory}$)와 총 할당 예산($B\_{allocated}$):

$$C\_{inventory} = \sum\_{i \in \mathcal{H}} B\_i H\_i \tag{식 24}$$

$$B\_{allocated} = \sum\_{i \in \mathcal{H}} B\_i H\_i + \sum\_{i \in \mathcal{E}} B\_i Q\_i \tag{식 25}$$

- $\mathcal{H}$: 코인을 보유 중인 활성 슬롯 집합 (Holding)
- $\mathcal{E}$: 코인을 들고 있지 않은 빈 슬롯 집합 (Empty)

---

## 6. 매수 판정 조건

### 6-1. 하락 매수 조건 (기본)
최근 시세 흐름이 가격 장벽을 하향 돌파할 때 매수합니다.

$$P\_{prev} > B\_i \ge P \tag{식 26}$$

**추가 통과 조건**:
1. 슬롯 $i$가 비어 있어야 함 ($i \in \mathcal{E}$)
2. 슬롯 $i$에 거래소 pending(미체결) 주문이 없어야 함
3. 슬롯 $i$가 활성 매수 윈도우($\mathcal{A}$) 내에 포함되어야 함
4. **Inventory Target Gate** 자산 통제 조건을 통과해야 함
5. **Breakout Guard** 이탈 방지가 작동하지 않아야 함

### 6-2. 상승 재진입 매수 조건
상승 돌파 시 추격 매수하는 로직입니다.

$$P > P\_{prev} \tag{식 27}$$

$$P\_{prev} < B\_i \le P \tag{식 28}$$

**추가 통과 조건**:
1. `UPWARD_BUY_ENABLED = true` 설정 상태여야 함
2. **Burst Guard** (동시 다발 체결 가드): 전략 주기 내에 감지된 상승 교차 슬롯이 **오직 1개**여야 함 (급등 시 동시 다수 슬롯 매수 진입 방지)
3. 지정가 매수가 아닌 시장가 예산 집행 주문으로 발주:

$$A\_{spend} = F\_{step}(B\_i Q\_i, 1 \text{ KRW}) \tag{식 29}$$

---

## 7. 활성 매수 윈도우 (Active Window)

현재가 주변 슬롯만 주문 가능 상태로 제한하여 예산 쏠림 및 미체결 잠김을 예방하는 윈도우 규칙입니다.

기준점은 직전 주기 가격인 $P\_{prev}$입니다.

$$\mathcal{B}\_{\le} = \{ i \in \mathcal{E} : B\_i \le P\_{prev} \} \quad (\text{하위 가격 빈 슬롯}) \tag{식 30}$$

$$\mathcal{B}\_{>} = \{ i \in \mathcal{E} : B\_i > P\_{prev} \} \quad (\text{상위 가격 빈 슬롯}) \tag{식 31}$$

- 정렬 기준:
  - $\mathcal{B}\_{\le}$: 가격 내림차순 (인덱스 오름차순)
  - $\mathcal{B}\_{>}$: 가격 오름차순 (인덱스 오름차순)

최종 가동할 슬롯 집합 $\mathcal{A}$는 다음과 같이 부분 슬롯 수 $n\_{\le}$ 및 $n\_{>}$ 개수만큼만 절단하여 활성화합니다:

$$\mathcal{A} = firstn\_{\le}(\mathcal{B}\_{\le}) \cup firstn\_{>}(\mathcal{B}\_{>}) \tag{식 32}$$

$$n\_{\le} = n\_{below} \tag{식 33}$$

$$n\_{>} = n\_{above} \tag{식 34}$$

---

## 8. Inventory Target Gate (재고 통제 조건)

시세의 밴드상 위치에 따라 안전 재고 비율을 차등 부여하는 알고리즘입니다.

최대 운영 예산 기준 분모 $B\_{op}$:

$$B\_{op} = \begin{cases} B\_{maxop} & \text{if } B\_{maxop} > 0 \\\\ B\_{allocated} & \text{if } B\_{maxop} \le 0 \end{cases} \tag{식 35}$$

현재 가격 사이클에서의 누적 가상 재고 비율 $q\_{current}$:

$$q\_{current} = \frac{C\_{projected}}{B\_{op}} \tag{식 36}$$

현재 가격의 밴드 내 로그 위치 비율 $z$:

$$z\_{raw} = \frac{\ln(P) - \ln(L)}{\ln(U) - \ln(L)} \tag{식 37}$$

$$z = clamp(z\_{raw}, 0, 1) \tag{식 38}$$

실시간 목표 재고 비중 한도 $q\_{target}(z)$:

$$q\_{target}(z) = q\_{min} + (q\_{max} - q\_{min})(1 - z)^\gamma \tag{식 39}$$

$$q\_{target}(z) = clamp(q\_{target}(z), q\_{min}, q\_{max}) \tag{식 40}$$

최종 매수 통과 조건:

$$\theta = \max(q\_{target}(z) - \epsilon, 0) \tag{식 41}$$

$$g\_{pass} = (q\_{current} < \theta) \tag{식 42}$$

> [!NOTE]
> **전략적 핵심 개념**:
> 식 39에서 $(1-z)^\gamma$ 연산 구조에 의해, 시세 위치 $z$가 $0$(하단)에 가까울수록 목표 재고량 한도는 $q_{max}$로 상향되고, $1$(상단)에 가까울수록 $q_{min}$으로 차단됩니다. 즉, **"가격이 내려갈수록 최대한 사고, 올라갈수록 신규 진입을 억제하여 위험을 낮추는"** 안전망 역할을 수행합니다.

---

## 9. Stale Previous Price Guard (시세 지연 보호)

네트워크 지연 등으로 인해 시세 데이터 업데이트가 임계 시간($T\_{stale}$)을 초과한 경우, 오작동 방지를 위해 신규 매수 판단을 한 주기 보류합니다.

$$t\_{elapsed} = t\_{monotonicNow} - t\_{previousPrice} \tag{식 43}$$

$$s\_{skip} = (t\_{elapsed} > T\_{stale}) \tag{식 44}$$

만약 시세가 지연되었을 경우, 다음 연산 주기를 위해 직전 가격과 시간을 즉시 현 시점으로 초기화합니다:

$$P\_{prev} \leftarrow P \tag{식 45}$$

$$t\_{previousPrice} \leftarrow t\_{monotonicNow} \tag{식 46}$$

---

## 10. 이익 실현 (Take-Profit) 연령 압축 (Age TP)

체결 재고의 보유 시간($a$)이 길어질 경우 자금 고착을 막기 위해 목표 매도가를 하향 압축하여 탈출을 돕습니다.

보유 시간 연산 (현재시각 - 체결 완료 시각):

$$a = t\_{nowUtc} - t\_{filledUtc} \tag{식 49}$$

보유 연령에 따른 $k$ 감쇄 변량 $d(a)$:

$$d(a) = \begin{cases} 1.0 & \text{if } a \ge 7 \text{ days} \\\\ 0.5 & \text{if } 48 \text{ hours} \le a < 7 \text{ days} \\\\ 0.0 & \text{if } a < 48 \text{ hours} \end{cases} \tag{식 50}$$

감쇄가 반영된 유효 배수 $k\_{eff}$:

$$k\_{eff} = \max(k\_{base} - d(a), k\_{floor}) \tag{식 51}$$

압축 매도 가격 산출:

$$g\_{base} = \ln\left(\frac{S\_i}{B\_i}\right) \tag{식 52}$$

$$g\_{compressed} = g\_{base} \cdot \frac{k\_{eff}}{k\_{base}} \tag{식 53}$$

$$S\_i' = F\_{norm}(B\_i \cdot e^{g\_{compressed}}) \tag{식 54}$$

최종 적용할 매도 호가 $S\_i^{eff}$:

$$S\_i^{eff} = \begin{cases} S\_i' & \text{if } B\_i < S\_i' < S\_i \\\\ S\_i & \text{otherwise} \end{cases} \tag{식 55}$$

---

## 11. Breakout Guard (추세 이탈 감지)

직전 완성된 $M$개의 분봉 캔들의 종가($C\_j$)를 분석하여 급변침 상황 시 진입을 일시적으로 차단합니다.

- **상단 이탈**: $M$개 연속 캔들이 그리드 상단 $U$ 위에서 마감

$$o\_{upper} = \bigwedge\_{j=1}^M (C\_j > U) \tag{식 56}$$

- **하단 이탈**: $M$개 연속 캔들이 그리드 하단 $L$ 아래에서 마감

$$o\_{lower} = \bigwedge\_{j=1}^M (C\_j < L) \tag{식 57}$$

가드 작동 판정:

$$b\_{guard} = o\_{upper} \lor o\_{lower} \tag{식 58}$$

> [!WARNING]
> 가드가 활성화($b_{guard} = true$)되면 **신규 매수(BUY) 주문 제출은 전면 차단**되며, 이미 진입해 있는 재고의 청산(SELL)은 정상 유지됩니다.

---

## 12. 매수 주문 필요 예산 정밀 산출

주문 체결에 필요한 실 가용 원화 잔고 평가식입니다.

- **시장가 매수 시 필요 원금**:

$$A\_{required} = A\_{spend} \tag{식 59}$$

- **지정가 매수 시 필요 원금**:

$$A\_{required} = P\_{order} Q\_{order} \tag{식 60}$$

수수료 및 안전 버퍼를 감안한 예상 투입 금액 $A\_{estimated}$:

$$A\_{estimated} = A\_{required}(1 + f\_{upbit}) + A\_{buffer} \tag{식 61}$$

최종 잔고 가용성 조건 검증:

$$A\_{available} \ge A\_{estimated} + A\_{reserve} \tag{식 62}$$

---

## 13. 라이브 가동 예산 조정 공식

운영 중 예산 개편 명령 발생 시 호출되는 로직입니다. 보유 수량($H_i$)은 고정하고, 빈 슬롯의 목표량($Q\_{i, new}$)만 재산출합니다.

$$B\_{total} \leftarrow X \quad (\text{조정 예산 주입}) \tag{식 63}$$

$$B\_{slot, i} = B\_{total} \cdot \frac{w\_i}{W} \tag{식 64}$$

$$Q\_{i, new} = F\_{step}\left( \frac{B\_{slot, i}}{B\_i}, 0.00000001 \text{ BTC} \right) \tag{식 65}$$
