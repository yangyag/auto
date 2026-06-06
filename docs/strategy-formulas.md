# Strategy Formulas

[auto](..) 자동매매 봇의 전략 동작에 사용되는 수식과 판정 조건을 실제 파이썬 코드 구현을 기준으로 정리한 기술 문서입니다.

---

## 📌 전략 인프라 요약

### 📐 핵심 전략 모듈
- **전략 평가 엔진**: [grid_strategy.py](../app/strategy/grid_strategy.py)
- **그리드 구조 연산**: [grid.py](../app/core/grid.py)
- **그리드 속성 파싱**: [grid_properties.py](../app/core/grid_properties.py)
- **이탈 가드 (Breakout Guard)**: [breakout_guard.py](../app/strategy/breakout_guard.py)
- **전체 제어 진입점**: [main.py](../app/main.py)

### ⚖ 수량 및 가격 단위 규칙
- **가격 (Price)**: KRW 기준 (정수, 업비트 호가 단위 정규화 반영)
- **수량 (Quantity)**: 기초자산(base asset) 단위 — `cfg.SYMBOL` 기준 (예: `KRW-USDT`이면 USDT). 최소 소수점 8자리, Step `0.00000001` 지정
  - Step `0.00000001`은 마켓에 무관한 공통 수량 step이다 ([decimal_utils.py](../app/utils/decimal_utils.py)의 `BTC_QUANTITY_STEP` — 이름만 BTC일 뿐 모든 마켓에 동일 적용)
- **주문 금액**: 최소 원화 1원 단위
- **호가 단위 정규화**: $F_{norm}(x)$ (업비트 가격 규칙에 맞춤)
- **소수점 단위 내림**: $F_{step}(x, s)$ (지정 단위 $s$ 기준 내림 연산)

---

## 기호 설명 및 환경변수 매핑

수식에 등장하는 변수 및 봇 설정 변수의 매핑 인덱스 테이블입니다.

| 기호 | 용도 및 의미 | 매핑된 설정 변수 / 함수 | 단위 및 비고 |
| :--- | :--- | :--- | :---: |
| $P$ | 현재 전략 평가 주기 시세 | — | KRW |
| $P_{prev}$ | 직전 평가 주기 시세 | — | KRW |
| $B_i$ | $i$번 그리드 슬롯의 매수 기준가 | `buy_price` | KRW |
| $S_i$ | $i$번 그리드 슬롯의 매도 기준가 | `sell_price` | KRW |
| $S_i^{eff}$ | 이익 실현(TP)이 적용된 최종 매도가 | `effective_sell_price` | KRW |
| $Q_i$ | $i$번 슬롯의 목표 매수량 | `planned_qty` | 기초자산 (cfg.SYMBOL, 예: USDT) |
| $H_i$ | $i$번 슬롯의 체결 재고량 | `held_qty` | 기초자산 (cfg.SYMBOL, 예: USDT) |
| $L$ | 그리드 최하단 한계 가격 | `MIN_BUY_PRICE` | KRW |
| $U$ | 그리드 최상단 한계 가격 | `MAX_BUY_PRICE` | KRW |
| $N$ | 그리드 슬롯 총 개수 | `GRID_COUNT` | 정수 |
| $I$ | 그리드 가격 구간 개수 | $I = N - 1$ | 정수 |
| $p_{step}$ | 슬롯 간의 고정 간격 비율 (%) | `GRID_STEP_PCT` | % |
| $k_{base}$ | 기준 이익 실현(TP) 배수 | `TP_K_BASE` | 실수 (가중치) |
| $k_{floor}$ | 최하단 이익 실현(TP) 제한 배수 | `TP_K_FLOOR` | 실수 (가중치) |
| $B_{total}$ | 봇 구동 가용 총예산 | `TOTAL_BUDGET_KRW` | KRW |
| $B_{maxop}$ | 최대 가용 예산 제한값 | `MAX_OPERATING_BUDGET_KRW` | KRW |
| $n_{below}$ | 현재가 이하 활성화할 슬롯 수 | `ACTIVE_WINDOW_BELOW_CURRENT_SLOTS` | 정수 |
| $n_{above}$ | 현재가 위 활성화할 재진입 슬롯 수 | `ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS` | 정수 |
| $T_{stale}$ | 직전 시세 갱신 지연 감지 임계점 | `STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS` | 초 (Seconds) |
| $A_{min}$ | 업비트 최소 주문 가능 금액 | `MIN_KRW_ORDER_AMOUNT` | KRW (기본 5,000) |
| $f_{upbit}$ | 업비트 거래 수수료율 | `UPBIT_FEE_RATE` | 비율 (기본 0.0005) |
| $A_{buffer}$ | 주문 예비 수수료 버퍼 | `FEE_BUFFER_KRW` | KRW |
| $A_{reserve}$ | 계정 최소 안전 유보금 | `MIN_BALANCE_RESERVE` | KRW |
| $M$ | 브레이크아웃 가드 분석 캔들 개수 | `BREAKOUT_GUARD_CONSECUTIVE_CANDLES` | 정수 |
| $q_{min}$ | 목표 재고 비중 하한 | `INVENTORY_TARGET_Q_MIN` | 비율 (기본 0.10) |
| $q_{max}$ | 목표 재고 비중 상한 | `INVENTORY_TARGET_Q_MAX` | 비율 (기본 0.85) |
| $\gamma$ | 목표 재고 곡선 감쇄 지수 | `INVENTORY_TARGET_GAMMA` | 실수 (기본 1.5) |
| $\epsilon$ | 목표 재고 통과 임계 여유분 | `INVENTORY_TARGET_EPSILON` | 비율 (기본 0.03) |

