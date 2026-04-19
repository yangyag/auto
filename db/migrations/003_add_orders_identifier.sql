BEGIN;

ALTER TABLE auto_trading.orders
    ADD COLUMN IF NOT EXISTS identifier TEXT;

DROP INDEX IF EXISTS auto_trading.orders_identifier_idx;

CREATE UNIQUE INDEX IF NOT EXISTS orders_identifier_idx
    ON auto_trading.orders (identifier)
    WHERE identifier IS NOT NULL;

COMMIT;
