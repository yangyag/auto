# AGENTS.md

## 프로젝트 개요
- Python 기반 그리드 자동매매 시스템
- 현재 운영 기준은 가상화폐 거래이며, 거래소는 업비트로 고정한다.
- `config/settings.py`의 현재 설정도 `EXCHANGE_TYPE = "crypto"` 기준이다.
- 주식 거래소(`exchange/stock.py`)는 아직 stub 상태이며, 현재 운영 범위에서는 우선순위가 낮다.
- `grid.txt`의 슬롯 상태를 읽고, 현재가 기준으로 매수/매도 주문을 생성한 뒤 실제 체결이 확인되면 결과를 다시 `grid.txt`에 반영한다

## 기준 거래소와 참고 문서
- 현재 기준 거래소는 업비트다.
- 업비트 API/인증/주문 파라미터/응답 해석이 불명확하면 공식 문서 `https://docs.upbit.com/kr`를 우선 기준으로 삼는다.
- 로컬 요약본은 `docs/UPBIT_API_REFERENCE.md`를 먼저 참고한다.
- `exchange/crypto.py` 수정 시에는 구현 편의보다 업비트 공식 문서 기준 정합성을 우선한다.

## 우선 읽을 파일
- `docs/UPBIT_API_REFERENCE.md`: 업비트 공식 문서 기반 로컬 요약 레퍼런스
- `main.py`: 메인 루프, 리스크 체크, 주문 실행 순서
- `config/settings.py`: 거래소 종류, 심볼, API 키, 리스크 파라미터
- `core/grid.py`: `grid.txt` 파싱/저장 규칙
- `core/models.py`: `GridRow`, `Order`, `OrderSide` 등 공용 모델
- `strategy/grid_strategy.py`: 가격 트리거 판정과 주문 생성
- `exchange/base.py`: 거래소 공용 인터페이스
- `exchange/crypto.py`: 업비트 연동 구현
- `exchange/stock.py`: 주식 연동 stub 구현

## 디렉터리 구조
```text
auto/
├── main.py                    # 메인 루프 진입점
├── config/
│   └── settings.py            # 설정 (거래소 선택, API 키, 리스크 파라미터)
├── core/
│   ├── grid.py                # grid.txt 파싱 + 그리드 상태 관리
│   └── models.py              # 공용 데이터 모델
├── exchange/
│   ├── base.py                # 거래소 추상 클래스
│   ├── crypto.py              # 업비트 구현
│   └── stock.py               # 주식 거래소 stub
├── strategy/
│   └── grid_strategy.py       # 그리드 전략 핵심 로직
├── utils/
│   └── logger.py              # 공용 로거
├── logs/                      # 날짜별 실행 로그 (런타임 생성)
├── run.sh                     # 백그라운드 실행 스크립트
├── stop.sh                    # 백그라운드 종료 스크립트
├── grid.txt                   # 그리드 상태 파일
└── requirements.txt           # 런타임 의존성
```

