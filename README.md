# auto

Python 기반 그리드 자동매매 시스템이다. 현재 운영 기준은 업비트 `KRW-BTC`와 PostgreSQL 상태 저장소다. 빈 슬롯과 보유 슬롯의 가격 교차를 감지해 주문을 접수하고, 업비트 주문 상태가 `done`으로 확인될 때만 상태 저장소를 갱신한다.

## 운영 기준

- 핵심 경로는 `exchange/crypto.py` 기반 업비트 연동이다.
- 상태 저장은 PostgreSQL 전용이다.
- 전략은 가격 절대값이 아니라 직전 가격 대비 `buy_price`/`sell_price` 교차 여부로 주문을 만든다.
- 빈 슬롯은 `previous_price > buy_price >= current_price` 인 하락 교차 시 지정가 매수한다. 한 poll 안에 여러 `buy_price`를 아래로 통과하면 그 empty 슬롯들은 모두 매수 후보가 된다. 다만 모든 신규 매수는 먼저 inventory-target gate 를 통과해야 한다. `q_current = Σ(buy_price * held_qty) / MAX_OPERATING_BUDGET_KRW`, `z = (ln(P) - ln(L)) / (ln(U) - ln(L))`, `q_target(z) = q_min + (q_max - q_min) * (1 - z)^gamma`, 허용 조건은 `q_current < q_target(z) - epsilon` 이다. 추가로 최근 완료된 15분 종가가 밴드 밖에서 4개 연속 나오면 브레이크아웃 가드가 켜져 신규 매수는 전부 차단되고, 보유 슬롯 매도만 계속 허용된다. 상승 시 단일 슬롯 상향 돌파 시장가 예산매수는 `UPWARD_BUY_ENABLED=True` 일 때만 켜지며, 그때도 `previous_price < buy_price <= current_price` 인 empty 슬롯이 한 poll 에서 정확히 1개일 때만 후보가 된다. 보유 슬롯은 현재가가 저장된 `sell_price` 가 아니라 Phase 6 age-aware `effective_sell_price` 이상이면 매도한다. `k` 기반 holding 슬롯은 `filled_at` 기준 48시간 이후 `k - 0.5`, 7일 이후 `k - 1.0` 로 TP 가 압축되지만, 저장된 `sell_price` 자체를 덮어쓰지는 않는다.
- 주문 접수만으로는 그리드 상태를 바꾸지 않고, `GET /v1/order` 재조회 결과가 `done`일 때만 반영한다.
- Phase 7부터 업비트 주문 접수는 `GET /v1/orders/chance` 확인, `POST /v1/orders/test` 프리플라이트, 실제 `POST /v1/orders` 순서로 진행한다. 실주문에는 `identifier` 를 포함해 저장소에 함께 남기고, `429` 와 짧은 `418` 차단만 제한적으로 재시도하며 timeout/network 오류는 자동 재시도하지 않는다.
- `run.sh` / `stop.sh` 기반 백그라운드 실행과 `logs/trading-YYYY-MM-DD.log` 날짜별 로그가 준비되어 있다.
- 최신 날짜 로그를 바로 따라가려면 `./tail-latest-log.sh`를 사용한다.
- `scripts/show_grid_state.py`와 `scripts/export_postgres_grid.py`는 현재 DB 상태를 확인하는 보조 도구다. holding 슬롯에 `filled_at`가 있으면 age TP 메타데이터도 함께 보여준다.
- `scripts/preview_recenter_plan.py`는 재중심화 가능 여부를 preview-only 로 계산한다. DB write, 주문 제출, 주문 취소는 하지 않는다.
- `grid.properties` 튜닝은 [docs/grid-parameter-tuning.md](docs/grid-parameter-tuning.md) 기준으로 계산한다.

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
│   ├── interfaces.py                     # GridStateRepository / PendingOrderRepository 인터페이스
│   ├── factory.py                        # 저장소 생성
│   ├── postgres_grid_repository.py       # PostgreSQL grid 저장소
│   ├── postgres_order_repository.py      # PostgreSQL pending/open order 저장소
│   └── postgres_common.py                # PostgreSQL 공통 연결/락 유틸
├── strategy/
│   ├── grid_strategy.py                  # 가격 교차 기반 주문 후보 생성
│   └── recenter_preview.py               # Phase 6 preview-only 재중심화 계산
├── utils/
│   ├── decimal_utils.py                  # Decimal 연산 유틸
│   ├── upbit_market.py                   # KRW 마켓 호가 단위 / 최소 주문 금액
│   └── logger.py                         # 날짜별 로그 파일 설정
├── scripts/
│   ├── apply_grid_properties_to_postgres.py
│   ├── export_postgres_grid.py
│   ├── preview_recenter_plan.py
│   └── show_grid_state.py
├── db/migrations/
│   ├── 001_auto_trading_schema.sql
│   ├── 002_add_grid_slots_filled_at.sql
│   └── 003_add_orders_identifier.sql
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
├── tail-latest-log.sh                    # 최신 날짜 로그 실시간 추적
└── requirements.txt
```

## 현재 전략 동작

```text
Grid3 SYMBOL
1) buy_price held_qty sell_price planned_qty
...

