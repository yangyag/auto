from __future__ import annotations

import hashlib
from dataclasses import dataclass

try:
    import psycopg
    from psycopg import sql
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when dependency is absent
    psycopg = None
    sql = None
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None


POSTGRES_DEFAULT_HOST = "127.0.0.1"
POSTGRES_DEFAULT_PORT = 5432
POSTGRES_DEFAULT_DATABASE = "yangyag"
POSTGRES_DEFAULT_USER = "yangyag"
POSTGRES_DEFAULT_SCHEMA = "auto_trading"
POSTGRES_DEFAULT_BOT_KEY = "default"


def require_psycopg() -> None:
    if psycopg is None:
        raise ModuleNotFoundError(
            "psycopg 패키지가 필요합니다. requirements.txt 의 psycopg[binary] 를 설치하세요."
        ) from _PSYCOPG_IMPORT_ERROR


@dataclass(frozen=True)
class PostgresConnectionSettings:
    host: str = POSTGRES_DEFAULT_HOST
    port: int = POSTGRES_DEFAULT_PORT
    dbname: str = POSTGRES_DEFAULT_DATABASE
    user: str = POSTGRES_DEFAULT_USER
    password: str = ""
    schema: str = POSTGRES_DEFAULT_SCHEMA
    bot_key: str = POSTGRES_DEFAULT_BOT_KEY

    @classmethod
    def from_config(cls, config) -> "PostgresConnectionSettings":
        return cls(
            host=getattr(config, "PGHOST", POSTGRES_DEFAULT_HOST),
            port=int(getattr(config, "PGPORT", POSTGRES_DEFAULT_PORT)),
            dbname=getattr(config, "PGDATABASE", POSTGRES_DEFAULT_DATABASE),
            user=getattr(config, "PGUSER", POSTGRES_DEFAULT_USER),
            password=getattr(config, "PGPASSWORD", ""),
            schema=getattr(config, "PGSCHEMA", POSTGRES_DEFAULT_SCHEMA),
            bot_key=getattr(config, "STATE_BOT_KEY", POSTGRES_DEFAULT_BOT_KEY),
        )


class PostgresRepositoryMixin:
    def __init__(
        self,
        *,
        host: str = POSTGRES_DEFAULT_HOST,
        port: int = POSTGRES_DEFAULT_PORT,
        dbname: str = POSTGRES_DEFAULT_DATABASE,
        user: str = POSTGRES_DEFAULT_USER,
        password: str = "",
        schema: str = POSTGRES_DEFAULT_SCHEMA,
        bot_key: str = POSTGRES_DEFAULT_BOT_KEY,
    ):
        require_psycopg()
        self.host = host
        self.port = int(port)
        self.dbname = dbname
        self.user = user
        self.password = password
        self.schema = schema
        self.bot_key = bot_key

    @classmethod
    def from_config(cls, config):
        settings = PostgresConnectionSettings.from_config(config)
        return cls(
            host=settings.host,
            port=settings.port,
            dbname=settings.dbname,
            user=settings.user,
            password=settings.password,
            schema=settings.schema,
            bot_key=settings.bot_key,
        )

    def _connect(self):
        connect_kwargs = {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "autocommit": False,
        }
        if self.password:
            connect_kwargs["password"] = self.password
        return psycopg.connect(**connect_kwargs)

    def _qualified(self, table_name: str):
        require_psycopg()
        return sql.SQL("{}.{}").format(sql.Identifier(self.schema), sql.Identifier(table_name))


def advisory_lock_key(schema: str, bot_key: str) -> int:
    digest = hashlib.sha256(f"{schema}:{bot_key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class PostgresRuntimeLock(PostgresRepositoryMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connection = None
        self._lock_key = advisory_lock_key(self.schema, self.bot_key)

    def acquire(self) -> bool:
        if self._connection is not None:
            return True

        conn = self._connect()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (self._lock_key,))
            locked = cur.fetchone()[0]
        if not locked:
            conn.close()
            return False

        self._connection = conn
        return True

    def release(self) -> None:
        if self._connection is None:
            return
        try:
            with self._connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (self._lock_key,))
        finally:
            self._connection.close()
            self._connection = None
