BEGIN;

CREATE SCHEMA IF NOT EXISTS auto_trading;

CREATE TABLE IF NOT EXISTS auto_trading.bot_state (
    bot_key TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    last_revision BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auto_trading.grid_slots (
    bot_key TEXT NOT NULL REFERENCES auto_trading.bot_state(bot_key) ON DELETE CASCADE,
    slot_index INTEGER NOT NULL CHECK (slot_index > 0),
    buy_price NUMERIC(20, 8) NOT NULL,
    held_qty NUMERIC(30, 16) NOT NULL,
    sell_price NUMERIC(20, 8) NOT NULL,
    planned_qty NUMERIC(30, 16) NOT NULL,
    PRIMARY KEY (bot_key, slot_index),
    CHECK (buy_price > 0),
    CHECK (sell_price > buy_price),
    CHECK (held_qty >= 0),
    CHECK (planned_qty >= 0)
);

CREATE TABLE IF NOT EXISTS auto_trading.grid_revisions (
    revision_id BIGSERIAL PRIMARY KEY,
    bot_key TEXT NOT NULL REFERENCES auto_trading.bot_state(bot_key) ON DELETE CASCADE,
    version BIGINT NOT NULL,
    symbol TEXT NOT NULL,
    source TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bot_key, version)
);

CREATE TABLE IF NOT EXISTS auto_trading.orders (
    bot_key TEXT NOT NULL REFERENCES auto_trading.bot_state(bot_key) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    slot_index INTEGER NOT NULL CHECK (slot_index > 0),
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    price NUMERIC(20, 8) NOT NULL,
    quantity NUMERIC(30, 16) NOT NULL,
    symbol TEXT NOT NULL,
    execution_type TEXT NOT NULL CHECK (execution_type IN ('limit', 'market_buy_by_price')),
    spend_amount NUMERIC(20, 8),
    status TEXT NOT NULL CHECK (status IN ('open', 'filled', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filled_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    PRIMARY KEY (bot_key, order_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS orders_one_open_slot_idx
    ON auto_trading.orders (bot_key, slot_index)
    WHERE status = 'open';

CREATE INDEX IF NOT EXISTS orders_status_idx
    ON auto_trading.orders (bot_key, status, order_id);

COMMIT;
