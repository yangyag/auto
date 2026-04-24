# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 먼저 읽을 문서

이 저장소는 용도별 문서가 이미 분리되어 있다. 추측하지 말고 해당 문서를 먼저 확인한다.

- `AGENTS.md` — 인프라, 운영, EC2 배포, 작업 파이프라인, venv 규칙
- `README.md` — 트레이딩 전략과 프로그램 로직 (매수/매도 규칙, 그리드 상태, Age TP, 브레이크아웃 가드, 주문 수명주기)
- `setup.md` — 최초 설치 절차
- `docs/quick-commands.md` — 자주 쓰는 운영 명령 모음
- `docs/UPBIT_API_REFERENCE.md` — 업비트 REST/WebSocket API 메모

## 작업 파이프라인 (AGENTS.md 기준)

기본 흐름은 `Planner → Generator → Evaluator` 다. 수식, 계산, 전략 로직, 예산 분배, 재고 비율, TP/리스크 규칙이 하나라도 바뀌면 흐름은 `Planner → Math Expert → Generator → Evaluator` 로 격상된다. Math Expert 는 코드 작성 전에 로직 정합성, 단위 일관성, 경계 조건을 검증하며 — 항상 최신 모델을 `xhigh` reasoning effort 로 쓴다 — 검증에 실패하면 계획을 Planner 단계로 되돌린다. 비단순 작업은 각 역할을 실제로 분리된 에이전트로 수행한다.

Git 커밋 메시지는 사용자가 다른 언어를 명시하지 않는 한 한국어를 우선한다.

## 명령어

아래 Python 명령은 모두 프로젝트 루트에서 `.venv/bin/python` 기준이다.

### 테스트
- 전체: `.venv/bin/python -m unittest discover -s tests -v`
- 파일 단위: `.venv/bin/python -m unittest tests.test_grid_strategy -v`
- 케이스 단위: `.venv/bin/python -m unittest tests.test_grid_strategy.TestClassName.test_method -v`
- import 스모크 체크: `.venv/bin/python -c "import main"`

### 봇 실행
- 백그라운드 시작: `PYTHON_BIN=.venv/bin/python ./run.sh` (`.auto-trading.pid` 기록, 로그는 `logs/trading-YYYY-MM-DD.log`)
- 종료: `./stop.sh`
- 최신 로그 추적: `./tail-latest-log.sh`
- 포그라운드 실행 (블로킹, PID 파일 없음): `.venv/bin/python main.py`

### CLI 서브커맨드 (`main.py`)
- 인자 없음 — 메인 트레이딩 루프
- `balance` — 업비트 KRW 주문 가능 잔고 1회 조회
- `init-grid [--force]` — 슬롯 개수 기반 그리드 시드 (`grid.properties` 경로의 대안)

### 그리드 / 예산 관리 스크립트
- `grid.properties` DB 반영 (기본 시드 경로): `.venv/bin/python scripts/apply_grid_properties_to_postgres.py --force`
- DB 그리드 상태 조회 (읽기 전용): `.venv/bin/python scripts/show_grid_state.py`
- 라이브 전체 리셋 (stop → 미체결 취소 → BTC 시장가 전량 매도 → `grid.properties` 기준 재시드 → run): `.venv/bin/python scripts/reset_krw_btc_live.py`
- 소프트 예산 조정 (보유 수량, 가격, `filled_at` 유지, `planned_qty` 만 재계산): `.venv/bin/python scripts/adjust_budget_live.py --target-budget <KRW>`

## 아키텍처

업비트 `KRW-BTC` 기반 그리드 자동매매 봇이며 상태는 PostgreSQL 에 저장된다. `main.py` 메인 루프는 업비트 public ticker WebSocket 이벤트 구동이고, 장애 시 5초 REST polling 으로 fallback 한다. 전략 평가는 최소 3초 간격으로 throttle 된다. **DB 쓰기와 주문 제출은 모두 메인 스레드에서 직렬로 처리된다.** WebSocket 콜백은 `exchange/upbit_ws.py` 의 인메모리 캐시만 채우므로, 틱 폭주가 있어도 backlog 로 쌓이지 않고 최신 가격으로 coalesce 된다.

모듈 책임 (파일 단위 상세는 README.md 참고):

