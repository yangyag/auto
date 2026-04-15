"""
그리드 자동매매 메인 루프
"""
import argparse
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

import config.settings as cfg
from core.grid_builder import build_cash_only_grid
from core.grid import GridState
from core.models import Order, OrderSide
from exchange.base import BaseExchange
from exchange.crypto import UpbitAPIError
from storage.factory import build_grid_repository, build_pending_order_repository
from storage.interfaces import GridStateRepository, PendingOrderRepository, RepositoryMetadata
from strategy.grid_strategy import GridStrategy
from utils.decimal_utils import format_decimal, to_decimal
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GridStateRuntime:
    metadata: RepositoryMetadata | None = None


class StatePersistenceError(RuntimeError):
    """상태 저장소 반영 실패로 새 주문을 중단해야 하는 경우."""


def validate_runtime_grid_state(grid_state: GridState) -> None:
    if not grid_state.rows:
        raise ValueError(
            "PostgreSQL 상태 저장소에 그리드 상태가 없습니다. "
            "마이그레이션/STATE_BOT_KEY/PGSCHEMA 설정을 확인하세요."
        )
    if grid_state.symbol and grid_state.symbol != cfg.SYMBOL:
        raise ValueError(
            f"저장소 심볼과 설정 심볼이 다릅니다: {grid_state.symbol} != {cfg.SYMBOL}"
        )


def load_grid_state(repository: GridStateRepository) -> tuple[GridState, GridStateRuntime]:
    snapshot = repository.load()
    grid_state = GridState.from_snapshot(snapshot)
    validate_runtime_grid_state(grid_state)
    return grid_state, GridStateRuntime(metadata=snapshot.metadata)


def persist_grid_state(
    grid_state: GridState,
    repository: GridStateRepository,
    runtime: GridStateRuntime,
) -> None:
    try:
        saved_snapshot = repository.save(grid_state.to_snapshot(runtime.metadata))
    except Exception as exc:
        raise StatePersistenceError(f"상태 저장 실패: {exc}") from exc
    runtime.metadata = saved_snapshot.metadata


def format_order_log(order: Order) -> str:
    if order.is_market_buy_by_price:
        return (
            f"{order.side.value} 슬롯{order.slot_index} 시장가 {format_decimal(order.required_krw)} KRW "
            f"(trigger={format_decimal(order.price)}, qty={format_decimal(order.quantity)})"
        )
    return (
        f"{order.side.value} 슬롯{order.slot_index} "
        f"{format_decimal(order.price)} x {format_decimal(order.quantity)}"
    )


def reconcile_pending_orders(
    exchange: BaseExchange,
    pending_orders: dict[str, Order],
    strategy: GridStrategy,
    on_grid_updated: Callable[[], None] | None = None,
    pending_order_repository: PendingOrderRepository | None = None,
) -> int:
    """대기 중인 주문의 실제 체결 여부를 조회해 그리드 상태에 반영한다."""
    completed = 0

    for order_id, order in list(pending_orders.items()):
        status = exchange.get_order_status(order_id)

        if status.is_open:
            continue

        if status.is_filled:
            if order.side == OrderSide.BUY and status.executed_volume > Decimal("0"):
                order.quantity = status.executed_volume
            strategy.apply_filled_order(order)
            if pending_order_repository is not None:
                pending_order_repository.mark_filled(order_id)
            if on_grid_updated is not None:
                on_grid_updated()
            completed += 1
            logger.info(f"[체결] {format_order_log(order)} (id={order_id})")
            del pending_orders[order_id]
            continue

        if status.is_cancelled:
            if pending_order_repository is not None:
                pending_order_repository.mark_cancelled(order_id)
            logger.warning(
                f"[취소] {format_order_log(order)} 주문 취소 "
                f"(id={order_id}, executed={format_decimal(status.executed_volume)}, "
                f"remaining={format_decimal(status.remaining_volume)})"
            )
            del pending_orders[order_id]
            continue

        logger.warning(
            f"[대기] 알 수 없는 주문 상태 감지 "
            f"(id={order_id}, state={status.state})"
        )

    return completed


