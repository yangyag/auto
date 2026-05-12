#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$PROJECT_DIR/.auto-command-worker.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Command worker PID 파일이 없습니다. 이미 종료되었을 수 있습니다."
  exit 0
fi

pid="$(tr -d '[:space:]' < "$PID_FILE")"
if [[ -z "$pid" ]]; then
  rm -f "$PID_FILE"
  echo "Command worker PID 파일이 비어 있어 정리했습니다."
  exit 0
fi

kill "$pid" 2>/dev/null || true

for _ in $(seq 1 10); do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Command worker 정상 종료. PID=$pid"
    exit 0
  fi
  sleep 1
done

kill -9 "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
echo "Command worker 강제 종료. PID=$pid"
