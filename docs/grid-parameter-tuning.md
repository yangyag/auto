# grid.properties 파라미터 튜닝 가이드

`MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `BUY_AMOUNT_KRW`를 바꿀 때마다 `GRID_COUNT`와 `SELL_PERCENT`를 다시 감으로 정하지 않고, 같은 방식으로 비교하기 위한 문서다.

이 문서는 현재 코드 기준 규칙을 그대로 따른다.

- 슬롯 생성 규칙: [core/grid_properties.py](/home/yangyag/auto/core/grid_properties.py:25)
- 전략 트리거 규칙: [strategy/grid_strategy.py](/home/yangyag/auto/strategy/grid_strategy.py:24)
- 주문 실행/체결 반영 순서: [main.py](/home/yangyag/auto/main.py:333)

## 1) 비교 전에 고정할 값

튜닝을 시작할 때 아래 값을 먼저 고정해야 한다.

- 상단/하단 가격: `MIN_BUY_PRICE`, `MAX_BUY_PRICE`
- 슬롯당 예산: `BUY_AMOUNT_KRW`
- 시작 가격: 비교를 시작할 현재 가격
- 가격 경로: 어떤 식으로 움직였다고 가정할지
- 자금 상한: 최대 얼마까지 묶여도 되는지
- 수수료 반영 여부

이 값이 바뀌면 최적 조합도 같이 바뀐다.  
즉 `GRID_COUNT`와 `SELL_PERCENT`만 따로 떼어서 최적값을 외우면 안 된다.

## 2) 현재 코드가 실제로 계산하는 규칙

### 슬롯 생성

- `buy_price`는 `MAX_BUY_PRICE`부터 `MIN_BUY_PRICE`까지 기하비율로 나눈다.
- 각 `buy_price`는 업비트 KRW 호가 단위로 보정된다.
- `sell_price = buy_price * (1 + SELL_PERCENT / 100)` 후 다시 호가 단위로 보정된다.
- 총예산은 `BUY_AMOUNT_KRW * GRID_COUNT` 로 보고, 슬롯별 예산은 상단/중단/하단 `0.7x / 1.0x / 1.3x` 가중치를 실제 슬롯 수에 맞춰 정규화해 나눈다.
- `planned_qty = slot_budget / buy_price`를 BTC 최소 step 단위로 내림한다.

### 전략 평가

- 하락 시: `previous_price > buy_price >= current_price` 인 empty 슬롯은 모두 지정가 매수 후보가 된다.
- 상승 시: `previous_price < buy_price <= current_price` 인 empty 슬롯이 한 poll 동안 정확히 1개일 때만 그 슬롯을 시장가 예산매수한다.
- 상승 시 여러 슬롯을 한 번에 뛰어넘으면 그 상승 구간 매수는 모두 건너뛴다.
- 보유 슬롯은 `current_price >= sell_price` 이면 즉시 매도 후보가 된다.

### 손익 비교 기준

같은 가격 경로를 기준으로 아래 값을 비교한다.

- `net pnl`: 최종 순손익
- `tied capital`: 경로 중간에 다시 가격이 돌아왔을 때 실제로 묶여 있는 원금
- `roi on tied capital`: `net pnl / tied capital`

이 문서에서는 아래처럼 계산한다.

- `실현손익`
- `+ 마지막 시점 보유분 평가손익`
- `- 시작 시점 이미 들고 있던 보유분의 평가 기준값`

### 쉬운 해석: `GRID_COUNT`와 `SELL_PERCENT`를 한 번에 보는 법

외부 자문 내용을 가장 쉽게 줄이면, 결국 봐야 하는 값은 `k` 하나다.

```text
Δ = 한 칸 간격
η = 매도까지 필요한 로그 거리
k = η / Δ
```

여기서 직관은 아래처럼 이해하면 된다.

- `GRID_COUNT`를 늘리면 한 칸 간격 `Δ`가 작아진다.
- `SELL_PERCENT`를 늘리면 매도까지 필요한 거리 `η`가 커진다.
- 그래서 `k`는 "한 번 매수한 뒤 몇 칸 정도 올라와야 매도되는가"를 뜻한다.

즉 `k`는 아래 두 질문을 한 번에 묶은 값이다.

- 그리드가 얼마나 촘촘한가
- 매도 목표가가 얼마나 먼가

이 문서 기준 범위에서는 대략 이렇게 읽으면 된다.

- `k`가 너무 작다: 너무 빨리 팔아서 회전은 많지만 슬롯당 이익이 얇아진다.
- `k`가 적당하다: 회전과 이익 폭이 균형을 이룬다.
- `k`가 너무 크다: 너무 멀리 팔려고 해서 자금이 오래 묶이고 회전이 둔해진다.

현재 범위에서는 자문 내용을 기준으로 `k ≈ 10 ~ 12` 정도를 가장 자연스러운 균형대로 봐도 된다.

예시:

| 조합 | 한 칸 간격 | `k` 해석 |
| --- | ---: | ---: |
| `112 / 3.0%` | 약 `0.3009%` | `9.84` |
| `122 / 3.0%` | 약 `0.2760%` | `10.73` |
| `122 / 3.2%` | 약 `0.2760%` | `11.43` |
| `122 / 3.3%` | 약 `0.2760%` | `11.78` |
| `140 / 3.2%` | 약 `0.2402%` | `13.13` |

이 표를 쉬운 말로 읽으면:

- `122 / 3.2%`는 "조금 촘촘하고, 매도는 약간 여유 있게 잡은" 균형형이다.
- `112 / 3.0%`는 "조금 덜 촘촘하고, 매도도 가까운" 보수형이다.
- `140 / 3.2%`는 "아주 촘촘한데 매도도 멀다"라서, 단순 업그레이드라기보다 자금이 더 오래 묶일 수 있는 공격형에 가깝다.

그래서 이 범위에서는 아래처럼 읽는 편이 쉽다.

- 보수형: `112 / 3.0%`
- 균형형: `122 / 3.1 ~ 3.2%`
- 공격형: `140 / 3.2%`

중요한 점은 `GRID_COUNT`만 늘린다고 무조건 좋아지지 않는다는 것이다.  
지금 전략은 상승 시 다중 상향 돌파를 건너뛰기 때문에, 그리드가 너무 촘촘하면 상승에서는 놓치는 구간이 늘고 하락에서는 보유만 빨리 쌓일 수 있다.

## 3) 비교할 가격 경로를 먼저 정한다

같은 파라미터라도 어떤 장세를 가정하느냐에 따라 결과가 바뀐다.  
그래서 반드시 가격 경로를 먼저 고정해야 한다.

예시 경로:

- 시작가 `P0`
- 1차 상승: `P0 -> 1.06 * P0`
- 복귀: `1.06 * P0 -> P0`
- 2차 상승: `P0 -> 1.03 * P0`

이 경로는 아래 의미를 가진다.

- 첫 상승에서 얼마나 잘 파는지
- 다시 내려왔을 때 얼마나 많이 다시 물리는지
- 마지막 반등에서 얼마나 다시 회전하는지

다른 장세를 보고 싶으면 경로만 바꾸면 된다.

- 급락 후 약반등
- 박스권 왕복
- 천천히 상승 후 급락

중요한 점:

- 같은 경로를 모든 조합에 똑같이 적용해야 공정하다.
- `GRID_COUNT`를 바꾸면 시작 시점에 들고 있는 슬롯 번호도 달라질 수 있다.

## 4) 바로 재사용 가능한 비교 스니펫

이 스니펫은 `천천히 움직여 각 슬롯을 순차적으로 보게 되는 경로`를 비교할 때 쓰는 기본형이다.

- 천천히 상승해서 회전이 많이 일어나는 경우
- 천천히 하락해서 하단 슬롯이 차례로 다시 채워지는 경우
- 다시 천천히 반등하는 경우

반대로 `한 poll 안에 여러 슬롯을 급등/급락으로 건너뛰는 경우`는 별도 테스트 케이스로 다시 확인해야 한다.  
그 경우에는 아래 스니펫의 `PEAK`, `RETURN`, `FINAL` 같은 경로를 더 거칠게 두거나, 아예 poll 단위 `PRICE_PATH`를 직접 만들어 검증하는 편이 안전하다.

아래 스니펫은 현재 코드의 슬롯 생성 규칙을 그대로 사용해서 `GRID_COUNT`와 `SELL_PERCENT` 범위를 훑는다.

```bash
python3 - <<'PY'
from decimal import Decimal

