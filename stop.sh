#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

if [[ ! -f "$PID_FILE" ]]; then
  echo "PID 파일이 없습니다. 이미 종료되었을 수 있습니다."
  exit 0
fi

pid="$(tr -d '[:space:]' < "$PID_FILE")"
if [[ -z "$pid" ]]; then
  rm -f "$PID_FILE"
  echo "PID 파일이 비어 있어 정리했습니다."
  exit 0
fi

if ! is_target_running "$pid"; then
  rm -f "$PID_FILE"
  echo "실행 중인 프로세스가 없어 PID 파일만 정리했습니다."
  exit 0
fi

kill "$pid"

for _ in $(seq 1 10); do
  if ! is_target_running "$pid"; then
    rm -f "$PID_FILE"
    echo "정상 종료했습니다. PID=$pid"
    exit 0
  fi
  sleep 1
done

kill -9 "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
echo "강제 종료했습니다. PID=$pid"