def submit_orders(
    approved_orders,
    exchange: BaseExchange,
    pending_orders: dict[str, Order],
    pending_order_repository: PendingOrderRepository | None = None,
) -> int:
    """주문을 거래소에 접수하고, 체결 확인 전까지 pending 으로 관리한다."""
    submitted = 0

    for order in approved_orders:
        order_id = exchange.place_order(order)
        if order_id:
            order.order_id = order_id
            pending_orders[order_id] = order
            if pending_order_repository is not None:
                try:
                    pending_order_repository.add(order)
                except Exception as exc:
                    pending_orders.pop(order_id, None)
                    logger.error(f"[실패] 주문 저장소 반영 실패 → 주문 취소 시도 (id={order_id}): {exc}")
                    try:
                        exchange.cancel_order(order_id)
                    except Exception as cancel_exc:  # pragma: no cover - 방어적 로깅
                        logger.error(f"[실패] 저장 실패 후 주문 취소도 실패 (id={order_id}): {cancel_exc}")
                    raise StatePersistenceError(
                        f"주문 저장소 반영 실패로 안전하게 중단합니다. order_id={order_id}"
                    ) from exc
            submitted += 1
            logger.info(f"[접수] {format_order_log(order)} (id={order_id})")
        else:
            logger.error(f"[실패] {format_order_log(order)} 주문 실패")

    return submitted


def build_exchange() -> BaseExchange:
    """설정에 따라 거래소 인스턴스 생성"""
    if cfg.EXCHANGE_TYPE == "crypto":
        from exchange.crypto import CryptoExchange
        return CryptoExchange(cfg.API_KEY, cfg.API_SECRET)
    elif cfg.EXCHANGE_TYPE == "stock":
        from exchange.stock import StockExchange
        return StockExchange(cfg.API_KEY, cfg.API_SECRET)
    else:
        raise ValueError(f"알 수 없는 EXCHANGE_TYPE: {cfg.EXCHANGE_TYPE}")


def acquire_runtime_lock_if_needed():
    from storage.postgres_common import PostgresRuntimeLock

    runtime_lock = PostgresRuntimeLock.from_config(cfg)
    if not runtime_lock.acquire():
        raise RuntimeError(
            f"같은 bot_key 로 이미 다른 postgres 백엔드 봇이 실행 중입니다: {cfg.STATE_BOT_KEY}"
        )
    logger.info(f"postgres 단일 실행 락 획득: bot_key={cfg.STATE_BOT_KEY}")
    return runtime_lock


def decimal_arg(value: str) -> Decimal:
    return to_decimal(value)


def validate_grid_state(grid_state: GridState):
    max_total_budget = cfg.MAX_TOTAL_BUDGET_KRW
    if max_total_budget is None or max_total_budget <= 0:
        return

    if grid_state.total_allocated_budget > max_total_budget:
        raise ValueError(
            f"그리드 총 배정 금액이 한도를 초과했습니다: "
            f"{format_decimal(grid_state.total_allocated_budget)} > {format_decimal(max_total_budget)}"
        )


def refresh_grid_state_if_changed(
    grid_state: GridState,
    repository: GridStateRepository,
    runtime: GridStateRuntime,
) -> bool:
    """실행 중 저장소 상태가 외부에서 바뀌면 즉시 다시 읽는다."""
    if not repository.has_changed(runtime.metadata):
        return False

    snapshot = repository.load()
    grid_state.replace_with(snapshot)
    runtime.metadata = snapshot.metadata
    validate_runtime_grid_state(grid_state)
    validate_grid_state(grid_state)
    logger.info("외부 상태 저장소 변경 감지 → 재로드")
    logger.info(grid_state.summary())
    return True