테이블 총재고 : N
```

- `held_qty > 0`: 보유 중 슬롯이다. 현재가가 런타임 `effective_sell_price` 이상이면 매도 후보가 된다. 기본값은 저장된 `sell_price` 이고, Phase 6 age 압축이 활성인 `k` 기반 holding 슬롯만 더 낮아질 수 있다.
- `held_qty = 0` and `planned_qty > 0`: 빈 슬롯이다. `previous_price > buy_price >= current_price` 이면 지정가 매수 후보가 된다. 이 하락 구간에서 여러 슬롯을 한 poll 안에 함께 통과하면 그 슬롯들은 모두 매수 후보가 된다. 다만 Phase 4부터는 `previous_price` 기준 활성 윈도우 안의 empty 슬롯만 실제 매수 후보가 된다. 기본값은 현재가 아래 최근접 `48` 슬롯과 위쪽 재진입 후보 `4` 슬롯이다. 모든 신규 매수는 여기에 더해 `q_current < q_target(z) - epsilon` 을 만족해야만 생성된다. `q_current` 는 현재 보유 슬롯의 `buy_price * held_qty` 합을 `MAX_OPERATING_BUDGET_KRW` 로 나눈 값이고, `q_target(z)` 는 현재 가격 위치 `z` 에서의 목표 재고 비율이다. 최근 완료된 15분 종가 4개가 같은 방향으로 밴드 밖에 연속 존재하면 브레이크아웃 가드가 켜져 신규 매수 후보는 최종 제출 전에 모두 제거된다. `previous_price < buy_price <= current_price` 인 empty 슬롯 단일 상향 돌파 시장가 예산매수는 옵션 기능이며 기본값은 꺼져 있고 `UPWARD_BUY_ENABLED=True` 일 때만 활성화된다.
- 매수 주문은 접수만으로 holding 이 되지 않고, 거래소 재조회 결과가 `done`일 때만 해당 슬롯의 `held_qty`가 채워진다. 이때 `filled_at` 도 함께 기록된다.
- 보유 슬롯에서도 `planned_qty`는 다음 빈 슬롯 복원용 목표 수량으로 유지될 수 있다.
- `grid.properties` 기반 DB 그리드 생성은 기본적으로 `MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `BUY_AMOUNT_KRW`, `GRID_COUNT`를 읽고, TP는 기본 `k` 모델로 계산한다. 필요하면 `TP_MODEL`, `TP_K_BASE`, `TP_K_FLOOR`를 추가로 줄 수 있다.
- 기본 TP 모델은 `k`다. 각 슬롯 `sell_price`는 현재 생성 경로의 로그 간격 `delta`에 대해 `exp(k * delta)` 배수로 계산한다. `SELL_PERCENT`는 `TP_MODEL=percent` fallback을 명시적으로 쓸 때만 의미가 있다.
- Phase 6부터 holding 슬롯은 `filled_at` 기반 age-aware TP 압축을 사용한다. 48시간 경과 시 `k - 0.5`, 7일 경과 시 `k - 1.0`, 최저치는 `k_floor` 이다.

## 설정 메모

