#!/usr/bin/env python3
"""라이브 그리드의 하단 매수합 목표를 갱신해 planned_qty 만 재계산한다.

DB 의 ladder 와 보유 수량은 그대로 두고, buy_price < 현재가 인 슬롯의
매수합이 사용자 지정 금액이 되도록 가중치 비율로 역산해 슬롯별
planned_qty 를 다시 계산한다.
"""
import argparse
import sys
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.config.settings as cfg
from app.core.grid_properties import GridPropertySpec, build_weighted_slot_budgets
from app.core.models import OrderSide
from app.storage.interfaces import GridSnapshot
from app.storage.postgres_common import PostgresRuntimeLock
from app.storage.postgres_grid_repository import PostgresGridRepository
from app.storage.postgres_order_repository import PostgresOrderRepository
from app.utils.decimal_utils import BTC_QUANTITY_STEP, DECIMAL_ZERO, format_decimal, quantize_to_step
from app.utils.upbit_market import MIN_KRW_ORDER_AMOUNT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="라이브 그리드 하단 매수합 조정 스크립트")
    parser.add_argument(
        "--target-lower-budget",
        type=Decimal,
        required=True,
        help=(
            "현재가 미만 슬롯들의 매수합 목표 금액 (KRW). "
            "현재가를 조회해서 buy_price < 현재가 인 슬롯의 가중치 비율로 총 예산을 역산한다."
        ),
    )
    parser.add_argument("--bot-key", default=cfg.STATE_BOT_KEY)
    parser.add_argument("--force", action="store_true", help="인벤토리 초과 경고 등을 무시하고 강제 실행")
    return parser


def fetch_current_price(symbol: str) -> Decimal:
    """업비트 ticker REST 로 현재가 1회 조회. WS 캐시는 깨우지 않는다."""
    from app.exchange.crypto import CryptoExchange

    exchange = CryptoExchange(cfg.API_KEY or "", cfg.API_SECRET or "")
    try:
        return exchange.get_current_price_rest(symbol)
    finally:
        exchange.close()


def compute_lower_actual_total(rows, lower_indices: list[int]) -> Decimal:
    """양자화 후 하단 슬롯의 buy_price × planned_qty 합. held_qty 와 무관."""
    total = DECIMAL_ZERO
    for idx in lower_indices:
        row = rows[idx]
        total += row.buy_price * row.planned_qty
    return total


def validate_snapshot_rows(snapshot: GridSnapshot) -> None:
    """DB에서 읽은 ladder가 연속 index와 내림차순 buy_price를 유지하는지 확인."""
    for expected_index, row in enumerate(snapshot.rows, start=1):
        if row.index != expected_index:
            raise ValueError(
                f"에러: 슬롯 인덱스 불일치 (기대값 {expected_index}, 실제값 {row.index})"
            )
        if row.buy_price <= DECIMAL_ZERO:
            raise ValueError(f"에러: Slot {row.index} buy_price는 0보다 커야 합니다.")
        if expected_index > 1 and row.buy_price >= snapshot.rows[expected_index - 2].buy_price:
            raise ValueError(
                "에러: buy_price가 내림차순이 아닙니다 "
                f"(Slot {expected_index - 1}: {snapshot.rows[expected_index - 2].buy_price} "
                f"-> Slot {expected_index}: {row.buy_price})"
            )


def list_open_buys(order_repo: PostgresOrderRepository) -> list:
    return [order for order in order_repo.list_open() if order.side == OrderSide.BUY]


