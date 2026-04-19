한마디로 말씀드리면, **“지금 쓰시는 형태 그대로”가 월가의 표준 전략은 아니지만, 그 안의 핵심 원리 자체는 월가에서 아주 많이 씁니다.** 공개 자료 기준으로 월가/기관권의 주류는 `고정 밴드 + 고정 간격 + 고정 익절`의 단순 그리드라기보다, **시장조성(market making), 인벤토리 관리, 주문 분할 실행, 평균회귀형(stat-arb/mean reversion) 로직**으로 더 정교하게 구현된 형태입니다. SEC도 미국 시장에서 다양한 알고리즘 전략이 여러 거래소에 매우 빠르게 주문을 제출한다고 설명하고 있습니다. ([Securities and Exchange Commission][1])

당신 방식과 가장 닮은 쪽은 **시장조성 + 평균회귀**입니다. 일본은행 정리 자료는 알고리즘의 주요 유형을 시장조성, 방향추종, 차익거래, 실행 알고리즘으로 나누고, **시장조성 알고리즘이 FX 현물시장에서 널리 쓰이며 대형 유럽·미국 은행과 비은행 HFT들이 적극 사용한다**고 설명합니다. 또 Avellaneda–Stoikov의 고전적 시장조성 모형도 핵심을 **“대칭적으로 계속 내는 단순 벤치마크”가 아니라, 현재 인벤토리에 따라 호가를 조정하는 inventory-based 전략**으로 잡고 있습니다. ([BOJ][2])

그래서 당신 전략의 철학, 즉 **“내려오면 분할로 받고, 튀면 되파는 구조”**, 그리고 **“재고가 쌓이면 무작정 추격하지 않는 것”**은 기관 로직과 꽤 닮아 있습니다. 특히 평균회귀 구간에서 이런 류의 전략이 잘 맞는다는 점은 학계에서도 오래 연구됐습니다. Penn 논문은 시장조성 전략이 **국소적 변동은 크고 전체 방향성 순이동은 작을 때** 유리하고, **평균회귀가 시장조성 수익성의 자연스러운 기반**이라고 설명합니다. ([Computer and Information Science][3])

다만 **기관은 보통 이렇게 “고정 그리드”로 끝내지 않습니다.** BIS 자료를 보면 초기 실행 알고리즘은 미리 정한 일정대로 주문을 쪼개는 정적 방식이었지만, 이후 세대는 **실시간 시장상황·호가창·유동성에 맞춰 동적으로 바뀌는 통계모형 기반**으로 진화했습니다. 또 실행 알고리즘은 부모 주문을 자식 주문으로 잘게 나누고, 시장충격을 줄이기 위해 가격·타이밍·공격성을 계속 조정합니다. 즉 월가식 구현은 **“그리드의 뼈대” 위에 동적 폭 조절, 체결강도 조절, 인벤토리 상한, 헤지, 레짐 필터**를 얹는 쪽에 가깝습니다. ([국제결제은행][4])

그리고 기관권에서 정말 큰 차이는 **리스크 관리 레이어**입니다. SEC의 Market Access Rule은 자동 주문에도 **사전 신용/자본 한도, 잘못된 주문 차단, 자동화된 프리트레이드 통제**를 요구하고, CFTC도 자동매매에 대해 각종 리스크 통제와 안전장치를 강조해 왔습니다. 즉 기관은 단순히 “격자 깔고 돌린다”가 아니라, **한도·차단·취소·킬스위치**까지 포함한 시스템으로 운영합니다. ([Securities and Exchange Commission][5])

그래서 제 답은 이렇게 정리됩니다. **“예, 많이 쓰입니다”라고 말할 수 있는 부분은 원리입니다. “아니요, 그대로는 아닙니다”라고 말해야 하는 부분은 구현입니다.** 당신 방식은 월가식으로 표현하면 **단순화된 시장조성/인벤토리 재조정 봇**에 가깝고, 특히 **횡보·평균회귀 구간**에서는 충분히 제도권 아이디어와 통합니다. 하지만 **고정 범위, 고정 슬롯, 고정 익절만으로 오래 돌리는 리테일형 순수 그리드**는 공개적으로 확인되는 월가의 주류 구현이라기보다는, 기관 전략의 **입문형·축약형**에 더 가깝습니다. ([Computer and Information Science][3])