- `MAX_TOTAL_BUDGET_KRW`: 전체 그리드 총배정금액 한도 검사에만 사용한다.
- `MAX_OPERATING_BUDGET_KRW`: 재고 비율 `q_current` 계산 분모다. 비어 있으면 inventory-target gate 는 형식만 남고 실질 의미가 없다.
- `UPWARD_BUY_ENABLED`: 상승 1칸 돌파 시장가 예산매수 기능 토글이다. 기본값은 `False` 다.
- `GRID_TP_MODEL="k"`: 신규 생성 그리드의 기본 TP 모델이다.
- `GRID_TP_K_BASE=11.0`, `GRID_TP_K_FLOOR=8.0`: 기본 `k` 기반 TP 파라미터다. Phase 5에서는 신규 생성 경로에만 적용되고, 기존 holding `sell_price`는 자동 재계산하지 않는다.
- `filled_at`: Phase 6부터 holding 슬롯 age 추적용 메타데이터다. `grid_slots` 테이블에도 함께 저장된다.
- `identifier`: Phase 7부터 pending/open 주문 저장소에 함께 남기는 업비트 사용자 지정 주문 식별자다. 현재 reconciliation 주키는 여전히 업비트 `uuid` 다. 업비트 계정 전체 유일 제약에 맞춰 현재 구현은 PostgreSQL schema 단위로도 유일하게 본다.
- Phase 6 age 압축은 현재 런타임 `GRID_TP_K_BASE` / `GRID_TP_K_FLOOR` 가 현재 DB 그리드를 만들 때 사용한 값과 같다는 전제를 둔다. 다른 값으로 생성한 그리드를 계속 운용할 때는 설정을 먼저 맞춘다.
- `ACTIVE_WINDOW_ENABLED=True`: 빈 슬롯 매수 후보를 poll 시작 가격 기준 근접 구간으로 제한한다.
- `ACTIVE_WINDOW_BELOW_CURRENT_SLOTS=48`, `ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS=4`: 하락 매수는 아래 최근접 슬롯 위주로, 옵션 상향 재진입은 위쪽 소수 슬롯만 사용한다.
- `BREAKOUT_GUARD_ENABLED`: 15분 캔들 기반 브레이크아웃 가드 토글이다. 기본값은 `True` 다.
- `BREAKOUT_GUARD_CANDLE_UNIT=15`, `BREAKOUT_GUARD_CONSECUTIVE_CANDLES=4`: 최근 15분 종가 4개를 본다.
- `BREAKOUT_GUARD_FAIL_OPEN=True`: 캔들 조회 실패 시 런타임을 멈추지 않고 기존 매수/매도 흐름을 유지한다.
- Phase 1 기본 inventory-target 파라미터는 `q_min=0.10`, `q_max=0.85`, `gamma=1.5`, `epsilon=0.03` 이다.
- `python3 main.py init-grid` 와 `scripts/apply_grid_properties_to_postgres.py` 는 같은 초기화 경로가 아니다.
  - `init-grid`: 첫 슬롯 기준 고정 수량
  - `grid.properties`: 총예산 `BUY_AMOUNT_KRW * GRID_COUNT` 를 가중 배분한 슬롯별 `slot_budget / buy_price`
- `python3 main.py init-grid` 는 기본적으로 `--tp-model k` 를 쓴다. `--sell-percent` 는 레거시 percent fallback용이고, 실제 모델은 실행 출력의 `TP 모델` 줄로 확인한다.

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

# 초기 그리드 생성 (코드 기반)
python3 main.py init-grid --first-buy-amount 200000 --sell-percent 5 --force

# grid.properties -> PostgreSQL 반영
python3 scripts/apply_grid_properties_to_postgres.py --force

# PostgreSQL 상태 export
python3 scripts/export_postgres_grid.py

# 현재 DB 상태 보기
python3 scripts/show_grid_state.py

# 재중심화 preview-only 평가
python3 scripts/preview_recenter_plan.py

# 백그라운드 실행 / 종료
./run.sh
./stop.sh

# 최신 날짜 로그 실시간 추적
./tail-latest-log.sh
```

실거래 루프 `python3 main.py`는 실제 주문을 발생시킬 수 있으므로 명시적으로 필요할 때만 실행한다.

## 환경변수

- 샘플 파일은 [.env_sample](/home/yangyag/auto/.env_sample:1) 이다. 보통 이 파일 내용을 기준으로 프로젝트 루트 `.env`를 채운다.

```dotenv
UPBIT_ACCESS_KEY=
UPBIT_SECRET_KEY=
STATE_BACKEND=postgres
STATE_BOT_KEY=krw-btc-live
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=
PGUSER=
PGPASSWORD=
PGSCHEMA=auto_trading
```

- `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`: 업비트 API 인증 키
- `STATE_BACKEND`: `.env_sample` 호환용 항목. 현재 코드는 PostgreSQL 전용으로 고정되어 있으며 이 값을 런타임에서 읽지 않는다.
- `STATE_BOT_KEY`: PostgreSQL 상태 저장소에서 사용할 봇 식별자
- `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSCHEMA`: PostgreSQL 접속 정보

`config/settings.py`는 프로젝트 루트 `.env`를 읽도록 되어 있으며, `python-dotenv`가 없어도 fallback 로더로 기본 `KEY=VALUE` 형식은 읽는다.

## 참고 문서

- [docs/UPBIT_API_REFERENCE.md](docs/UPBIT_API_REFERENCE.md)
- [docs/grid-parameter-tuning.md](docs/grid-parameter-tuning.md)
- [AGENTS.md](AGENTS.md)
- [docs/quick-commands.md](docs/quick-commands.md)
- [docs/postgres-cutover-checklist.md](docs/postgres-cutover-checklist.md)
- [docs/macos-deployment-guide.md](docs/macos-deployment-guide.md)