---

## 1. 그리드 슬롯 수 연산

그리드의 가격 계단 개수($N$)를 결정하는 방식은 두 가지가 있습니다.

### (1) `GRID_COUNT` 값을 직접 고정 주입하는 경우

$$N = G_N \tag{식 1}$$

$$I = N - 1 \tag{식 2}$$

### (2) `GRID_STEP_PCT` (슬롯 간격 비율)를 지정하는 경우
그리드 범위 내의 총 로그 변동률과 지정 간격의 로그 변동률을 비교하여 최적의 정수 구간 수 $I$를 산출합니다.

$$\Delta_{log} = \ln\left(\frac{U}{L}\right) \tag{식 3}$$

$$\delta_{log} = \ln\left(1 + \frac{p_{step}}{100}\right) \tag{식 4}$$

$$I_{raw} = \frac{\Delta_{log}}{\delta_{log}} \tag{식 5}$$

구간 수는 정수여야 하므로 올림과 내림을 후보군으로 잡습니다:

$$\mathcal{I}_{cand} = \{ \lfloor I_{raw} \rfloor, \lceil I_{raw} \rceil \} \tag{식 6}$$

각 정수 후보 $j \in \mathcal{I}_{cand}$에 대해 실제 계산되는 격자 간격과 목표 간격 간의 절대 오차 $E(j)$를 구합니다:

$$E(j) = \left| \frac{\Delta_{log}}{j} - \delta_{log} \right| \tag{식 7}$$

오차 $E(j)$를 최소화하는 정수를 최종 구간 수 $I$로 채택하며, 오차가 같을 경우 안전마진 확보를 위해 더 큰 값을 선택합니다. 슬롯 수 $N$은 다음과 같습니다:

$$N = I + 1 \tag{식 8}$$

---

## 2. 매수 가격 사다리 구성

상단 경계($U$)에서 하단 경계($L$)로 내려가는 로그 간격 사다리를 생성합니다.

$$\ell = \frac{\ln(U / L)}{N - 1} \tag{식 9}$$

$$g = e^\ell \tag{식 10}$$

$$B_0 = U \tag{식 11}$$

$$B_i = F_{norm}\left( \frac{U}{g^i} \right), \quad 0 < i < N - 1 \tag{식 12}$$

$$B_{N-1} = L \tag{식 13}$$

> [!WARNING]
> **중복 호가 생성 예방**: 
> 업비트 호가 정규화 함수 $F_{norm}$을 거친 후, 인접한 슬롯 가격 $B_i$와 $B_{i+1}$이 동일한 가격으로 수렴(중복)하면 그리드 생성 스크립트는 안전을 위해 실패 처리됩니다.

---

## 3. 이익 실현 (Take-Profit) 매도 가격 결정

`k` 모델은 단순 고정 비율이 아닌, 그리드 슬롯 간의 로그 거리인 $\ell$을 바탕으로 하여 $k$배수 영역에 매도를 등록합니다.

$$k_{eff} = k_{base} \tag{식 14}$$

$$S_{i, raw} = B_i \cdot e^{\ell \cdot k_{eff}} \tag{식 15}$$

