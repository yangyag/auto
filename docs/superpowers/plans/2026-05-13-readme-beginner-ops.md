# README 초보 운영자 보강 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `README.md` 상단에 초보 운영자가 일상 운영 명령을 바로 찾을 수 있는 빠른 시작 섹션을 추가한다.

**Architecture:** 기존 README의 전략/구현 설명은 유지하고, 문서 초반에 운영자용 안내 레이어를 추가한다. 상세 명령 전체를 중복하지 않고 `docs/setup.md`, `docs/operations.md`, `docs/quick-commands.md`로 연결한다.

**Tech Stack:** Markdown, 기존 shell 운영 명령, Python 가상환경 `.venv/bin/python`

---

### Task 1: README 상단 운영자 안내 추가

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 현재 README 상단 구조 확인**

Run:

```bash
sed -n '1,80p' README.md
```

Expected: 제목, 시스템 요약, "파일 구성 및 역할" 섹션이 보인다.

- [ ] **Step 2: README 제목 아래에 운영자용 안내 섹션 추가**

`README.md`의 첫 설명 문단과 "파일 구성 및 역할" 사이에 다음 구조를 추가한다.

```markdown
## 먼저 읽기

...

## 초보 운영자 빠른 시작

...

## grid.properties 수정 후 기본 흐름

...

## 위험 명령

...

## 문제가 생기면 먼저 볼 것

...
```

Expected: 기존 전략 설명은 삭제하지 않고 새 운영자 섹션만 삽입된다.

- [ ] **Step 3: Markdown 제목 목록 확인**

Run:

```bash
rg -n '^## ' README.md
```

Expected: 새 섹션들이 "파일 구성 및 역할"보다 앞에 있고, 기존 섹션 제목들이 유지된다.

### Task 2: README 변경 검증

**Files:**
- Verify: `README.md`

- [ ] **Step 1: 미완성 문구 확인**

Run:

```bash
rg -n 'TBD|TODO|작성 예정|나중에|placeholder' README.md docs/superpowers/specs/2026-05-13-readme-beginner-ops-design.md docs/superpowers/plans/2026-05-13-readme-beginner-ops.md || true
```

Expected: 새 문서의 설명 문맥을 제외하고 미완성 문구가 없다.

- [ ] **Step 2: 변경 diff 확인**

Run:

```bash
git diff -- README.md docs/superpowers/specs/2026-05-13-readme-beginner-ops-design.md docs/superpowers/plans/2026-05-13-readme-beginner-ops.md
```

Expected: 변경 범위가 README 보강, 설계 문서, 계획 문서에 한정된다.

- [ ] **Step 3: 작업 트리 확인**

Run:

```bash
git status --short
```

Expected: 사용자 기존 변경인 `docs/infinite-team.md`는 건드리지 않았고, 새 작업 파일과 README만 변경된다.

## Self-Review

- Spec coverage: 설계의 빠른 시작, grid.properties 흐름, 위험 명령, 문제 확인 순서를 Task 1에서 모두 반영한다.
- Placeholder scan: 계획 안에는 실행 가능한 명령과 기대 결과가 있으며 미완성 작업 지시가 없다.
- Scope consistency: 코드와 런타임 설정은 변경하지 않는다.
