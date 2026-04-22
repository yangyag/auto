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

## 5) 현재 DB 상태를 export

### 기본 export 파일 생성
```bash
python3 scripts/export_postgres_grid.py
```

기본 출력 파일:
```text
grid.postgres-export.txt
```

### 파일명을 직접 지정
```bash
python3 scripts/export_postgres_grid.py --output my-grid-export.txt
```

## 6) 현재 그리드 슬롯 상태 바로 보기

### 현재 DB 상태 출력
```bash
python3 scripts/show_grid_state.py
```

이 명령은 기본적으로 아래를 사용한다:
- `.env`의 `STATE_BOT_KEY`
- `.env`의 `PGSCHEMA`
- PostgreSQL 접속정보

출력에는 조회 source, 슬롯별 `buy/held/sell/planned/planned_krw/status`, 총재고, 상단/하단/총 계획매수금액 요약이 포함된다.

## 7) 테스트

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

## 8) 설정 확인

### 현재 상태 저장 backend 확인
```bash
python3 - <<'PY'
import config.settings as cfg
print(cfg.STATE_BOT_KEY)
print(cfg.PGHOST, cfg.PGPORT, cfg.PGDATABASE, cfg.PGUSER, cfg.PGSCHEMA)
PY
```

## 9) grid.properties 예시

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

## 10) 제일 자주 쓸 명령 3개

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

## 11) KRW-BTC 라이브 리셋 후 새 그리드 반영

```bash
.venv/bin/python scripts/reset_krw_btc_live.py
```

이 명령은 아래를 순서대로 수행한다:
- `./stop.sh`
- 업비트 `KRW-BTC` 미체결 주문 취소
- BTC 전량 시장가 매도
- `grid.properties` 기준 DB 그리드 재반영
- 상태 출력
- `./run.sh`
