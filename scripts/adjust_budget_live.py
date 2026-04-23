#!/usr/bin/env python3
"""
라이브 그리드의 예산을 증액 또는 감액합니다. (방법 A: 보수적 업데이트)
리뷰 의견을 반영하여 DB 상태를 기준으로 엄격하게 동작하도록 개편되었습니다.
"""
import argparse
import sys
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config.settings as cfg
from core.grid_properties import GridPropertySpec, build_weighted_slot_budgets
from core.models import OrderSide
from storage.interfaces import GridSnapshot
from storage.postgres_grid_repository import PostgresGridRepository
from storage.postgres_order_repository import PostgresOrderRepository
from utils.decimal_utils import BTC_QUANTITY_STEP, DECIMAL_ZERO, format_decimal, quantize_to_step
from utils.upbit_market import MIN_KRW_ORDER_AMOUNT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="라이브 그리드 예산 증/감액 스크립트 (개선판)")
    parser.add_argument(
        "--target-budget",
        type=Decimal,
        required=True,
        help="새로운 목표 총 예산 금액 (KRW)",
    )
    parser.add_argument("--bot-key", default=cfg.STATE_BOT_KEY)
    parser.add_argument("--force", action="store_true", help="인벤토리 초과 경고 등을 무시하고 강제 실행")
    return parser


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
    target_budget: Decimal,
) -> tuple[list, Decimal]:
    """현재 DB ladder 기준으로 새 planned_qty를 계산하고, 저장 전 전 슬롯 검증."""
    grid_count = len(snapshot.rows)
    spec = GridPropertySpec(
        min_buy_price=snapshot.rows[-1].buy_price,
        max_buy_price=snapshot.rows[0].buy_price,
        total_budget_krw=target_budget,
        grid_count=grid_count,
    )
    slot_budgets = build_weighted_slot_budgets(spec)

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

    return updated_rows, new_planned_buy_budget


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_budget = args.target_budget
    bot_key = args.bot_key

    if target_budget <= DECIMAL_ZERO:
        print("에러: 목표 총 예산은 0보다 커야 합니다.")
        return 1

    # 1. 저장소 초기화
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

    # 2. 현재 상태 로드 및 검증
    snapshot = grid_repo.load()
    if not snapshot.rows:
        print("에러: 로드된 그리드 슬롯이 없습니다.")
        return 1

    # 3. Open BUY 주문 확인 (리뷰 3번 반영)
    open_buys = list_open_buys(order_repo)
    if open_buys:
        print(f"에러: 현재 열려 있는 BUY 주문이 {len(open_buys)}개 있습니다.")
        print("예산 조정 전에 모든 BUY 주문을 취소하고 봇을 중지해야 합니다.")
        for o in open_buys:
            print(f"  - Slot {o.slot_index}: {o.order_id}")
        return 1

    # 4. DB 데이터 일관성 검증 (리뷰 2, 5번 반영)
    try:
        validate_snapshot_rows(snapshot)
    except ValueError as exc:
        print(exc)
        return 1

    # 5. 인벤토리 현황 계산 및 요약 (리뷰 4, 6번 반영)
    current_inventory_cost = sum((r.buy_price * r.held_qty for r in snapshot.rows), DECIMAL_ZERO)
    current_planned_buy_budget = sum(
        (r.buy_price * r.planned_qty for r in snapshot.rows if r.is_empty),
        DECIMAL_ZERO,
    )

    try:
        updated_rows, new_planned_buy_budget = build_updated_rows(snapshot, target_budget)
    except ValueError as exc:
        print(exc)
        return 1

    # 6. 리포트 출력 및 감액 시 경고
    print("=" * 60)
    print(f" 그리드 예산 조정 리포트 (Bot: {bot_key})")
    print("-" * 60)
    print(f" 1. 목표 총 예산: {format_decimal(target_budget)} KRW")
    print(f" 2. 현재 인벤토리 가치: {format_decimal(current_inventory_cost)} KRW")
    print(f" 3. 적용 전 매수 대기 예산: {format_decimal(current_planned_buy_budget)} KRW")
    print(f" 4. 적용 후 매수 대기 예산: {format_decimal(new_planned_buy_budget)} KRW")
    print("-" * 60)

    if target_budget < current_inventory_cost:
        print(" [경고] 목표 예산이 현재 보유 중인 인벤토리 가치보다 작습니다!")
        print(" 이 조정은 '빈 슬롯'의 매수 금액만 줄일 뿐, 이미 보유한 물량을 매도하지는 않습니다.")
        print(" 실제 예산 회수는 현재 보유 물량이 매도된 후에나 완료됩니다.")
        if not args.force:
            print("-" * 60)
            print(" 강제 진행하려면 --force 옵션을 사용하세요.")
            return 1

    # 7. 저장 (리뷰 2번 반영: 일관성 확인 후 한꺼번에 저장)
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
        sys.exit(1)
