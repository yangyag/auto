#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

if [[ ! -d "$LOG_DIR" ]]; then
  echo "logs 디렉터리가 없습니다: $LOG_DIR" >&2
  exit 1
fi

shopt -s nullglob
log_files=("$LOG_DIR"/trading-????-??-??.log)
shopt -u nullglob

if (( ${#log_files[@]} == 0 )); then
  echo "추적할 로그 파일이 없습니다: $LOG_DIR/trading-YYYY-MM-DD.log" >&2
  exit 1
fi

latest_name="$(printf '%s\n' "${log_files[@]##*/}" | sort | tail -n 1)"
latest_log="$LOG_DIR/$latest_name"

if [[ ! -r "$latest_log" ]]; then
  echo "로그 파일을 읽을 수 없습니다: $latest_log" >&2
  exit 1
fi

echo "최신 로그 추적: $latest_log"
exec tail -f "$latest_log"
