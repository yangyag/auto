# CLAUDE.md

이 프로젝트의 전체 설명과 주요 로직은 `README.md`를 기준으로 확인한다.

더 세부적인 운영, 명령어, API, 전략 수식 관련 내용은 `docs/` 폴더의 각 Markdown 문서를 참조한다.

- `docs/setup.md`
- `docs/operations.md`
- `docs/quick-commands.md`
- `docs/mobile-api.md`
- `docs/strategy-formulas.md`
- `docs/UPBIT_API_REFERENCE.md`

## 멀티 에이전트 운영
이 프로젝트의 `.claude/settings.json` 은 팀 모드 (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `teammateMode: in-process`) 가 켜져 있다. 사용자가 "팀", "병렬", "여러 에이전트" 등으로 멀티 에이전트 작업을 요청하면 일회성 Agent 호출 대신 `TeamCreate` → `TaskCreate` (의존성 포함) → named teammate spawn → `SendMessage` 조율 → `shutdown_request` 종료 흐름을 사용한다.
