#!/usr/bin/env python3
"""grid.properties를 읽어 PostgreSQL source of truth 그리드를 생성/반영한다."""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROPERTIES_FILE = PROJECT_ROOT / "grid.properties"

sys.path.insert(0, str(PROJECT_ROOT))

import config.settings as cfg
from core.grid_properties import build_grid_rows_from_property_spec, load_grid_property_spec
from storage.interfaces import GridSnapshot, RepositoryMetadata
from storage.postgres_grid_repository import PostgresGridRepository


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
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = load_grid_property_spec(args.properties_file)
    rows = build_grid_rows_from_property_spec(spec)

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
    print(f"top_buy_price: {rows[0].buy_price}")
    print(f"bottom_buy_price: {rows[-1].buy_price}")
    print(f"version: {saved.metadata.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
