# Strategy Formulas

이 문서는 전략 동작에 쓰이는 수식과 판정 조건만 코드 기준으로 정리한다.

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
- $\operatorname{normalize\_price}(x)$: 업비트 KRW 호가 단위 정규화
- $\operatorname{floor\_step}(x, s)$: 지정 step $s$ 단위 내림

## 그리드 슬롯 수

`GRID_COUNT`를 직접 지정하면:

$$
N = \texttt{GRID\_COUNT}
$$

$$
I = N - 1
$$

`GRID_STEP_PCT`를 지정하면:

$$
\Delta_{\log} = \ln\left(\frac{U}{L}\right)
$$

$$
\delta_{\log} = \ln\left(1 + \frac{\texttt{GRID\_STEP\_PCT}}{100}\right)
$$

$$
I_{\mathrm{raw}} = \frac{\Delta_{\log}}{\delta_{\log}}
$$

후보 구간 수:

$$
\mathcal{I}_{\mathrm{candidate}}
= \left\{ \left\lfloor I_{\mathrm{raw}} \right\rfloor,
          \left\lceil I_{\mathrm{raw}} \right\rceil \right\}
$$

선택 기준:

$$
I
= \underset{j \in \mathcal{I}_{\mathrm{candidate}}}{\operatorname{argmin}}
  \left| \frac{\Delta_{\log}}{j} - \delta_{\log} \right|
$$

$$
N = I + 1
$$

오차가 같으면 더 큰 $I$를 선택한다.

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
B_i = \operatorname{normalize\_price}\left(\frac{U}{g^i}\right),
\quad 0 < i < N - 1
$$

$$
B_{N-1} = L
$$

호가 단위 적용 후 $B_i$가 중복되면 그리드 생성은 실패한다.

## 신규 TP 가격

`k` 모델은 고정 퍼센트가 아니라 그리드 로그 간격을 $k$배 적용하는 모델이다.

$$
k_{\mathrm{effective}} = \texttt{TP\_K\_BASE}
$$

$$
S_i^{\mathrm{raw}} = B_i \cdot e^{\ell k_{\mathrm{effective}}}
$$

$$
S_i = \operatorname{normalize\_price}\left(S_i^{\mathrm{raw}}\right)
$$

검증 조건:

$$
S_i > B_i
$$

$$
\texttt{TP\_K\_BASE} \ge \texttt{TP\_K\_FLOOR} > 0
$$

## 예산 가중치

슬롯 인덱스는 상단이 $0$, 하단이 $N - 1$이다.

$$
b_i = \min\left(\left\lfloor \frac{3i}{N - 1} \right\rfloor, 2\right)
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
\mathcal{L} = \{\, i \mid B_i < P_{\mathrm{seed}} \,\}
$$

$$
W_{\mathrm{lower}} = \sum_{i \in \mathcal{L}} w_i
$$

$$
r_{\mathrm{lower}} = \frac{W_{\mathrm{lower}}}{W}
$$

하단 매수합 목표에서 implicit 총 예산을 역산한다.

$$
B_{\mathrm{total}} = \frac{\texttt{LOWER\_BUDGET\_KRW}}{r_{\mathrm{lower}}}
$$

$$
B_{\mathrm{slot}, i} = B_{\mathrm{total}} \cdot \frac{w_i}{W}
$$

$$
Q_i
= \operatorname{floor\_step}
  \left(\frac{B_{\mathrm{slot}, i}}{B_i},\ 0.00000001\ \mathrm{BTC}\right)
$$

양자화 후 실제 하단 매수합:

$$
B_{\mathrm{lower, actual}}
= \sum_{i \in \mathcal{L}} B_i Q_i
$$

$$
B_{\mathrm{lower, actual}} \le \texttt{LOWER\_BUDGET\_KRW}
$$

$\mathcal{L}$이 비어 있으면 그리드 생성은 실패한다. 모든 슬롯이 $\mathcal{L}$에 포함되면 `LOWER_BUDGET_KRW`가 사실상 총 예산이 된다.

## 현재 재고 원가와 총 배정 금액

현재 보유 재고 원가:

$$
C_{\mathrm{inventory}}
= \sum_{i \in \mathcal{H}} B_i H_i
$$

