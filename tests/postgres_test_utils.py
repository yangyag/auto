import json
import os
import subprocess
import unittest
import uuid
from pathlib import Path

from app.storage.postgres_common import psycopg, require_psycopg


def _docker_postgres_password() -> str:
    raw = subprocess.check_output(
        ["docker", "inspect", "postgres", "--format", "{{json .Config.Env}}"],
        text=True,
    )
    env = json.loads(raw)
    for item in env:
        if item.startswith("POSTGRES_PASSWORD="):
            return item.split("=", 1)[1]
    raise RuntimeError("postgres container password not found")


def postgres_test_config(*, schema: str | None = None, bot_key: str | None = None):
    password = os.getenv("PGPASSWORD") or _docker_postgres_password()
    return type(
        "Config",
        (),
        {
            "STATE_BOT_KEY": bot_key or f"test-bot-{uuid.uuid4().hex[:8]}",
            "PGHOST": os.getenv("PGHOST", "127.0.0.1"),
            "PGPORT": int(os.getenv("PGPORT", "5432")),
            "PGDATABASE": os.getenv("PGDATABASE", "yangyag"),
            "PGUSER": os.getenv("PGUSER", "yangyag"),
            "PGPASSWORD": password,
            "PGSCHEMA": schema or f"auto_trading_test_{uuid.uuid4().hex[:8]}",
        },
    )()


def _connect():
    require_psycopg()
    password = os.getenv("PGPASSWORD") or _docker_postgres_password()
    kwargs = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "yangyag"),
        "user": os.getenv("PGUSER", "yangyag"),
        "password": password,
        "autocommit": True,
    }
    return psycopg.connect(**kwargs)


def apply_test_schema(schema: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            migrations_dir = Path(__file__).resolve().parents[1] / "db" / "migrations"
            for sql_path in sorted(migrations_dir.glob("*.sql")):
                sql_text = sql_path.read_text(encoding="utf-8").replace("auto_trading", schema)
                cur.execute(sql_text)


def drop_test_schema(schema: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


class PostgresIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            require_psycopg()
            subprocess.run(["docker", "inspect", "postgres"], capture_output=True, check=True)
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
        except Exception as exc:  # pragma: no cover - skip path depends on environment
            raise unittest.SkipTest(f"postgres integration prerequisites unavailable: {exc}")