from core.grid_properties import GridPropertySpec, build_grid_rows_from_property_spec

MIN_BUY = Decimal("91623000")
MAX_BUY = Decimal("127886000")
BUY_AMOUNT = Decimal("100000")

CURRENT = Decimal("110713000")
PEAK = CURRENT * Decimal("1.06")
RETURN = CURRENT
FINAL = CURRENT * Decimal("1.03")

GRID_COUNTS = range(80, 141, 2)
SELL_PERCENTS = [Decimal(i) / Decimal("10") for i in range(20, 51)]  # 2.0% ~ 5.0%


class RowState:
    def __init__(self, index, buy, sell, qty):
        self.index = index
        self.buy = buy
        self.sell = sell
        self.qty = qty
        self.holding = False


def simulate(grid_count: int, sell_percent: Decimal) -> dict:
    spec = GridPropertySpec(
        min_buy_price=MIN_BUY,
        max_buy_price=MAX_BUY,
        buy_amount_krw=BUY_AMOUNT,
        grid_count=grid_count,
        sell_percent=sell_percent,
    )
    rows = build_grid_rows_from_property_spec(spec)
    states = [RowState(r.index, r.buy_price, r.sell_price, r.planned_qty) for r in rows]

    # 현재가 이하 슬롯 중 상단 2개를 시작 보유분으로 가정한다.
    eligible = [row for row in states if row.buy <= CURRENT]
    eligible.sort(key=lambda row: row.buy, reverse=True)
    for row in eligible[:2]:
        row.holding = True

    start_equity = sum(CURRENT * row.qty for row in states if row.holding)
    cash = Decimal("0")

    def rise(start: Decimal, end: Decimal) -> None:
        nonlocal cash

        # 아래는 "천천히 움직여 각 슬롯이 순차적으로 체결된다"는 경로를 가정한다.
        for row in [row for row in states if (not row.holding) and start < row.buy <= end]:
            row.holding = True
            cash -= row.buy * row.qty

        for row in [row for row in states if row.holding and row.sell <= end]:
            row.holding = False
            cash += row.sell * row.qty

    def fall(start: Decimal, end: Decimal) -> None:
        nonlocal cash

        for row in [row for row in states if (not row.holding) and end <= row.buy < start]:
            row.holding = True
            cash -= row.buy * row.qty

    rise(CURRENT, PEAK)
    fall(PEAK, RETURN)
    tied_capital = sum(row.buy * row.qty for row in states if row.holding)
    rise(RETURN, FINAL)

    final_equity = cash + sum(FINAL * row.qty for row in states if row.holding)
    net_pnl = final_equity - start_equity

    return {
        "grid": grid_count,
        "sell": sell_percent,
        "net": net_pnl,
        "tied": tied_capital,
        "roi": (net_pnl / tied_capital) if tied_capital else Decimal("0"),
        "open_slots": sum(1 for row in states if row.holding),
    }


