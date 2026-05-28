# USDT Open Sell Monitor Design

## Goal

`scripts/upbit_open_sell_monitor.py`가 현재 설정된 마켓에 맞춰 수량 라벨을 표시하도록 바꾼다. `KRW-USDT` 환경에서는 매도 대기 표가 `qty(USDT)`로 보여야 하고, 과거 `KRW-BTC` 장부 조회도 명시 옵션으로 계속 가능해야 한다.

## Scope

변경 범위는 읽기 전용 출력과 문서로 제한한다. 미체결 주문 조회, closed orders 조회, 슬롯 FIFO 매칭, 매수원가 계산, 미실현 손익 계산식은 그대로 둔다.

## Design

기존 `scripts.upbit_realized_pnl.market_base_currency()`를 재사용해 `KRW-USDT`에서 `USDT`, `KRW-BTC`에서 `BTC`를 얻는다. `print_open_sell_summary()`는 `market` 인자를 이미 받으므로 출력 직전에 기초자산 라벨을 계산하고 헤더의 `qty(BTC)`를 `qty(<base>)`로 바꾼다.

수량 포매터는 기초자산 수량 포맷터로 중립화하되 기존 계산 정밀도인 8자리 소수 출력은 유지한다. `--market` 기본값은 이미 `pnl.DEFAULT_MARKET`, 즉 `cfg.SYMBOL` 기반이므로 동작은 유지하고 테스트로 고정한다.

## Tests

새 테스트 파일 `tests/test_upbit_open_sell_monitor.py`를 추가한다. 테스트는 `cfg.SYMBOL`을 `KRW-USDT`로 패치했을 때 parser 기본 마켓이 USDT가 되는지, `print_open_sell_summary()`가 `qty(USDT)`를 출력하고 `qty(BTC)`를 출력하지 않는지 검증한다.

## Documentation

`README.md`와 `docs/quick-commands.md`의 open sell monitor 설명을 현재 `SYMBOL` 기준으로 바꾸고, 과거 BTC 장부 조회 예시는 `--market KRW-BTC --bot-key krw-btc-live`로 명시한다.
