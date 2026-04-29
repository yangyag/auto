# 설치 및 적용 가이드

## 파일 구조

```
프로젝트/
├── CLAUDE.md                          # 슬림화 (아래 예시)
└── .claude/
    ├── skills/
    │   └── strategy-pipeline/
    │       └── SKILL.md               # 본체 (자동 발동)
    └── agents/
        ├── math-expert.md             # subagent (opus)
        ├── generator.md               # subagent (sonnet)
        └── evaluator.md               # subagent (sonnet)
```

## 설치 단계

### 1. 디렉토리 생성

프로젝트 루트에서:

```bash
mkdir -p .claude/skills/strategy-pipeline
mkdir -p .claude/agents
```

### 2. 파일 배치

- `strategy-pipeline/SKILL.md` → `.claude/skills/strategy-pipeline/SKILL.md`
- `agents/math-expert.md` → `.claude/agents/math-expert.md`
- `agents/generator.md` → `.claude/agents/generator.md`
- `agents/evaluator.md` → `.claude/agents/evaluator.md`

### 3. CLAUDE.md 슬림화

기존 작업 파이프라인 섹션은 모두 빼고, 다음 한 줄만 남긴다:

```markdown
## 작업 파이프라인

전략 로직, 수식, 예산 분배, TP/리스크 규칙, 트리거 조건이 변경되는
작업에서는 `strategy-pipeline` skill의 흐름을 따른다.
검증 우선 원칙을 유지하고, 실거래 부작용 없는 검증 경로를 우선한다.
```

이렇게만 남겨도 skill의 description이 트리거를 잡아서 자동으로 발동한다.

## 동작 방식

**분리 결정은 파일 수가 아니라 작업 부피와 성격으로 한다.**
**분리하기로 결정했다면 반드시 Task 도구로 호출. 같은 세션 롤플레이 금지.**

### 단순 작업 (오타 수정, 로그 변경)
- skill이 발동하지 않는다.
- 메인 세션이 직접 처리한다.

### 짧은 코드 변경 (수식/리스크 무관, 짧은 수정)
- skill 발동 → Planner → Generator → Evaluator 흐름.
- Math Expert는 건너뛴다.
- Generator는 메인 세션이 직접 처리.
- Evaluator는 Task 도구로 반드시 호출.

### 부피가 큰 작업 (코드량 많음, 새 클래스/모듈 작성)
- 파일 수가 1개여도 분리 대상.
- Generator를 Task 도구로 호출 (sonnet subagent).
- Evaluator도 Task 도구로 호출.

### 수식/리스크 변경
- skill 발동 → Planner → **Math Expert (Task 도구로 호출, opus)** → **Generator (Task 도구로 호출, sonnet)** → **Evaluator (Task 도구로 호출, sonnet)**.
- Math Expert가 REJECT하면 Planner로 자동 회귀.
- Generator는 검증된 수식을 fresh 컨텍스트로 받아 그대로 구현.

### 컨텍스트가 이미 무거운 상태
- 긴 대화나 여러 파일 탐색 후에는 짧은 작업이라도 Generator를 Task 도구로 분리.

## 진짜 분리되는지 확인하는 방법

작업 시 다음 신호를 확인한다:

✅ **진짜 subagent 호출일 때 보이는 신호:**
- UI에 "Launching agent: math-expert" 같은 알림이 뜸
- 별도 toolkit/도구 호출 흐름이 시각적으로 분리됨
- subagent가 자기 컨텍스트에서 파일을 새로 Read하는 흔적
- 토큰 카운트가 별도로 표시될 수 있음

❌ **롤플레이로 흉내내고 있을 때의 신호:**
- 같은 응답 흐름 안에서 "## Math Expert 검증" 같은 헤더로 모드 전환만
- 새로운 도구 호출 없이 텍스트만 추가됨
- "Launching agent" 알림이 안 뜸

**롤플레이가 감지되면**: SKILL.md의 ⚠️ Subagent 호출 메커니즘 섹션을 다시 인지시키고, Task 도구로 호출하도록 명시 요청한다.

## 변경 사항 요약

| 항목 | 기존 | 변경 후 |
|---|---|---|
| CLAUDE.md 길이 | 길다 (모든 작업에 로드됨) | 3-4줄 (슬림) |
| 단순 작업 오버헤드 | 매번 파이프라인 지시 로드 | 발동 안 함 |
| 수식 검증 | 같은 모델/세션에서 self-check | opus subagent로 분리 |
| 코드 구현 | 메인 세션이 직접 (컨텍스트 누적) | sonnet subagent로 분리 (선택적) |
| Evaluator | 같은 세션에서 검토 | 별도 subagent로 관점 분리 |
| 모델 비용 | 일정 | Math Expert만 opus, 나머지 sonnet |
| 컨텍스트 보호 | 메인 세션이 모든 흔적 누적 | 각 subagent는 깨끗한 시작 |

## 보완 권장 사항

게임 서버 쪽 작업도 하시므로, 같은 패턴으로 도메인 skill을 추가로 분리하면 좋다:

- `.claude/skills/guild-arena-tournament/SKILL.md` — 길드 아레나 토너먼트 전용 컨벤션
- `.claude/skills/dungeon-strategy/SKILL.md` — 던전 전략 클래스 패턴
- `.claude/skills/cs-ws-cws-sync/SKILL.md` — 분산 서버 동기화 가이드

이건 다음 작업으로 진행할 수 있다.