총 배정 금액:

$$
B_{\mathrm{allocated}}
= \sum_{i \in \mathcal{H}} B_i H_i
  + \sum_{i \in \mathcal{E}} B_i Q_i
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
A_{\mathrm{spend}}
= \operatorname{floor\_step}(B_i Q_i,\ 1\ \mathrm{KRW})
$$

## 활성 매수 윈도우

기준 가격은 $P_{\mathrm{prev}}$다.

$$
\mathcal{B}_{\le}
= \{\, i \in \mathcal{E} \mid B_i \le P_{\mathrm{prev}} \,\}
$$

$$
\mathcal{B}_{>}
= \{\, i \in \mathcal{E} \mid B_i > P_{\mathrm{prev}} \,\}
$$

정렬 기준:
- $\mathcal{B}_{\le}$: $B_i$ 내림차순, `slot_index` 오름차순
- $\mathcal{B}_{>}$: $B_i$ 오름차순, `slot_index` 오름차순

활성 슬롯 집합:

$$
\mathcal{A}
= \operatorname{first}_{n_{\le}}(\mathcal{B}_{\le})
  \cup
  \operatorname{first}_{n_{>}}(\mathcal{B}_{>})
$$

여기서:

$$
n_{\le} = \texttt{ACTIVE\_WINDOW\_BELOW\_CURRENT\_SLOTS}
$$

$$
n_{>} = \texttt{ACTIVE\_WINDOW\_ABOVE\_CURRENT\_REENTRY\_SLOTS}
$$

활성 윈도우가 꺼져 있으면 모든 empty 슬롯을 활성 후보로 본다.

## Inventory Target Gate

운영 예산 분모:

$$
B_{\mathrm{op}} =
\begin{cases}
\texttt{MAX\_OPERATING\_BUDGET\_KRW}
  & \text{if } \texttt{MAX\_OPERATING\_BUDGET\_KRW} > 0 \\
B_{\mathrm{allocated}}
  & \text{otherwise}
\end{cases}
$$

현재 재고 비율은 같은 평가 사이클에서 이미 승인된 매수 후보까지 반영한 projected inventory 기준이다.

$$
q_{\mathrm{current}}
= \frac{C_{\mathrm{projected}}}{B_{\mathrm{op}}}
$$

로그 밴드 위치:

$$
z_{\mathrm{raw}}
= \frac{\ln(P) - \ln(L)}{\ln(U) - \ln(L)}
$$

$$
z = \operatorname{clamp}(z_{\mathrm{raw}}, 0, 1)
$$

목표 재고 비율:

$$
q_{\mathrm{target}}(z)
= q_{\min} + (q_{\max} - q_{\min})(1 - z)^\gamma
$$

$$
q_{\mathrm{target}}(z)
= \operatorname{clamp}(q_{\mathrm{target}}(z), q_{\min}, q_{\max})
$$

통과 조건:

$$
\theta = \max(q_{\mathrm{target}}(z) - \epsilon,\ 0)
$$

$$
\operatorname{gate\_passed}
= \left(q_{\mathrm{current}} < \theta\right)
$$

## Stale Previous Price Guard

직전 평가 이후 경과 시간이 임계값을 초과하면 그 cycle의 신규 매수 평가는 스킵한다.

$$
t_{\mathrm{elapsed}}
= t_{\mathrm{monotonic, now}} - t_{\mathrm{previous\_price}}
$$

$$
\operatorname{skip\_new\_buys}
= \left(t_{\mathrm{elapsed}} > \texttt{STALE\_PREVIOUS\_PRICE\_THRESHOLD\_SECONDS}\right)
$$

이 경우:

$$
P_{\mathrm{prev}} \leftarrow P
$$

$$
t_{\mathrm{previous\_price}} \leftarrow t_{\mathrm{monotonic, now}}
$$

SELL 평가는 계속 수행한다.

## 매도 조건

보유 슬롯의 매도 후보:

$$
P \ge S_i^{\mathrm{effective}}
$$

TP 주문 생성 최소 금액 조건:

$$
S_i^{\mathrm{effective}} H_i \ge \texttt{MIN\_KRW\_ORDER\_AMOUNT}
$$

