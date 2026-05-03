#!/usr/bin/env python3
"""grid.properties를 읽어 PostgreSQL source of truth 그리드를 생성/반영한다."""
import argparse
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROPERTIES_FILE = PROJECT_ROOT / "grid.properties"

sys.path.insert(0, str(PROJECT_ROOT))

import app.config.settings as cfg
from app.core.grid_properties import (
    _compute_buy_prices_desc,
    _compute_raw_weights,
    build_grid_rows_from_property_spec,
    load_grid_property_spec,
    normalize_tp_model,
    resolve_total_budget_from_lower,
)
from app.storage.interfaces import GridSnapshot, RepositoryMetadata
from app.storage.postgres_grid_repository import PostgresGridRepository
from app.utils.decimal_utils import DECIMAL_ZERO, format_decimal
from app.utils.grid_reporting import summarize_planned_buy_budget
from app.utils.upbit_market import normalize_krw_price


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 scripts/apply_grid_properties_to_postgres.py")
    parser.add_argument("--properties-file", default=str(DEFAULT_PROPERTIES_FILE))
    parser.add_argument("--bot-key", default=cfg.STATE_BOT_KEY)
    parser.add_argument("--symbol", default=cfg.SYMBOL)
    parser.add_argument("--schema", default=cfg.PGSCHEMA)
    parser.add_argument("--host", default=cfg.PGHOST)
    parser.add_argument("--port", type=int, default=cfg.PGPORT)
    parser.add_argument("--dbname", default=cfg.PGDATABASE)
    parser.add_argument("--user", default=cfg.PGUSER)
    parser.add_argument("--password", default=cfg.PGPASSWORD)
    parser.add_argument(
        "--current-price",
        type=Decimal,
        default=None,
        help="현재가를 직접 지정 (테스트/리허설용). 미지정 시 업비트 ticker REST 로 조회.",
    )
    parser.add_argument("--force", action="store_true")
    return parser


def fetch_current_price(symbol: str) -> Decimal:
    """업비트 ticker REST 로 현재가 1회 조회. WS 캐시는 깨우지 않는다."""
    from app.exchange.crypto import CryptoExchange

    exchange = CryptoExchange(cfg.API_KEY or "", cfg.API_SECRET or "")
    try:
        return exchange.get_current_price_rest(symbol)
    finally:
        exchange.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = load_grid_property_spec(args.properties_file)

    if args.current_price is not None:
        current_price = Decimal(args.current_price)
    else:
        try:
            current_price = fetch_current_price(args.symbol)
        except Exception as exc:
            print("상태: 실패")
            print(f"사유: 현재가 조회 실패: {exc}")
            return 1
    if current_price <= DECIMAL_ZERO:
        print("상태: 실패")
        print(f"사유: 현재가가 0 이하입니다: {current_price}")
        return 1

    try:
        rows = build_grid_rows_from_property_spec(spec, current_price=current_price)
        raw_weights = _compute_raw_weights(spec.grid_count)
        buy_prices_desc = _compute_buy_prices_desc(
            min_buy_price=normalize_krw_price(spec.min_buy_price),
            max_buy_price=normalize_krw_price(spec.max_buy_price),
            grid_count=spec.grid_count,
        )
        target_total_budget, lower_indices, lower_ratio = resolve_total_budget_from_lower(
            raw_weights=raw_weights,
            buy_prices_desc=buy_prices_desc,
            current_price=current_price,
            lower_budget_krw=spec.lower_budget_krw,
        )
    except ValueError as exc:
        print("상태: 실패")
        print(f"사유: {exc}")
        return 1

    budget_summary = summarize_planned_buy_budget(rows)
    resolved_tp_model = normalize_tp_model(spec.tp_model)
    actual_lower_total = sum(
        (rows[i].buy_price * rows[i].planned_qty for i in lower_indices),
        DECIMAL_ZERO,
    )

    repository = PostgresGridRepository(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        schema=args.schema,
        bot_key=args.bot_key,
    )
    if repository.exists() and not args.force:
        print("상태: 실패")
        print("사유: 동일 bot_key 상태가 이미 존재합니다. 덮어쓰려면 --force 를 사용하세요.")
        return 1

    saved = repository.save(
        GridSnapshot(
            symbol=args.symbol,
            rows=tuple(rows),
            metadata=RepositoryMetadata(),
        )
    )
    print("상태: 성공")
    print(f"bot_key: {args.bot_key}")
    print(f"symbol: {args.symbol}")
    print(f"rows: {len(rows)}")
    print(f"tp_model: {resolved_tp_model}")
    print(f"tp_k_base: {spec.tp_k_base or cfg.GRID_TP_K_BASE}")
    print(f"tp_k_floor: {spec.tp_k_floor or cfg.GRID_TP_K_FLOOR}")
    print(f"current_price: {format_decimal(current_price)}")
    print(f"top_buy_price: {rows[0].buy_price}")
    print(f"bottom_buy_price: {rows[-1].buy_price}")
    print(f"lower_slot_count: {len(lower_indices)} / {len(rows)}")
    print(f"lower_ratio: {format_decimal(lower_ratio)}")
    print(f"target_lower_budget: {format_decimal(spec.lower_budget_krw)}")
    print(f"actual_lower_budget: {format_decimal(actual_lower_total)}")
    print(f"implicit_total_budget: {format_decimal(target_total_budget)}")
    print(f"planned_buy_budget_total: {format_decimal(budget_summary.total)}")
    print(f"top_slot_planned_buy_budget: {format_decimal(budget_summary.top_slot)}")
    print(f"bottom_slot_planned_buy_budget: {format_decimal(budget_summary.bottom_slot)}")
    print(f"version: {saved.metadata.version}")
    if len(lower_indices) == len(rows):
        print(
            "[경고] 현재가가 최상단 buy_price 보다 높아 모든 슬롯이 '하단'으로 잡혔습니다. "
            "이 경우 LOWER_BUDGET_KRW 가 곧 총 예산이 됩니다."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
