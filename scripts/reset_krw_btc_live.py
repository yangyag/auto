#!/usr/bin/env python3
"""KRW-BTC 라이브 상태를 정리하고 새 grid.properties를 반영한다."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config.settings as cfg
from core.models import Order, OrderExecutionType, OrderSide
from exchange.crypto import UpbitAPIError
from main import build_exchange
from storage.factory import build_pending_order_repository
from utils.decimal_utils import DECIMAL_ZERO, format_decimal
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT
from utils.logger import get_logger

logger = get_logger("reset_krw_btc_live")

DEFAULT_ORDER_WAIT_SECONDS = 30
DEFAULT_ORDER_POLL_SECONDS = 1.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 scripts/reset_krw_btc_live.py")
    parser.add_argument("--tail-lines", type=int, default=50)
    parser.add_argument("--wait-timeout", type=int, default=DEFAULT_ORDER_WAIT_SECONDS)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_ORDER_POLL_SECONDS)
    return parser


def run_project_command(args: list[str], *, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        logger.info(completed.stdout.rstrip())
    if completed.stderr:
        logger.error(completed.stderr.rstrip())


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


def print_latest_log_tail(*, lines: int) -> None:
    log_dir = PROJECT_ROOT / cfg.LOG_DIR
    log_files = sorted(log_dir.glob("trading-*.log"))
    if not log_files:
        print("로그 파일이 없습니다.")
        return

    latest_log = max(log_files, key=lambda path: path.stat().st_mtime)
    print(f"=== latest log tail: {latest_log.name} ===")
    content = latest_log.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in content[-max(lines, 1):]:
        print(line)


def validate_environment() -> None:
    if cfg.EXCHANGE_TYPE != "crypto":
        raise RuntimeError("이 운영 스크립트는 업비트 crypto 모드에서만 지원합니다.")
    if cfg.SYMBOL != "KRW-BTC":
        raise RuntimeError(f"이 운영 스크립트는 KRW-BTC 전용입니다: {cfg.SYMBOL}")
    if not cfg.API_KEY or not cfg.API_SECRET:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 환경변수가 필요합니다.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_environment()

    exchange = build_exchange()
    pending_order_repository = build_pending_order_repository(cfg)

    print_runtime_snapshot(exchange)
    run_project_command([str(PROJECT_ROOT / "stop.sh")])
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
        [python_bin, "scripts/apply_grid_properties_to_postgres.py", "--force"]
    )
    run_project_command([python_bin, "scripts/show_grid_state.py"])
    run_project_command(
        [str(PROJECT_ROOT / "run.sh")],
        env={**os.environ, "PYTHON_BIN": python_bin},
    )
    print_latest_log_tail(lines=args.tail_lines)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, UpbitAPIError, subprocess.CalledProcessError) as exc:
        logger.error(f"상태: 실패\n사유: {exc}")
        raise SystemExit(1)
