from __future__ import annotations

from dataclasses import replace

from app.core.models import GridRow
from app.storage.interfaces import GridSnapshot, GridStateRepository, RepositoryMetadata
from app.storage.postgres_common import PostgresRepositoryMixin, sql


def _copy_row(row: GridRow) -> GridRow:
    return replace(row)


class PostgresGridRepository(GridStateRepository, PostgresRepositoryMixin):

    def load(self) -> GridSnapshot:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT symbol, version, last_revision, "
                        "stop_loss_active, stop_loss_level, stop_loss_armed_at, liquidated_at "
                        "FROM {} WHERE bot_key = %s"
                    ).format(self._qualified("bot_state")),
                    (self.bot_key,),
                )
                state_row = cur.fetchone()
                if state_row is None:
                    return GridSnapshot(symbol="", rows=tuple(), metadata=RepositoryMetadata())

                (
                    symbol,
                    version,
                    revision,
                    stop_loss_active,
                    stop_loss_level,
                    stop_loss_armed_at,
                    liquidated_at,
                ) = state_row
                cur.execute(
                    sql.SQL(
                        "SELECT slot_index, buy_price, held_qty, sell_price, planned_qty, filled_at "
                        "FROM {} WHERE bot_key = %s ORDER BY slot_index"
                    ).format(self._qualified("grid_slots")),
                    (self.bot_key,),
                )
                rows = tuple(
                    GridRow(
                        index=slot_index,
                        buy_price=buy_price,
                        held_qty=held_qty,
                        sell_price=sell_price,
                        planned_qty=planned_qty,
                        filled_at=filled_at,
                    )
                    for slot_index, buy_price, held_qty, sell_price, planned_qty, filled_at in cur.fetchall()
                )

        return GridSnapshot(
            symbol=symbol or "",
            rows=rows,
            metadata=RepositoryMetadata(
                version=version,
                revision=str(revision) if revision is not None else None,
                stop_loss_active=bool(stop_loss_active),
                stop_loss_level=stop_loss_level,
                stop_loss_armed_at=stop_loss_armed_at.isoformat() if stop_loss_armed_at else None,
                liquidated_at=liquidated_at.isoformat() if liquidated_at else None,
            ),
        )

    def save(self, snapshot: GridSnapshot) -> GridSnapshot:
        rows = tuple(_copy_row(row) for row in snapshot.rows)
        expected_version = snapshot.metadata.version

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT version FROM {} WHERE bot_key = %s FOR UPDATE"
                    ).format(self._qualified("bot_state")),
                    (self.bot_key,),
                )
                existing = cur.fetchone()
                current_version = None if existing is None else int(existing[0])

                if expected_version is not None and current_version != expected_version:
                    raise ValueError(
                        f"postgres grid version conflict: expected={expected_version}, current={current_version}"
                    )

                new_version = 1 if existing is None else current_version + 1

                if existing is None:
                    cur.execute(
                        sql.SQL(
                            "INSERT INTO {} ("
                            "bot_key, symbol, version, stop_loss_active, stop_loss_level, "
                            "stop_loss_armed_at, liquidated_at, updated_at"
                            ") VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())"
                        ).format(self._qualified("bot_state")),
                        (
                            self.bot_key,
                            snapshot.symbol,
                            new_version,
                            snapshot.metadata.stop_loss_active,
                            snapshot.metadata.stop_loss_level,
                            snapshot.metadata.stop_loss_armed_at,
                            snapshot.metadata.liquidated_at,
                        ),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "UPDATE {} SET "
                            "symbol = %s, version = %s, stop_loss_active = %s, stop_loss_level = %s, "
                            "stop_loss_armed_at = %s, liquidated_at = %s, updated_at = NOW() "
                            "WHERE bot_key = %s"
                        ).format(self._qualified("bot_state")),
                        (
                            snapshot.symbol,
                            new_version,
                            snapshot.metadata.stop_loss_active,
                            snapshot.metadata.stop_loss_level,
                            snapshot.metadata.stop_loss_armed_at,
                            snapshot.metadata.liquidated_at,
                            self.bot_key,
                        ),
                    )

                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE bot_key = %s").format(self._qualified("grid_slots")),
                    (self.bot_key,),
                )

                if rows:
                    cur.executemany(
                        sql.SQL(
                            "INSERT INTO {} "
                            "(bot_key, slot_index, buy_price, held_qty, sell_price, planned_qty, filled_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
                        ).format(self._qualified("grid_slots")),
                        [
                            (
                                self.bot_key,
                                row.index,
                                row.buy_price,
                                row.held_qty,
                                row.sell_price,
                                row.planned_qty,
                                row.filled_at,
                            )
                            for row in rows
                        ],
                    )

                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} (bot_key, version, symbol, source, note) "
                        "VALUES (%s, %s, %s, %s, %s) RETURNING revision_id"
                    ).format(self._qualified("grid_revisions")),
                    (
                        self.bot_key,
                        new_version,
                        snapshot.symbol,
                        "postgres_grid_repository.save",
                        f"rows={len(rows)}",
                    ),
                )
                revision_id = cur.fetchone()[0]

                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET last_revision = %s, updated_at = NOW() WHERE bot_key = %s"
                    ).format(self._qualified("bot_state")),
                    (revision_id, self.bot_key),
                )

        return GridSnapshot(
            symbol=snapshot.symbol,
            rows=rows,
            metadata=RepositoryMetadata(version=new_version, revision=str(revision_id)),
        )

    def has_changed(self, metadata: RepositoryMetadata | None) -> bool:
        if metadata is None or metadata.version is None:
            return True

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT version FROM {} WHERE bot_key = %s").format(self._qualified("bot_state")),
                    (self.bot_key,),
                )
                row = cur.fetchone()

        current_version = None if row is None else row[0]
        return current_version != metadata.version

    def exists(self) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT 1 FROM {} WHERE bot_key = %s").format(self._qualified("bot_state")),
                    (self.bot_key,),
                )
                return cur.fetchone() is not None
