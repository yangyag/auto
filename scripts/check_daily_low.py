#!/usr/bin/env python3
"""logs/trading-YYYY-MM-DD.log 파일들에서 날짜별 최저가를 출력한다."""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = PROJECT_ROOT / "logs"
PRICE_RE = re.compile(r"현재가: (\d+)")
LOG_RE = re.compile(r"^trading-(\d{4}-\d{2}-\d{2})\.log$")


def main() -> int:
    files = sorted(LOGS_DIR.glob("trading-*.log"))
    if not files:
        print(f"로그 파일이 없습니다: {LOGS_DIR}")
        return 1

    print(f"{'날짜':<12} {'최저가':>14}")
    for path in files:
        m = LOG_RE.match(path.name)
        if not m:
            continue
        date = m.group(1)
        prices = [int(p) for p in PRICE_RE.findall(path.read_text(encoding="utf-8", errors="replace"))]
        if not prices:
            print(f"{date:<12} {'-':>14}")
            continue
        print(f"{date:<12} {min(prices):>14,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
