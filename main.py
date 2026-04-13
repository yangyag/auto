"""
그리드 자동매매 메인 루프
"""
import time

import config.settings as cfg
from core.grid import GridState
from core.models import OrderSide
from exchange.base import BaseExchange
from strategy.grid_strategy import GridStrategy
from utils.logger import get_logger

logger = get_logger(__name__)


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


def check_risk(orders, exchange: BaseExchange, grid_state: GridState) -> list:
    """
    간단한 리스크 체크: 잔고 부족 / 최대 재고 한도 초과 시 매수 주문 제외
    통과한 주문만 반환한다.
    """
    balance = exchange.get_balance()
    approved = []

    for order in orders:
        if order.side == OrderSide.BUY:
            required = order.price * order.quantity
            if balance < required + cfg.MIN_BALANCE_RESERVE:
                logger.warning(f"[BLOCK] 슬롯 {order.slot_index} 잔고 부족 (필요: {required:.0f}, 가용: {balance:.0f})")
                continue
            if grid_state.total_inventory + order.quantity > cfg.MAX_TOTAL_INVENTORY:
                logger.warning(f"[BLOCK] 슬롯 {order.slot_index} 최대 재고 한도 초과")
                continue
            balance -= required  # 동일 루프 내 다음 주문 잔고 선반영

        approved.append(order)

    return approved


def run():
    logger.info("=== 그리드 자동매매 시작 ===")

    grid_state = GridState(cfg.GRID_FILE)
    logger.info(grid_state.summary())

    exchange = build_exchange()
    strategy = GridStrategy(grid_state, exchange, cfg.SYMBOL)

    daily_order_count = 0

    while True:
        try:
            current_price = exchange.get_current_price(cfg.SYMBOL)
            logger.info(f"현재가: {current_price}")

            buy_orders, sell_orders = strategy.evaluate(current_price)
            all_orders = sell_orders + buy_orders  # 매도 우선 처리

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

            # 주문 실행
            for order in approved:
                order_id = exchange.place_order(order)
                if order_id:
                    order.order_id = order_id
                    strategy.apply_filled_order(order)
                    daily_order_count += 1
                    logger.info(
                        f"[체결] {order.side.value} 슬롯{order.slot_index} "
                        f"{order.price} x {order.quantity}주 (id={order_id})"
                    )
                else:
                    logger.error(f"[실패] 슬롯 {order.slot_index} 주문 실패")

            logger.info(grid_state.summary())

        except KeyboardInterrupt:
            logger.info("사용자 중단")
            break
        except Exception as e:
            logger.error(f"오류 발생: {e}", exc_info=True)

        time.sleep(cfg.PRICE_POLL_INTERVAL)


if __name__ == "__main__":
    run()