## 에이전트 작업 원칙
- 기본 작업 순서는 항상 `Planner -> Generator -> Evaluator`다. 비단순 작업은 가능하면 이 세 역할을 각각 에이전트로 띄워서 수행하고, 단순 작업이라도 최소한 이 순서의 사고 흐름을 유지한다.
- 변경 전에 관련 모듈을 먼저 읽고, 영향 범위를 `config`, `core`, `exchange`, `strategy` 중 어디까지인지 명확히 잡는다.
- 실거래 주문이 발생할 수 있는 `python main.py` 실행은 사용자가 명시적으로 요청한 경우에만 한다.
- 기본 검증은 비파괴 방식으로 한다. 우선순위는 `python -c "import main"` 같은 임포트/정적 검증이다.
- API 키는 환경변수 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`로만 주입한다. 민감정보를 문서, 샘플 파일, 커밋에 복제하지 않는다.
- `grid.txt` 포맷은 깨지면 안 된다. 헤더, 슬롯 본문, 마지막 총재고 줄을 모두 유지해야 한다.
- `Generator`는 외부 플러그인이나 별도 Codex 호출이 아니라, 메인 Codex가 직접 하위 에이전트를 병렬로 생성해서 운영한다.
- 코인 거래 로직과 업비트 연동은 현재 시스템의 기준 경로다. 관련 동작을 바꿀 때는 설정, 전략, 주문 파라미터를 함께 점검한다.
- 거래소 인터페이스를 바꾸면 `exchange/base.py`만 고치지 말고 `main.py`, `strategy/grid_strategy.py`, 구현체까지 함께 맞춘다.
- `exchange/stock.py`는 미구현 상태다. 주식 기능 요청을 처리할 때는 stub 제거 범위와 누락된 메서드를 먼저 명시한다.
- 현재 주문 수량 모델은 `Decimal` 기준이다. KRW-BTC 운영에서는 소수 BTC 수량이 기본 경로다.
- KRW-BTC 운영 시 수량은 소수 BTC 단위로 관리하고, 가격은 업비트 KRW 마켓 호가 단위에 맞춰야 한다.
- `grid.properties` 기반 DB 그리드 생성 도구가 있다. `MIN_BUY_PRICE`, `MAX_BUY_PRICE`, `BUY_AMOUNT_KRW`, `GRID_COUNT`, `SELL_PERCENT`를 채우면 `scripts/apply_grid_properties_to_postgres.py`가 최상단/최하단 buy_price를 그 범위에 맞추고, 각 슬롯 `planned_qty`는 `BUY_AMOUNT_KRW / buy_price`를 소수 BTC 단위 내림으로 계산해 PostgreSQL에 직접 저장한다.
- 이 도구에서 중간 슬롯 buy_price는 기하비율로 계산하며, 각 슬롯의 `sell_price`는 `buy_price * (1 + SELL_PERCENT / 100)` 기준으로 계산한다. `SELL_PERCENT=5`는 5%를 뜻한다.
- 백그라운드 실행/종료는 가능하면 `./run.sh`, `./stop.sh`를 우선 사용한다. 직접 `nohup python3 main.py`를 실행하면 PID 추적과 로그 해석이 꼬일 수 있다.
- 운영 로그는 `logs/trading-YYYY-MM-DD.log`를 기준으로 본다. 테스트 로그가 같은 날짜 파일에 남을 수 있으므로 로거 이름 `__main__`/`main`도 함께 확인한다.

## 작업 파이프라인

- 모든 구현 작업은 먼저 `Planner` 에이전트를 띄워 범위와 완료 기준을 고정하고, 그 다음 `Generator` 에이전트를 띄워 구현/검증을 수행하며, 마지막으로 `Evaluator` 에이전트를 띄워 회귀/리스크를 다시 점검하는 순서로 마무리한다.
- 비단순 작업은 가능하면 세 역할을 실제로 분리된 에이전트로 띄우고, 단순 작업도 최소한 메인 세션 안에서 같은 순서로 점검한다.

### Planner
- `Planner` 에이전트를 먼저 띄운다.
- 사용자 요청을 기능 단위로 쪼갠다.
- 영향 파일과 선행 인터페이스를 먼저 고정한다.
- 완료 기준을 명확히 적는다.
  - `grid.txt` 포맷 유지
  - 리스크 파라미터 동작 유지 또는 변경 의도 명시
  - 실거래 부작용 없는 검증 우선

### Generator
- `Planner` 다음에 `Generator` 에이전트를 띄운다.
- 메인 Codex가 직접 하위 에이전트를 여러 개 병렬로 띄워 구현한다. 외부 플러그인이나 `/codex:...` 같은 별도 호출을 전제로 하지 않는다.
- `Planner`가 고정한 범위와 완료 기준을 바꾸지 않고 구현한다. 중간에 계약 변경이 필요하면 먼저 `Planner` 관점으로 다시 정리한 뒤 진행한다.
- 즉시 다음 행동을 막는 핵심 작업은 메인 세션이 직접 처리하고, 독립적인 보조 작업만 하위 에이전트에 분배한다.
- 하위 에이전트는 파일 충돌이 없도록 책임 범위를 분리한다.
- 공용 계약 변경은 먼저 확정하고, 그 다음 병렬 작업에 들어간다.
- 코드 변경 시 기존 저장 포맷, 주문 방향, 리스크 체크 흐름을 깨지 않는지 확인한다.
- 문서나 설정 의미가 달라졌다면 `AGENTS.md`와 관련 문서를 함께 맞춘다.
- 기본 검증 명령:
  - `pip install -r requirements.txt`
  - `python -c "import main"`
  - `python -m unittest discover -s tests -v`

### Evaluator
- 구현/검증이 끝난 뒤 `Evaluator` 에이전트를 마지막으로 띄운다.
- 구현이 끝난 뒤 반드시 한 번 더 별도 검토 관점으로 본다. 핵심은 “돌아간다”가 아니라 “운영 중 깨질 수 있는 지점이 남아 있지 않은가”다.
- 매수/매도 트리거 조건이 반대로 뒤집히지 않았는지 본다.
- `check_risk()`의 잔고/재고 한도 계산이 변경 의도와 맞는지 본다.
- `GridState.save()`가 기존 포맷을 그대로 재생성하는지 본다.
- 민감정보 노출, 실거래 실행, 미구현 stub 호출 가능성을 반드시 점검한다.
- 테스트가 있으면 통과 여부만 보지 말고, 이번 변경이 막아야 하는 회귀 케이스가 실제로 추가됐는지도 확인한다.

## 주의할 구현 포인트
- 거래 심볼은 현재 두 곳에 존재한다: `config/settings.py`의 `SYMBOL`, `grid.txt` 헤더의 심볼. 실제 주문은 `cfg.SYMBOL`을 사용하고, 그리드 파일 요약/저장은 `GridState.symbol`을 사용한다.
- `core/grid_builder.py::build_cash_only_grid()`는 상단/하단 매수 경계를 고정한 뒤 그 사이를 슬롯 수만큼 분할하고, 첫 슬롯 `buy_price` 기준 `GRID_FIRST_BUY_AMOUNT_KRW` 만큼 살 수 있는 BTC 수량을 모든 슬롯의 고정 수량으로 사용한다. 각 슬롯 `sell_price`는 `GRID_SELL_PERCENT` 기준으로 계산한다.
- `python3 main.py init-grid`의 생성 기준은 총예산 분배가 아니라 `--first-buy-amount` 기반이다. 현재 기본값은 `config/settings.py::GRID_FIRST_BUY_AMOUNT_KRW`를 따르며, 매도 가격은 `--sell-percent` 또는 `config/settings.py::GRID_SELL_PERCENT`를 따른다.
- `strategy/grid_strategy.py`의 트리거는 절대값 판정이 아니라 가격 교차 판정이다. 첫 가격 스냅샷에서는 주문을 내지 않고, 이후 빈 슬롯은 `buy_price`를 위에서 아래로 또는 아래에서 위로 교차할 때 매수하고, 보유 슬롯은 `이전 가격 < sell_price <= 현재 가격`일 때 매도한다.
- 하락 교차 매수와 매도는 지정가 주문이다. 상승 교차 매수는 업비트 `ord_type=price` 시장가 매수로 보내며, 슬롯 목표 예산은 `buy_price * planned_qty`를 원 단위 내림한 KRW 금액으로 계산한다.
- `main.py`는 같은 루프의 매도/매수 후보가 함께 생기면 매도를 먼저 접수하고 즉시 체결 재확인한 뒤, 실제로 늘어난 KRW 잔고 기준으로 매수 주문을 판단한다. `check_risk()` 자체는 현재 주문 가능 KRW만 본다.
- 주문 생성 성공은 체결 완료와 다르다. `main.py`는 업비트 `GET /v1/order`로 주문 상태를 재조회해 `state=done`일 때만 `grid.txt`를 갱신한다. `wait`/`watch` 상태 주문은 pending으로 유지한다.
- `exchange/crypto.py`는 외부 업비트 API를 호출하므로 네트워크, 인증, 주문 부작용을 항상 고려해야 한다.
- `exchange/stock.py`는 모든 핵심 메서드가 `NotImplementedError`를 던진다.
- `main.py`는 무한 루프 구조라서, 단순 검증 용도로 직접 실행하는 것은 적절하지 않다.

## grid.txt 포맷
```text
Grid3 SYMBOL
1) buy_price held_qty sell_price planned_sell_qty
...

