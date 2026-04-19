#!/usr/bin/env python3
"""PostgreSQL 상태를 사람이 읽는 텍스트로 내보낸다."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config.settings as cfg
from storage.interfaces import GridSnapshot
from storage.postgres_grid_repository import PostgresGridRepository
from utils.decimal_utils import DECIMAL_ZERO, format_decimal
from utils.grid_reporting import summarize_planned_buy_budget


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 scripts/export_postgres_grid.py")
    parser.add_argument("--output", default="grid.postgres-export.txt")
    parser.add_argument("--bot-key", default=cfg.STATE_BOT_KEY)
    parser.add_argument("--schema", default=cfg.PGSCHEMA)
    parser.add_argument("--host", default=cfg.PGHOST)
    parser.add_argument("--port", type=int, default=cfg.PGPORT)
    parser.add_argument("--dbname", default=cfg.PGDATABASE)
    parser.add_argument("--user", default=cfg.PGUSER)
    parser.add_argument("--password", default=cfg.PGPASSWORD)
    return parser


def render_grid_text(snapshot: GridSnapshot) -> str:
    lines = [f"Grid3 {snapshot.symbol}"]
    for row in snapshot.rows:
        lines.append(
            f"{row.index}) {format_decimal(row.buy_price)} {format_decimal(row.held_qty)} "
            f"{format_decimal(row.sell_price)} {format_decimal(row.planned_qty)}"
        )

    total_inventory = sum((row.held_qty for row in snapshot.rows), DECIMAL_ZERO)
    budget_summary = summarize_planned_buy_budget(snapshot.rows)
    lines.append("")
    lines.append(f"테이블 총재고 : {format_decimal(total_inventory)}")
    lines.append(f"총 계획매수금액 : {format_decimal(budget_summary.total)}")
    lines.append(f"최상단 슬롯 계획매수금액 : {format_decimal(budget_summary.top_slot)}")
    lines.append(f"최하단 슬롯 계획매수금액 : {format_decimal(budget_summary.bottom_slot)}")
    age_rows = [row for row in snapshot.rows if getattr(row, "filled_at", None) is not None]
    if age_rows:
        lines.append("")
        lines.append("보유 슬롯 age 메타데이터")
        for row in age_rows:
            lines.append(f"{row.index}) filled_at={row.filled_at.isoformat()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    postgres_repo = PostgresGridRepository(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        schema=args.schema,
        bot_key=args.bot_key,
    )
    snapshot = postgres_repo.load()
    output_path = Path(args.output)
    output_path.write_text(render_grid_text(snapshot), encoding="utf-8")
    print("상태: 성공")
    print(f"bot_key: {args.bot_key}")
    print(f"source: postgres:{args.schema}/{args.bot_key}")
    print(f"output: {args.output}")
    print(f"rows: {len(snapshot.rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
