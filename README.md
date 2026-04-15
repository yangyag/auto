# auto

Python 기반 그리드 자동매매 시스템이다. 현재 운영 기준 경로는 업비트 `KRW-BTC`이며, 빈 슬롯/보유 슬롯의 가격 교차를 감지해 주문을 접수하고, 업비트 주문 상태가 `done`으로 확인될 때만 상태 저장소를 갱신한다.

이 README는 `docs/current-status.md`를 대체하는 루트 문서이며, 2026-04-14 기준으로 전체 소스를 다시 읽어 현재 구조와 남은 작업 지점을 정리한 내용이다. 일회성 PID, 로그 끝줄 같은 런타임 스냅샷은 제외하고 소스 기준으로 유지 가능한 정보만 남겼다.

## 현재 상태 요약

- 현재 핵심 경로는 `exchange/crypto.py` 기반 업비트 연동이다.
- `config/settings.py` 기본 설정은 `EXCHANGE_TYPE = "crypto"`, `SYMBOL = "KRW-BTC"`다.
- 상태 저장은 `file`/`postgres` 두 백엔드를 지원한다.
- 전략은 가격 절대값이 아니라 직전 가격 대비 `buy_price`/`sell_price` 교차 여부로 주문을 만든다.
- 상승 교차 매수는 업비트 `ord_type=price` 시장가 매수, 하락 교차 매수와 매도는 지정가 주문으로 처리한다.
- 주문 접수만으로는 그리드 상태를 바꾸지 않고, `GET /v1/order` 재조회 결과가 `done`일 때만 반영한다.
- `grid.txt` 외부 수정 감지 후 런타임 재로드가 가능하다.
- `run.sh` / `stop.sh` 기반 백그라운드 실행과 `logs/trading-YYYY-MM-DD.log` 날짜별 로그가 준비되어 있다.
- PostgreSQL 저장소, pending order 영속화, 단일 실행 advisory lock, 관련 마이그레이션/테스트가 이미 들어와 있다.

## 현재 추적 중인 기본 운영 데이터

- 현재 저장소의 `grid.txt`는 `KRW-BTC` 20개 슬롯 구조다.
- 현재 추적 파일 기준으로는 20개 슬롯이 모두 빈 슬롯이며 총재고는 `0 BTC`다.
- 현재 추적 파일 기준 총 배정 금액은 `3,999,987.10096 KRW`다.
- `GRID_FIRST_BUY_AMOUNT_KRW` 기본값은 `200000 KRW`, `GRID_SELL_PERCENT` 기본값은 `5`, `PRICE_POLL_INTERVAL` 기본값은 `5초`다.

## 디렉터리 구조

```text
auto/
├── main.py                               # 메인 루프, 리스크 체크, CLI
├── config/settings.py                    # 거래소/심볼/백엔드/리스크/로그 설정
├── core/
│   ├── grid.py                           # 도메인 그리드 상태
│   ├── grid_builder.py                   # 파일 기반 초기 그리드 생성기
│   ├── grid_properties.py                # grid.properties -> 슬롯 계산
│   └── models.py                         # GridRow / Order / OrderStatus 등
├── exchange/
│   ├── base.py                           # 거래소 인터페이스
│   ├── crypto.py                         # 업비트 구현
│   └── stock.py                          # 주식 거래소 stub
├── storage/
│   ├── factory.py                        # 백엔드별 저장소 선택
│   ├── file_grid_repository.py           # grid.txt 저장 + in-memory pending order stub
│   ├── postgres_grid_repository.py       # PostgreSQL grid 저장소
│   ├── postgres_order_repository.py      # PostgreSQL pending/open order 저장소
│   └── postgres_common.py                # PostgreSQL 공통 연결/락 유틸
├── strategy/grid_strategy.py             # 가격 교차 기반 주문 후보 생성
├── scripts/
│   ├── apply_grid_properties_to_postgres.py
│   └── export_postgres_grid.py
├── db/migrations/001_auto_trading_schema.sql
├── docs/
│   ├── UPBIT_API_REFERENCE.md
│   ├── quick-commands.md
│   ├── postgres-cutover-checklist.md
│   └── macos-deployment-guide.md
├── tests/
├── AGENTS.md
├── grid.properties
├── grid.txt
├── run.sh
├── stop.sh
└── requirements.txt
```

## 현재 전략 동작

### 슬롯 의미

```text
Grid3 SYMBOL
1) buy_price held_qty sell_price planned_qty
...

테이블 총재고 : N
```

- `held_qty > 0`: 보유 중 슬롯이다. `sell_price`를 아래에서 위로 교차하면 매도 후보가 된다.
- `held_qty = 0` and `planned_qty > 0`: 빈 슬롯이다. `buy_price`를 위에서 아래로 또는 아래에서 위로 교차하면 매수 후보가 된다.
- 보유 슬롯에서도 `planned_qty`는 다음 빈 슬롯 복원용 목표 수량으로 유지될 수 있다.

### 주문 생성/반영 흐름

1. 첫 가격 스냅샷에서는 주문을 만들지 않는다.
2. 빈 슬롯 하락 교차는 지정가 매수, 상승 교차는 시장가 KRW 금액 매수로 접수한다.
3. 보유 슬롯은 `이전 가격 < sell_price <= 현재 가격`일 때만 매도 주문을 만든다.
4. 같은 루프에 매도/매수가 함께 생기면 `main.py`가 매도를 먼저 접수하고 즉시 체결 여부를 재확인한다.
5. 실제로 늘어난 KRW 잔고를 다시 조회한 뒤 매수 주문 가능 여부를 판단한다.
6. 주문 상태가 `done`일 때만 그리드 상태를 저장소에 반영한다. `wait`/`watch`는 pending으로 유지한다.

