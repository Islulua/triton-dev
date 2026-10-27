"""Database lifecycle and transactions. SQLite is a local-development adapter only."""

import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from triton_dev.common.contracts import ToolError
from . import models as m

LEASE = ContextVar("platform_lease", default=None)
SYSTEM = "system"
LEGACY = "legacy"


def uid(prefix=""):
    return prefix + uuid.uuid4().hex


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class Database:
    def __init__(self, url, root):
        if not url.startswith(("postgresql+psycopg://", "sqlite:///")):
            raise ToolError(
                "INVALID_DATABASE", "Use PostgreSQL+psycopg or explicit local SQLite URL"
            )
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine = sa.create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30}
            if url.startswith("sqlite")
            else {},
        )
        if self.engine.dialect.name == "sqlite":

            @sa.event.listens_for(self.engine, "connect")
            def sqlite_pragmas(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA journal_mode=WAL")

        self.migrate()
        with self.tx() as c:
            for wid in [SYSTEM, LEGACY]:
                if not c.execute(
                    sa.select(m.workspaces.c.id).where(m.workspaces.c.id == wid)
                ).first():
                    c.execute(m.workspaces.insert().values(id=wid, kind=wid))

    def migrate(self):
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                connection.execute(sa.text("SELECT pg_advisory_xact_lock(81724101)"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    @contextmanager
    def tx(self):
        with self.engine.begin() as connection:
            yield connection

    def log(self, workspace, action, object_id, payload=None):
        with self.tx() as c:
            c.execute(
                m.audit.insert().values(
                    id=uid(),
                    workspace_id=workspace,
                    action=action,
                    object_id=object_id,
                    created_at=time.time(),
                    payload=payload or {},
                )
            )

    def dispose(self):
        self.engine.dispose()
