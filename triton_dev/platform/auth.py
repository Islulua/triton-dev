"""Name-only cooperative identity, opaque sessions and CSRF validation."""

import hashlib
import secrets
import time
import unicodedata

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from triton_dev.common.contracts import ToolError
from .database import uid
from . import models as m


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Auth:
    def __init__(self, db):
        self.db = db

    def login(self, name):
        if not isinstance(name, str):
            raise ToolError("INVALID_NAME", "请输入姓名")
        name = unicodedata.normalize("NFC", name).strip()
        if not 1 <= len(name) <= 64 or any(unicodedata.category(x).startswith("C") for x in name):
            raise ToolError("INVALID_NAME", "姓名长度需为1..64，不能包含控制字符")
        canonical = name.casefold()
        for _ in range(3):
            try:
                with self.db.tx() as c:
                    user = (
                        c.execute(sa.select(m.users).where(m.users.c.canonical_name == canonical))
                        .mappings()
                        .first()
                    )
                    if not user:
                        user = {
                            "id": uid("usr_"),
                            "name": name,
                            "canonical_name": canonical,
                            "created_at": time.time(),
                        }
                        c.execute(m.users.insert().values(**user))
                        c.execute(
                            m.workspaces.insert().values(
                                id=uid("ws_"), kind="personal", user_id=user["id"]
                            )
                        )
                    workspace = c.execute(
                        sa.select(m.workspaces.c.id).where(m.workspaces.c.user_id == user["id"])
                    ).scalar_one()
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                    c.execute(
                        m.sessions.insert().values(
                            token_hash=sha(token),
                            user_id=user["id"],
                            csrf_hash=sha(csrf),
                            expires_at=time.time() + 86400,
                            revoked=False,
                        )
                    )
                self.db.log(workspace, "login", user["id"])
                return {
                    "user_id": user["id"],
                    "name": user["name"],
                    "workspace_id": workspace,
                    "csrf_token": csrf,
                    "auth_mode": "name-only",
                    "identity_verified": False,
                }, token
            except IntegrityError:
                continue
        raise ToolError("LOGIN_CONFLICT", "Concurrent account creation; retry")

    def actor(self, token, csrf=None, write=False):
        if not token:
            raise ToolError("UNAUTHORIZED", "请先输入姓名登录")
        with self.db.tx() as c:
            row = (
                c.execute(
                    sa.select(m.sessions, m.users.c.name, m.workspaces.c.id.label("workspace_id"))
                    .join(m.users, m.users.c.id == m.sessions.c.user_id)
                    .join(m.workspaces, m.workspaces.c.user_id == m.users.c.id)
                    .where(
                        m.sessions.c.token_hash == sha(token),
                        m.sessions.c.revoked.is_(False),
                        m.sessions.c.expires_at > time.time(),
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise ToolError("UNAUTHORIZED", "登录已失效")
        if write and (not csrf or not secrets.compare_digest(row["csrf_hash"], sha(csrf))):
            raise ToolError("CSRF_REJECTED", "Session CSRF token required")
        return {
            "user_id": row["user_id"],
            "name": row["name"],
            "workspace_id": row["workspace_id"],
            "auth_mode": "name-only",
            "identity_verified": False,
        }

    def logout(self, token):
        with self.db.tx() as c:
            c.execute(
                m.sessions.update()
                .where(m.sessions.c.token_hash == sha(token))
                .values(revoked=True)
            )