테이블 총재고 : N
```

### 슬롯 해석 규칙
- `held_qty > 0`: 보유 중 슬롯, `sell_price` 도달 시 매도 대상. `planned_sell_qty`는 다음 빈 슬롯 복원 시 사용할 목표 수량으로 함께 유지될 수 있다.
- `held_qty = 0`, `planned_sell_qty > 0`: 빈 슬롯, `buy_price` 도달 시 매수 대상

### 그리드 전략 의미
- `grid.txt`의 각 줄은 하나의 독립된 매매 슬롯이다.
- 빈 슬롯은 현재가가 해당 `buy_price`를 위에서 아래로 교차하면 지정가 수량 매수, 아래에서 위로 교차하면 시장가 KRW 금액 매수로 진입한다.
- 상승 교차 시장가 매수는 실제 체결 BTC 수량이 목표 수량보다 조금 적을 수 있고, `held_qty`에는 그 실제 체결 수량이 기록된다.
- 보유 슬롯은 현재가가 해당 `sell_price`를 아래에서 위로 교차할 때, 그 줄에서 보유한 수량만큼만 분할 매도한다.
- 전략은 전체 물량을 한 번에 매수하거나 한 번에 청산하는 구조가 아니다.
- 핵심은 가격 변동 구간마다 슬롯별로 왕복 체결을 반복해 실현수익을 누적하는 것이다.
- 따라서 전체 평가손익이 일시적으로 마이너스로 보여도, 변동성이 충분하면 개별 슬롯의 반복 매매로 수익이 발생할 수 있다.
- `grid.txt`에 적힌 종목이 예시일 수는 있지만, 파일 의미 자체는 자산 종류와 무관하게 동일하다.

## 실행 및 검증
```bash
# 의존성 설치
pip install -r requirements.txt

