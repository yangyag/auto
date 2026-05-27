# CLAUDE.md

이 프로젝트의 전체 설명과 주요 로직은 `README.md`를 기준으로 확인한다.

더 세부적인 운영, 명령어, API, 전략 수식 관련 내용은 `docs/` 폴더의 각 Markdown 문서를 참조한다. 원본 HTML은 `docs/html/` 에 보존되어 있다 (브라우저로 직접 열어볼 수 있다).

- `docs/setup.md` — 설치 / 초기 설정 가이드. `.env`, PostgreSQL, 가상환경 준비가 필요할 때 본다.
- `docs/operations.md` — 운영 / 인프라 가이드. EC2 접속, 배포, `run.sh`/`venv` 절차 등 서버 운영 전반.
- `docs/quick-commands.md` — 빠른 명령어 모음 (Cheat Sheet). 명령어만 빠르게 찾을 때 본다.
- `docs/mobile-api.md` — Mobile API 사용 문서. FastAPI 서버(`run-api.sh`/`stop-api.sh`) 구동 및 엔드포인트.
- `docs/strategy-formulas.md` — 전략 수식과 세부 판정 조건. 매수/매도 로직, 그리드 계산식 참조.
- `docs/UPBIT_API_REFERENCE.md` — Upbit Open API 레퍼런스. 업비트 API 호출 방식과 사용 범위.

## 커밋 메시지
커밋 메시지는 한글로 작성한다.

## 멀티 에이전트 운영
이 프로젝트의 `.claude/settings.json` 은 팀 모드 (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `teammateMode: in-process`) 가 켜져 있다. 사용자가 "팀", "병렬", "여러 에이전트" 등으로 멀티 에이전트 작업을 요청하면 일회성 Agent 호출 대신 `TeamCreate` → `TaskCreate` (의존성 포함) → named teammate spawn → `SendMessage` 조율 → `shutdown_request` 종료 흐름을 사용한다.