당신 전략을 월가 쪽 언어로 가장 정확히 번역하면 이렇습니다.

**“inventory-aware mean-reversion market making의 단순형”**

이 표현이 제일 가깝습니다. 원하시면 다음엔 제가 **당신 현재 규칙을 “기관형으로 한 단계 업그레이드”하려면 어떤 필터 5개를 붙여야 하는지** 아주 실전적으로 정리해드리겠습니다.

[1]: https://www.sec.gov/files/algo_trading_report_2020.pdf "Report to Congress on Algorithmic Trading"
[2]: https://www.boj.or.jp/en/research/wps_rev/rev_2020/data/rev20e05.pdf "An Overview of Algorithmic Trading in Foreign Exchange Markets and Its Impacts on Market Liquidity"
[3]: https://www.cis.upenn.edu/~mkearns/papers/marketmaking.pdf "ec196-chakraborty.dvi"
[4]: https://www.bis.org/publ/mktc13.pdf "FX execution algorithms and market functioning"
[5]: https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0 "SEC.gov | Responses to Frequently Asked Questions Concerning Risk Management Controls for Brokers or Dealers with Market Access"


좋습니다. 구현 관점에서 딱 잘라 말씀드리면, 지금 전략은 `GRID_COUNT`나 고정 `SELL_PERCENT`를 더 미세하게 만지는 것보다 **재고(inventory)를 목표곡선으로 관리하는 것**이 제일 큰 개선입니다. 현재 메모의 구조는 이미 비대칭 평균회귀/시장조성형에 가깝고, 관련 연구들도 핵심 리스크를 inventory risk로 봅니다.  ([arXiv][1])

제가 기획자·개발자에게 바로 넘길 사양으로 바꾸면, 우선순위는 네 가지입니다. **재고목표곡선**, **비대칭 자금배분**, **밴드 이탈 보호장치**, **이벤트 기반 주문엔진**입니다.

## 1) 제일 먼저 넣을 규칙: “목표 재고곡선”

지금은 사실상 “그리드가 열리면 산다”에 가깝습니다. 이걸 “**현재 가격 위치에 따라 내가 원래 들고 있어야 하는 재고량이 얼마인가**”로 바꾸면 전략이 한 단계 올라갑니다.

정의는 이렇게 두면 됩니다.

[
z=\frac{\ln P-\ln L}{\ln U-\ln L}\in[0,1]
]

* (P): 현재가
* (L,U): 밴드 하단/상단
* (z=0): 하단, (z=1): 상단

현재 투자비중을

[
q=\frac{\text{현재 투입 KRW}}{\text{허용 최대 투입 KRW}}
]

로 두고, 목표 재고곡선을

[
q^*(z)=q_{\min}+(q_{\max}-q_{\min})(1-z)^\gamma
]

로 둡니다.

초기값은 이렇게 시작하면 좋습니다.

* `q_min = 0.10`
* `q_max = 0.85`
* `gamma = 1.5`

해석은 간단합니다. **상단에서는 거의 안 들고, 하단으로 갈수록 더 많이 들고 있어야 한다**는 뜻입니다.
그리고 새 매수는 무조건 하지 말고 아래 조건일 때만 허용합니다.

[
q < q^*(z)-\epsilon
]

예를 들어 `epsilon = 0.03` 정도.

이 규칙 하나만 넣어도 “그리드 개수만큼 전부 보유해야 하나?” 문제가 상당히 정리됩니다. 이제부터는 **모든 슬롯이 동등한 게 아니라, 가격 위치에 맞는 재고량만 맞추면 되기 때문**입니다.

## 2) `SELL_PERCENT`를 버리지 말고, 핵심 파라미터를 `k`로 바꾸세요

지금처럼 `GRID_COUNT`와 `SELL_PERCENT`를 따로 조정하면 감이 흔들립니다. 구현은 이렇게 바꾸는 게 훨씬 낫습니다.

[
\Delta=\frac{\ln(U/L)}{N-1},\qquad
s_i = e^{k_i\Delta}-1
]

* (N): 그리드 개수
* (\Delta): 한 칸의 로그 간격
* (k_i): 그 슬롯이 몇 칸 반등하면 팔 것인가

즉, **고정 퍼센트가 아니라 “몇 칸 먹고 팔지”를 본질 파라미터로 두는 것**입니다.

초기값 추천:

* `k_base = 11.0`
* 과재고일수록 `k`를 낮춤
* 오래 묶인 슬롯일수록 `k`를 낮춤

예:

* 정상 상태: `k = 11`
* 재고 과다: `k = 10`
* 오래 묶임: `k = 9`

이렇게 하면 그리드 수를 112에서 122로 바꿔도 전략의 “실제 성격”이 덜 흔들립니다.

## 3) 슬롯당 금액은 균등배분보다 “하단 가중”이 낫습니다

지금처럼 모든 슬롯이 같은 예산인 구조는 구현은 쉽지만, 자본 효율은 그리 좋지 않습니다. 특히 300만원처럼 자금이 한정되어 있으면 더 그렇습니다. 같은 총예산이라도 **상단은 작게, 하단은 크게** 두는 편이 훨씬 자연스럽습니다.

아주 단순하게 3구간만 나눠도 충분합니다.

* 상단 1/3: `0.7x`
* 중단 1/3: `1.0x`
* 하단 1/3: `1.3x`

이유는 분명합니다.

* 상단 근처 매수는 추격 성격이 강하니 작게
* 하단 근처 매수는 평균회귀 기대값이 상대적으로 높으니 크게
* 자금이 부족할 때 가장 아까운 것은 보통 **아래쪽 좋은 가격에서 못 사는 것**입니다

그래서 300만원이면 “112개 전부에 균등금액”보다, **112개 그리드는 개념적으로 유지하되 실제 자금은 하단 쪽으로 기울여 배분**하는 쪽이 좋습니다.

## 4) 전체 밴드를 다 활성화하지 말고 “활성 윈도우”만 운영하세요

이건 특히 중요합니다. 300만원으로 굴릴 때는 **밴드 전체의 112개 슬롯을 다 같은 강도로 운영하려고 하면 비효율**이 커집니다.

추천 방식은 이겁니다.

* 전체 그리드 레벨은 112개를 유지
* 하지만 **현재가 아래쪽 최근접 36~48개만 활성 매수 구간**
* 위쪽은 **0~4개만 재진입 후보**
* 나머지는 “개념적 레벨”로만 두고 실제 주문/트리거는 꺼둠

이렇게 하면

* 주문 수가 줄고
* 자금이 얇게 퍼지지 않고
* 급락 시 실제로 중요한 근접 하단 구간에 자금이 남습니다

그리고 업비트는 주문 생성과 취소 후 재주문이 `order` 그룹으로 초당 8회, 일반 Exchange REST는 초당 30회, WebSocket 연결은 초당 5회 제한이 있으니, 전 구간을 계속 재배치하는 구조보다 **활성 윈도우 방식이 훨씬 운영 친화적**입니다. `Remaining-Req` 헤더를 읽어 자체 rate limiter를 두는 것도 필수입니다. ([업비트 개발자 센터][2])

## 5) “상승 1칸 돌파 매수”는 기본값을 OFF로 두는 걸 권합니다

현재 규칙에서 제일 위험한 부분은 사실 이겁니다. 하락 분할매수는 전략 정체성과 맞는데, **상승 1칸 돌파 매수는 리테일형 추격 매수의 냄새가 조금 납니다.** 메모상 의도는 이해되지만, 실제 구현에서는 이 규칙이 상단 근처에서 불필요한 inventory를 늘릴 가능성이 큽니다. 

제 추천은:

* **v1 기본값:** `up_buy_enabled = false`
* 꼭 남기고 싶다면 아래 조건을 모두 만족할 때만 허용

  * `crossed_up == 1`
  * `q < 0.35`
  * `z < 0.55`
  * 15분 추세가 `flat` 또는 `mild_up`

그리고 `crossed_up >= 2`일 때는 즉시 추격하지 말고,

* 첫 돌파 레벨 또는 그 아래에
* **작은 retracement buy**를 예약
* 15~30분 내 미체결이면 취소

이 구조가 훨씬 덜 위험합니다.

## 6) 오래 묶인 물량은 “나이(age)”에 따라 TP를 줄이세요

고정 TP의 가장 큰 약점은 **자금잠김**입니다. 그래서 각 슬롯에 `age_hours`를 넣고, 오래된 재고는 점점 더 빨리 빠져나오게 해야 합니다.

추천 규칙:

* 48시간 경과: `k - 0.5`
* 7일 경과: `k - 1.0`
* 단, 바닥값은 `k_floor = 8`