$$S_i = F_{norm}(S_{i, raw}) \tag{식 16}$$

정상 등록 검증 조건:

$$S_i > B_i \tag{식 17}$$

$$k_{base} \ge k_{floor} > 0 \tag{식 18}$$

---

## 4. 슬롯별 예산 가중치 배분

하단으로 내려갈수록 더 큰 예산을 투입하는 **하단 가중 분배 방식**을 적용합니다. 슬롯 인덱스 $i$는 상단이 $0$, 최하단이 $N-1$입니다.

$$b_i = \min\left( \left\lfloor \frac{3i}{N-1} \right\rfloor, 2 \right) \tag{식 19}$$

각 구간 변수 $b_i$에 따른 매칭 가중치 $w_i$:

$$w_i = \begin{cases} 0.7 & \text{if } b_i = 0 \quad (\text{상단 } 1/3) \\ 1.0 & \text{if } b_i = 1 \quad (\text{중단 } 1/3) \\ 1.3 & \text{if } b_i = 2 \quad (\text{하단 } 1/3) \end{cases} \tag{식 20}$$

전체 그리드 가중치 합산 $W$:

$$W = \sum_{i=0}^{N-1} w_i \tag{식 21}$$

슬롯별 할당 예산 $B_{slot, i}$ 및 목표 매수량 $Q_i$:

$$B_{slot, i} = B_{total} \cdot \frac{w_i}{W} \tag{식 22}$$

$$Q_i = F_{step}\left( \frac{B_{slot, i}}{B_i}, 0.00000001 \text{ (기초자산 단위, cfg.SYMBOL)} \right) \tag{식 23}$$

---

## 5. 현재 보유 재고 및 가용 자산 연산

현재 가동 중인 봇의 재고 원가($C_{inventory}$)와 총 할당 예산($B_{allocated}$):

$$C_{inventory} = \sum_{i \in \mathcal{H}} B_i H_i \tag{식 24}$$

$$B_{allocated} = \sum_{i \in \mathcal{H}} B_i H_i + \sum_{i \in \mathcal{E}} B_i Q_i \tag{식 25}$$

- $\mathcal{H}$: 코인을 보유 중인 활성 슬롯 집합 (Holding)
- $\mathcal{E}$: 코인을 들고 있지 않은 빈 슬롯 집합 (Empty)

---

## 6. 매수 판정 조건

### 6-1. 하락 매수 조건 (기본)
최근 시세 흐름이 가격 장벽을 하향 돌파할 때 매수합니다.

$$P_{prev} > B_i \ge P \tag{식 26}$$

**추가 통과 조건**:
1. 슬롯 $i$가 비어 있어야 함 ($i \in \mathcal{E}$)
2. 슬롯 $i$에 거래소 pending(미체결) 주문이 없어야 함
3. 슬롯 $i$가 활성 매수 윈도우($\mathcal{A}$) 내에 포함되어야 함
4. **Inventory Target Gate** 자산 통제 조건을 통과해야 함
5. **Breakout Guard** 이탈 방지가 작동하지 않아야 함

### 6-2. 상승 재진입 매수 조건
상승 돌파 시 추격 매수하는 로직입니다.

$$P > P_{prev} \tag{식 27}$$

$$P_{prev} < B_i \le P \tag{식 28}$$

**추가 통과 조건**:
1. `UPWARD_BUY_ENABLED = true` 설정 상태여야 함
2. **Burst Guard** (동시 다발 체결 가드): 전략 주기 내에 감지된 상승 교차 슬롯이 **오직 1개**여야 함 (급등 시 동시 다수 슬롯 매수 진입 방지)
3. 지정가 매수가 아닌 시장가 예산 집행 주문으로 발주:

$$A_{spend} = F_{step}(B_i Q_i, 1 \text{ KRW}) \tag{식 29}$$

---

## 7. 활성 매수 윈도우 (Active Window)

현재가 주변 슬롯만 주문 가능 상태로 제한하여 예산 쏠림 및 미체결 잠김을 예방하는 윈도우 규칙입니다.

기준점은 직전 주기 가격인 $P_{prev}$입니다.

$$\mathcal{B}_{\le} = \{ i \in \mathcal{E} : B_i \le P_{prev} \} \quad (\text{하위 가격 빈 슬롯}) \tag{식 30}$$

