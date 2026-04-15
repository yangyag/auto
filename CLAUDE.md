# CLAUDE.md

## 프로젝트 개요
- Python 기반 그리드 자동매매 시스템
- 현재 운영 기준은 업비트 KRW-BTC 코인 거래다.
- 상태 저장은 PostgreSQL 전용이다.
- 가격 교차 조건에 따라 주문 후보를 만들고, 실제 체결이 확인되면 PostgreSQL 그리드 상태에 반영한다.

## 현재 기준 경로
- 기준 거래소는 업비트다.
- `config/settings.py`의 현재 운영 설정은 `EXCHANGE_TYPE = "crypto"`다.
- `exchange/stock.py`는 아직 stub 상태라 현재 운영 범위의 핵심 경로가 아니다.
- 업비트 API 세부 동작이 불명확하면 `docs/UPBIT_API_REFERENCE.md`와 업비트 공식 문서를 우선 본다.

## 디렉터리 구조
```text
auto/
├── main.py                    # 메인 루프 진입점
├── config/
│   └── settings.py            # 설정 (거래소, 심볼, 리스크 파라미터)
├── core/
│   ├── grid.py                # 그리드 상태
│   ├── grid_builder.py        # 초기 그리드 생성
│   └── models.py              # 공용 데이터 모델
├── exchange/
│   ├── base.py                # 거래소 추상 인터페이스
│   ├── crypto.py              # 업비트 구현
│   └── stock.py               # 주식 거래소 stub
├── storage/
│   ├── factory.py             # PostgreSQL 저장소 생성
│   ├── postgres_grid_repository.py
│   ├── postgres_order_repository.py
│   └── postgres_common.py
├── scripts/
│   ├── apply_grid_properties_to_postgres.py
│   ├── export_postgres_grid.py
│   └── show_grid_state.py
├── strategy/
│   └── grid_strategy.py       # 가격 교차 기반 주문 후보 생성
├── utils/
│   └── logger.py              # 공용 로거
├── logs/                      # 날짜별 실행 로그
├── run.sh                     # 백그라운드 실행
├── stop.sh                    # 백그라운드 종료
├── grid.properties            # 그리드 생성 입력
└── requirements.txt
```

## 현재 로직 핵심
- 첫 가격 스냅샷에서는 주문을 만들지 않는다.
- 빈 슬롯은 `buy_price`를 위에서 아래로 또는 아래에서 위로 교차할 때 매수 후보가 된다.
- 보유 슬롯은 `sell_price`를 아래에서 위로 교차할 때 매도 후보가 된다.
- 같은 루프에 매도와 매수가 함께 생겨도 `main.py`의 매수 주문 판단은 현재 주문 가능 KRW 기준으로 독립 처리한다.
- 하락 교차 매수와 매도는 지정가 주문이고, 상승 교차 매수는 업비트 `ord_type=price` 시장가 매수로 보낸다.
- 상승 교차 매수는 슬롯 목표 예산 `buy_price * planned_qty`를 원 단위 내림한 KRW 금액만큼 즉시 체결을 우선한다.
- 시장가 매수의 실제 체결 BTC는 `held_qty`에 기록되므로, 목표 수량보다 조금 적게 잡힐 수 있다.
- `main.py::check_risk()`는 현재 주문 가능 KRW 잔고와 최소 주문 금액만 기준으로 매수 허용 여부를 본다.

## 상태 표현
```text
Grid3 SYMBOL
1) buy_price held_qty sell_price planned_sell_qty
...

테이블 총재고 : N
```

- `held_qty > 0`: 보유 중 슬롯
- `held_qty = 0`, `planned_sell_qty > 0`: 빈 슬롯
- 위 텍스트는 export 결과의 표현 형식이다. 운영 source of truth 는 PostgreSQL snapshot 이다.

