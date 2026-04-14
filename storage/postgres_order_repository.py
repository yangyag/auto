from __future__ import annotations

from core.models import Order, OrderExecutionType, OrderSide
from storage.interfaces import PendingOrderRepository
from storage.postgres_common import PostgresRepositoryMixin, sql


class PostgresOrderRepository(PendingOrderRepository, PostgresRepositoryMixin):

    def add(self, order: Order) -> None:
        if not order.order_id:
            raise ValueError("order_id 없는 주문은 저장할 수 없습니다.")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} (bot_key, symbol, version, updated_at) "
                        "VALUES (%s, %s, 1, NOW()) ON CONFLICT (bot_key) DO NOTHING"
                    ).format(self._qualified("bot_state")),
                    (self.bot_key, order.symbol),
                )
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} ("
                        "bot_key, order_id, slot_index, side, price, quantity, symbol, "
                        "execution_type, spend_amount, status, created_at, updated_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', NOW(), NOW()) "
                        "ON CONFLICT (bot_key, order_id) DO UPDATE SET "
                        "slot_index = EXCLUDED.slot_index, "
                        "side = EXCLUDED.side, "
                        "price = EXCLUDED.price, "
                        "quantity = EXCLUDED.quantity, "
                        "symbol = EXCLUDED.symbol, "
                        "execution_type = EXCLUDED.execution_type, "
                        "spend_amount = EXCLUDED.spend_amount, "
                        "status = 'open', "
                        "filled_at = NULL, "
                        "cancelled_at = NULL, "
                        "updated_at = NOW()"
                    ).format(self._qualified("orders")),
                    (
                        self.bot_key,
                        order.order_id,
                        order.slot_index,
                        order.side.value,
                        order.price,
                        order.quantity,
                        order.symbol,
                        order.execution_type.value,
                        order.spend_amount,
                    ),
                )

    def get(self, order_id: str) -> Order | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT slot_index, side, price, quantity, symbol, execution_type, spend_amount, order_id "
                        "FROM {} WHERE bot_key = %s AND order_id = %s"
                    ).format(self._qualified("orders")),
                    (self.bot_key, order_id),
                )
                row = cur.fetchone()

        return None if row is None else self._row_to_order(row)

    def remove(self, order_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE bot_key = %s AND order_id = %s").format(self._qualified("orders")),
                    (self.bot_key, order_id),
                )

    def mark_filled(self, order_id: str) -> None:
        self._mark_status(order_id, "filled", timestamp_column="filled_at")

    def mark_cancelled(self, order_id: str) -> None:
        self._mark_status(order_id, "cancelled", timestamp_column="cancelled_at")

    def list_open(self) -> list[Order]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT slot_index, side, price, quantity, symbol, execution_type, spend_amount, order_id "
                        "FROM {} WHERE bot_key = %s AND status = 'open' ORDER BY slot_index, order_id"
                    ).format(self._qualified("orders")),
                    (self.bot_key,),
                )
                rows = cur.fetchall()

        return [self._row_to_order(row) for row in rows]

    def _mark_status(self, order_id: str, status: str, *, timestamp_column: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET status = %s, {} = NOW(), updated_at = NOW() "
                        "WHERE bot_key = %s AND order_id = %s"
                    ).format(self._qualified("orders"), sql.Identifier(timestamp_column)),
                    (status, self.bot_key, order_id),
                )

    @staticmethod
    def _row_to_order(row) -> Order:
        slot_index, side, price, quantity, symbol, execution_type, spend_amount, order_id = row
        return Order(
            slot_index=slot_index,
            side=OrderSide(side),
            price=price,
            quantity=quantity,
            symbol=symbol,
            execution_type=OrderExecutionType(execution_type),
            spend_amount=spend_amount,
            order_id=order_id,
        )
