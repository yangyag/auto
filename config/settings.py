"""
전역 설정
거래소 종류 변경은 EXCHANGE_TYPE만 바꾸면 된다.
"""
import os
from decimal import Decimal
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


def _load_env_file_without_dotenv(env_file: Path) -> None:
    """python-dotenv 없이도 단순 KEY=VALUE 형식 .env를 읽는다."""
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def _load_project_env() -> None:
    """프로젝트 루트의 .env를 읽어 환경변수로 주입한다."""
    project_root = Path(__file__).resolve().parents[1]
    env_file = project_root / ".env"
    if env_file.exists():
        if load_dotenv is not None:
            load_dotenv(env_file, override=False)
        else:
            _load_env_file_without_dotenv(env_file)


_load_project_env()

# ── 거래소 선택 ──────────────────────────────────────────
# "crypto" : 코인 거래소 (exchange/crypto.py) → 업비트
# "stock"  : 주식 거래소 (exchange/stock.py)
EXCHANGE_TYPE = "crypto"

# ── 거래 대상 ────────────────────────────────────────────
# 업비트 마켓 형식: "KRW-BTC", "KRW-ETH" 등
SYMBOL = "KRW-BTC"

# ── PostgreSQL 상태 저장 ─────────────────────────────────
STATE_BOT_KEY = os.getenv("STATE_BOT_KEY", "krw-btc-live")
GRID_SLOT_COUNT = 10
GRID_LOWER_PRICE = Decimal("92253123")
GRID_UPPER_PRICE = Decimal("111137221")
GRID_FIRST_BUY_AMOUNT_KRW = Decimal("200000")
GRID_SELL_PERCENT = Decimal("5")

# ── PostgreSQL 접속 정보 ─────────────────────────────────
PGHOST = os.getenv("PGHOST", "127.0.0.1")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "yangyag")
PGUSER = os.getenv("PGUSER", "yangyag")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PGSCHEMA = os.getenv("PGSCHEMA", "auto_trading")

# ── API 키 (환경변수 우선, 없으면 프로젝트 루트 .env 사용) ─────
API_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
API_SECRET = os.getenv("UPBIT_SECRET_KEY", "")

# ── 리스크 파라미터 ──────────────────────────────────────
MAX_TOTAL_BUDGET_KRW = None  # BTC 그리드 총 투입 한도. None 또는 0 이하면 제한 비활성화
MAX_DAILY_ORDERS = 50        # 일일 최대 주문 횟수
MIN_BALANCE_RESERVE = Decimal("10000")  # 최소 유보 잔고 KRW (이 금액 이하이면 매수 block)

# ── 모니터링 주기 ────────────────────────────────────────
PRICE_POLL_INTERVAL = 5      # 가격 조회 간격 (초)

# ── 로그 ─────────────────────────────────────────────────
LOG_DIR = "logs"
LOG_FILE = "trading.log"
LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 7
