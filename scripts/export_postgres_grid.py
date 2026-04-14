#!/usr/bin/env python3
"""PostgreSQL 상태를 grid.txt 형식 파일로 내보낸다."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config.settings as cfg
from storage.file_grid_repository import FileGridRepository
from storage.postgres_grid_repository import PostgresGridRepository


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
    FileGridRepository(args.output).save(snapshot)
    print("상태: 성공")
    print(f"bot_key: {args.bot_key}")
    print(f"output: {args.output}")
    print(f"rows: {len(snapshot.rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
