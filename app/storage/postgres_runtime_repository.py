from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.storage.postgres_common import PostgresRepositoryMixin, sql


@dataclass(frozen=True)
class BotHeartbeat:
    bot_key: str
    symbol: str
    last_heartbeat_at: datetime
    last_cycle_at: datetime | None
    current_price: Decimal | None
    breakout_guard_active: bool | None
    breakout_guard_side: str | None
    breakout_guard_reason: str | None
    stop_loss_active: bool
    stop_loss_level: int | None
    stop_loss_armed_at: datetime | None
    liquidated_at: datetime | None


class PostgresBotHeartbeatRepository(PostgresRepositoryMixin):
    def upsert(
        self,
        *,
        symbol: str,
        current_price: Decimal | None,
        breakout_guard_active: bool | None,
        breakout_guard_side: str | None,
        breakout_guard_reason: str | None,
        stop_loss_active: bool,
        stop_loss_level: int | None,
        stop_loss_armed_at: datetime | None,
        liquidated_at: datetime | None,
        last_cycle_at: datetime | None = None,
    ) -> None:
        heartbeat_at = datetime.now(timezone.utc)
        if last_cycle_at is None:
            last_cycle_at = heartbeat_at

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} ("
                        "bot_key, symbol, last_heartbeat_at, last_cycle_at, current_price, "
                        "breakout_guard_active, breakout_guard_side, breakout_guard_reason, "
                        "stop_loss_active, stop_loss_level, stop_loss_armed_at, liquidated_at, updated_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()) "
                        "ON CONFLICT (bot_key) DO UPDATE SET "
                        "symbol = EXCLUDED.symbol, "
                        "last_heartbeat_at = EXCLUDED.last_heartbeat_at, "
                        "last_cycle_at = EXCLUDED.last_cycle_at, "
                        "current_price = EXCLUDED.current_price, "
                        "breakout_guard_active = EXCLUDED.breakout_guard_active, "
                        "breakout_guard_side = EXCLUDED.breakout_guard_side, "
                        "breakout_guard_reason = EXCLUDED.breakout_guard_reason, "
                        "stop_loss_active = EXCLUDED.stop_loss_active, "
                        "stop_loss_level = EXCLUDED.stop_loss_level, "
                        "stop_loss_armed_at = EXCLUDED.stop_loss_armed_at, "
                        "liquidated_at = EXCLUDED.liquidated_at, "
                        "updated_at = NOW()"
                    ).format(self._qualified("bot_heartbeat")),
                    (
                        self.bot_key,
                        symbol,
                        heartbeat_at,
                        last_cycle_at,
                        current_price,
                        breakout_guard_active,
                        breakout_guard_side,
                        breakout_guard_reason,
                        stop_loss_active,
                        stop_loss_level,
                        stop_loss_armed_at,
                        liquidated_at,
                    ),
                )

    def get(self) -> BotHeartbeat | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT bot_key, symbol, last_heartbeat_at, last_cycle_at, current_price, "
                        "breakout_guard_active, breakout_guard_side, breakout_guard_reason, "
                        "stop_loss_active, stop_loss_level, stop_loss_armed_at, liquidated_at "
                        "FROM {} WHERE bot_key = %s"
                    ).format(self._qualified("bot_heartbeat")),
                    (self.bot_key,),
                )
                row = cur.fetchone()

        if row is None:
            return None

        return BotHeartbeat(*row)
