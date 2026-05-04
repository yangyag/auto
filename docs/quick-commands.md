# auto 빠른 명령어 모음

기준 위치:
```bash
cd /home/yangyag/auto
```

## 1) 현재 봇 실행 / 종료 / 상태

### 실행
```bash
./run.sh
```

### 종료
```bash
./stop.sh
```

### 실행 중인지 확인
```bash
ps -eo pid,args | grep '[p]ython3 /home/yangyag/auto/main.py'
```

## 2) 로그 보기

### 오늘 로그 마지막 50줄
```bash
tail -n 50 logs/trading-$(date +%F).log
```

### 실시간 로그 보기
```bash
tail -f logs/trading-$(date +%F).log
```

### 최신 날짜 로그 자동 선택 후 실시간 보기
```bash
./tail-latest-log.sh
```

## 3) 업비트 잔고 확인

### 주문 가능 KRW 잔고 1회 조회
```bash
python3 main.py balance
```

## 4) grid.properties 기반으로 DB 그리드 반영

### 네가 `grid.properties` 작성 후 실행할 명령
```bash
python3 scripts/apply_grid_properties_to_postgres.py --force
```

`main.py init-grid`는 슬롯 개수 기반이고, `grid.properties`는 `GRID_COUNT` 또는 `GRID_STEP_PCT` 중 정확히 하나를 쓴다.

이 명령은 기본적으로 아래를 사용한다:
- `grid.properties`
- 현재 `.env`의 `STATE_BOT_KEY`
- 현재 `.env`의 PostgreSQL 접속정보

Phase 2 하단 가중 배분을 확인할 때는 출력의 아래 항목을 같이 본다:
- `planned_buy_budget_total`
- `top_slot_planned_buy_budget`
- `bottom_slot_planned_buy_budget`

하단 가중이 적용된 새 그리드라면 보통 `bottom_slot_planned_buy_budget > top_slot_planned_buy_budget` 이어야 한다.

### 다른 properties 파일을 쓰고 싶을 때
```bash
python3 scripts/apply_grid_properties_to_postgres.py --properties-file my-grid.properties --force
```

## 5) 현재 그리드 슬롯 상태 바로 보기

### 현재 DB 상태 출력
```bash
python3 scripts/show_grid_state.py
```

이 명령은 기본적으로 아래를 사용한다:
- `.env`의 `STATE_BOT_KEY`
- `.env`의 `PGSCHEMA`
- PostgreSQL 접속정보

출력에는 조회 source, 슬롯별 `buy/held/sell/planned/planned_krw/status`, 총재고, 상단/하단/총 계획매수금액 요약이 포함된다.

### 실현 손익 조회 (KRW-BTC, 업비트 API 기준)
```bash
./scripts/upbit_realized_pnl.py [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--period daily|weekly|monthly|yearly|all] [--reset-sell-uuid UUID]
```

기본 최근 90일, period=all (일/주/월/년/전체). 업비트 `GET /v1/orders/closed` 와 `/v1/order` 만 사용하는 read-only 분석. 매수/매도 FIFO 매칭으로 수수료 차감 순손익을 산출하며, 매칭되지 않는 매도(윈도우 시작 이전 매수분)는 별도 라인으로 분리. 기간은 2자리 연도 형식으로 표시하며, 주간 기간은 `26-04-20 ~ 26-04-26` 처럼 출력한다.

`reset_krw_btc_live.py` 로 발생한 reset 전량 시장가 매도는 `{STATE_BOT_KEY}-reset-sell-...` identifier 로 자동 인식된다. 코드 반영 전 발생한 과거 reset 매도처럼 identifier 가 없는 청산 주문은 `--reset-sell-uuid <UUID>` 를 반복 지정해서 reset 청산 경계로 포함한다.

## 6) 테스트

### 전체 테스트
```bash
python3 -m unittest discover -s tests -v
```

