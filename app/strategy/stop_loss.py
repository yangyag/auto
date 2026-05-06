"""자동 손절 판정 및 실행 로직."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.models import Order, OrderSide, OrderExecutionType
from app.strategy.breakout_guard import evaluate_breakout_guard
from app.utils.decimal_utils import to_decimal, DECIMAL_ZERO

if TYPE_CHECKING:
    from app.core.grid_properties import GridPropertySpec
    from app.core.grid import GridState
    from app.exchange.base import BaseExchange

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StopLossDecision:
    level: int | None
    threshold: Decimal | None
    lower_price: Decimal
    current_price: Decimal
    triggered: bool
    candle_close_prices: tuple[Decimal, ...] = ()
    armed_at: datetime | None = None


@dataclass
class StopLossExecutionResult:
    """손절 실행 결과"""
    level: int  # 0=L0, 1=L1, 2=L2
    success: bool
    total_slots_to_sell: int = 0
    successful_sells: int = 0
    failed_slots: list[int] = field(default_factory=list)
    total_qty_liquidated: Decimal = DECIMAL_ZERO
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


def _resolve_stop_loss_threshold(
    lower: Decimal,
    upper: Decimal,
    level: int,
    *,
    mode: str,
    band_multiple: Decimal | None,
    l0_pct: Decimal | None,
    l1_pct: Decimal | None,
    l2_pct: Decimal | None,
) -> Decimal | None:
    """손절 임계값 계산 (band_multiple 또는 fixed_pct 모드)."""
    if mode == "off":
        return None

    if mode == "band_multiple":
        if band_multiple is None:
            raise ValueError("band_multiple 모드는 STOP_LOSS_BAND_MULTIPLE이 필요합니다.")
        band_drop_ratio = Decimal("1") - lower / upper
        threshold = lower * (Decimal("1") - band_multiple * band_drop_ratio)
    elif mode == "fixed_pct":
        pct_map = {0: l0_pct, 1: l1_pct, 2: l2_pct}
        pct = pct_map.get(level)
        if pct is None:
            raise ValueError(f"fixed_pct 모드는 level {level}에 대한 pct가 필요합니다.")
        threshold = lower * (Decimal("1") - pct / Decimal("100"))
    else:
        raise ValueError(f"지원하지 않는 STOP_LOSS_MODE: {mode}")

    return threshold


def evaluate_stop_loss(
    grid_state: GridState,
    current_price: Decimal,
    exchange: BaseExchange,
    grid_spec: GridPropertySpec,
    symbol: str,
    previous_armed_at: datetime | None = None,
) -> StopLossDecision:
    """
    손절 발동 여부 판정.

    Args:
        previous_armed_at: 이전 armed_at 상태 (호출자가 영속 상태를 주입).
                          시간 컨펌 윈도우 검증을 위해 필요.

    Returns StopLossDecision with:
    - level: 발동 단계 (0=L0, 1=L1, 2=L2) or None (미발동)
    - triggered: 발동 여부
    - candle_close_prices: 캔들 종가 (감사 추적용)
    - armed_at: 발동 시각 (이미 armed면 유지, 새 진입시 현재 시간)
    """
    if not grid_state.rows:
        raise ValueError("GridState must have rows to evaluate stop-loss")

    lower = min(row.buy_price for row in grid_state.rows)
    upper = max(row.buy_price for row in grid_state.rows)
    current_price = to_decimal(current_price)

    if grid_spec.stop_loss_mode == "off":
        return StopLossDecision(
            level=None,
            threshold=None,
            lower_price=lower,
            current_price=current_price,
            triggered=False,
            candle_close_prices=(),
        )

    _thresh_kwargs = dict(
        mode=grid_spec.stop_loss_mode,
        band_multiple=grid_spec.stop_loss_band_multiple,
        l0_pct=grid_spec.stop_loss_l0_pct,
        l1_pct=grid_spec.stop_loss_l1_pct,
        l2_pct=grid_spec.stop_loss_l2_pct,
    )
    l0_threshold = _resolve_stop_loss_threshold(lower, upper, 0, **_thresh_kwargs)
    l1_threshold = _resolve_stop_loss_threshold(lower, upper, 1, **_thresh_kwargs)
    l2_threshold = _resolve_stop_loss_threshold(lower, upper, 2, **_thresh_kwargs)

    if current_price >= l0_threshold:
        return StopLossDecision(
            level=None,
            threshold=l0_threshold,
            lower_price=lower,
            current_price=current_price,
            triggered=False,
            candle_close_prices=(),
        )

    if current_price < l2_threshold:
        level = 2
        required_closes = grid_spec.stop_loss_l2_consecutive_closes
        close_threshold = l2_threshold
    elif current_price < l1_threshold:
        level = 1
        required_closes = grid_spec.stop_loss_l1_consecutive_closes
        close_threshold = l1_threshold
    else:
        level = 0
        required_closes = grid_spec.stop_loss_l0_consecutive_closes
        close_threshold = l0_threshold

    close_prices = exchange.get_minute_candle_closes(
        symbol,
        unit_minutes=grid_spec.stop_loss_candle_unit,
        count=required_closes,
    )

    guard_status = evaluate_breakout_guard(
        close_prices,
        lower_price=close_threshold,
        upper_price=lower,
        consecutive_count=required_closes,
    )

    if guard_status.active:
        new_armed_at = previous_armed_at if previous_armed_at is not None else datetime.now(tz=timezone.utc)
    else:
        new_armed_at = None

    return StopLossDecision(
        level=level if guard_status.active else None,
        threshold=close_threshold,
        lower_price=lower,
        current_price=current_price,
        triggered=guard_status.active,
        candle_close_prices=guard_status.close_prices,
        armed_at=new_armed_at,
    )


def execute_stop_loss(
    exchange: BaseExchange,
    grid_state: GridState,
    decision: StopLossDecision,
    symbol: str,
    reconcile_fn: callable,
    notifier_fn: callable | None = None,
    grid_spec: "GridPropertySpec | None" = None,
) -> StopLossExecutionResult:
    """
    손절 실행: 미체결 주문 취소 → 시장가/지정가 매도 → reconcile.

    Args:
        exchange: 거래소 인터페이스
        grid_state: 그리드 상태 (슬롯별 보유 수량 포함)
        decision: evaluate_stop_loss() 반환값
        symbol: 종목 심볼 (e.g., "KRW-BTC")
        reconcile_fn: 주문 reconcile 콜백 함수 (grid_state 업데이트)
        notifier_fn: 외부 알림 콜백 함수 (optional)
        grid_spec: 그리드 설정 (L1 청산 비율 추출용)

    Returns:
        StopLossExecutionResult: 실행 결과 (성공/실패 슬롯, 청산 수량 등)

    Note:
        - L0: 신규 매수 차단만. 이 함수에서는 no-op.
        - L1: 보유 슬롯의 50% 지정가 매도 (임계값 기준)
        - L2: 보유 슬롯 100% 시장가 매도
        - 부분 실패 허용: 일부 슬롯 매도 실패 시에도 계속 진행
    """
    if decision.level is None or not decision.triggered:
        return StopLossExecutionResult(level=0, success=False)

    level = decision.level

    # L0: 매수 차단은 호출자(main.py)가 담당, execute 자체는 no-op
    if level == 0:
        logger.error(f"[STOP_LOSS] L0 발동. 신규 매수 차단만 적용 (호출자가 담당).")
        return StopLossExecutionResult(level=0, success=True)

    logger.error(f"[STOP_LOSS] L{level} 손절 발동. 현재가={decision.current_price}, 임계값={decision.threshold}")

    # 알림: 손절 발동 (ARMED)
    if notifier_fn:
        try:
            notifier_fn(
                kind="armed",
                level=level,
                current_price=decision.current_price,
                threshold=decision.threshold,
                lower_price=decision.lower_price,
                symbol=symbol,
            )
        except Exception as e:
            logger.warning(f"[STOP_LOSS] armed 알림 전송 실패: {e}")

    # 1. 기존 미체결 주문 전부 취소
    open_orders = exchange.get_open_order_ids(symbol)
    for order_id in open_orders:
        try:
            exchange.cancel_order(order_id)
            logger.info(f"[STOP_LOSS] 미체결 주문 취소: {order_id}")
        except Exception as e:
            logger.warning(f"[STOP_LOSS] 주문 취소 실패 {order_id}: {e}")

    # 2. is_holding 슬롯 필터 및 청산 대상 결정
    holding_slots = [row for row in grid_state.rows if row.is_holding]

    if not holding_slots:
        logger.info(f"[STOP_LOSS] 보유 슬롯 없음. L{level} 손절 완료 (미청산).")
        return StopLossExecutionResult(
            level=level,
            success=True,
            total_slots_to_sell=0,
            successful_sells=0,
        )

    # 3. 시장가/지정가 매도 주문 생성 및 실행
    initial_qty_by_index = {row.index: row.held_qty for row in holding_slots}
    successful_order_indices = set()

    # L1: 50% 지정가 매도, L2: 100% 시장가 매도
    if level == 1:
        liquidate_ratio = Decimal("0.5")
        if grid_spec and grid_spec.stop_loss_l1_liquidate_ratio:
            liquidate_ratio = grid_spec.stop_loss_l1_liquidate_ratio
        order_exec_type = OrderExecutionType.LIMIT
        order_price = decision.threshold
    else:  # L2
        liquidate_ratio = Decimal("1")
        order_exec_type = OrderExecutionType.MARKET_SELL_BY_VOLUME
        order_price = decision.current_price

    logger.error(f"[STOP_LOSS] L{level} 청산 비율: {liquidate_ratio * 100:.0f}%, 주문 방식: {order_exec_type.value}")

    for row in holding_slots:
        try:
            quantity = row.held_qty * liquidate_ratio
            order = Order(
                slot_index=row.index,
                side=OrderSide.SELL,
                price=order_price,
                quantity=quantity,
                symbol=symbol,
                execution_type=order_exec_type,
            )
            order_id = exchange.place_order(order)
            if order_id:
                successful_order_indices.add(row.index)
                logger.error(f"[STOP_LOSS] L{level} 매도 주문 생성: slot {row.index}, qty={quantity}, price={order_price}")
            else:
                logger.error(f"[STOP_LOSS] L{level} 매도 주문 실패: slot {row.index}")
        except Exception as e:
            logger.error(f"[STOP_LOSS] L{level} 매도 주문 예외: slot {row.index}: {e}")

    # 4. reconcile 호출 (주문 체결 확인 및 grid_state 반영)
    try:
        reconcile_fn()
        logger.info(f"[STOP_LOSS] L{level} reconcile 완료")
    except Exception as e:
        logger.error(f"[STOP_LOSS] reconcile 실패: {e}")

    # 5. 결과 집계
    failed_slots = [idx for idx in initial_qty_by_index if idx not in successful_order_indices]

    liquidated_qty = DECIMAL_ZERO
    for idx, initial_qty in initial_qty_by_index.items():
        current_row = next((r for r in grid_state.rows if r.index == idx), None)
        if current_row:
            liquidated_qty += max(DECIMAL_ZERO, initial_qty - current_row.held_qty)

    result = StopLossExecutionResult(
        level=level,
        success=len(failed_slots) == 0,
        total_slots_to_sell=len(holding_slots),
        successful_sells=len(successful_order_indices),
        failed_slots=failed_slots,
        total_qty_liquidated=liquidated_qty,
    )

    logger.error(
        f"[STOP_LOSS] L{level} 청산 결과: "
        f"총 슬롯={result.total_slots_to_sell}, "
        f"성공={result.successful_sells}, "
        f"청산수량={result.total_qty_liquidated}"
    )

    # 알림: 청산 완료 또는 실패
    if notifier_fn:
        try:
            if result.success:
                notifier_fn(
                    kind="executed",
                    level=level,
                    current_price=decision.current_price,
                    threshold=decision.threshold,
                    lower_price=decision.lower_price,
                    symbol=symbol,
                    liquidated_qty=result.total_qty_liquidated,
                )
            else:
                notifier_fn(
                    kind="failed",
                    level=level,
                    current_price=decision.current_price,
                    threshold=decision.threshold,
                    lower_price=decision.lower_price,
                    symbol=symbol,
                    failed_slots=result.failed_slots,
                )
        except Exception as e:
            logger.warning(f"[STOP_LOSS] 청산 알림 전송 실패: {e}")

    return result
