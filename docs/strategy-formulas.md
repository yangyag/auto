# Strategy Formulas

이 문서는 전략 동작에 쓰이는 수식과 판정 조건만 코드 기준으로 정리한다. GitHub Markdown 수식 렌더링 호환성을 위해 수식 안에는 긴 설정 키 문자열을 직접 넣지 않고, 아래 기호로 치환한다.

기준 구현:
- `strategy/grid_strategy.py`
- `core/grid.py`
- `core/grid_properties.py`
- `strategy/breakout_guard.py`
- `main.py`

## 기호

- $P_{\mathrm{prev}}$: 직전 전략 평가 가격
- $P$: 현재 전략 평가 가격
- $B_i$: $i$번 슬롯의 `buy_price`
- $S_i$: $i$번 슬롯의 저장된 `sell_price`
- $Q_i$: $i$번 슬롯의 `planned_qty`
- $H_i$: $i$번 슬롯의 `held_qty`
- $L$: 그리드 하단 가격
- $U$: 그리드 상단 가격
- $N$: 슬롯 수
- $I$: 가격 구간 수
- $F_{\mathrm{norm}}(x)$: `normalize_price(x)`, 업비트 KRW 호가 단위 정규화
- $F_{\mathrm{step}}(x, s)$: `floor_step(x, s)`, 지정 step $s$ 단위 내림
- $G_N$: `GRID_COUNT`
- $p_{\mathrm{step}}$: `GRID_STEP_PCT`
- $k_{\mathrm{base}}$: `TP_K_BASE`
- $k_{\mathrm{floor}}$: `TP_K_FLOOR`
- $B_{\mathrm{lower}}$: `LOWER_BUDGET_KRW`
- $n_{\mathrm{below}}$: `ACTIVE_WINDOW_BELOW_CURRENT_SLOTS`
- $n_{\mathrm{above}}$: `ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS`
- $B_{\mathrm{maxop}}$: `MAX_OPERATING_BUDGET_KRW`
- $T_{\mathrm{stale}}$: `STALE_PREVIOUS_PRICE_THRESHOLD_SECONDS`
- $A_{\mathrm{min}}$: `MIN_KRW_ORDER_AMOUNT`
- $f_{\mathrm{upbit}}$: `UPBIT_FEE_RATE`
- $A_{\mathrm{buffer}}$: `FEE_BUFFER_KRW`
- $A_{\mathrm{reserve}}$: `MIN_BALANCE_RESERVE`
- $M$: `BREAKOUT_GUARD_CONSECUTIVE_CANDLES`

## 그리드 슬롯 수

`GRID_COUNT`를 직접 지정하면:

$$
N = G_N
$$

$$
I = N - 1
$$

`GRID_STEP_PCT`를 지정하면:

$$
\Delta_{\mathrm{log}} = \ln(\frac{U}{L})
$$

$$
\delta_{\mathrm{log}} = \ln(1 + \frac{p_{\mathrm{step}}}{100})
$$

$$
I_{\mathrm{raw}} = \frac{\Delta_{\mathrm{log}}}{\delta_{\mathrm{log}}}
$$

후보 구간 수:

$$
\mathcal{I}_{\mathrm{cand}} =
\lbrace \lfloor I_{\mathrm{raw}} \rfloor,\ \lceil I_{\mathrm{raw}} \rceil \rbrace
$$

각 후보의 오차:

$$
E(j) = |\frac{\Delta_{\mathrm{log}}}{j} - \delta_{\mathrm{log}}|
$$

$\mathcal{I}_{\mathrm{cand}}$ 안에서 $E(j)$가 가장 작은 후보를 $I$로 선택한다. 오차가 같으면 더 큰 $I$를 선택한다.

$$
N = I + 1
$$

## 매수 가격 사다리

상단에서 하단으로 내려가는 로그 간격 사다리다.

$$
\ell = \frac{\ln(U/L)}{N - 1}
$$

$$
g = e^\ell
$$

$$
B_0 = U
$$