즉, 오래 묶인 물량은 익절 목표를 약간 낮춰서 회전을 회복하는 겁니다.
이건 수익 극대화보다 **자본 효율과 생존성**을 올리는 장치입니다.

## 7) 밴드 밖으로 나가면 “재진입 중지”와 “재중심화 조건”이 있어야 합니다

고정 밴드는 편하지만, BTC는 추세가 길게 이어질 수 있어서 **밴드 밖을 오래 걷는 순간 순수 그리드는 약해집니다.**

그래서 최소한 이 두 개는 있어야 합니다.

### A. 브레이크아웃 가드

* 15분 종가가 밴드 밖에서 4개 연속 나오면
* 새 매수 중지
* 기존 포지션 청산만 허용

### B. 재중심화 조건

* 브레이크아웃이 24시간 이상 지속되고
* 현재 inventory ratio가 20% 이하일 때만
* 밴드를 새 중심으로 재계산

즉, **물량이 많이 남아 있을 때는 자동 리셋 금지**입니다.
이걸 안 넣으면 급락장에서 “아래로 계속 받기만 하는” 구조가 됩니다.

## 8) 업비트 구현 디테일은 반드시 이대로 가세요

업비트 KRW 마켓은 최소 주문 가능 금액이 5,000 KRW이고, 1,000,000원 이상 가격대의 호가 단위는 1,000원입니다. 지금 메모의 KRW-BTC 밴드(9천만~1.2억원대)는 당연히 이 구간에 들어가므로, **모든 주문 가격은 1,000원 단위로 반올림/절삭되어야 하고**, 슬롯 금액은 최소 주문 금액 위만 확인하면 됩니다. 또 `orders/chance`에서 페어별 `bid_fee`, `ask_fee`, `market.bid.min_total`, `market.ask.min_total`를 조회할 수 있으니, 수수료와 최소 주문금액은 코드에 하드코딩하지 말고 런타임 조회값을 써야 합니다.  ([업비트 개발자 센터][3])

주문 엔진은 **REST polling 중심이 아니라 WebSocket 중심**으로 짜는 게 좋습니다. 업비트는 시세용 WebSocket과 인증이 필요한 private WebSocket을 따로 두고, private 쪽에서 `myOrder`와 `myAsset`을 받을 수 있습니다. `myOrder`에는 `wait`, `trade`, `done`, `cancel`, `prevented` 같은 상태가 오므로, 로컬에서 “주문 넣었으니 체결됐겠지” 식으로 추정하지 말고 **private stream을 단일 진실원천(source of truth)** 으로 쓰는 게 안전합니다. ([업비트 개발자 센터][4])

주문 식별은 반드시 `identifier` 기반으로 하세요. 업비트는 클라이언트 주문 식별자를 지원하고, 이 값은 사용자 계정 전체 주문 내에서 유일해야 하며 한 번 사용한 값은 재사용할 수 없습니다. 슬롯 단위 상태머신을 만들기 아주 좋습니다. 예를 들면 `botA-20260417-slot037-buy-r3` 같은 식으로 생성하면 됩니다. ([업비트 개발자 센터][5])

주문 방식은 두 갈래로 나누는 게 좋습니다. **평소 수동적 진입/청산**은 `post_only` 지정가를 우선 쓰고, **급한 재배치나 가격 수정**은 `cancel_and_new`로 처리하는 방식입니다. 업비트의 `post_only`는 즉시 체결될 상황이면 주문을 취소해 maker 주문만 남기게 도와주고, `cancel_and_new`는 기존 주문 취소 완료 후 같은 페어·같은 방향에서 새 주문을 생성하며 `remain_only`로 잔량 재주문도 지원합니다. 다만 `post_only`는 SMP와 함께 쓸 수 없고, `cancel_and_new` 및 주문 생성은 초당 8회 제한을 공유하니 큐와 백오프가 필요합니다. ([업비트 개발자 센터][5])

SMP도 켜둘 가치가 있습니다. 업비트는 `cancel_taker`, `cancel_maker`, `reduce` 세 가지 SMP 모드를 지원하고, `myOrder`에서도 `prevented` 상태로 확인할 수 있습니다. 특히 리프라이싱이 많거나 양방향 주문이 겹칠 수 있는 구조라면 자기 체결 방지 로직이 유용합니다. 다만 routine maker 주문은 `post_only`, 비정상/공격적 흐름은 SMP로 나누는 게 더 낫습니다. ([업비트 개발자 센터][6])

