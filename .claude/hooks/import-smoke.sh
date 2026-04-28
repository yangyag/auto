#!/usr/bin/env bash
# PreToolUse hook for Bash. git push 직전에 `import main` 스모크 체크.
# 실패하면 exit 2 로 push 를 차단해 broken main 이 원격에 올라가는 것을 막는다.
# .venv/bin/python 이 없는 환경(예: 일부 CI/원격)에서는 조용히 건너뛴다.

set -uo pipefail

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))' 2>/dev/null || echo "")

# git push 호출이 아니면 통과
if ! printf '%s' "$COMMAND" | grep -qE '(^|[[:space:];|&(])git[[:space:]]+push([[:space:]]|$)'; then
    exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

PY=""
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PY="$PROJECT_DIR/.venv/bin/python"
elif [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
fi

if [ -z "$PY" ]; then
    echo "[import-smoke] .venv/bin/python 없음 — 스모크 체크 건너뜀." >&2
    exit 0
fi

OUTPUT=$("$PY" -c "import main" 2>&1)
RC=$?
if [ $RC -ne 0 ]; then
    {
        echo "[import-smoke] git push 차단 — 'import main' 실패:"
        printf '%s\n' "$OUTPUT" | sed 's/^/    /'
        echo ""
        echo "원인을 먼저 진단하세요. 실제 import 가 깨진 상태면 push 하면 안 됩니다."
    } >&2
    exit 2
fi

exit 0