cases = []
for grid_count in GRID_COUNTS:
    for sell_percent in SELL_PERCENTS:
        try:
            cases.append(simulate(grid_count, sell_percent))
        except Exception:
            continue


print("TOP_NET")
for row in sorted(cases, key=lambda item: item["net"], reverse=True)[:10]:
    print(
        f'grid={row["grid"]} sell={row["sell"]}% '
        f'net={row["net"]:.2f} tied={row["tied"]:.2f} roi={row["roi"]*100:.3f}%'
    )

print()
print("TOP_ROI_UNDER_2_2M")
for row in sorted(
    [item for item in cases if item["tied"] <= Decimal("2200000")],
    key=lambda item: item["roi"],
    reverse=True,
)[:10]:
    print(
        f'grid={row["grid"]} sell={row["sell"]}% '
        f'net={row["net"]:.2f} tied={row["tied"]:.2f} roi={row["roi"]*100:.3f}%'
    )
PY
```

### 입력값을 바꿀 때 수정할 부분

- 상단/하단 가격을 바꾸면 `MIN_BUY`, `MAX_BUY`
- 슬롯당 예산을 바꾸면 `BUY_AMOUNT`
- 시작 가격을 바꾸면 `CURRENT`
- 가격 경로를 바꾸면 `PEAK`, `RETURN`, `FINAL`
- 비교 범위를 바꾸면 `GRID_COUNTS`, `SELL_PERCENTS`

### 결과 해석 방법

- `TOP_NET`: 절대 수익이 가장 큰 조합
- `TOP_ROI_UNDER_2_2M`: 자금 상한 안에서 자금 효율이 좋은 조합
- `tied`: 중간에 다시 물렸을 때 실제로 묶이는 원금

실전에서는 아래 셋을 같이 본다.

- 절대 수익 1위
- 자금 효율 1위
- 현재 계좌 규모에서 감당 가능한 자금 상한 안의 균형형

## 5) 권장 테스트 케이스

튜닝할 때는 최소한 아래 케이스를 같이 본다.

### 케이스 A: 느린 상승 -> 복귀 -> 느린 재상승

- 목적: 회전이 잘 되는 조합 찾기
- 예시 경로: `P0 -> 1.06P0 -> P0 -> 1.03P0`
- 비교 지표: `net pnl`, `tied capital`, `roi`

### 케이스 B: 한 poll 급등

- 목적: 상향 다중 돌파 skip 영향 확인
- 예시 경로: `[P0, 1.06P0]`
- 확인 포인트: 중간 슬롯이 실제로 건너뛰어지는지, 보유분만 매도되는지

### 케이스 C: 한 poll 급락

- 목적: 하락 다중 교차 동시 매수 영향 확인
- 예시 경로: `[P0, 0.94P0]`
- 확인 포인트: 내려오며 통과한 empty 슬롯들이 한 번에 얼마나 채워지는지

### 케이스 D: 자금 상한 필터

- 목적: 절대 수익보다 계좌 부담을 우선할 때 후보를 좁히기
- 예시 기준: `tied capital <= 2,000,000`, `<= 2,200,000`처럼 잘라서 다시 정렬

`GRID_COUNT`와 `SELL_PERCENT`는 케이스 A만 보고 정하지 말고, B/C에서도 같이 버틸 수 있는지 확인해야 한다.

## 6) 현재 문서 기준 예시 해석

예를 들어 아래처럼 읽으면 된다.

- `112 / 3.0%`보다 `122 / 3.0%`가 순손익은 더 좋다.
- 하지만 그만큼 `tied capital`도 함께 커진다.
- `140 / 3.2%`가 절대 수익이 좋아 보여도, 계좌 규모가 작으면 효율이 나빠질 수 있다.

외부 자문 내용을 기준으로 더 쉽게 풀면:

- `122 / 3.2%`는 지금 범위에서 `k`가 약 `11.43`이라, "너무 짧지도 너무 길지도 않은" 쪽에 들어간다.
- `140 / 3.2%`는 `k`가 약 `13.13`이라, 더 촘촘한데 매도까지는 더 오래 기다리는 구조가 된다.
- 그래서 `140 / 3.2%`는 "더 정교한 버전"이라기보다 "자금을 더 오래 태워서 더 길게 먹는 버전"에 가깝다.
- 반대로 `122 / 3.2%`는 "회전도 너무 죽지 않고, 슬롯당 이익도 너무 얇지 않은" 균형형으로 읽을 수 있다.

문서 기준 기본 추천을 한 줄로 정리하면:

- 자금 여유가 보통이면 `122 / 3.1 ~ 3.2%`
- 더 보수적으로 가면 `112 / 3.0%`
- 자금이 충분하고 공격적으로 굴리면 `140 / 3.2%`, 다만 과밀 여부를 실제 로그로 다시 확인

즉 정답은 항상 하나가 아니라 아래 셋 중 하나다.

- 절대 수익이 가장 큰 조합
- 자금 효율이 가장 좋은 조합
- 내 자금 상한 안에서 가장 괜찮은 균형형 조합

## 7) 운영상 주의사항

- 이 비교는 기본적으로 수수료 제외 기준이다. 실전 판단 전에는 업비트 수수료를 반영해 다시 보는 편이 안전하다.
- `SELL_PERCENT=3.2` 같은 소수점 퍼센트는 현재 코드에서 지원된다.
- 다만 `sell_price`는 업비트 호가 단위로 보정되므로 실제 수익률은 정확히 `3.2000%`가 아니라 근처 값이 된다.
- 전략 규칙이 바뀌면 이 문서의 스니펫도 함께 갱신해야 한다.
- 특히 상승 시 다중 상향 돌파 skip 규칙을 다르게 바꾸면, 과거 비교 결과는 그대로 재사용하면 안 된다.

## 8) 최소 검증 체크리스트

파라미터를 새로 정한 뒤에는 아래 순서로 확인한다.

```bash
python3 -c "from core.grid_properties import load_grid_property_spec, build_grid_rows_from_property_spec; spec = load_grid_property_spec('grid.properties'); rows = build_grid_rows_from_property_spec(spec); print(spec.grid_count, spec.sell_percent, len(rows))"

python3 scripts/show_grid_state.py

python3 scripts/apply_grid_properties_to_postgres.py --force
```

실거래 재시작 전에는 반드시 아래도 같이 본다.

- 내가 감당 가능한 `tied capital`인지
- `SELL_PERCENT`가 너무 커서 회전이 죽지 않는지
- `GRID_COUNT`가 너무 커서 자금이 과도하게 분산되지 않는지