$$\mathcal{B}_{>} = \{ i \in \mathcal{E} : B_i > P_{prev} \} \quad (\text{상위 가격 빈 슬롯}) \tag{식 31}$$

- 정렬 기준:
  - $\mathcal{B}_{\le}$: 가격 내림차순 (인덱스 오름차순)
  - $\mathcal{B}_{>}$: 가격 오름차순 (인덱스 오름차순)

최종 가동할 슬롯 집합 $\mathcal{A}$는 다음과 같이 부분 슬롯 수 $n_{\le}$ 및 $n_{>}$ 개수만큼만 절단하여 활성화합니다:

$$\mathcal{A} = firstn_{\le}(\mathcal{B}_{\le}) \cup firstn_{>}(\mathcal{B}_{>}) \tag{식 32}$$

$$n_{\le} = n_{below} \tag{식 33}$$

$$n_{>} = n_{above} \tag{식 34}$$

---

## 8. Inventory Target Gate (재고 통제 조건)

시세의 밴드상 위치에 따라 안전 재고 비율을 차등 부여하는 알고리즘입니다.

최대 운영 예산 기준 분모 $B_{op}$:

$$B_{op} = \begin{cases} B_{maxop} & \text{if } B_{maxop} > 0 \\ B_{allocated} & \text{if } B_{maxop} \le 0 \end{cases} \tag{식 35}$$

현재 가격 사이클에서의 누적 가상 재고 비율 $q_{current}$:

$$q_{current} = \frac{C_{projected}}{B_{op}} \tag{식 36}$$

현재 가격의 밴드 내 로그 위치 비율 $z$:

$$z_{raw} = \frac{\ln(P) - \ln(L)}{\ln(U) - \ln(L)} \tag{식 37}$$

$$z = clamp(z_{raw}, 0, 1) \tag{식 38}$$

실시간 목표 재고 비중 한도 $q_{target}(z)$:

$$q_{target}(z) = q_{min} + (q_{max} - q_{min})(1 - z)^\gamma \tag{식 39}$$

$$q_{target}(z) = clamp(q_{target}(z), q_{min}, q_{max}) \tag{식 40}$$

최종 매수 통과 조건:

$$\theta = \max(q_{target}(z) - \epsilon, 0) \tag{식 41}$$

$$g_{pass} = (q_{current} < \theta) \tag{식 42}$$

> [!NOTE]
> **전략적 핵심 개념**:
> 식 39에서 $(1-z)^\gamma$ 연산 구조에 의해, 시세 위치 $z$가 $0$(하단)에 가까울수록 목표 재고량 한도는 $q_{max}$로 상향되고, $1$(상단)에 가까울수록 $q_{min}$으로 차단됩니다. 즉, **"가격이 내려갈수록 최대한 사고, 올라갈수록 신규 진입을 억제하여 위험을 낮추는"** 안전망 역할을 수행합니다.

---

## 9. Stale Previous Price Guard (시세 지연 보호)

네트워크 지연 등으로 인해 시세 데이터 업데이트가 임계 시간($T_{stale}$)을 초과한 경우, 오작동 방지를 위해 신규 매수 판단을 한 주기 보류합니다.

$$t_{elapsed} = t_{monotonicNow} - t_{previousPrice} \tag{식 43}$$

$$s_{skip} = (t_{elapsed} > T_{stale}) \tag{식 44}$$

만약 시세가 지연되었을 경우, 다음 연산 주기를 위해 직전 가격과 시간을 즉시 현 시점으로 초기화합니다:

$$P_{prev} \leftarrow P \tag{식 45}$$

$$t_{previousPrice} \leftarrow t_{monotonicNow} \tag{식 46}$$

---

## 10. 이익 실현 (Take-Profit) 연령 압축 (Age TP)

체결 재고의 보유 시간($a$)이 길어질 경우 자금 고착을 막기 위해 목표 매도가를 하향 압축하여 탈출을 돕습니다.

보유 시간 연산 (현재시각 - 체결 완료 시각):

$$a = t_{nowUtc} - t_{filledUtc} \tag{식 47}$$

보유 연령에 따른 $k$ 감쇄 변량 $d(a)$:

$$d(a) = \begin{cases} 1.0 & \text{if } a \ge 7 \text{ days} \\ 0.5 & \text{if } 48 \text{ hours} \le a < 7 \text{ days} \\ 0.0 & \text{if } a < 48 \text{ hours} \end{cases} \tag{식 48}$$

