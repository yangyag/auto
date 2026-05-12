from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import app.config.settings as cfg
from app.api.schemas.grid import (
    BreakoutGuardStatus,
    GridSlotResponse,
    GridStateResponse,
    GridSummaryResponse,
    StopLossStatus,
)
from app.api.schemas.order import OrderResponse
from app.core.grid import GridState
from app.storage.factory import build_grid_repository, build_pending_order_repository
from app.storage.interfaces import GridSnapshot
from app.storage.postgres_runtime_repository import BotHeartbeat
from app.utils.decimal_utils import DECIMAL_ZERO
from app.utils.grid_reporting import summarize_planned_buy_budget


def _order_response_from_order(order, *, status: str | None = None) -> OrderResponse:
    return OrderResponse(
        order_id=order.order_id,
        identifier=order.identifier,
        slot_index=order.slot_index,
        side=order.side.value,
        price=order.price,
        quantity=order.quantity,
        symbol=order.symbol,
        execution_type=order.execution_type.value,
        spend_amount=order.spend_amount,
        status=status,
    )


def order_response_from_row(row: dict) -> OrderResponse:
    return OrderResponse(
        order_id=row.get("order_id"),
        identifier=row.get("identifier"),
        slot_index=row["slot_index"],
        side=row["side"],
        price=row["price"],
        quantity=row["quantity"],
        symbol=row["symbol"],
        execution_type=row["execution_type"],
        spend_amount=row.get("spend_amount"),
        status=row.get("status"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        filled_at=row.get("filled_at"),
        cancelled_at=row.get("cancelled_at"),
    )


def load_grid_snapshot() -> GridSnapshot:
    return build_grid_repository(cfg).load()


def build_grid_state_response() -> GridStateResponse:
    snapshot = load_grid_snapshot()
    pending_by_slot = {
        order.slot_index: _order_response_from_order(order, status="open")
        for order in build_pending_order_repository(cfg).list_open()
    }
    state = GridState.from_snapshot(snapshot)
    now = datetime.now(timezone.utc)
    slots = []
    for row in snapshot.rows:
        effective_tp_k = state.effective_tp_k(
            row.index,
            now=now,
            tp_k_base=cfg.GRID_TP_K_BASE,
            tp_k_floor=cfg.GRID_TP_K_FLOOR,
        )
        slots.append(
            GridSlotResponse(
                slot_index=row.index,
                buy_price=row.buy_price,
                sell_price=row.sell_price,
                held_qty=row.held_qty,
                planned_qty=row.planned_qty,
                filled_at=row.filled_at,
                status="holding" if row.is_holding else "empty",
                planned_buy_krw=row.buy_price * row.planned_qty,
                inventory_cost_krw=row.buy_price * row.held_qty,
                effective_sell_price=state.effective_sell_price(
                    row.index,
                    now=now,
                    tp_k_base=cfg.GRID_TP_K_BASE,
                    tp_k_floor=cfg.GRID_TP_K_FLOOR,
                ),
                effective_tp_k=effective_tp_k,
                pending_order=pending_by_slot.get(row.index),
            )
        )
    return GridStateResponse(
        symbol=snapshot.symbol,
        version=snapshot.metadata.version,
        revision=snapshot.metadata.revision,
        slots=slots,
    )


def build_grid_summary_response(heartbeat: BotHeartbeat | None = None) -> GridSummaryResponse:
    snapshot = load_grid_snapshot()
    state = GridState.from_snapshot(snapshot)
    budget_summary = summarize_planned_buy_budget(snapshot.rows)
    total_inventory = state.total_inventory
    current_inventory_cost = state.current_inventory_cost
    avg_buy_price = None
    if total_inventory > DECIMAL_ZERO:
        avg_buy_price = current_inventory_cost / total_inventory

    holding_count = sum(1 for row in snapshot.rows if row.is_holding)
    empty_count = sum(1 for row in snapshot.rows if row.is_empty)
    lower_price = min((row.buy_price for row in snapshot.rows), default=None)
    upper_price = max((row.buy_price for row in snapshot.rows), default=None)

    breakout_guard = BreakoutGuardStatus()
    if heartbeat is not None:
        breakout_guard = BreakoutGuardStatus(
            active=heartbeat.breakout_guard_active,
            side=heartbeat.breakout_guard_side,
            reason=heartbeat.breakout_guard_reason,
        )

    metadata = snapshot.metadata
    stop_loss = StopLossStatus(
        active=metadata.stop_loss_active,
        level=metadata.stop_loss_level,
        armed_at=metadata.stop_loss_armed_at,
        liquidated_at=metadata.liquidated_at,
    )
    if heartbeat is not None:
        stop_loss = StopLossStatus(
            active=heartbeat.stop_loss_active,
            level=heartbeat.stop_loss_level,
            armed_at=heartbeat.stop_loss_armed_at.isoformat() if heartbeat.stop_loss_armed_at else None,
            liquidated_at=heartbeat.liquidated_at.isoformat() if heartbeat.liquidated_at else None,
        )

    return GridSummaryResponse(
        symbol=snapshot.symbol,
        row_count=len(snapshot.rows),
        holding_count=holding_count,
        empty_count=empty_count,
        total_inventory_btc=total_inventory,
        current_inventory_cost_krw=current_inventory_cost,
        total_allocated_budget_krw=state.total_allocated_budget,
        planned_buy_budget_total=budget_summary.total,
        top_slot_planned_buy_budget=budget_summary.top_slot,
        bottom_slot_planned_buy_budget=budget_summary.bottom_slot,
        avg_buy_price=avg_buy_price,
        lower_price=lower_price,
        upper_price=upper_price,
        breakout_guard=breakout_guard,
        stop_loss=stop_loss,
    )