### properties 관련 테스트만
```bash
python3 -m unittest tests.test_grid_properties tests.test_apply_grid_properties_script -v
```

### postgres 관련 테스트만
```bash
python3 -m unittest tests.test_postgres_grid_repository tests.test_postgres_order_repository tests.test_postgres_runtime_lock -v
```

### 상태 조회 스크립트 테스트만
```bash
python3 -m unittest tests.test_show_grid_state_script -v
```

## 7) 설정 확인

### 현재 상태 저장 backend 확인
```bash
python3 - <<'PY'
import app.config.settings as cfg
print(cfg.STATE_BOT_KEY)
print(cfg.PGHOST, cfg.PGPORT, cfg.PGDATABASE, cfg.PGUSER, cfg.PGSCHEMA)
PY
```

### 현재가 WebSocket 이벤트 루프 설정 확인
```bash
python3 - <<'PY'
import app.config.settings as cfg
print("UPBIT_WS_PUBLIC_ENABLED=", cfg.UPBIT_WS_PUBLIC_ENABLED)
print("UPBIT_WS_EVENT_LOOP_ENABLED=", cfg.UPBIT_WS_EVENT_LOOP_ENABLED)
print("UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=", cfg.UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS)
print("PRICE_POLL_INTERVAL=", cfg.PRICE_POLL_INTERVAL)
PY
```

기본값은 public ticker WebSocket 이벤트 루프 사용, 전략 평가 최소 3초 간격, 장애 시 5초 REST polling fallback 이다.

## 8) grid.properties 예시

```properties
MIN_BUY_PRICE=91623000
MAX_BUY_PRICE=127886000
TOTAL_BUDGET_KRW=4000000
GRID_STEP_PCT=1.770527625862
TP_MODEL=k
TP_K_BASE=9.0
TP_K_FLOOR=7.0
```

의미:
- `MIN_BUY_PRICE`: 최하단 슬롯 buy_price
- `MAX_BUY_PRICE`: 최상단 슬롯 buy_price
- `TOTAL_BUDGET_KRW`: 그리드 전체에 배정할 총예산
- `GRID_COUNT`: 슬롯 개수
- `GRID_STEP_PCT`: 슬롯 간격 비율
- `TP_MODEL`: TP 계산 모드, 현재 운영 기준은 `k`
- `TP_K_BASE`: 기본 TP `k`
- `TP_K_FLOOR`: Age TP 최저 `k`

주의:
- `grid.properties`는 `GRID_COUNT` 또는 `GRID_STEP_PCT` 중 정확히 하나만 둔다.
- `MIN_BUY_PRICE`, `MAX_BUY_PRICE`는 업비트 호가 단위에 맞는 값으로 넣어야 한다.
- 안 맞으면 스크립트가 에러를 낸다.

## 9) 제일 자주 쓸 명령 3개

### 그리드 반영
```bash
python3 scripts/apply_grid_properties_to_postgres.py --force
```

### 현재 상태 보기
```bash
python3 scripts/show_grid_state.py
```

### 로그 확인
```bash
tail -f logs/trading-$(date +%F).log
```

### 재시작
```bash
./stop.sh && ./run.sh
```

## 10) KRW-BTC 라이브 리셋 후 새 그리드 반영

```bash
.venv/bin/python scripts/reset_krw_btc_live.py
```

이 명령은 아래를 순서대로 수행한다:
- `./stop.sh`
- 업비트 `KRW-BTC` 미체결 주문 취소
- BTC 전량 시장가 매도
- `grid.properties` 기준 DB 그리드 재반영
- 상태 출력

재시작은 자동으로 하지 않는다. 결과 확인 후 필요하면 직접 실행한다:

```bash
./run.sh
```

전량 시장가 매도 주문에는 reset 전용 identifier 가 붙으므로, 이후 `scripts/upbit_realized_pnl.py` 에서 옵션 없이 reset 청산 손익에 포함된다.
