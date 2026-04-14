"""
그리드 자동매매 메인 루프
"""
import argparse
import sys
import time
from decimal import Decimal

import config.settings as cfg
from core.grid_builder import build_cash_only_grid
from core.grid import GridState
from core.models import Order, OrderSide
from exchange.base import BaseExchange
from exchange.crypto import UpbitAPIError
from strategy.grid_strategy import GridStrategy
from utils.decimal_utils import format_decimal, to_decimal
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT
from utils.logger import get_logger

logger = get_logger(__name__)


def reconcile_pending_orders(exchange: BaseExchange, pending_orders: dict[str, Order], strategy: GridStrategy) -> int:
    """대기 중인 주문의 실제 체결 여부를 조회해 그리드 상태에 반영한다."""
    completed = 0

    for order_id, order in list(pending_orders.items()):
        status = exchange.get_order_status(order_id)

        if status.is_open:
            continue

        if status.is_filled:
            strategy.apply_filled_order(order)
            completed += 1
            logger.info(
                f"[체결] {order.side.value} 슬롯{order.slot_index} "
                f"{order.price} x {order.quantity} (id={order_id})"
            )
            del pending_orders[order_id]
            continue

        if status.is_cancelled:
            logger.warning(
                f"[취소] {order.side.value} 슬롯{order.slot_index} 주문 취소 "
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


def submit_orders(approved_orders, exchange: BaseExchange, pending_orders: dict[str, Order]) -> int:
    """주문을 거래소에 접수하고, 체결 확인 전까지 pending 으로 관리한다."""
    submitted = 0

    for order in approved_orders:
        order_id = exchange.place_order(order)
        if order_id:
            order.order_id = order_id
            pending_orders[order_id] = order
            submitted += 1
            logger.info(
                f"[접수] {order.side.value} 슬롯{order.slot_index} "
                f"{order.price} x {order.quantity} (id={order_id})"
            )
        else:
            logger.error(f"[실패] 슬롯 {order.slot_index} 주문 실패")

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


def refresh_grid_state_if_changed(grid_state: GridState) -> bool:
    """실행 중 grid.txt가 외부에서 바뀌면 즉시 다시 읽는다."""
    changed = grid_state.reload_if_changed()
    if changed:
        validate_grid_state(grid_state)
        logger.info("외부 grid.txt 변경 감지 → 재로드")
        logger.info(grid_state.summary())
    return changed


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
            required = order.price * order.quantity
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


def run():
    logger.info("=== 그리드 자동매매 시작 ===")

    grid_state = GridState(cfg.GRID_FILE)
    validate_grid_state(grid_state)
    logger.info(grid_state.summary())

    exchange = build_exchange()
    strategy = GridStrategy(grid_state, exchange, cfg.SYMBOL)

    daily_order_count = 0
    pending_orders: dict[str, Order] = {}

    while True:
        try:
            refresh_grid_state_if_changed(grid_state)

            completed = reconcile_pending_orders(exchange, pending_orders, strategy)
            if completed:
                logger.info(grid_state.summary())

            current_price = exchange.get_current_price(cfg.SYMBOL)
            logger.info(f"현재가: {current_price}")

            buy_orders, sell_orders = strategy.evaluate(current_price)
            all_orders = sell_orders + buy_orders  # 매도 우선 처리

            pending_slots = {order.slot_index for order in pending_orders.values()}
            all_orders = [order for order in all_orders if order.slot_index not in pending_slots]

            if not all_orders:
                time.sleep(cfg.PRICE_POLL_INTERVAL)
                continue

            # 리스크 체크
            approved = check_risk(all_orders, exchange, grid_state)

            # 일일 주문 한도 체크
            if daily_order_count + len(approved) > cfg.MAX_DAILY_ORDERS:
                logger.warning("[BLOCK] 일일 주문 한도 초과")
                time.sleep(cfg.PRICE_POLL_INTERVAL)
                continue

            submitted = submit_orders(approved, exchange, pending_orders)
            daily_order_count += submitted

            if submitted:
                logger.info(grid_state.summary())

        except KeyboardInterrupt:
            logger.info("사용자 중단")
            break
        except Exception as e:
            logger.error(f"오류 발생: {e}", exc_info=True)

        time.sleep(cfg.PRICE_POLL_INTERVAL)


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
    grid_file: str,
    lower_price: Decimal,
    upper_price: Decimal,
    slot_count: int,
    first_buy_amount: Decimal,
    current_price: Decimal | None,
) -> int:
    """KRW-BTC 초기 그리드를 생성하고 저장."""
    print("=== KRW-BTC 초기 그리드 생성 ===")
    print(f"심볼: {cfg.SYMBOL}")
    print(f"저장 파일: {grid_file}")

    if cfg.EXCHANGE_TYPE != "crypto":
        print("상태: 실패")
        print("사유: 현재 그리드 생성 명령은 업비트 코인 거래 모드에서만 지원합니다.")
        return 1

    exchange = build_exchange()

    try:
        live_price = current_price if current_price is not None else exchange.get_current_price(cfg.SYMBOL)
        rows = build_cash_only_grid(
            lower_price=lower_price,
            upper_price=upper_price,
            current_price=live_price,
            slot_count=slot_count,
            first_buy_amount_krw=first_buy_amount,
        )
        state = GridState.from_rows(cfg.SYMBOL, rows, grid_file=grid_file)
        validate_grid_state(state)
        state.save()
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
    print(f"고정 수량: {format_decimal(rows[0].planned_qty)} BTC")
    print(f"총 배정 금액: {format_decimal(state.total_allocated_budget)} KRW")
    print("상태: 성공")
    return 0


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 main.py")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("balance", help="업비트 KRW 주문 가능 잔고를 1회 조회하고 종료")

    grid_parser = subparsers.add_parser("init-grid", help="KRW-BTC 초기 그리드를 생성하고 grid.txt에 저장")
    grid_parser.add_argument("--grid-file", default=cfg.GRID_FILE)
    grid_parser.add_argument("--lower-price", type=decimal_arg, default=cfg.GRID_LOWER_PRICE)
    grid_parser.add_argument("--upper-price", type=decimal_arg, default=cfg.GRID_UPPER_PRICE)
    grid_parser.add_argument("--slot-count", type=int, default=cfg.GRID_SLOT_COUNT)
    grid_parser.add_argument("--first-buy-amount", type=decimal_arg, default=cfg.GRID_FIRST_BUY_AMOUNT_KRW)
    grid_parser.add_argument("--current-price", type=decimal_arg, default=None)

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
            grid_file=args.grid_file,
            lower_price=args.lower_price,
            upper_price=args.upper_price,
            slot_count=args.slot_count,
            first_buy_amount=args.first_buy_amount,
            current_price=args.current_price,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