def check_risk(orders, exchange: BaseExchange, grid_state: GridState) -> list:
    """
    간단한 리스크 체크: 잔고 부족 / 최소 주문 금액 미달 시 매수 주문 제외
    통과한 주문만 반환한다.
    """
    validate_grid_state(grid_state)
    balance = exchange.get_balance()
    approved = []

    for order in orders:
        if order.side == OrderSide.BUY:
            required = order.required_krw
            if required < MIN_KRW_ORDER_AMOUNT:
                logger.warning(f"[BLOCK] 슬롯 {order.slot_index} 최소 주문 금액 미달")
                continue
            if balance < required + cfg.MIN_BALANCE_RESERVE:
                logger.warning(
                    f"[BLOCK] 슬롯 {order.slot_index} 잔고 부족 "
                    f"(필요: {format_decimal(required)}, 가용: {format_decimal(balance)})"
                )
                continue
            balance -= required  # 동일 루프 내 다음 주문 잔고 선반영

        approved.append(order)

    return approved


def filter_pending_slot_orders(orders, pending_orders: dict[str, Order]) -> list[Order]:
    """이미 pending 인 슬롯은 중복 주문하지 않는다."""
    pending_slots = {order.slot_index for order in pending_orders.values()}
    return [order for order in orders if order.slot_index not in pending_slots]


def process_cycle_orders(
    *,
    sell_orders: list[Order],
    buy_orders: list[Order],
    exchange: BaseExchange,
    strategy: GridStrategy,
    pending_orders: dict[str, Order],
    daily_order_count: int,
    on_grid_updated: Callable[[], None] | None = None,
    pending_order_repository: PendingOrderRepository | None = None,
) -> int:
    """
    한 번의 가격 평가에서 나온 주문을 실제 체결 흐름에 맞춰 처리한다.
    매수 주문 승인은 현재 주문 가능 KRW 기준으로만 판단하고,
    같은 사이클에서 발생한 매도 체결대금은 즉시 매수 재원으로 재사용하지 않는다.
    """
    grid_state = strategy.grid
    submitted_total = 0

    sell_orders = filter_pending_slot_orders(sell_orders, pending_orders)
    buy_orders = filter_pending_slot_orders(buy_orders, pending_orders)
    approved_buys = check_risk(buy_orders, exchange, grid_state) if buy_orders else []

    if sell_orders:
        if daily_order_count + len(sell_orders) > cfg.MAX_DAILY_ORDERS:
            logger.warning("[BLOCK] 일일 주문 한도 초과")
            return 0

        submitted_sells = submit_orders(
            sell_orders,
            exchange,
            pending_orders,
            pending_order_repository=pending_order_repository,
        )
        submitted_total += submitted_sells

    if not approved_buys:
        if submitted_total:
            completed = reconcile_pending_orders(
                exchange,
                pending_orders,
                strategy,
                on_grid_updated=on_grid_updated,
                pending_order_repository=pending_order_repository,
            )
            if completed:
                logger.info(grid_state.summary())
        return submitted_total

    approved_buys = filter_pending_slot_orders(approved_buys, pending_orders)
    if approved_buys:
        if daily_order_count + submitted_total + len(approved_buys) > cfg.MAX_DAILY_ORDERS:
            logger.warning("[BLOCK] 일일 주문 한도 초과")
        else:
            submitted_buys = submit_orders(
                approved_buys,
                exchange,
                pending_orders,
                pending_order_repository=pending_order_repository,
            )
            submitted_total += submitted_buys

    if submitted_total:
        completed = reconcile_pending_orders(
            exchange,
            pending_orders,
            strategy,
            on_grid_updated=on_grid_updated,
            pending_order_repository=pending_order_repository,
        )
        if completed:
            logger.info(grid_state.summary())
    return submitted_total