- **`core/`** — 그리드 데이터 모델: 슬롯 상태(`GridState`), 슬롯 생성(`grid_builder.py`), `grid.properties` 스펙 파싱, 공용 Enum.
- **`strategy/`** — 트레이딩 판정: `grid_strategy.py` 는 교차 판정 + 활성 윈도우 + inventory-target gate + 브레이크아웃 가드를 실행하고, `breakout_guard.py` 는 캔들 기반 신규 매수 차단, `recenter_preview.py` 는 recenter 시뮬레이션.
- **`exchange/`** — 업비트 연동: `crypto.py` 는 REST 로 주문 제출/재조회를 수행하고, `upbit_ws.py` 는 ticker/candle/myAsset/myOrder WebSocket 캐시를 관리한다. WS 캐시가 켜져 있어도 주문 생성/취소는 계속 REST 로만 나간다.
- **`storage/`** — PostgreSQL 영속성: 그리드 repo + pending 주문 repo + factory + interfaces. 주문은 업비트 `uuid` 와 nullable `identifier` 를 함께 저장하며, reconciliation 주키는 `uuid` 다.
- **`config/settings.py`** — `.env` 로드 후 런타임 토글(WS enable, TP `k_base`/`k_floor`, 활성 윈도우 크기, 브레이크아웃 가드 파라미터, 예산 한도, `STATE_BOT_KEY`) 전부를 노출.

## 반드시 유지할 불변식

- **주문 수명주기는 업비트가 authoritative.** 슬롯이 `holding` 으로 바뀌는 건 `GET /v1/order` 가 `done` 을 돌려주거나, `cancelled` 이면서 `executed_volume > 0` 인 경우뿐이다. `POST /v1/orders` 응답만 보고 그리드 상태를 바꾸면 안 된다.
- **BUY 체결이 확정되면 즉시 TP SELL pending 을 건다.** 보유 슬롯은 대응하는 SELL pending 을 하나씩 가지는 구조가 기본이며, reconciliation 은 누락된 경우에만 보강한다.
- **Age TP 는 런타임 `effective_sell_price` 에만 적용된다.** 저장된 `sell_price` 는 절대 덮어쓰지 않고, 이미 제출된 SELL pending 은 압축 변화에 맞춰 재호가하지 않는다. 압축은 새 SELL 주문을 만들 때만 반영된다.
- **런타임 `GRID_TP_K_BASE` / `GRID_TP_K_FLOOR` 는 DB 그리드를 시드할 때 쓴 값과 일치해야 한다.** 어긋나면 의도한 TP 폭이 조용히 늘거나 줄어든다.
- **브레이크아웃 가드는 기본 fail-close 다** (`BREAKOUT_GUARD_FAIL_OPEN=False`). 캔들 조회 실패 시 신규 매수는 막고 매도는 계속 허용한다.
- **단일 프로세스 락은 PostgreSQL 에 `STATE_BOT_KEY` 단위로 걸린다.** 같은 키에 대해서는 봇이 하나만 돌 수 있다.
- **`POST /v1/orders` timeout / network error 는 자동 재시도하지 않는다.** 모호한 결과는 reconciliation 이 재조회로 수습할 때까지 모호한 상태로 둔다.

## 흔한 함정

- `grid.properties` 의 `TOTAL_BUDGET_KRW` 는 상단/중단/하단 **0.7× / 1.0× / 1.3×** 가중치로 분배된다. 정상 시드된 그리드는 `show_grid_state.py` 출력에서 `bottom_slot_planned_buy_budget > top_slot_planned_buy_budget` 이 성립한다 — 이걸 sanity check 로 쓴다.
- `grid.properties` 는 `GRID_COUNT` 와 `GRID_STEP_PCT` 중 **정확히 하나만** 받는다.
- EC2 의 venv 는 `/home/ubuntu/auto/.venv` 에 이미 구성되어 있다. **재생성하지 말고 그대로 쓴다.** `.venv/` 는 정상적으로 untracked 상태이며 `git clean -fd` 로 날려서는 안 된다. 자세한 건 AGENTS.md "Python 실행 환경 메모" 참고.
- EC2 호스트의 `/home/ubuntu/llm.env` 는 다른 서비스용 파일이다. 자동매매 봇의 env 는 `/home/ubuntu/auto/.env` 다.