그리고 실주문 전에 `orders/test`를 반드시 붙이세요. 업비트는 실제 주문을 만들지 않고도 형식·주문 가능 상태를 검증하는 주문 테스트 API를 제공합니다. 이걸 프리플라이트 체크에 넣으면, 점검 직후나 페어 상태 이상 시 실제 자금을 건드리지 않고 오류를 미리 잡을 수 있습니다. 운영 중에는 WebSocket과 별도로 `orders/open`으로 30~60초마다 reconciliation을 돌려 누락 이벤트를 보정하면 더 안정적입니다. ([업비트 개발자 센터][7])

추가로, 업비트는 rate limit을 넘기면 429를 반환하고, 계속 밀어붙이면 418로 차단 시간을 줍니다. 심지어 limit을 안 넘겨도 주문 안정화 시스템 때문에 주문이 실패할 수 있다고 안내하므로, **지수 백오프 + jitter 재시도 + dead-letter queue**는 꼭 넣어야 합니다. ([업비트 개발자 센터][8])

## 9) 제가 권하는 v1 설정

첫 프로덕션 릴리스는 이렇게 가는 게 좋습니다.

```yaml
grid_count: 112
band_mode: fixed
k_base: 11.0
k_floor: 8.0

cash_buffer_ratio: 0.30
max_gross_ratio: 0.70

inventory_target:
  q_min: 0.10
  q_max: 0.85
  gamma: 1.5
  epsilon: 0.03

slot_weight:
  upper_third: 0.7
  middle_third: 1.0
  lower_third: 1.3

active_window:
  below_current_slots: 36-48
  above_current_reentry_slots: 0-4

up_buy:
  enabled: false
  optional_rule:
    crossed_up_eq_1_only: true
    max_inventory_ratio: 0.35
    max_band_position_z: 0.55

age_tp_compression:
  after_48h: -0.5_step
  after_7d: -1.0_step

breakout_guard:
  freeze_if_15m_close_outside_band_for_4_bars: true
  recenter_only_if_inventory_ratio_below: 0.20
```

이 조합이면 지금 구조의 장점은 살리고, 가장 큰 약점인 **과재고·자금잠김·추세장 취약성**을 많이 줄일 수 있습니다.

## 10) 딱 하나만 먼저 만들라면

**`q_target(z)` 기반 재고 제어**를 먼저 만드세요.

이유는 간단합니다.

* 그리드 수를 몇 개로 하든
* 슬롯당 금액을 얼마로 하든
* 결국 전략이 무너지는 순간은 “내가 지금 이 가격에서 너무 많이 들고 있느냐”에서 시작합니다

그걸 가장 직접적으로 해결하는 게 목표 재고곡선입니다.

그 다음 순서는:

1. `k` 기반 TP
2. 하단 가중 배분
3. 브레이크아웃 가드
4. WebSocket + identifier + cancel_and_new 엔진
   이 순서가 좋습니다.

원하시는 방향이면 다음 답변에서 바로 **개발 명세서 형태의 상태머신(FSM), DB 스키마, API 호출 순서도**까지 적어드리겠습니다.

[1]: https://arxiv.org/abs/1105.3115?utm_source=chatgpt.com "Dealing with the Inventory Risk. A solution to the market making problem"
[2]: https://docs.upbit.com/kr/reference/rate-limits?utm_source=chatgpt.com "요청 수 제한(Rate Limits)"
[3]: https://docs.upbit.com/kr/docs/krw-market-info "원화(KRW) 마켓 주문 가격 단위 / 최소 주문 가능 금액"
[4]: https://docs.upbit.com/kr/reference/websocket-guide "WebSocket 사용 및 에러 안내"
[5]: https://docs.upbit.com/kr/reference/new-order?utm_source=chatgpt.com "주문 생성"
[6]: https://docs.upbit.com/kr/docs/smp "자전거래 체결 방지(Self-Match Prevention, SMP)"
[7]: https://docs.upbit.com/kr/reference/order-test?utm_source=chatgpt.com "주문 생성 테스트"
[8]: https://docs.upbit.com/kr/reference/rate-limits "요청 수 제한(Rate Limits)"