$$
B_i = F_{\mathrm{norm}}(\frac{U}{g^i}),\quad 0 < i < N - 1
$$

$$
B_{N-1} = L
$$

호가 단위 적용 후 $B_i$가 중복되면 그리드 생성은 실패한다.

## 신규 TP 가격

`k` 모델은 고정 퍼센트가 아니라 그리드 로그 간격을 $k$배 적용하는 모델이다.

$$
k_{\mathrm{eff}} = k_{\mathrm{base}}
$$

$$
S_i^{\mathrm{raw}} = B_i e^{\ell k_{\mathrm{eff}}}
$$

$$
S_i = F_{\mathrm{norm}}(S_i^{\mathrm{raw}})
$$

검증 조건:

$$
S_i > B_i
$$

$$
k_{\mathrm{base}} \ge k_{\mathrm{floor}} > 0
$$

## 예산 가중치

슬롯 인덱스는 상단이 $0$, 하단이 $N - 1$이다.

$$
b_i = \min(\lfloor \frac{3i}{N - 1} \rfloor,\ 2)
$$

$$
w_i =
\begin{cases}
0.7 & b_i = 0 \\
1.0 & b_i = 1 \\
1.3 & b_i = 2
\end{cases}
$$

$$
W = \sum_{i=0}^{N-1} w_i
$$

현재가 미만 슬롯:

$$
\mathcal{L} = \lbrace i : B_i < P_{\mathrm{seed}} \rbrace
$$

$$
W_{\mathrm{lower}} = \sum_{i \in \mathcal{L}} w_i
$$

$$
r_{\mathrm{lower}} = \frac{W_{\mathrm{lower}}}{W}
$$

하단 매수합 목표에서 implicit 총 예산을 역산한다.

$$
B_{\mathrm{total}} = \frac{B_{\mathrm{lower}}}{r_{\mathrm{lower}}}
$$

$$
B_{\mathrm{slot}, i} = B_{\mathrm{total}} \frac{w_i}{W}
$$

$$
Q_i = F_{\mathrm{step}}(\frac{B_{\mathrm{slot}, i}}{B_i},\ 0.00000001\ \mathrm{BTC})
$$

양자화 후 실제 하단 매수합:

$$
B_{\mathrm{lowerActual}} = \sum_{i \in \mathcal{L}} B_i Q_i
$$

$$
B_{\mathrm{lowerActual}} \le B_{\mathrm{lower}}
$$

$\mathcal{L}$이 비어 있으면 그리드 생성은 실패한다. 모든 슬롯이 $\mathcal{L}$에 포함되면 `LOWER_BUDGET_KRW`가 사실상 총 예산이 된다.

## 현재 재고 원가와 총 배정 금액

현재 보유 재고 원가:

$$
C_{\mathrm{inventory}} = \sum_{i \in \mathcal{H}} B_i H_i
$$

총 배정 금액:

$$
B_{\mathrm{allocated}} = \sum_{i \in \mathcal{H}} B_i H_i + \sum_{i \in \mathcal{E}} B_i Q_i
$$

여기서 $\mathcal{H}$는 holding 슬롯 집합, $\mathcal{E}$는 empty 슬롯 집합이다.

## 매수 교차 조건

하락 매수 후보:

$$
P_{\mathrm{prev}} > B_i \ge P
$$

추가 조건:
- 슬롯 $i$가 empty 상태다.
- 슬롯 $i$에 pending BUY가 없다.
- 슬롯 $i$가 active buy window 안에 있다.
- inventory target gate를 통과한다.
- breakout guard가 비활성이다.

첫 가격 스냅샷에서는 $P_{\mathrm{prev}}$ 기준선만 저장하고 신규 매수를 만들지 않는다.

## 상승 재진입 조건

상승 매수 후보:

$$
P > P_{\mathrm{prev}}
$$

$$
P_{\mathrm{prev}} < B_i \le P
$$

