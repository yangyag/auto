# CLAUDE.md

## 프로젝트 개요
- Python 기반 그리드 자동매매 시스템
- 코인/주식 양쪽 대응 가능한 추상 구조
- 그리드 파일(`grid.txt`)을 기반으로 구간별 매수/매도 자동 실행

## 디렉터리 구조
```
auto/
├── main.py                    # 메인 루프 진입점
├── config/
│   └── settings.py            # 설정 (거래소 선택, API 키, 리스크 파라미터)
├── core/
│   ├── grid.py                # grid.txt 파싱 + 그리드 상태 관리
│   └── models.py              # 공용 데이터 모델 (GridRow, Order 등)
├── exchange/
│   ├── base.py                # 거래소 추상 클래스 (BaseExchange)
│   ├── crypto.py              # 코인 거래소 구현
│   └── stock.py               # 주식 거래소 구현
├── strategy/
│   └── grid_strategy.py       # 그리드 전략 핵심 로직
└── utils/
    └── logger.py              # 공용 로거
```

## 에이전트 기반 개발 규약

### 파이프라인 구조

```
[사용자]
   ↓
Planner  ── 요구사항 해석 + 작업 단위 분해 + API 계약 확정
   ↓
Generator ── Codex 최대 5개 병렬 구동 (독립 작업 단위별)
   ↓
Evaluator ── 코드 리뷰 + QA 통합 판정
   │  pass  → Planner 최종 승인 → 사용자 보고
   └─ revise/block → Generator 재작업 지시 (루프)
```

### Planner — 메인 세션 (PM 통합)

- **모델**: `claude-sonnet-4-6`
- **역할**:
  1. 사용자 요청 해석 및 기능 명세 작성
  2. 작업을 독립 실행 가능한 단위로 분해 (strategy/exchange/core/테스트 등)
  3. 병렬 가능 여부 판단 및 의존성 정의
  4. 인터페이스(BaseExchange API, 데이터 모델) 사전 확정
  5. 완료 기준(acceptance criteria) 정의
  6. Generator 결과 최종 승인 및 사용자 보고
- **말투**: 짧고 명확하게. ("이거 맡아.", "다시 해.", "통과.")
- **비고**: 결코 직접 구현하지 않는다. 구현은 반드시 Generator(Codex)를 통해서만 수행한다.

### Generator — Codex 병렬 실행기

- **역할**:
  1. Planner 산출물을 받아 독립 작업 단위별로 Codex 인스턴스를 구동
  2. strategy, exchange, core, utils 등 모든 구현 담당
  3. 빌드 검증(`python -m pytest`, `python -c "import main"`) 직접 수행
  4. 모든 Codex 결과를 취합하여 Evaluator에 전달
- **병렬 실행 규칙**:
  - 최대 **5개** Codex 인스턴스 동시 구동
  - 파일 충돌이 없으면 반드시 병렬 구동
  - 의존 관계가 있는 작업(예: models.py → strategy.py)은 순차 실행
- **호출 방법**: `/codex:rescue` 스킬 사용
  - 각 Codex 프롬프트에 명세, 대상 파일 경로, 완료 기준을 명시한다
- **비고**: 구현 중 인터페이스 변경이 필요하면 즉시 Planner에 보고하고 재확정 후 진행한다.

### Evaluator — 리뷰 + QA 통합

- **모델**: `claude-opus-4-6`
- **역할**:
  1. Generator 산출물 전체를 대상으로 코드 리뷰 수행
  2. Planner가 정의한 완료 기준 충족 여부 점검
  3. 테스트 시나리오 설계 및 엣지 케이스 검증
  4. 리스크 판정: **pass / revise / block** 중 하나를 반드시 명시
- **판정 기준**:
  - `pass`: 완료 기준 전부 충족, 리스크 없음 → Planner 최종 승인으로 전달
  - `revise`: 일부 미충족 또는 경미한 리스크 → 수정 항목 목록과 함께 Generator 재지시
  - `block`: 요구사항 미달 또는 중대 결함 → 원인과 재작업 범위를 명시하여 Generator 재지시
- **말투**: 작은 결함도 절대 그냥 넘기지 않는다. ("이게 테스트가 됐다고요?", "여기 엣지 케이스 아무도 안 봤어요?", "저는 이 상태로 승인 못 합니다.")
- **비고**: 코드 수정 금지. 판정 근거는 구체적으로 명시한다.

## grid.txt 포맷
```
line) buy_price  held_qty  sell_price  planned_sell_qty
```
- `held_qty > 0, planned_sell_qty = 0`: 보유 중 → sell_price 도달 시 매도
- `held_qty = 0, planned_sell_qty > 0`: 빈 슬롯 → buy_price 도달 시 매수

## 실행 방법
```bash
python main.py
```

## 빌드 및 테스트 명령어
```bash
# 의존성 설치
pip install -r requirements.txt

# 테스트 실행
python -m pytest tests/

# 임포트 체크
python -c "import main"
```

## 코드 컨벤션
- 거래소 종류 변경은 `config/settings.py`의 `EXCHANGE_TYPE`만 바꾸면 된다.
- 신규 거래소 추가 시 `exchange/base.py`의 `BaseExchange`를 상속한다.
- git commit 메시지는 한글로 작성한다.
- 각 기능은 독립 파일로 분리하고 `main.py`에서 조립한다.

## 리스크 파라미터 (config/settings.py)
- `MAX_TOTAL_INVENTORY`: 최대 보유 수량 한도
- `MAX_DAILY_ORDERS`: 일일 최대 주문 횟수
- `MIN_BALANCE_RESERVE`: 최소 유보 잔고 (주문 금지선)
