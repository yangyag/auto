from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.storage.postgres_common import PostgresRepositoryMixin, sql


class MobileApiRepository(PostgresRepositoryMixin):
    def create_refresh_token(
        self,
        *,
        token_hash: str,
        username: str,
        expires_at: datetime,
        user_agent: str | None,
        client_host: str | None,
    ) -> str:
        token_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} (id, token_hash, username, expires_at, user_agent, client_host) "
                        "VALUES (%s, %s, %s, %s, %s, %s)"
                    ).format(self._qualified("api_refresh_tokens")),
                    (token_id, token_hash, username, expires_at, user_agent, client_host),
                )
        return token_id

    def rotate_refresh_token(
        self,
        *,
        old_token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        client_host: str | None,
    ) -> str | None:
        new_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT id, username FROM {} "
                        "WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > NOW() "
                        "FOR UPDATE"
                    ).format(self._qualified("api_refresh_tokens")),
                    (old_token_hash,),
                )
                row = cur.fetchone()
                if row is None:
                    return None

                old_id, username = row
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} (id, token_hash, username, expires_at, user_agent, client_host) "
                        "VALUES (%s, %s, %s, %s, %s, %s)"
                    ).format(self._qualified("api_refresh_tokens")),
                    (new_id, new_token_hash, username, expires_at, user_agent, client_host),
                )
                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET revoked_at = NOW(), replaced_by = %s WHERE id = %s"
                    ).format(self._qualified("api_refresh_tokens")),
                    (new_id, old_id),
                )
        return username

    def revoke_refresh_token(self, *, token_hash: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET revoked_at = NOW() "
                        "WHERE token_hash = %s AND revoked_at IS NULL"
                    ).format(self._qualified("api_refresh_tokens")),
                    (token_hash,),
                )
                return cur.rowcount > 0

    def list_recent_orders(self, *, limit: int) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT order_id, identifier, slot_index, side, price, quantity, symbol, "
                        "execution_type, spend_amount, status, created_at, updated_at, filled_at, cancelled_at "
                        "FROM {} WHERE bot_key = %s "
                        "ORDER BY updated_at DESC, created_at DESC LIMIT %s"
                    ).format(self._qualified("orders")),
                    (self.bot_key, limit),
                )
                columns = [desc.name for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]

    def enqueue_command(
        self,
        *,
        kind: str,
        params: dict[str, Any],
        requested_by: str,
    ) -> dict[str, Any]:
        command_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} (id, bot_key, kind, params, status, requested_by) "
                        "VALUES (%s, %s, %s, %s::jsonb, 'queued', %s) "
                        "RETURNING id, kind, params, status, requested_by, requested_at, "
                        "started_at, finished_at, log, result, error"
                    ).format(self._qualified("commands")),
                    (
                        command_id,
                        self.bot_key,
                        kind,
                        json.dumps(params, ensure_ascii=True),
                        requested_by,
                    ),
                )
                return self._command_row_to_dict(cur.fetchone())

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT id, kind, params, status, requested_by, requested_at, started_at, "
                        "finished_at, log, result, error FROM {} "
                        "WHERE bot_key = %s AND id = %s"
                    ).format(self._qualified("commands")),
                    (self.bot_key, command_id),
                )
                row = cur.fetchone()
                return None if row is None else self._command_row_to_dict(row)

    def claim_next_command(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT id FROM {} WHERE bot_key = %s AND status = 'queued' "
                        "ORDER BY requested_at LIMIT 1 FOR UPDATE SKIP LOCKED"
                    ).format(self._qualified("commands")),
                    (self.bot_key,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                command_id = row[0]
                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET status = 'running', started_at = NOW() "
                        "WHERE id = %s "
                        "RETURNING id, kind, params, status, requested_by, requested_at, "
                        "started_at, finished_at, log, result, error"
                    ).format(self._qualified("commands")),
                    (command_id,),
                )
                return self._command_row_to_dict(cur.fetchone())

    def finish_command(
        self,
        *,
        command_id: str,
        status: str,
        log: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET status = %s, finished_at = NOW(), log = %s, "
                        "result = %s::jsonb, error = %s WHERE id = %s"
                    ).format(self._qualified("commands")),
                    (
                        status,
                        log[-20000:],
                        json.dumps(result, ensure_ascii=True) if result is not None else None,
                        error,
                        command_id,
                    ),
                )

    @staticmethod
    def _command_row_to_dict(row) -> dict[str, Any]:
        (
            command_id,
            kind,
            params,
            status,
            requested_by,
            requested_at,
            started_at,
            finished_at,
            log,
            result,
            error,
        ) = row
        return {
            "id": str(command_id),
            "kind": kind,
            "params": params or {},
            "status": status,
            "requested_by": requested_by,
            "requested_at": requested_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "log": log or "",
            "result": result,
            "error": error,
        }
