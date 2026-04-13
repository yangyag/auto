"""
전역 설정
거래소 종류 변경은 EXCHANGE_TYPE만 바꾸면 된다.
"""
import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv


def _load_project_env() -> None:
    """프로젝트 루트의 .env를 읽어 환경변수로 주입한다."""
    project_root = Path(__file__).resolve().parents[1]
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


_load_project_env()

# ── 거래소 선택 ──────────────────────────────────────────
# "crypto" : 코인 거래소 (exchange/crypto.py) → 업비트
# "stock"  : 주식 거래소 (exchange/stock.py)
EXCHANGE_TYPE = "crypto"

# ── 거래 대상 ────────────────────────────────────────────
# 업비트 마켓 형식: "KRW-BTC", "KRW-ETH" 등
SYMBOL = "KRW-BTC"

# ── 그리드 파일 ──────────────────────────────────────────
GRID_FILE = "grid.txt"
GRID_SLOT_COUNT = 10
GRID_LOWER_PRICE = Decimal("92253123")
GRID_UPPER_PRICE = Decimal("111137221")
GRID_TOTAL_BUDGET_KRW = Decimal("990000")

# ── API 키 (환경변수 우선, 없으면 프로젝트 루트 .env 사용) ─────
API_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
API_SECRET = os.getenv("UPBIT_SECRET_KEY", "")

# ── 리스크 파라미터 ──────────────────────────────────────
MAX_TOTAL_BUDGET_KRW = GRID_TOTAL_BUDGET_KRW  # BTC 그리드 총 투입 한도
MAX_DAILY_ORDERS = 50                         # 일일 최대 주문 횟수
MIN_BALANCE_RESERVE = Decimal("10000")       # 최소 유보 잔고 KRW (이 금액 이하이면 매수 block)

# ── 모니터링 주기 ────────────────────────────────────────
PRICE_POLL_INTERVAL = 5      # 가격 조회 간격 (초)

# ── 로그 ─────────────────────────────────────────────────
LOG_FILE = "trading.log"
LOG_LEVEL = "INFO"
