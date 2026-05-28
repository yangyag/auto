from __future__ import annotations

import time
import warnings
from datetime import datetime
from decimal import Decimal

import requests

import app.config.settings as cfg
from app.api.schemas.monitor import (
    OpenSellDiagnosticSchema,
    OpenSellMonitorResponse,
    OpenSellRowSchema,
    OpenSellSummarySchema,
)
from scripts import upbit_realized_pnl as pnl
from scripts.upbit_open_sell_monitor import (
    _compile_slot_pattern,
    build_open_sell_rows,
    fetch_open_orders,
    fetch_remaining_buy_queues,
    match_open_sells_to_buy_lots,
)

try:
    from jwt.warnings import InsecureKeyLengthWarning
except ImportError:
    InsecureKeyLengthWarning = Warning

warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
warnings.filterwarnings(
    "ignore",
    message=r"The HMAC key is .* below the minimum recommended length of 64 bytes for SHA512\\.",
    category=Warning,
)

DEFAULT_LOOKBACK_DAYS = 120


def get_open_sell_monitor_data(
    *,
    market: str = pnl.DEFAULT_MARKET,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    bot_key: str | None = None,
    reset_sell_uuids: list[str] | None = None,
) -> OpenSellMonitorResponse:
    if not cfg.API_KEY or not cfg.API_SECRET:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY is not configured")

    if lookback_days <= 0:
        raise RuntimeError("lookback_days must be >= 1")

    bot_key = bot_key or cfg.STATE_BOT_KEY
    slot_pattern = _compile_slot_pattern(bot_key)
    reset_sell_uuids = reset_sell_uuids or []

    current_price_data = requests.get(
        f"{pnl.BASE_URL}/v1/ticker",
        params={"markets": market},
        timeout=10,
    )
    current_price_data.raise_for_status()
    ticker_list = current_price_data.json()
    current_price = pnl._to_decimal(ticker_list[0]["trade_price"])

    open_orders = fetch_open_orders(cfg.API_KEY, cfg.API_SECRET, market)
    time.sleep(pnl.RATE_LIMIT_SLEEP_SEC)

    queues_by_slot = fetch_remaining_buy_queues(
        api_key=cfg.API_KEY,
        api_secret=cfg.API_SECRET,
        market=market,
        lookback_days=lookback_days,
        reset_sell_uuids=set(reset_sell_uuids),
        bot_key=bot_key,
        slot_pattern=slot_pattern,
    )

    buy_cost_map = match_open_sells_to_buy_lots(open_orders, queues_by_slot, slot_pattern)
    rows = build_open_sell_rows(open_orders, buy_cost_map, current_price, slot_pattern)

    matched = sum(1 for r in rows if r.buy_unit_cost is not None)
    unmatched = len(rows) - matched

    profit_count = 0
    loss_count = 0
    total_unrealized = Decimal("0")
    for row in rows:
        if row.unrealized_at_current is not None:
            total_unrealized += row.unrealized_at_current
            if row.unrealized_at_current >= 0:
                profit_count += 1
            else:
                loss_count += 1

    schema_rows = [
        OpenSellRowSchema(
            slot_index=row.slot_index,
            qty=row.qty,
            buy_unit_cost=row.buy_unit_cost,
            sell_limit_price=row.sell_limit_price,
            current_price=row.current_price,
            unrealized_at_current=row.unrealized_at_current,
            gap_to_fill_krw=row.gap_to_fill_krw,
        )
        for row in rows
    ]

    return OpenSellMonitorResponse(
        market=market,
        current_price=current_price,
        generated_at=datetime.now(pnl.KST),
        rows=schema_rows,
        summary=OpenSellSummarySchema(
            total_count=len(rows),
            matched_count=matched,
            unmatched_count=unmatched,
            profit_count=profit_count,
            loss_count=loss_count,
            total_unrealized_krw=total_unrealized,
        ),
        diagnostic=OpenSellDiagnosticSchema(
            open_orders=len(open_orders),
            matched=matched,
            unmatched=unmatched,
            lookback_days=lookback_days,
        ),
    )