## Age TP 압축

보유 시간:

$$
a = t_{\mathrm{now, utc}} - t_{\mathrm{filled, utc}}
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
k_{\mathrm{effective}}
= \max(\texttt{TP\_K\_BASE} - d(a),\ \texttt{TP\_K\_FLOOR})
$$

압축 매도 가격:

$$
g_{\mathrm{base}} = \ln\left(\frac{S_i}{B_i}\right)
$$

$$
g_{\mathrm{compressed}}
= g_{\mathrm{base}} \cdot \frac{k_{\mathrm{effective}}}{\texttt{TP\_K\_BASE}}
$$

$$
\widetilde{S}_i
= \operatorname{normalize\_price}
  \left(B_i \cdot e^{g_{\mathrm{compressed}}}\right)
$$

최종 매도 가격:

$$
S_i^{\mathrm{effective}} =
\begin{cases}
\widetilde{S}_i & B_i < \widetilde{S}_i < S_i \\
S_i & \text{otherwise}
\end{cases}
$$

Age TP는 `k` 모델로 생성된 그리드이고 holding 슬롯에 `filled_at`이 있을 때만 적용된다.

## 브레이크아웃 가드

최근 완료 캔들 종가 $C_j$를 최신순으로 $M = \texttt{BREAKOUT\_GUARD\_CONSECUTIVE\_CANDLES}$개 본다.

상단 이탈:

$$
\operatorname{outside\_upper}
= \bigwedge_{j=1}^{M} (C_j > U)
$$

하단 이탈:

$$
\operatorname{outside\_lower}
= \bigwedge_{j=1}^{M} (C_j < L)
$$

가드 활성:

$$
\operatorname{breakout\_guard\_active}
= \operatorname{outside\_upper} \lor \operatorname{outside\_lower}
$$

가드가 활성화되면 신규 BUY 후보는 제거하고 SELL 후보는 유지한다.

캔들 조회 실패, 캔들 부족, invalid band 같은 입력 실패는 `main.py`의 failure policy에서 fail-open/fail-close로 처리한다.

## 매수 필요 KRW 추정

BUY 주문 원금:

$$
A_{\mathrm{required}} =
\begin{cases}
A_{\mathrm{spend}} & \text{market buy by price} \\
\mathrm{price} \cdot \mathrm{quantity} & \text{limit BUY}
\end{cases}
$$

수수료와 버퍼를 포함한 필요 금액:

$$
A_{\mathrm{estimated}}
= A_{\mathrm{required}}(1 + \texttt{UPBIT\_FEE\_RATE})
  + \texttt{FEE\_BUFFER\_KRW}
$$

잔고 통과 조건:

$$
A_{\mathrm{available}}
\ge A_{\mathrm{estimated}} + \texttt{MIN\_BALANCE\_RESERVE}
$$

같은 cycle에서 여러 BUY를 검사할 때는 통과한 주문의 $A_{\mathrm{estimated}}$를 가용 잔고에서 선반영 차감한다.

## 라이브 예산 조정

`scripts/adjust_budget_live.py --target-lower-budget X`는 기존 ladder와 보유 수량을 유지하고 $Q_i$만 다시 계산한다.

$$
\texttt{LOWER\_BUDGET\_KRW} \leftarrow X
$$

$$
B_{\mathrm{total}} = \frac{X}{r_{\mathrm{lower}}}
$$

$$
B_{\mathrm{slot}, i} = B_{\mathrm{total}} \cdot \frac{w_i}{W}
$$

$$
Q_i^{\mathrm{new}}
= \operatorname{floor\_step}
  \left(\frac{B_{\mathrm{slot}, i}}{B_i},\ 0.00000001\ \mathrm{BTC}\right)
$$

검증용 새 계획 매수합:

$$
B_{\mathrm{planned, new}}
= \sum_{i=0}^{N-1} B_i Q_i^{\mathrm{new}}
$$

$$
B_{\mathrm{lower, new}}
= \sum_{i \in \mathcal{L}} B_i Q_i^{\mathrm{new}}
$$

보유 슬롯의 $H_i$, $S_i$, `filled_at`은 유지한다.