def build_updated_rows(
    snapshot: GridSnapshot,
    target_lower_budget: Decimal,
    current_price: Decimal,
) -> tuple[list, Decimal, list[int], Decimal, Decimal]:
    """현재 DB ladder 와 현재가 기준으로 새 planned_qty 를 계산.

    Returns: (updated_rows, new_planned_buy_budget, lower_indices, lower_ratio, target_total_budget).
    """
    grid_count = len(snapshot.rows)
    spec = GridPropertySpec(
        min_buy_price=snapshot.rows[-1].buy_price,
        max_buy_price=snapshot.rows[0].buy_price,
        lower_budget_krw=target_lower_budget,
        grid_count=grid_count,
    )
    buy_prices_desc = [row.buy_price for row in snapshot.rows]
    slot_budgets, lower_indices, lower_ratio, target_total_budget = build_weighted_slot_budgets(
        spec,
        current_price=current_price,
        buy_prices_desc=buy_prices_desc,
    )

    updated_rows = []
    new_planned_buy_budget = DECIMAL_ZERO

    for row, slot_budget in zip(snapshot.rows, slot_budgets):
        new_planned_qty = quantize_to_step(
            slot_budget / row.buy_price,
            BTC_QUANTITY_STEP,
            rounding=ROUND_DOWN,
        )
        if new_planned_qty <= DECIMAL_ZERO:
            raise ValueError(
                "에러: 슬롯 "
                f"{row.index} planned_qty가 0 이하가 됩니다. "
                f"slot_budget={format_decimal(slot_budget)} KRW, "
                f"buy_price={format_decimal(row.buy_price)} KRW"
            )

        order_total = row.buy_price * new_planned_qty
        if order_total < MIN_KRW_ORDER_AMOUNT:
            raise ValueError(
                "에러: 슬롯 "
                f"{row.index} 매수 금액이 업비트 최소 주문 금액보다 작습니다. "
                f"order_total={format_decimal(order_total)} KRW < "
                f"{format_decimal(MIN_KRW_ORDER_AMOUNT)} KRW"
            )

        updated_rows.append(replace(row, planned_qty=new_planned_qty))
        if row.is_empty:
            new_planned_buy_budget += order_total

    return updated_rows, new_planned_buy_budget, lower_indices, lower_ratio, target_total_budget


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bot_key = args.bot_key
    target_lower_budget = args.target_lower_budget

    if target_lower_budget <= DECIMAL_ZERO:
        print("에러: --target-lower-budget 은 0보다 커야 합니다.")
        return 1

    lock = PostgresRuntimeLock(
        host=cfg.PGHOST,
        port=cfg.PGPORT,
        dbname=cfg.PGDATABASE,
        user=cfg.PGUSER,
        password=cfg.PGPASSWORD,
        schema=cfg.PGSCHEMA,
        bot_key=bot_key,
    )
    if not lock.acquire():
        print("락 점유 실패: 봇이 실행 중이거나 기존 스크립트 실행 중", file=sys.stderr)
        sys.exit(1)

    try:
        grid_repo = PostgresGridRepository(
            host=cfg.PGHOST,
            port=cfg.PGPORT,
            dbname=cfg.PGDATABASE,
            user=cfg.PGUSER,
            password=cfg.PGPASSWORD,
            schema=cfg.PGSCHEMA,
            bot_key=bot_key,
        )
        order_repo = PostgresOrderRepository(
            host=cfg.PGHOST,
            port=cfg.PGPORT,
            dbname=cfg.PGDATABASE,
            user=cfg.PGUSER,
            password=cfg.PGPASSWORD,
            schema=cfg.PGSCHEMA,
            bot_key=bot_key,
        )

        if not grid_repo.exists():
            print(f"에러: DB에 bot_key='{bot_key}' 인 그리드 상태가 없습니다.")
            return 1

            snapshot = grid_repo.load()
        if not snapshot.rows:
            print("에러: 로드된 그리드 슬롯이 없습니다.")
            return 1

        open_buys = list_open_buys(order_repo)
        if open_buys:
            print(f"에러: 현재 열려 있는 BUY 주문이 {len(open_buys)}개 있습니다.")
            print("예산 조정 전에 모든 BUY 주문을 취소하고 봇을 중지해야 합니다.")
            for o in open_buys:
                print(f"  - Slot {o.slot_index}: {o.order_id}")
            return 1

        try:
            validate_snapshot_rows(snapshot)
        except ValueError as exc:
            print(exc)
            return 1

        try:
            current_price = fetch_current_price(snapshot.symbol or cfg.SYMBOL)
        except Exception as exc:
            print(f"에러: 현재가 조회 실패: {exc}")
            return 1
        if current_price <= DECIMAL_ZERO:
            print(f"에러: 현재가가 0 이하입니다: {current_price}")
            return 1

        current_inventory_cost = sum((r.buy_price * r.held_qty for r in snapshot.rows), DECIMAL_ZERO)
        current_planned_buy_budget = sum(
            (r.buy_price * r.planned_qty for r in snapshot.rows if r.is_empty),
            DECIMAL_ZERO,
        )

        try:
            updated_rows, new_planned_buy_budget, lower_indices, lower_ratio, target_total_budget = build_updated_rows(
                snapshot, target_lower_budget, current_price,
            )
        except ValueError as exc:
            print(exc)
            return 1

        actual_lower_total = compute_lower_actual_total(updated_rows, lower_indices)

        print("=" * 60)
        print(f" 그리드 예산 조정 리포트 (Bot: {bot_key})")
        print("-" * 60)
        print(f" 0. 현재가(KRW-BTC): {format_decimal(current_price)} KRW")
        print(f"    하단 슬롯 수: {len(lower_indices)} / {len(snapshot.rows)}")
        print(f"    하단 가중치 비율: {format_decimal(lower_ratio)}")
        print(f"    목표 하단 매수합: {format_decimal(target_lower_budget)} KRW")
        print(f"    양자화 후 실제 하단 매수합: {format_decimal(actual_lower_total)} KRW")
        print(f"    역산된 implicit total budget: {format_decimal(target_total_budget)} KRW")
        if len(lower_indices) == len(snapshot.rows):
            print(
                "    [경고] 현재가가 최상단 buy_price 보다 높아 모든 슬롯이 '하단'으로 잡혔습니다. "
                "이 경우 --target-lower-budget 가 곧 총 예산이 됩니다."
            )
        print(f" 1. 현재 인벤토리 가치: {format_decimal(current_inventory_cost)} KRW")
        print(f" 2. 적용 전 매수 대기 예산: {format_decimal(current_planned_buy_budget)} KRW")
        print(f" 3. 적용 후 매수 대기 예산: {format_decimal(new_planned_buy_budget)} KRW")
        print("-" * 60)

        if target_total_budget < current_inventory_cost:
            print(" [경고] 역산된 총 예산이 현재 보유 중인 인벤토리 가치보다 작습니다!")
            print(" 이 조정은 '빈 슬롯'의 매수 금액만 줄일 뿐, 이미 보유한 물량을 매도하지는 않습니다.")
            print(" 실제 예산 회수는 현재 보유 물량이 매도된 후에나 완료됩니다.")
            if not args.force:
                print("-" * 60)
                print(" 강제 진행하려면 --force 옵션을 사용하세요.")
                return 1

        print(" DB 업데이트를 진행하시겠습니까? (y/n): ", end="")
        confirm = input().strip().lower()
        if confirm != 'y':
            print("중단되었습니다.")
            return 0

        open_buys = list_open_buys(order_repo)
        if open_buys:
            print("에러: 확인 이후 새로운 BUY 주문이 감지되었습니다.")
            print("봇을 중지하고 미체결 BUY 주문을 정리한 뒤 다시 시도하세요.")
            for order in open_buys:
                print(f"  - Slot {order.slot_index}: {order.order_id}")
            return 1

        try:
            new_snapshot = GridSnapshot(
                symbol=snapshot.symbol,
                rows=tuple(updated_rows),
                metadata=snapshot.metadata,
            )
            grid_repo.save(new_snapshot)
        except Exception as e:
            print(f"에러: DB 저장 실패: {e}")
            return 1

        print("-" * 60)
        print("상태: 성공")
        print("DB의 planned_qty가 성공적으로 업데이트되었습니다.")
        print("=" * 60)
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
        sys.exit(1)