## 운영 규칙
- 실거래가 걸릴 수 있는 `python3 main.py` 실행은 명시 요청이 있을 때만 한다.
- 기본 검증은 비파괴 방식으로 한다. 우선순위는 `python3 -c "import main"`이다.
- API 키는 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` 환경변수로만 주입한다.
- PostgreSQL 상태 계약과 export/show 스크립트의 출력 의미를 함께 맞춰야 한다.
- 백그라운드 실행/종료는 `./run.sh`, `./stop.sh`를 우선 사용한다.
- 운영 로그는 `logs/trading-YYYY-MM-DD.log`를 기준으로 본다.

## 실행 및 검증
```bash
# 의존성 설치
pip install -r requirements.txt

# 비파괴 검증
python3 -c "import main"

# 잔고 확인
python3 main.py balance

# 초기 그리드 생성
python3 main.py init-grid --first-buy-amount 200000 --sell-percent 5 --force

# DB 상태 확인
python3 scripts/show_grid_state.py

# DB 상태 export
python3 scripts/export_postgres_grid.py

# 백그라운드 실행 / 종료
./run.sh
./stop.sh

# 실거래/실시간 루프
python3 main.py

# 테스트
python3 -m unittest discover -s tests -v
```

## 최근 반영된 변경
- PostgreSQL 전용 상태 저장
- `GRID_FIRST_BUY_AMOUNT_KRW` / `--first-buy-amount` 기반 초기 그리드 생성
- 날짜별 로그 파일 `logs/trading-YYYY-MM-DD.log`
- `run.sh` / `stop.sh` 기반 백그라운드 실행
- 빈 슬롯 양방향 교차 진입
- 같은 루프의 매도 체결대금을 즉시 상위 매수 재원으로 재사용하지 않는 주문 흐름
- 상승 교차 매수를 시장가 매수로 바꾸고 실제 체결 BTC를 `held_qty`에 반영

## 작업 파이프라인

모든 구현 작업은 **Planner → Generator → Evaluator** 순서로 진행한다. 비단순 작업은 이 세 단계를 명확히 분리하고, 단순 작업도 같은 사고 흐름을 유지한다. 외부 도구나 Codex에 위임하지 않고 Claude Code가 직접 수행한다.

### Planner
- 사용자 요청을 기능 단위로 쪼갠다.
- 영향 파일과 선행 인터페이스를 먼저 고정한다.
- 완료 기준을 명확히 정한다.
  - PostgreSQL 상태 계약 유지
  - 리스크 파라미터 동작 유지 또는 변경 의도 명시
  - 실거래 부작용 없는 검증 우선
- 변경 전에 관련 모듈을 먼저 읽고, 영향 범위를 `config`, `core`, `exchange`, `strategy`, `storage` 중 어디까지인지 명확히 잡는다.

### Generator
- Planner가 고정한 범위와 완료 기준을 바꾸지 않고 구현한다.
- 중간에 계약 변경이 필요하면 먼저 Planner 관점으로 다시 정리한 뒤 진행한다.
- 코드 변경 시 기존 저장 포맷, 주문 방향, 리스크 체크 흐름을 깨지 않는지 확인한다.
- 기본 검증 명령:
  - `python3 -c "import main"`
  - `python3 -m unittest discover -s tests -v`

### Evaluator
- 구현이 끝난 뒤 반드시 별도 검토 관점으로 점검한다. 핵심은 "돌아간다"가 아니라 "운영 중 깨질 수 있는 지점이 남아 있지 않은가"다.
- 매수/매도 트리거 조건이 반대로 뒤집히지 않았는지 본다.
- `check_risk()`의 잔고/재고 한도 계산이 변경 의도와 맞는지 본다.
- `GridState.save()`가 저장 계약을 그대로 재생성하는지 본다.
- 민감정보 노출, 실거래 실행, 미구현 stub 호출 가능성을 반드시 점검한다.
- 테스트가 있으면 통과 여부만 보지 말고, 이번 변경이 막아야 하는 회귀 케이스가 실제로 추가됐는지도 확인한다.

## 코드 컨벤션
- 리스크 정책 변경은 `config/settings.py`와 `main.py`를 함께 본다.
- 그리드 저장 계약을 바꾸면 PostgreSQL 저장소와 export/show 스크립트를 같이 수정한다.
- 신규 거래소 추가 시 `exchange/base.py`와 `main.py::build_exchange()`를 함께 갱신한다.
- git commit 메시지는 한글로 작성한다.
