BEGIN;

ALTER TABLE auto_trading.bot_state
    ADD COLUMN IF NOT EXISTS stop_loss_active BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stop_loss_level INTEGER,
    ADD COLUMN IF NOT EXISTS stop_loss_armed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS liquidated_at TIMESTAMPTZ;

ALTER TABLE auto_trading.orders
    DROP CONSTRAINT IF EXISTS orders_execution_type_check;

ALTER TABLE auto_trading.orders
    ADD CONSTRAINT orders_execution_type_check
    CHECK (execution_type IN ('limit', 'market_buy_by_price', 'market_sell_by_volume'));

CREATE TABLE IF NOT EXISTS auto_trading.bot_heartbeat (
    bot_key TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_cycle_at TIMESTAMPTZ,
    current_price NUMERIC(20, 8),
    breakout_guard_active BOOLEAN,
    breakout_guard_side TEXT,
    breakout_guard_reason TEXT,
    stop_loss_active BOOLEAN NOT NULL DEFAULT FALSE,
    stop_loss_level INTEGER,
    stop_loss_armed_at TIMESTAMPTZ,
    liquidated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auto_trading.api_refresh_tokens (
    id UUID PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by UUID,
    user_agent TEXT,
    client_host TEXT
);

CREATE INDEX IF NOT EXISTS api_refresh_tokens_username_idx
    ON auto_trading.api_refresh_tokens (username, expires_at DESC);

CREATE TABLE IF NOT EXISTS auto_trading.commands (
    id UUID PRIMARY KEY,
    bot_key TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('bot_stop', 'bot_start', 'reset', 'adjust_budget', 'reset_stop_loss')
    ),
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    requested_by TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    log TEXT NOT NULL DEFAULT '',
    result JSONB,
    error TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS commands_one_active_kind_idx
    ON auto_trading.commands (bot_key, kind)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS commands_status_idx
    ON auto_trading.commands (bot_key, status, requested_at);

COMMIT;