추가 조건:
- `UPWARD_BUY_ENABLED`가 true다.
- 정확히 1개 empty 슬롯만 상향 교차한다.
- 슬롯 $i$에 pending BUY가 없다.
- 슬롯 $i$가 active buy window 안에 있다.
- inventory target gate를 통과한다.
- breakout guard가 비활성이다.

시장가 예산매수 금액:

$$
A_{\mathrm{spend}} = F_{\mathrm{step}}(B_i Q_i,\ 1\ \mathrm{KRW})
$$

## 활성 매수 윈도우

기준 가격은 $P_{\mathrm{prev}}$다.

$$
\mathcal{B}_{\le} = \lbrace i \in \mathcal{E} : B_i \le P_{\mathrm{prev}} \rbrace
$$

$$
\mathcal{B}_{>} = \lbrace i \in \mathcal{E} : B_i > P_{\mathrm{prev}} \rbrace
$$

정렬 기준:
- $\mathcal{B}_{\le}$: $B_i$ 내림차순, `slot_index` 오름차순
- $\mathcal{B}_{>}$: $B_i$ 오름차순, `slot_index` 오름차순

활성 슬롯 집합:

$$
\mathcal{A} =
\mathrm{first}_{n_{\le}}(\mathcal{B}_{\le})
\cup
\mathrm{first}_{n_{>}}(\mathcal{B}_{>})
$$

여기서:

$$
n_{\le} = n_{\mathrm{below}}
$$

$$
n_{>} = n_{\mathrm{above}}
$$

활성 윈도우가 꺼져 있으면 모든 empty 슬롯을 활성 후보로 본다.

## Inventory Target Gate

운영 예산 분모:

$$
B_{\mathrm{op}} =
\begin{cases}
B_{\mathrm{maxop}} & B_{\mathrm{maxop}} > 0 \\
B_{\mathrm{allocated}} & B_{\mathrm{maxop}} \le 0
\end{cases}
$$

현재 재고 비율은 같은 평가 사이클에서 이미 승인된 매수 후보까지 반영한 projected inventory 기준이다.

$$
q_{\mathrm{current}} = \frac{C_{\mathrm{projected}}}{B_{\mathrm{op}}}
$$

로그 밴드 위치:

$$
z_{\mathrm{raw}} =
\frac{\ln(P) - \ln(L)}{\ln(U) - \ln(L)}
$$

$$
z = \mathrm{clamp}(z_{\mathrm{raw}},\ 0,\ 1)
$$

목표 재고 비율:

$$
q_{\mathrm{target}}(z) =
q_{\min} + (q_{\max} - q_{\min})(1 - z)^\gamma
$$

$$
q_{\mathrm{target}}(z) =
\mathrm{clamp}(q_{\mathrm{target}}(z),\ q_{\min},\ q_{\max})
$$

통과 조건:

$$
\theta = \max(q_{\mathrm{target}}(z) - \epsilon,\ 0)
$$

$$
g_{\mathrm{pass}} = (q_{\mathrm{current}} < \theta)
$$

## Stale Previous Price Guard

직전 평가 이후 경과 시간이 임계값을 초과하면 그 cycle의 신규 매수 평가는 스킵한다.

$$
t_{\mathrm{elapsed}} =
t_{\mathrm{monotonicNow}} - t_{\mathrm{previousPrice}}
$$

$$
s_{\mathrm{skip}} = (t_{\mathrm{elapsed}} > T_{\mathrm{stale}})
$$

이 경우:

$$
P_{\mathrm{prev}} \leftarrow P
$$

$$
t_{\mathrm{previousPrice}} \leftarrow t_{\mathrm{monotonicNow}}
$$

SELL 평가는 계속 수행한다.

## 매도 조건

보유 슬롯의 매도 후보:

$$
P \ge S_i^{\mathrm{eff}}
$$

TP 주문 생성 최소 금액 조건:

$$
S_i^{\mathrm{eff}} H_i \ge A_{\mathrm{min}}
$$

## Age TP 압축

보유 시간:

$$
a = t_{\mathrm{nowUtc}} - t_{\mathrm{filledUtc}}
$$

`k` 압축량:

$$
d(a) =
\begin{cases}
1.0 & a \ge 7\ \mathrm{days} \\
0.5 & 48\ \mathrm{hours} \le a < 7\ \mathrm{days} \\
0.0 & a < 48\ \mathrm{hours}
\end{cases}
$$

유효 $k$:

$$
k_{\mathrm{eff}} = \max(k_{\mathrm{base}} - d(a),\ k_{\mathrm{floor}})
$$

압축 매도 가격:

$$
g_{\mathrm{base}} = \ln(\frac{S_i}{B_i})
$$

$$
g_{\mathrm{compressed}} =
g_{\mathrm{base}} \frac{k_{\mathrm{eff}}}{k_{\mathrm{base}}}
$$

$$
\widetilde{S}_i =
F_{\mathrm{norm}}(B_i e^{g_{\mathrm{compressed}}})
$$

최종 매도 가격:

$$
S_i^{\mathrm{eff}} =
\begin{cases}
\widetilde{S}_i & B_i < \widetilde{S}_i < S_i \\
S_i & \mathrm{otherwise}
\end{cases}
$$

Age TP는 `k` 모델로 생성된 그리드이고 holding 슬롯에 `filled_at`이 있을 때만 적용된다.

## 브레이크아웃 가드

최근 완료 캔들 종가 $C_j$를 최신순으로 $M$개 본다.

상단 이탈:

$$
o_{\mathrm{upper}} = \bigwedge_{j=1}^{M} (C_j > U)
$$

하단 이탈:

$$
o_{\mathrm{lower}} = \bigwedge_{j=1}^{M} (C_j < L)
$$

가드 활성:

$$
b_{\mathrm{guard}} = o_{\mathrm{upper}} \lor o_{\mathrm{lower}}
$$

가드가 활성화되면 신규 BUY 후보는 제거하고 SELL 후보는 유지한다.

캔들 조회 실패, 캔들 부족, invalid band 같은 입력 실패는 `main.py`의 failure policy에서 fail-open/fail-close로 처리한다.

## 매수 필요 KRW 추정

BUY 주문 원금:

시장가 예산매수:

$$
A_{\mathrm{required}} = A_{\mathrm{spend}}
$$

지정가 BUY:

$$
A_{\mathrm{required}} = P_{\mathrm{order}} Q_{\mathrm{order}}
$$

수수료와 버퍼를 포함한 필요 금액:

$$
A_{\mathrm{estimated}} = A_{\mathrm{required}}(1 + f_{\mathrm{upbit}}) + A_{\mathrm{buffer}}
$$

잔고 통과 조건:

$$
A_{\mathrm{available}}
\ge A_{\mathrm{estimated}} + A_{\mathrm{reserve}}
$$

같은 cycle에서 여러 BUY를 검사할 때는 통과한 주문의 $A_{\mathrm{estimated}}$를 가용 잔고에서 선반영 차감한다.

## 라이브 예산 조정

`scripts/adjust_budget_live.py --target-lower-budget X`는 기존 ladder와 보유 수량을 유지하고 $Q_i$만 다시 계산한다.

$$
B_{\mathrm{lower}} \leftarrow X
$$

$$
B_{\mathrm{total}} = \frac{X}{r_{\mathrm{lower}}}
$$

$$
B_{\mathrm{slot}, i} = B_{\mathrm{total}} \frac{w_i}{W}
$$

$$
Q_i^{\mathrm{new}} =
F_{\mathrm{step}}(\frac{B_{\mathrm{slot}, i}}{B_i},\ 0.00000001\ \mathrm{BTC})
$$

검증용 새 계획 매수합:

$$
B_{\mathrm{plannedNew}} =
\sum_{i=0}^{N-1} B_i Q_i^{\mathrm{new}}
$$

$$
B_{\mathrm{lowerNew}} =
\sum_{i \in \mathcal{L}} B_i Q_i^{\mathrm{new}}
$$

보유 슬롯의 $H_i$, $S_i$, `filled_at`은 유지한다.