def run():
    logger.info("=== 그리드 자동매매 시작 ===")

    runtime_lock = acquire_runtime_lock_if_needed()
    try:
        grid_repository = build_grid_repository(cfg)
        grid_state, runtime = load_grid_state(grid_repository)
        validate_grid_state(grid_state)
        logger.info(grid_state.summary())

        exchange = build_exchange()
        strategy = GridStrategy(grid_state, exchange, cfg.SYMBOL)
        persist_current_grid = lambda: persist_grid_state(grid_state, grid_repository, runtime)

        daily_order_count = 0
        pending_order_repository = build_pending_order_repository(cfg)
        pending_orders = {
            order.order_id: order
            for order in pending_order_repository.list_open()
            if order.order_id is not None
        }
        if pending_orders:
            logger.info(f"미체결 주문 복구: {len(pending_orders)}건")

        while True:
            try:
                refresh_grid_state_if_changed(grid_state, grid_repository, runtime)

                completed = reconcile_pending_orders(
                    exchange,
                    pending_orders,
                    strategy,
                    on_grid_updated=persist_current_grid,
                    pending_order_repository=pending_order_repository,
                )
                if completed:
                    logger.info(grid_state.summary())

                current_price = exchange.get_current_price(cfg.SYMBOL)
                logger.info(f"현재가: {current_price}")

                buy_orders, sell_orders = strategy.evaluate(current_price)
                if not sell_orders and not buy_orders:
                    time.sleep(cfg.PRICE_POLL_INTERVAL)
                    continue

                submitted = process_cycle_orders(
                    sell_orders=sell_orders,
                    buy_orders=buy_orders,
                    exchange=exchange,
                    strategy=strategy,
                    pending_orders=pending_orders,
                    daily_order_count=daily_order_count,
                    on_grid_updated=persist_current_grid,
                    pending_order_repository=pending_order_repository,
                )
                daily_order_count += submitted

                if submitted:
                    logger.info(grid_state.summary())

            except KeyboardInterrupt:
                logger.info("사용자 중단")
                break
            except StatePersistenceError as e:
                logger.error(f"치명적 상태 저장 오류 발생 → 새 주문 중단: {e}", exc_info=True)
                break
            except Exception as e:
                logger.error(f"오류 발생: {e}", exc_info=True)

            time.sleep(cfg.PRICE_POLL_INTERVAL)
    finally:
        if runtime_lock is not None:
            runtime_lock.release()


def run_balance_check() -> int:
    """업비트 KRW 주문 가능 잔고를 1회 조회하고 종료."""
    print("=== 업비트 KRW 잔고 조회 ===")
    print("거래소: Upbit")
    print(f"마켓: {cfg.SYMBOL}")

    if cfg.EXCHANGE_TYPE != "crypto":
        print("상태: 실패")
        print("사유: 현재 잔고 조회 원샷 명령은 업비트 코인 거래 모드에서만 지원합니다.")
        return 1

    if not cfg.API_KEY or not cfg.API_SECRET:
        print("상태: 실패")
        print("사유: UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 환경변수를 먼저 설정하세요.")
        return 1

    exchange = build_exchange()

    try:
        balance = exchange.get_balance()
    except UpbitAPIError as e:
        print("상태: 실패")
        print(f"사유: {e}")
        return 1
    except Exception as e:
        print("상태: 실패")
        print(f"사유: 잔고 조회 중 예상치 못한 오류가 발생했습니다: {e}")
        return 1

    print(f"주문 가능 KRW 잔고: {format_decimal(balance)} KRW")
    print("상태: 성공")
    return 0


