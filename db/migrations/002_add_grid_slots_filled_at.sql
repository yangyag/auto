BEGIN;

ALTER TABLE auto_trading.grid_slots
    ADD COLUMN IF NOT EXISTS filled_at TIMESTAMPTZ;

COMMIT;
