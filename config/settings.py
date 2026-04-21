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
GRID_TOTAL_BUDGET_KRW = Decimal("2400000")
GRID_TP_MODEL = "k"
GRID_TP_K_BASE = Decimal("9.0")
GRID_TP_K_FLOOR = Decimal("7.0")

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
MAX_TOTAL_BUDGET_KRW = None  # 기본은 현재 로드된 그리드 총배정금액을 truth로 본다.
MAX_OPERATING_BUDGET_KRW = None  # q_current 분모는 기본적으로 현재 그리드 총배정금액을 따른다.
MAX_DAILY_ORDERS = 50        # 일일 최대 주문 횟수
MIN_BALANCE_RESERVE = Decimal("10000")  # 최소 유보 잔고 KRW (이 금액 이하이면 매수 block)
UPBIT_FEE_RATE = Decimal("0.0005")  # 매수 필요 KRW 추정에 반영할 업비트 수수료율
FEE_BUFFER_KRW = Decimal("100")  # 수수료 외 추가 안전 버퍼

# ── 전략 안전장치 / 재고 목표 ─────────────────────────────
UPWARD_BUY_ENABLED = True    # 상승 1칸 돌파 시장가 매수. 기본값 ON
UPWARD_SINGLE_SLOT_BUY_ENABLED = UPWARD_BUY_ENABLED
INVENTORY_TARGET_Q_MIN = Decimal("0.10")
INVENTORY_TARGET_Q_MAX = Decimal("0.85")
INVENTORY_TARGET_GAMMA = Decimal("1.5")
INVENTORY_TARGET_EPSILON = Decimal("0.03")
ACTIVE_WINDOW_ENABLED = True
ACTIVE_WINDOW_BELOW_CURRENT_SLOTS = 48
ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS = 4
ACTIVE_BUY_WINDOW_ENABLED = ACTIVE_WINDOW_ENABLED
ACTIVE_WINDOW_ABOVE_CURRENT_SLOTS = ACTIVE_WINDOW_ABOVE_CURRENT_REENTRY_SLOTS
BREAKOUT_GUARD_ENABLED = True
BREAKOUT_GUARD_CANDLE_UNIT = 15
BREAKOUT_GUARD_CONSECUTIVE_CANDLES = 4
BREAKOUT_GUARD_FAIL_OPEN = False  # 캔들 조회 실패 시 신규 매수를 차단
BREAKOUT_GUARD_CANDLE_UNIT_MINUTES = BREAKOUT_GUARD_CANDLE_UNIT
BREAKOUT_GUARD_CONSECUTIVE_CLOSES = BREAKOUT_GUARD_CONSECUTIVE_CANDLES
BREAKOUT_GUARD_FAILURE_POLICY = "open" if BREAKOUT_GUARD_FAIL_OPEN else "close"

# ── 모니터링 주기 ────────────────────────────────────────
PRICE_POLL_INTERVAL = 5      # 가격 조회 간격 (초)

# ── 로그 ─────────────────────────────────────────────────
LOG_DIR = "logs"
LOG_FILE = "trading.log"
LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 3
