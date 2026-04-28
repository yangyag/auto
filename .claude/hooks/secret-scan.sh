#!/usr/bin/env bash
# PreToolUse hook for Bash. git commit 직전에 staged 변경에서 민감정보 패턴을 검사한다.
# - .env 파일이 staged 되어 있으면 차단
# - KEY/SECRET/TOKEN/PASSWORD 류 변수에 길이 20+ 의 값이 할당되면 차단
# - AWS access key ID 패턴(AKIA...) 차단
# 차단 시 exit 2 (Claude 에게 stderr 가 전달되어 후속 행동을 막음).

set -uo pipefail

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))' 2>/dev/null || echo "")

# git commit 호출이 아니면 통과
if ! printf '%s' "$COMMAND" | grep -qE '(^|[[:space:];|&(])git[[:space:]]+commit([[:space:]]|$)'; then
    exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

STAGED_FILES=$(git diff --cached --name-only 2>/dev/null)
if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

VIOLATIONS=()

# 1) .env 류 staged
ENV_HITS=$(printf '%s\n' "$STAGED_FILES" | grep -E '(^|/)\.env(\..*)?$' || true)
if [ -n "$ENV_HITS" ]; then
    VIOLATIONS+=("'.env' 류 파일이 staged: $(printf '%s' "$ENV_HITS" | tr '\n' ' ')")
fi

# 2) staged diff 의 추가 라인만 검사 (^\+[^+] 패턴으로 +++ 헤더 자동 제외)
DIFF_ADDED=$(git diff --cached -U0 2>/dev/null | grep -E '^\+[^+]' || true)

if [ -n "$DIFF_ADDED" ]; then
    SUSPECT=$(printf '%s\n' "$DIFF_ADDED" | grep -nE '[A-Z_]*(KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z_]*[[:space:]]*=[[:space:]]*["'"'"']?[A-Za-z0-9+/=_\-]{20,}' || true)
    if [ -n "$SUSPECT" ]; then
        VIOLATIONS+=("자격증명 의심 할당:")
        while IFS= read -r line; do
            [ -n "$line" ] && VIOLATIONS+=("    $line")
        done <<< "$SUSPECT"
    fi

    AWS_HITS=$(printf '%s\n' "$DIFF_ADDED" | grep -nE 'AKIA[0-9A-Z]{16}' || true)
    if [ -n "$AWS_HITS" ]; then
        VIOLATIONS+=("AWS access key 패턴:")
        while IFS= read -r line; do
            [ -n "$line" ] && VIOLATIONS+=("    $line")
        done <<< "$AWS_HITS"
    fi
fi

if [ ${#VIOLATIONS[@]} -gt 0 ]; then
    {
        echo "[secret-scan] git commit 차단 — 민감정보 가능성:"
        for v in "${VIOLATIONS[@]}"; do
            echo "  $v"
        done
        echo ""
        echo "조치 방법:"
        echo "  - 환경변수 참조/플레이스홀더라면 패턴이 잡히지 않게 표현을 바꾸거나,"
        echo "  - 정말 민감정보면 staged 에서 제거 (git restore --staged <file>) 후 재커밋"
        echo "  - 스캔이 잘못 잡았다고 확신하면 .claude/hooks/secret-scan.sh 패턴을 조정"
    } >&2
    exit 2
fi

exit 0
