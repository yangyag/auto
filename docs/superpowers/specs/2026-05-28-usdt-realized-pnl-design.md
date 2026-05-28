# USDT 실현손익 리포트 개편 설계

## 배경

운영 대상이 `KRW-BTC`에서 `KRW-USDT`로 전환되었고, EC2 운영 환경도 `SYMBOL=KRW-USDT`, `STATE_BOT_KEY=krw-usdt-live`를 사용한다. 그러나 `scripts/upbit_realized_pnl.py`는 기본 마켓이 `KRW-BTC`로 고정되어 있어 옵션 없이 실행하면 새 USDT 운영 손익을 조회하지 못한다. 출력 라벨도 `BTC` 수량 기준이라 USDT 운영 결과와 맞지 않는다.

## 목표

- 옵션 없이 실행하면 현재 설정(`cfg.SYMBOL`) 기준 마켓을 조회한다.
- EC2에서는 기본 실행만으로 `KRW-USDT`와 `krw-usdt-live` 기준 실현손익을 집계한다.
- 수량 출력 라벨은 마켓의 base currency를 사용한다. 예: `KRW-USDT`는 `매도수량(USDT)`, `KRW-BTC`는 `매도수량(BTC)`.
- 기존 BTC 손익 분석은 명시 옵션으로 계속 가능해야 한다.

## 제외 범위

- 과거 BTC와 새 USDT 손익을 한 번에 합산하는 통합 리포트는 만들지 않는다.
- Upbit API 조회 방식, 슬롯별 FIFO 매칭 알고리즘, reset 청산 매칭 알고리즘은 바꾸지 않는다.
- 원본 HTML 문서 재생성은 하지 않는다. Markdown 문서와 테스트만 갱신한다.

## 접근

### 기본 마켓

`DEFAULT_MARKET`를 `KRW-BTC` 고정값에서 `cfg.SYMBOL` 기반으로 변경한다. `.env`가 없는 개발 환경에서는 `cfg.SYMBOL` 기본값이 여전히 `KRW-BTC`이므로 기존 호환성이 유지된다.

```python
DEFAULT_MARKET = cfg.SYMBOL
```

### 수량 단위

마켓 코드를 `QUOTE-BASE`로 파싱하는 작은 헬퍼를 둔다.

```python
def market_base_currency(market: str) -> str:
    return market.split("-", 1)[1].upper()
```

출력 함수는 `quantity_label` 또는 `base_currency`를 인자로 받아 헤더와 상세 라벨에 반영한다.

예:

```text
매도수량(USDT)
잔여수량(USDT)
qty=123.45678901 USDT
```

수량의 소수점 포맷은 기존 8자리 고정 포맷을 유지한다. 업비트 KRW 마켓의 수량 step과 기존 저장소 수량 포맷이 8자리 기준으로 맞춰져 있어, 이번 변경에서 자산별 소수점 정책까지 확장하지 않는다.

### 기존 BTC 조회

BTC 손익 조회가 필요하면 환경변수와 옵션을 명시한다.

```bash
STATE_BOT_KEY=krw-btc-live .venv/bin/python scripts/upbit_realized_pnl.py --market KRW-BTC
```

새 USDT 운영 기본 조회는 아래처럼 실행한다.

```bash
.venv/bin/python scripts/upbit_realized_pnl.py
```

### 문서

`README.md`와 `docs/quick-commands.md`에서 `upbit_realized_pnl.py` 설명을 `KRW-BTC` 고정 문구에서 현재 `SYMBOL` 기준으로 갱신한다. 기존 BTC 조회 방법은 명시 옵션 예시로 남긴다.

## 테스트

- `.env` 또는 monkeypatch로 `cfg.SYMBOL=KRW-USDT`일 때 parser 기본 `--market` 값이 `KRW-USDT`인지 검증한다.
- `KRW-USDT` 리포트 출력 헤더가 `매도수량(USDT)`를 사용하는지 검증한다.
- `KRW-BTC`를 명시하면 기존 `매도수량(BTC)` 출력이 유지되는지 검증한다.
- 기존 FIFO 및 reset 매칭 테스트는 그대로 통과해야 한다.

## 운영 확인

구현 후 EC2에서 아래 순서로 확인한다.

```bash
cd /home/ubuntu/auto
.venv/bin/python scripts/upbit_realized_pnl.py --period d
```

출력 첫 줄의 마켓이 `KRW-USDT`이고, 표 헤더가 `매도수량(USDT)`이면 기본 조회 대상이 새 운영 기준으로 전환된 것이다.