def run_grid_init(
    *,
    lower_price: Decimal,
    upper_price: Decimal,
    slot_count: int,
    first_buy_amount: Decimal,
    sell_percent: Decimal,
    current_price: Decimal | None,
    force: bool = False,
) -> int:
    """KRW-BTC 초기 그리드를 PostgreSQL 상태 저장소에 저장."""
    print("=== KRW-BTC 초기 그리드 생성 ===")
    print(f"심볼: {cfg.SYMBOL}")
    print(f"저장 대상: postgres:{cfg.PGSCHEMA}/{cfg.STATE_BOT_KEY}")

    if cfg.EXCHANGE_TYPE != "crypto":
        print("상태: 실패")
        print("사유: 현재 그리드 생성 명령은 업비트 코인 거래 모드에서만 지원합니다.")
        return 1

    exchange = build_exchange()
    repository = build_grid_repository(cfg)

    try:
        existing_snapshot = repository.load()
        if existing_snapshot.metadata.version is not None and not force:
            print("상태: 실패")
            print("사유: 기존 PostgreSQL 그리드 스냅샷이 있습니다. 덮어쓰려면 --force 를 사용하세요.")
            return 1

        live_price = current_price if current_price is not None else exchange.get_current_price(cfg.SYMBOL)
        rows = build_cash_only_grid(
            lower_price=lower_price,
            upper_price=upper_price,
            current_price=live_price,
            slot_count=slot_count,
            first_buy_amount_krw=first_buy_amount,
            sell_percent=sell_percent,
        )
        state = GridState.from_rows(cfg.SYMBOL, rows)
        validate_grid_state(state)

        metadata = existing_snapshot.metadata if existing_snapshot.metadata.version is not None else None
        saved_snapshot = repository.save(state.to_snapshot(metadata))
    except (UpbitAPIError, ValueError) as e:
        print("상태: 실패")
        print(f"사유: {e}")
        return 1
    except Exception as e:
        print("상태: 실패")
        print(f"사유: 그리드 생성 중 예상치 못한 오류가 발생했습니다: {e}")
        return 1

    print(f"현재가 스냅샷: {format_decimal(live_price)} KRW")
    print(f"상단 경계: {format_decimal(upper_price)} KRW")
    print(f"하단 경계: {format_decimal(lower_price)} KRW")
    print(f"슬롯 수: {slot_count}")
    print(f"첫 칸 기준 매수금액: {format_decimal(first_buy_amount)} KRW")
    print(f"매도 퍼센트: {format_decimal(sell_percent)}%")
    print(f"고정 수량: {format_decimal(rows[0].planned_qty)} BTC")
    print(f"총 배정 금액: {format_decimal(state.total_allocated_budget)} KRW")
    print(f"버전: {saved_snapshot.metadata.version}")
    print("상태: 성공")
    return 0


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 main.py")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("balance", help="업비트 KRW 주문 가능 잔고를 1회 조회하고 종료")

    grid_parser = subparsers.add_parser("init-grid", help="KRW-BTC 초기 그리드를 PostgreSQL 상태 저장소에 저장")
    grid_parser.add_argument("--lower-price", type=decimal_arg, default=cfg.GRID_LOWER_PRICE)
    grid_parser.add_argument("--upper-price", type=decimal_arg, default=cfg.GRID_UPPER_PRICE)
    grid_parser.add_argument("--slot-count", type=int, default=cfg.GRID_SLOT_COUNT)
    grid_parser.add_argument("--first-buy-amount", type=decimal_arg, default=cfg.GRID_FIRST_BUY_AMOUNT_KRW)
    grid_parser.add_argument("--sell-percent", type=decimal_arg, default=cfg.GRID_SELL_PERCENT)
    grid_parser.add_argument("--current-price", type=decimal_arg, default=None)
    grid_parser.add_argument("--force", action="store_true", help="기존 PostgreSQL 그리드 스냅샷을 덮어쓴다")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        run()
        return 0

    parser = build_cli_parser()
    args = parser.parse_args(argv)

    if args.command == "balance":
        return run_balance_check()

    if args.command == "init-grid":
        return run_grid_init(
            lower_price=args.lower_price,
            upper_price=args.upper_price,
            slot_count=args.slot_count,
            first_buy_amount=args.first_buy_amount,
            sell_percent=args.sell_percent,
            current_price=args.current_price,
            force=args.force,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