### 리스크 체크

- 현재 `check_risk()`는 매수 주문에 대해서만 최소 주문 금액과 주문 가능 KRW 잔고를 본다.
- 추가 예산 한도는 `MAX_TOTAL_BUDGET_KRW`가 설정된 경우에만 활성화된다.
- 업비트 KRW 최소 주문 금액 `5000 KRW`보다 작은 매수는 차단된다.

## 상태 저장 백엔드

### `file` 백엔드

- `grid.txt`를 source of truth로 사용한다.
- 외부 수정 감지 시 핫리로드가 가능하다.
- pending order 저장소는 `FilePendingOrderRepository`의 in-memory stub이라 프로세스 재시작 후 open order 복구가 되지 않는다.

### `postgres` 백엔드

- `bot_state`, `grid_slots`, `grid_revisions`, `orders` 테이블을 사용한다.
- grid 상태 version 충돌을 검사한다.
- pending/open order를 영속화해 프로세스 재시작 시 복구한다.
- 같은 `STATE_BOT_KEY`에 대해 advisory lock으로 단일 실행을 강제한다.
- 빈 snapshot으로 시작하면 fail-fast 하도록 막아 두었다.

## `grid.properties` 기반 DB 그리드 반영

- `MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `BUY_AMOUNT_KRW`, `GRID_COUNT`, `SELL_PERCENT`를 읽는다.
- 중간 `buy_price`는 기하비율로 계산한다.
- 각 슬롯 `planned_qty`는 `BUY_AMOUNT_KRW / buy_price`를 BTC 소수 단위로 내림해 계산한다.
- 각 슬롯 `sell_price`는 `buy_price * (1 + SELL_PERCENT / 100)` 기준으로 계산한다. `SELL_PERCENT=5`는 5%를 뜻한다.
- 결과는 `scripts/apply_grid_properties_to_postgres.py`가 PostgreSQL에 직접 저장한다.

## 실행 및 검증

```bash
# 의존성 설치
pip install -r requirements.txt

# 비파괴 검증
python3 -c "import main"

# 전체 테스트
python3 -m unittest discover -s tests -v

# 업비트 KRW 주문 가능 잔고 1회 조회
python3 main.py balance

# 파일 기반 초기 그리드 생성
python3 main.py init-grid --first-buy-amount 200000 --sell-percent 5

# grid.properties -> PostgreSQL 반영
python3 scripts/apply_grid_properties_to_postgres.py --force

# PostgreSQL 상태 export
python3 scripts/export_postgres_grid.py

# 백그라운드 실행 / 종료
./run.sh
./stop.sh

# 운영 로그
tail -f logs/trading-$(date +%F).log
```

실거래 루프 `python3 main.py`는 실제 주문을 발생시킬 수 있으므로 명시적으로 필요할 때만 실행한다.

## 환경변수

- 업비트 키: `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`
- 상태 저장: `STATE_BACKEND`, `STATE_BOT_KEY`
- PostgreSQL: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSCHEMA`

`config/settings.py`는 프로젝트 루트 `.env`를 읽도록 되어 있으며, `python-dotenv`가 없어도 fallback 로더로 기본 `KEY=VALUE` 형식은 읽는다.

## 검증 결과

2026-04-14 기준 현재 작업 트리에서 아래 검증을 다시 수행했다.

- `python3 -c "import main"` 통과
- `python3 -m unittest discover -s tests -v` 통과
- 전체 테스트 수: `56`

## 현재 수정 필요 사항

### 1. file 백엔드의 pending order 영속화 부재

`storage/file_grid_repository.py`의 `FilePendingOrderRepository`는 in-memory stub이다. 따라서 `file` 백엔드에서는 프로세스 재시작 후 open order를 복구하지 못한다. 운영을 계속 `file`로 둘 생각이면 파일 기반 pending order 저장 또는 재시작 전 open order 0 확인 절차를 더 강하게 가져가야 한다.

### 2. 전체 open order 백필 API 부재

현재 런타임은 이미 알고 있는 `order_id`만 `GET /v1/order`로 재조회한다. 거래소 전체 open order를 스캔해 미등록 주문을 다시 붙이는 로직은 없다. 특히 백엔드 전환이나 수동 개입 이후에는 미체결 주문이 없는 시점에서만 재시작/컷오버하는 것이 안전하다.

### 3. 주식 경로는 아직 stub

`exchange/stock.py`는 모든 핵심 메서드가 `NotImplementedError`를 던진다. 현재 운영 범위는 업비트 코인 경로로 한정해서 보는 것이 맞다.

### 4. 실거래 통합 검증은 별도 필요

테스트 56개는 파일/전략/PostgreSQL/주문 상태 반영 흐름까지 커버하지만, 실제 업비트 네트워크·인증·시장가 체결 결과를 포함한 end-to-end 검증은 아니다. 라이브 반영 전에는 잔고 조회, 최소 주문 금액, 시장가 매수 체결 수량 차이를 운영 로그로 다시 확인해야 한다.

## 참고 문서

- [docs/UPBIT_API_REFERENCE.md](docs/UPBIT_API_REFERENCE.md)
- [AGENTS.md](AGENTS.md)
- [docs/quick-commands.md](docs/quick-commands.md)
- [docs/postgres-cutover-checklist.md](docs/postgres-cutover-checklist.md)
- [docs/macos-deployment-guide.md](docs/macos-deployment-guide.md)
