---
name: strategy-pipeline
description: Use for strategy logic, formulas, budget allocation, TP/SL or risk rules, trigger conditions, inventory ratio, or position sizing changes. Enforce a Planner -> optional strategy_math_expert -> strategy_generator -> strategy_evaluator flow. Trigger on Korean or English requests such as "전략 수정", "TP 변경", "리스크 룰", "예산 분배", "수식 추가", "계산 로직", "트리거 조건", or when numeric trading logic may change. Do not use for typos, logs, docs-only updates, simple refactors, or non-calculation bug fixes.
---

# Strategy Pipeline

Use this workflow for trading strategy, formula, and risk logic changes. These changes can affect live trading behavior, so preserve validation integrity and keep edits surgical.

## Subagent Rule

When this skill says "use a subagent", use a real Codex subagent/custom agent. Do not roleplay as Math Expert, Generator, or Evaluator inside the same context.

Preferred custom agents:
- `strategy_math_expert` (`.agents/agents/strategy_math_expert.md`): validates formulas and numeric logic before implementation.
- `strategy_generator` (`.agents/agents/strategy_generator.md`): implements only the approved scope.
- `strategy_evaluator` (`.agents/agents/strategy_evaluator.md`): reviews the finished implementation for operational risk.

If the current Codex environment or higher-priority instructions block subagent spawning, say so explicitly and continue in the main session without pretending the review was isolated.

## When To Apply

Apply this pipeline to:
- Strategy logic changes.
- Formula or calculation changes.
- Budget allocation changes.
- TP, SL, or risk-rule changes.
- Entry or exit trigger changes.
- Inventory ratio or position-sizing changes.
- Threshold changes that affect trading decisions.

Do not apply it to:
- Typos, log text, or docs-only updates.
- Variable rename refactors or import cleanup.
- Simple non-calculation packet or handler fixes.

## Flow

Default:

```text
Planner -> strategy_generator -> strategy_evaluator
```

If formulas, calculations, strategy logic, budget allocation, TP/SL, or risk rules are involved:

```text
Planner -> strategy_math_expert -> strategy_generator -> strategy_evaluator
```

## Planner

Before implementation, fix the scope and success criteria.

Planner output must include:
1. Changed files or intended file scope.
2. Success criteria.
3. Whether Math Expert review is required, with reasoning.
4. Affected interfaces and call paths.

Planner must inspect the real files and usage paths with search/read tools before deciding. Do not rely on memory.

## Math Expert

Use `strategy_math_expert` before code changes when numeric trading logic is involved.

Send the agent:
- Planner output.
- Formula, calculation, threshold, budget allocation, TP/SL, risk, trigger, or inventory-ratio spec.
- Relevant file paths and existing code snippets or symbols to inspect.

The Math Expert checks:
- Unit consistency: quantity, amount, price, ratio, and time units.
- Sign and direction: long/short TP/SL, numerator/denominator, cumulative vs incremental values.
- Boundary conditions: zero, negative inputs, empty positions/lists, min/max limits, floating-point comparison.
- Budget allocation: total allocation, ratio sum, rounding drift, simultaneous-entry conflicts.
- Trigger behavior: one-shot vs every tick, duplicate orders, time-boundary behavior.
- State dependency: initial state, restart equivalence, cached vs live values.

Only proceed to implementation after `APPROVED`. If the result is `REJECTED` or `INCOMPLETE`, revise the plan and run Math Expert again.

## Generator

Use `strategy_generator` when:
- Math Expert approved the numeric spec.
- The change is large enough to benefit from fresh context.
- A new class/module is being created.
- The main context is already heavy.
- The same implementation pattern must be repeated.

For very small non-numeric changes, the main session may implement directly, but it must still follow the Planner scope.

Send the Generator:
- Planner scope and success criteria.
- Affected interfaces.
- Math Expert `APPROVED` output, if any, without changing the approved formulas.
- Existing code-style constraints discovered from the repo.

Generator constraints:
- Do not expand Planner scope.
- Do not alter approved formulas, even if mathematically equivalent.
- Match existing code style.
- Keep changes minimal and directly tied to the request.
- Stop and report if new formulas, wider scope, interface design decisions, or conflicting call paths appear.

## Evaluator

Use `strategy_evaluator` after implementation. The evaluator should inspect the changed files and relevant call paths as a fresh reviewer.

Send the Evaluator:
- Changed file list.
- Planner scope.
- Math Expert `APPROVED` output, if any.
- Summary of implementation decisions.

Evaluator checks:
- Regression risk across all changed symbols and call paths.
- Sensitive data exposure in logs, errors, and responses.
- Live-trading side effects, dry-run bypasses, duplicate orders, retry/idempotency risk.
- Agreement with Math Expert formulas and boundary requirements.
- State persistence and restart behavior.
- Observability gaps directly caused by the change.

If the evaluator returns `FAIL`, go back to Planner or Generator as appropriate. If it returns `NEEDS_FOLLOWUP`, clearly separate required follow-up from the current completed scope.