감쇄가 반영된 유효 배수 $k_{eff}$:

$$k_{eff} = \max(k_{base} - d(a), k_{floor}) \tag{식 49}$$

압축 매도 가격 산출:

$$g_{base} = \ln\left(\frac{S_i}{B_i}\right) \tag{식 50}$$

$$g_{compressed} = g_{base} \cdot \frac{k_{eff}}{k_{base}} \tag{식 51}$$

$$S_i' = F_{norm}(B_i \cdot e^{g_{compressed}}) \tag{식 52}$$

최종 적용할 매도 호가 $S_i^{eff}$:

$$S_i^{eff} = \begin{cases} S_i' & \text{if } B_i < S_i' < S_i \\ S_i & \text{otherwise} \end{cases} \tag{식 53}$$

---

## 11. Breakout Guard (추세 이탈 감지)

직전 완성된 $M$개의 분봉 캔들의 종가($C_j$)를 분석하여 급변침 상황 시 진입을 일시적으로 차단합니다.

- **상단 이탈**: $M$개 연속 캔들이 그리드 상단 $U$ 위에서 마감

$$o_{upper} = \bigwedge_{j=1}^M (C_j > U) \tag{식 54}$$

- **하단 이탈**: $M$개 연속 캔들이 그리드 하단 $L$ 아래에서 마감

$$o_{lower} = \bigwedge_{j=1}^M (C_j < L) \tag{식 55}$$

가드 작동 판정:

$$b_{guard} = o_{upper} \lor o_{lower} \tag{식 56}$$

> [!WARNING]
> 가드가 활성화($b_{guard} = true$)되면 **신규 매수(BUY) 주문 제출은 전면 차단**되며, 이미 진입해 있는 재고의 청산(SELL)은 정상 유지됩니다.

---

## 12. 매수 주문 필요 예산 정밀 산출

주문 체결에 필요한 실 가용 원화 잔고 평가식입니다.

- **시장가 매수 시 필요 원금**:

$$A_{required} = A_{spend} \tag{식 57}$$

- **지정가 매수 시 필요 원금**:

$$A_{required} = P_{order} Q_{order} \tag{식 58}$$

수수료 및 안전 버퍼를 감안한 예상 투입 금액 $A_{estimated}$:

$$A_{estimated} = A_{required}(1 + f_{upbit}) + A_{buffer} \tag{식 59}$$

최종 잔고 가용성 조건 검증:

$$A_{available} \ge A_{estimated} + A_{reserve} \tag{식 60}$$

---

## 13. 라이브 가동 예산 조정 공식

운영 중 예산 개편 명령 발생 시 호출되는 로직입니다. 보유 수량($H_i$)은 고정하고, 빈 슬롯의 목표량($Q_{i, new}$)만 재산출합니다.

$$B_{total} \leftarrow X \quad (\text{조정 예산 주입}) \tag{식 61}$$

$$B_{slot, i} = B_{total} \cdot \frac{w_i}{W} \tag{식 62}$$

$$Q_{i, new} = F_{step}\left( \frac{B_{slot, i}}{B_i}, 0.00000001 \text{ (기초자산 단위, cfg.SYMBOL)} \right) \tag{식 63}$$

---

## 14. 손절(Stop Loss) 판정 수식

그리드 하한($L$) 아래로 시세가 추가 이탈할 때 단계별로 청산하는 자동 손절 서브시스템입니다. 구현은 [stop_loss.py](../app/strategy/stop_loss.py), 파라미터 검증은 [grid_properties.py](../app/core/grid_properties.py)의 `validate_stop_loss_config()`, 운영값은 [grid.properties](../grid.properties)를 기준으로 합니다. 여기서 $L = $ `MIN_BUY_PRICE`(최하단 슬롯 매수가), $U = $ `MAX_BUY_PRICE`(최상단 슬롯 매수가)입니다.

### 14-1. 손절 임계가 산출

손절 모드는 `STOP_LOSS_MODE`로 선택하며 `band_multiple`(기본/권장), `fixed_pct`, `off` 세 가지입니다.

- **`band_multiple` 모드** — 밴드 폭(하락률)에 배수 $k_{band}$(`STOP_LOSS_BAND_MULTIPLE`)를 곱한 **단일 임계가**를 사용합니다. 레벨에 무관하게 동일한 값입니다.

