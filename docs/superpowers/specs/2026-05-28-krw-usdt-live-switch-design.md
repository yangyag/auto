# KRW-USDT 라이브 전환 설계

## 배경

현재 봇은 `KRW-BTC` 운영을 기준으로 작성되어 있으며, 최근 `scripts/reset_krw_btc_live.py`로 BTC 포지션을 전량 청산한 상태다. 다음 운영 대상은 업비트 `KRW-USDT` 마켓이며, 기존 BTC 운영 이력과 분리하기 위해 새 `STATE_BOT_KEY`를 사용한다.

## 목표

- 운영 심볼을 `KRW-USDT`로 바꾼다.
- 새 상태 키는 `krw-usdt-live-local`을 사용한다.
- 그리드 매수 범위는 1430원부터 1530원까지로 설정한다.
- 총 배정 예산은 기존과 동일하게 6,000,000 KRW로 유지한다.
- 기존 BTC 상태, 주문 identifier 이력, 손익 분석 경계를 새 USDT 운영 상태와 섞지 않는다.

## 제외 범위

- 기존 BTC 주문 및 잔고를 다시 청산하는 작업은 하지 않는다. 사용자가 이미 `scripts/reset_krw_btc_live.py`로 청산했다.
- USDT 전용 손익 리포트 문구나 모바일 UI의 `BTC` 라벨 정리는 이번 전환의 필수 조건으로 보지 않는다.
- 운영 봇 자동 재시작은 하지 않는다. 설정과 DB 반영 후 사용자가 직접 실행 여부를 결정한다.

## 접근

### 설정

`app/config/settings.py`의 `SYMBOL`을 환경변수에서 읽도록 바꾼다. 기본값은 기존 호환성을 위해 `KRW-BTC`로 유지한다.

```python
SYMBOL = os.getenv("SYMBOL", "KRW-BTC")
```

로컬 `.env`에는 아래 값을 반영한다.

```bash
SYMBOL=KRW-USDT
STATE_BOT_KEY=krw-usdt-live-local
```

### 그리드 입력값

`grid.properties`는 아래 운영 값으로 변경한다.

```properties
MIN_BUY_PRICE=1430
MAX_BUY_PRICE=1530
TOTAL_BUDGET_KRW=6000000
GRID_STEP_PCT=0.2
```

TP 모델과 손절 설정은 기존 값을 유지한다.

### DB 반영

설정 변경 후에는 아래 명령으로 새 bot key의 PostgreSQL 그리드를 생성 또는 덮어쓴다.

```bash
.venv/bin/python scripts/apply_grid_properties_to_postgres.py --force
```

`cfg.SYMBOL`과 `cfg.STATE_BOT_KEY`가 `.env`에서 로드되므로, 별도 `--symbol`/`--bot-key` 인자를 넘기지 않아도 `KRW-USDT`와 `krw-usdt-live-local`이 적용되어야 한다.

### 리셋 스크립트

`scripts/reset_krw_btc_live.py`는 이름과 가드가 BTC 전용이므로 이번 USDT 전환 경로에서는 사용하지 않는다. 이미 BTC 청산이 끝난 뒤 새 USDT 상태를 만드는 작업은 `apply_grid_properties_to_postgres.py --force` 경로가 더 명확하다.

## 검증

- `tests/test_settings_env.py`에 `SYMBOL` 환경변수 로드 검증을 추가한다.
- `grid.properties`를 파싱해 `KRW-USDT` 가격대에서 슬롯이 정상 생성되는지 확인한다.
- `.env`의 `SYMBOL`/`STATE_BOT_KEY` 값이 기대값인지 확인한다.
- `apply_grid_properties_to_postgres.py --force` 실행 후 `scripts/show_grid_state.py` 출력에서 `symbol: KRW-USDT`와 새 bot key 상태가 반영됐는지 확인한다.

## 운영 주의

- `KRW-USDT` 현재가가 1430~1530 범위 밖으로 벗어난 상태에서 봇을 시작하면 매수/매도 후보 판단이 즉시 달라질 수 있으므로, 시작 직전 현재가를 다시 확인한다.
- 기존 `krw-btc-live-local` 상태는 보존한다. 되돌림이 필요하면 `.env`의 `SYMBOL`과 `STATE_BOT_KEY`를 기존 값으로 돌리고 해당 bot key 상태를 조회한다.
