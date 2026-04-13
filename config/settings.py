"""
전역 설정
거래소 종류 변경은 EXCHANGE_TYPE만 바꾸면 된다.
"""
import os

# ── 거래소 선택 ──────────────────────────────────────────
# "crypto" : 코인 거래소 (exchange/crypto.py) → 업비트
# "stock"  : 주식 거래소 (exchange/stock.py)
EXCHANGE_TYPE = "crypto"

# ── 거래 대상 ────────────────────────────────────────────
# 업비트 마켓 형식: "KRW-BTC", "KRW-ETH" 등
SYMBOL = "KRW-BTC"

# ── 그리드 파일 ──────────────────────────────────────────
GRID_FILE = "grid.txt"

# ── API 키 (환경변수 우선, 없으면 직접 입력) ──────────────
API_KEY    = os.getenv("UPBIT_ACCESS_KEY", "")
API_SECRET = os.getenv("UPBIT_SECRET_KEY", "")

# ── 리스크 파라미터 ──────────────────────────────────────
MAX_TOTAL_INVENTORY = 300    # 최대 보유 수량 한도 (초과 시 신규 매수 block)
MAX_DAILY_ORDERS    = 50     # 일일 최대 주문 횟수
MIN_BALANCE_RESERVE = 10000  # 최소 유보 잔고 KRW (이 금액 이하이면 매수 block)

# ── 모니터링 주기 ────────────────────────────────────────
PRICE_POLL_INTERVAL = 5      # 가격 조회 간격 (초)

# ── 로그 ─────────────────────────────────────────────────
LOG_FILE  = "trading.log"
LOG_LEVEL = "INFO"
