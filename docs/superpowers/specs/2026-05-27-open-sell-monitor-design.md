# Open Sell Order Monitor — Design Spec

## Purpose

`upbit_actual_assets.py` shows the gap between Upbit's average-buy-price and bot
slot-level cost. However it only summarizes these remaining BUY lots in aggregate
— it says nothing about which open sell orders are currently sitting on the
order book, how they match against those lots, or whether each lot is currently
underwater.

This spec is for a separate, read-only script that shows open sell orders side
by side with the corresponding bot-slot buy cost so the user can quickly see
which positions are profitable or underwater.

No existing file is modified.

---

## Core Logic

### Data Inputs (3 API calls)

1. `GET /v1/orders/open?market=KRW-BTC&states[]=wait&states[]=watch` — open sell orders
2. `GET /v1/ticker?markets=KRW-BTC` — current price
3. `GET /v1/accounts` — spot balances (needed for the remaining BUY-lot cost calculation)

### Matching Open Sells → Bot Buy Lots

The script reuses `upbit_realized_pnl.run_fifo` the same way
`upbit_actual_assets.py` does: fetch closed orders over a lookback window, run
FIFO matching, and extract `queues_by_slot`. Each queue entry is a remaining
unmatched BUY lot with `unit_cost`.

For each open sell order:
- Parse the slot index from its `identifier` (via `extract_slot_index`)
- Look up the remaining BUY queue for that slot
- The first (oldest FIFO) entry in that queue is the buy lot the open sell was
  placed against; use its `unit_cost` as the buy price

### Per-Order Computation

For each open sell order at `sell_limit_price` with matched buy cost
`buy_unit_cost` and current market price `current_price`:

```
unrealized_at_current = (current_price - buy_unit_cost) × quantity
unrealized_at_sell    = (sell_limit_price - buy_unit_cost) × quantity
gap_to_fill           = sell_limit_price - current_price   (how far until the order fills)
```

---

## Output Format (CLI Plain Text)

```
=== 매도 대기 주문 현황 ===
마켓: KRW-BTC | 현재가: 152,000,000 KRW | 조회시각: 2026-05-27 14:30 KST

slot  qty(BTC)   buy_cost       sell_limit     current       미실현손익   도달까지
3     0.00100    148,500,000    153,000,000    152,000,000    +3,500      1,000,000 남음
7     0.00100    155,000,000    160,000,000    152,000,000    -3,000      8,000,000 남음
-*    0.00500    -              -              152,000,000    -           수동주문 의심

합계: 2개 중 1개 수익권, 1개 손실권 | 총 미실현 손익: +500 KRW
```

- `slot` = `-` when identifier is missing or can't be parsed (manual/external order)
- `도달까지` = the KRW gap between current price and sell limit (`sell_limit_price - current_price`). Negative means the order would be an instant marketable fill.

### Diagnostic Footer

```
[진단]
open_orders=5  matched=4  unmatched=1  lookback_days=120
```

- `matched`: an open sell whose slot had a matching BUY queue entry
- `unmatched`: an open sell whose slot had no remaining BUY queue entry (manual order, or lookback too short)

---

## Script Structure

### File: `scripts/upbit_open_sell_monitor.py`

New standalone script. Follows the same patterns as `upbit_actual_assets.py`:

| Responsibility | Implementation |
|---|---|
| Config (API keys, market, lookback) | `argparse`, `cfg.API_KEY/API_SECRET` |
| API calls | `get_with_retry` copied, or import from `upbit_actual_assets` |
| Current price | `requests.get("/v1/ticker")` — no auth needed |
| Open orders | `GET /v1/orders/open` with `states[]=wait&states[]=watch` |
| Remaining BUY lots | import `run_fifo`, `fetch_closed_orders` from `upbit_realized_pnl` |
| Output | `print_*` function(s) |

### Dataclasses

```python
@dataclass
class OpenSellRow:
    slot_index: int | None
    qty: Decimal
    buy_unit_cost: Decimal | None   # None when unmatched
    sell_limit_price: Decimal
    current_price: Decimal
    unrealized_at_current: Decimal | None
    gap_to_fill: Decimal
```

### Error / Edge Cases

- **No open orders**: Print "미체결 매도 주문 없음" and exit 0
- **Open order has no identifier (manual order)**: Show the row with `slot=-` and `buy_unit_cost=None`
- **Slot not found in remaining BUY queues**: Show unmatched, suggest increasing `--lookback-days`
- **Rate limit**: Same retry logic as `upbit_actual_assets.py`
- **API auth failure**: Clear error message, exit 1

---

## CLI Arguments

```
--market         기본: KRW-BTC
--lookback-days  기본: 120  (잔여 BUY 큐 계산용)
--reset-sell-uuid  과거 reset 시장가 SELL uuid 지정
```

---

## Non-Goals

- Does NOT cancel or modify any orders (read-only)
- Does NOT modify `upbit_actual_assets.py` or `upbit_realized_pnl.py`
- Does NOT support multiple markets simultaneously
- Does NOT persist anything