$$T_{band} = L \cdot \left( 1 - k_{band} \left( 1 - \frac{L}{U} \right) \right) \tag{식 64}$$

- **`fixed_pct` 모드** — 레벨별 하락 백분율 $p_{Ln}$(`STOP_LOSS_Ln_PCT`)에 따라 레벨별 임계가를 산출합니다.

$$T_{Ln} = L \cdot \left( 1 - \frac{p_{Ln}}{100} \right), \quad n \in \{0, 1, 2\} \tag{식 65}$$

### 14-2. 레벨 분기

현재가 $P$가 $T_{L0}$ 이상이면 미발동입니다. 그 아래로 떨어지면 임계가 비교로 레벨을 분기합니다.

$$level = \begin{cases} \text{미발동} & \text{if } P \ge T_{L0} \\ 2 & \text{if } P < T_{L2} \\ 1 & \text{if } T_{L2} \le P < T_{L1} \\ 0 & \text{if } T_{L1} \le P < T_{L0} \end{cases} \tag{식 66}$$

> [!IMPORTANT]
> **`band_multiple` 모드의 L2 직행**: 식 64의 $T_{band}$는 레벨과 무관한 단일값이므로 $T_{L0} = T_{L1} = T_{L2} = T_{band}$로 수렴합니다. 따라서 시세가 단일 밴드 임계가 아래로 이탈하는 순간, 식 66에서 $P < T_{L2}$ 분기가 먼저 성립해 **곧바로 L2(전량 시장가 청산)로 직행**합니다 (L0/L1 중간 단계 없음).

### 14-3. 연속 종가 컨펌

레벨이 분기되어도 즉시 청산하지 않고, `STOP_LOSS_CANDLE_UNIT`(분) 단위 캔들의 **연속 종가가 임계가 아래에서 마감**되는지로 컨펌합니다. 레벨별 필요 연속 종가 수는 $n_{Ln}$(`STOP_LOSS_Ln_CONSECUTIVE_CLOSES`)입니다.

$$c_{arm} = \bigwedge_{j=1}^{n_{Ln}} (C_j < T_{Ln}) \tag{식 67}$$

- `STOP_LOSS_L0_CONSECUTIVE_CLOSES` = 4 (검증: ≥ 2)
- `STOP_LOSS_L1_CONSECUTIVE_CLOSES` = 4 (검증: ≥ 2)
- `STOP_LOSS_L2_CONSECUTIVE_CLOSES` = 2 (검증: ≥ 1)

$c_{arm} = true$일 때 해당 레벨이 ARM(무장)되며, `armed_at`(최초 무장 시각)이 기록·유지됩니다.

### 14-4. 레벨별 청산 동작

- **L0**: 신규 매수만 차단(no-op). 보유 재고는 청산하지 않습니다.
- **L1**: 보유 슬롯을 임계가($T_{L1}$) 기준 **지정가 부분 청산**합니다. 청산 비율 $r_{L1}$ = `STOP_LOSS_L1_LIQUIDATE_RATIO` = 0.5.

$$q_{sell, i} = H_i \cdot r_{L1}, \quad r_{L1} = 0.5 \tag{식 68}$$

- **L2**: 보유 슬롯 **전량 시장가 청산**($r_{L2} = 1$). 청산 후 재시작 잠금 시간 $\tau_{lock}$(`STOP_LOSS_RESTART_LOCKOUT_HOURS`) 동안 봇 재가동이 잠깁니다.

$$\tau_{lock} = 24 \text{ hours} \tag{식 69}$$

> [!WARNING]
> 현재 라이브는 `STOP_LOSS_MODE = off`로 운용 중입니다 (그리드 폭이 `MIN_BUY_PRICE = 1450`~`MAX_BUY_PRICE = 1500` ≈ 3.45%로 좁아 `band_multiple`을 적용할 수 없기 때문). 참고로 `band_multiple`은 `validate_stop_loss_config()`에서 1.0~2.0 범위로 강제되며, 식 64의 $T_{band}$가 $0.5L < T_{band} < 0.9L$ 구간에 들어야 정상 운영 구간 침범/하한 50% 초과 검증을 통과합니다 (코드 기본값은 [settings.py](../app/config/settings.py)의 `1.5`). 좁은 그리드에서는 이 두 검증을 동시에 만족하는 배수가 존재하지 않아(대략 그리드 폭 5.26% 이상이어야 성립) `band_multiple` 적용이 불가합니다.
