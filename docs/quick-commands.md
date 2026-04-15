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

이 명령은 기본적으로 아래를 사용한다:
- `grid.properties`
- 현재 `.env`의 `STATE_BOT_KEY`
- 현재 `.env`의 PostgreSQL 접속정보

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

출력에는 조회 source, 슬롯별 `buy/held/sell/planned/status`, 총재고가 포함된다.

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
BUY_AMOUNT_KRW=200000
GRID_COUNT=20
SELL_PERCENT=5
```

의미:
- `MIN_BUY_PRICE`: 최하단 슬롯 buy_price
- `MAX_BUY_PRICE`: 최상단 슬롯 buy_price
- `BUY_AMOUNT_KRW`: 각 슬롯별 목표 매수금액
- `GRID_COUNT`: 슬롯 개수
- `SELL_PERCENT`: 매도 퍼센트, `5`는 `5%`를 뜻함

주의:
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
