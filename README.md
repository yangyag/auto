# auto

Python 기반 그리드 자동매매 시스템이다. 현재 운영 기준은 업비트 `KRW-BTC`와 PostgreSQL 상태 저장소다. 빈 슬롯과 보유 슬롯의 가격 교차를 감지해 주문을 접수하고, 업비트 주문 상태가 `done`으로 확인될 때만 상태 저장소를 갱신한다.

## 운영 기준

- 핵심 경로는 `exchange/crypto.py` 기반 업비트 연동이다.
- 상태 저장은 PostgreSQL 전용이다.
- 전략은 가격 절대값이 아니라 직전 가격 대비 `buy_price`/`sell_price` 교차 여부로 주문을 만든다.
- 상승 교차 매수는 업비트 `ord_type=price` 시장가 매수, 하락 교차 매수와 매도는 지정가 주문으로 처리한다.
- 주문 접수만으로는 그리드 상태를 바꾸지 않고, `GET /v1/order` 재조회 결과가 `done`일 때만 반영한다.
- `run.sh` / `stop.sh` 기반 백그라운드 실행과 `logs/trading-YYYY-MM-DD.log` 날짜별 로그가 준비되어 있다.
- 최신 날짜 로그를 바로 따라가려면 `./tail-latest-log.sh`를 사용한다.
- `scripts/show_grid_state.py`와 `scripts/export_postgres_grid.py`는 현재 DB 상태를 확인하는 보조 도구다.

## 디렉터리 구조

```text
auto/
├── main.py                               # 메인 루프, 리스크 체크, CLI
├── config/settings.py                    # 거래소/심볼/리스크/로그 설정
├── core/
│   ├── grid.py                           # 그리드 상태
│   ├── grid_builder.py                   # 초기 그리드 생성기
│   ├── grid_properties.py                # grid.properties -> 슬롯 계산
│   └── models.py                         # GridRow / Order / OrderStatus 등
├── exchange/
│   ├── base.py                           # 거래소 인터페이스
│   ├── crypto.py                         # 업비트 구현
│   └── stock.py                          # 주식 거래소 stub
├── storage/
│   ├── factory.py                        # 저장소 선택
│   ├── postgres_grid_repository.py       # PostgreSQL grid 저장소
│   ├── postgres_order_repository.py      # PostgreSQL pending/open order 저장소
│   └── postgres_common.py                # PostgreSQL 공통 연결/락 유틸
├── strategy/grid_strategy.py             # 가격 교차 기반 주문 후보 생성
├── scripts/
│   ├── apply_grid_properties_to_postgres.py
│   ├── export_postgres_grid.py
│   └── show_grid_state.py
├── db/migrations/001_auto_trading_schema.sql
├── docs/
│   ├── UPBIT_API_REFERENCE.md
│   ├── quick-commands.md
│   ├── postgres-cutover-checklist.md
│   └── macos-deployment-guide.md
├── tests/
├── AGENTS.md
├── grid.properties
├── run.sh
├── stop.sh
└── requirements.txt
```

## 현재 전략 동작

```text
Grid3 SYMBOL
1) buy_price held_qty sell_price planned_qty
...

테이블 총재고 : N
```

- `held_qty > 0`: 보유 중 슬롯이다. `sell_price`를 아래에서 위로 교차하면 매도 후보가 된다.
- `held_qty = 0` and `planned_qty > 0`: 빈 슬롯이다. `buy_price`를 위에서 아래로 또는 아래에서 위로 교차하면 매수 후보가 된다.
- 보유 슬롯에서도 `planned_qty`는 다음 빈 슬롯 복원용 목표 수량으로 유지될 수 있다.
- `grid.properties` 기반 DB 그리드 생성은 `MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `BUY_AMOUNT_KRW`, `GRID_COUNT`, `SELL_PERCENT`를 읽는다.
- 각 슬롯 `sell_price`는 `buy_price * (1 + SELL_PERCENT / 100)` 기준으로 계산한다. `SELL_PERCENT=5`는 5%를 뜻한다.

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

# grid.properties -> PostgreSQL 반영
python3 scripts/apply_grid_properties_to_postgres.py --force

# PostgreSQL 상태 export
python3 scripts/export_postgres_grid.py

# 현재 DB 상태 보기
python3 scripts/show_grid_state.py

# 백그라운드 실행 / 종료
./run.sh
./stop.sh

# 최신 날짜 로그 실시간 추적
./tail-latest-log.sh
```

실거래 루프 `python3 main.py`는 실제 주문을 발생시킬 수 있으므로 명시적으로 필요할 때만 실행한다.

## 환경변수

- 업비트 키: `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`
- 상태 저장: `STATE_BOT_KEY`
- PostgreSQL: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSCHEMA`

`config/settings.py`는 프로젝트 루트 `.env`를 읽도록 되어 있으며, `python-dotenv`가 없어도 fallback 로더로 기본 `KEY=VALUE` 형식은 읽는다.

## 참고 문서

- [docs/UPBIT_API_REFERENCE.md](docs/UPBIT_API_REFERENCE.md)
- [AGENTS.md](AGENTS.md)
- [docs/quick-commands.md](docs/quick-commands.md)
- [docs/postgres-cutover-checklist.md](docs/postgres-cutover-checklist.md)
- [docs/macos-deployment-guide.md](docs/macos-deployment-guide.md)