# 비파괴 검증
python3 -c "import main"

# 업비트 KRW 주문 가능 잔고 1회 조회
python3 main.py balance

# KRW-BTC 초기 그리드 생성
python3 main.py init-grid --first-buy-amount 200000 --sell-percent 5

# grid.properties -> PostgreSQL 그리드 반영
python3 scripts/apply_grid_properties_to_postgres.py --properties-file grid.properties --force

# 백그라운드 실행 / 종료
./run.sh
./stop.sh

# 실거래/실시간 루프: 명시적 요청 시에만 실행
python3 main.py

# 운영 로그 확인
tail -f logs/trading-$(date +%F).log

# 테스트가 추가된 경우
python3 -m unittest discover -s tests -v
```

## 코드 컨벤션
- 신규 거래소 추가 시 `exchange/base.py`를 상속하고 `main.py`의 `build_exchange()` 분기도 함께 갱신한다.
- 그리드 파일 파싱 규칙을 바꾸면 `core/grid.py`의 `load()`와 `save()`를 같이 수정한다.
- 리스크 정책 변경은 `config/settings.py`와 `main.py::check_risk()`를 함께 본다.
- 초기 그리드 생성 수량/매도 퍼센트 기준을 바꾸면 `config/settings.py`의 `GRID_FIRST_BUY_AMOUNT_KRW`, `GRID_SELL_PERCENT`, `main.py init-grid` 인자, `core/grid_builder.py` 계산식을 함께 맞춘다.
- BTC 그리드는 총 수량 한도보다 총 투입 KRW 예산과 최소 유보 잔고 기준으로 점검한다.
- 기능은 가능한 한 파일 단위 책임을 유지하고 `main.py`에서 조립한다.
- git commit 메시지를 쓸 상황이면 한글로 작성한다.
