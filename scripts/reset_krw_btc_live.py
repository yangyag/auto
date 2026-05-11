#!/usr/bin/env python3
"""KRW-BTC 라이브 상태를 정리하고 새 grid.properties를 반영한다."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.config.settings as cfg
from app.core.models import Order, OrderExecutionType, OrderSide
from app.exchange.crypto import UpbitAPIError
from app.main import build_exchange
from app.storage.factory import build_pending_order_repository
from app.storage.postgres_common import PostgresRuntimeLock
from app.utils.decimal_utils import DECIMAL_ZERO, format_decimal
from app.utils.upbit_market import MIN_KRW_ORDER_AMOUNT
from app.utils.logger import get_logger

logger = get_logger("reset_krw_btc_live")

DEFAULT_ORDER_WAIT_SECONDS = 30
DEFAULT_ORDER_POLL_SECONDS = 1.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 scripts/reset_krw_btc_live.py")
    parser.add_argument("--wait-timeout", type=int, default=DEFAULT_ORDER_WAIT_SECONDS)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_ORDER_POLL_SECONDS)
    return parser


def run_project_command(args: list[str], *, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        logger.info(completed.stdout.rstrip())
    if completed.stderr:
        logger.error(completed.stderr.rstrip())
    completed.check_returncode()


def print_runtime_snapshot(exchange) -> None:
    krw_balance = exchange.get_balance()
    holdings = exchange.get_holdings(cfg.SYMBOL)
    current_price = exchange.get_current_price(cfg.SYMBOL)
    open_order_ids = exchange.get_open_order_ids(cfg.SYMBOL)

    logger.info("=== 런타임 스냅샷 ===")
    logger.info(f"symbol: {cfg.SYMBOL}")
    logger.info(f"current_price: {format_decimal(current_price)}")
    logger.info(f"krw_balance: {format_decimal(krw_balance)}")
    logger.info(f"holdings: {format_decimal(holdings)}")
    logger.info(f"live_open_orders: {len(open_order_ids)}")


def cancel_open_orders(
    exchange,
    pending_order_repository,
    *,
    timeout_seconds: int = DEFAULT_ORDER_WAIT_SECONDS,
    poll_interval: float = DEFAULT_ORDER_POLL_SECONDS,
) -> None:
    open_order_ids = exchange.get_open_order_ids(cfg.SYMBOL)
    logger.info(f"취소 대상 live open orders: {len(open_order_ids)}")

    for order_id in open_order_ids:
        if not exchange.cancel_order(order_id):
            raise RuntimeError(f"업비트 주문 취소 실패: {order_id}")
        if pending_order_repository.get(order_id) is not None:
            pending_order_repository.mark_cancelled(order_id)

    deadline = time.monotonic() + max(timeout_seconds, 1)
    while True:
        remaining_order_ids = exchange.get_open_order_ids(cfg.SYMBOL)
        if not remaining_order_ids:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "KRW-BTC 미체결 주문이 남아 있습니다: "
                + ", ".join(remaining_order_ids)
            )
        time.sleep(max(poll_interval, 0.1))

    repository_open_orders = pending_order_repository.list_open()
    for order in repository_open_orders:
        if order.order_id is not None:
            pending_order_repository.mark_cancelled(order.order_id)
    logger.info(f"pending repository open orders 정리: {len(repository_open_orders)}")


def wait_for_terminal_order_status(
    exchange,
    order_id: str,
    *,
    timeout_seconds: int,
    poll_interval: float,
):
    deadline = time.monotonic() + max(timeout_seconds, 1)
    while True:
        status = exchange.get_order_status(order_id)
        if not status.is_open:
            return status
        if time.monotonic() >= deadline:
            raise RuntimeError(f"주문 상태 확인 타임아웃: {order_id}")
        time.sleep(max(poll_interval, 0.1))


def liquidate_btc_position(
    exchange,
    *,
    timeout_seconds: int,
    poll_interval: float,
) -> str | None:
    quantity = exchange.get_holdings(cfg.SYMBOL)
    if quantity <= DECIMAL_ZERO:
        logger.info("BTC 보유 수량이 없어 전량 매도를 건너뜁니다.")
        return None

    current_price = exchange.get_current_price(cfg.SYMBOL)
    notional = current_price * quantity
    if notional < MIN_KRW_ORDER_AMOUNT:
        logger.info(
            "BTC 보유 금액이 업비트 최소 주문 금액보다 작아 전량 매도를 건너뜁니다: "
            f"{format_decimal(notional)}"
        )
        return None

    order = Order(
        slot_index=0,
        side=OrderSide.SELL,
        price=current_price,
        quantity=quantity,
        symbol=cfg.SYMBOL,
        execution_type=OrderExecutionType.MARKET_SELL_BY_VOLUME,
        identifier=(
            f"{cfg.STATE_BOT_KEY}-reset-sell-"
            f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:12]}"
        ),
    )
    order_id = exchange.place_order(order)
    if not order_id:
        raise RuntimeError("BTC 전량 시장가 매도 주문 접수에 실패했습니다.")

    status = wait_for_terminal_order_status(
        exchange,
        order_id,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )
    if not status.is_filled:
        raise RuntimeError(
            "BTC 전량 시장가 매도가 체결 완료 상태로 끝나지 않았습니다: "
            f"state={status.state}"
        )

    remaining_holdings = exchange.get_holdings(cfg.SYMBOL)
    logger.info(
        "BTC 전량 시장가 매도 완료: "
        f"order_id={order_id}, remaining_holdings={format_decimal(remaining_holdings)}"
    )
    return order_id


def validate_environment() -> None:
    if cfg.EXCHANGE_TYPE != "crypto":
        raise RuntimeError("이 운영 스크립트는 업비트 crypto 모드에서만 지원합니다.")
    if cfg.SYMBOL != "KRW-BTC":
        raise RuntimeError(f"이 운영 스크립트는 KRW-BTC 전용입니다: {cfg.SYMBOL}")
    if not cfg.API_KEY or not cfg.API_SECRET:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 환경변수가 필요합니다.")


def main(argv: list[str] | None = None) -> int:
    os.chdir(PROJECT_ROOT)
    args = build_parser().parse_args(argv)
    validate_environment()

    run_project_command([str(PROJECT_ROOT / "stop.sh")])

    lock = PostgresRuntimeLock(
        host=cfg.PGHOST,
        port=cfg.PGPORT,
        dbname=cfg.PGDATABASE,
        user=cfg.PGUSER,
        password=cfg.PGPASSWORD,
        schema=cfg.PGSCHEMA,
        bot_key=cfg.STATE_BOT_KEY,
    )
    if not lock.acquire():
        logger.error("락 점유 실패: 봇이 실행 중이거나 기존 스크립트 실행 중")
        sys.exit(1)

    try:
        exchange = build_exchange()
        pending_order_repository = build_pending_order_repository(cfg)

        print_runtime_snapshot(exchange)
        cancel_open_orders(
            exchange,
            pending_order_repository,
            timeout_seconds=args.wait_timeout,
            poll_interval=args.poll_interval,
        )
        liquidate_btc_position(
            exchange,
            timeout_seconds=args.wait_timeout,
            poll_interval=args.poll_interval,
        )

        python_bin = sys.executable
        run_project_command(
            [
                python_bin,
                "scripts/apply_grid_properties_to_postgres.py",
                "--force",
                "--assume-external-lock",
            ]
        )
        run_project_command([python_bin, "scripts/show_grid_state.py"])
        logger.info("리셋 완료. 봇 재시작은 필요 시 ./run.sh 로 직접 수행하세요.")
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, UpbitAPIError, subprocess.CalledProcessError) as exc:
        logger.error(f"상태: 실패\n사유: {exc}")
        raise SystemExit(1)
