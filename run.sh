#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PID_FILE="$PROJECT_DIR/.auto-trading.pid"
TARGET_SCRIPT="$PROJECT_DIR/main.py"

is_target_running() {
  local pid="$1"
  if ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi

  local args
  args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$args" == *"$TARGET_SCRIPT"* ]]
}

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(tr -d '[:space:]' < "$PID_FILE")"
  if [[ -n "$existing_pid" ]] && is_target_running "$existing_pid"; then
    echo "이미 실행 중입니다. PID=$existing_pid"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

mkdir -p "$PROJECT_DIR/logs"

nohup "$PYTHON_BIN" "$TARGET_SCRIPT" >/dev/null 2>&1 &
new_pid=$!
echo "$new_pid" > "$PID_FILE"

sleep 1
if is_target_running "$new_pid"; then
  echo "백그라운드 실행 시작. PID=$new_pid"
  echo "로그: $PROJECT_DIR/logs/trading-$(date +%F).log"
  exit 0
fi

rm -f "$PID_FILE"
echo "실행에 실패했습니다. logs 폴더와 환경설정을 확인하세요." >&2
exit 1
