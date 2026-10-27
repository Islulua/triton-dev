"""Owned immutable model profiles and encrypted write-only secrets. No live API calls."""

import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import sqlalchemy as sa
from cryptography.fernet import Fernet
from triton_dev.common.contracts import ToolError
from .database import uid
from . import models as m


class ModelProfiles:
    def __init__(self, db, root, allowed_endpoints=()):
        self.db = db
        path = Path(root) / "credentials" / "master.key"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise ToolError("INVALID_KEY_PATH", "Master key cannot be a symlink")
        if not path.exists():
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(Fernet.generate_key())
            except FileExistsError:
                pass
        if path.stat().st_mode & 0o077:
            raise ToolError("INSECURE_KEY", "Master key permissions must be 0600")
        self.cipher = Fernet(path.read_bytes())
        self.allowed_endpoints = set(allowed_endpoints)

    def list(self, workspace):
        with self.db.tx() as c:
            rows = (
                c.execute(
                    sa.select(
                        m.profiles,
                        m.profile_revisions.c.config,
                        m.profile_revisions.c.secret_id,
                        m.profile_revisions.c.created_at,
                    )
                    .join(
                        m.profile_revisions,
                        m.profiles.c.current_revision == m.profile_revisions.c.id,
                    )
                    .where(m.profiles.c.workspace_id == workspace)
                )
                .mappings()
                .all()
            )
        return [
            {k: v for k, v in dict(row).items() if k not in {"secret_id", "workspace_id"}}
            | {"has_key": bool(row["secret_id"])}
            for row in rows
        ]

    def save(self, workspace, data, profile_id=None):
        allowed = {
            "name",
            "provider",
            "base_url",
            "model",
            "api_flavor",
            "timeout_seconds",
            "max_output_tokens",
            "enabled",
            "is_default",
            "api_key",
        }
        if not isinstance(data, dict) or set(data) - allowed:
            raise ToolError("INVALID_PROFILE", "Unknown model profile field")
        if not isinstance(data.get("name"), str) or not 1 <= len(data["name"].strip()) <= 100:
            raise ToolError("INVALID_PROFILE", "Configuration name required")
        provider = data.get("provider", "mock")
        if provider not in {"mock", "openai_compatible"}:
            raise ToolError("INVALID_PROFILE", "Unsupported provider type")
        base = data.get("base_url", "").strip()
        if provider != "mock":
            parsed = urlsplit(base)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ToolError(
                    "INVALID_ENDPOINT", "Use an endpoint URL without embedded credentials/query"
                )
            # Explicit server-side endpoints; user cannot turn the API into an arbitrary network proxy.
            if base.rstrip("/") not in self.allowed_endpoints:
                raise ToolError(
                    "ENDPOINT_NOT_ALLOWED", "Ask the server administrator to register this endpoint"
                )
        model = data.get("model", "mock-planner-v1")
        if not isinstance(model, str) or not 1 <= len(model) <= 200:
            raise ToolError("INVALID_PROFILE", "Explicit model name required")
        for name, default, minimum, maximum in [
            ("timeout_seconds", 60, 1, 300),
            ("max_output_tokens", 2048, 1, 32000),
        ]:
            if (
                type(data.get(name, default)) is not int
                or not minimum <= data.get(name, default) <= maximum
            ):
                raise ToolError("INVALID_PROFILE", "Invalid model limits")
        key = data.get("api_key")
        if key is not None and (not isinstance(key, str) or not 1 <= len(key) <= 8192):
            raise ToolError("INVALID_SECRET", "Nonempty bounded API key required")
        for field in ["enabled", "is_default"]:
            if field in data and type(data[field]) is not bool:
                raise ToolError("INVALID_PROFILE", "Boolean flags required")
        config = {
            k: v
            for k, v in dict(
                provider=provider,
                base_url=base,
                model=model,
                api_flavor=data.get("api_flavor", "chat_completions"),
                timeout_seconds=data.get("timeout_seconds", 60),
                max_output_tokens=data.get("max_output_tokens", 2048),
                send_policy="redacted_summary_only",
            ).items()
        }
        if config["api_flavor"] not in {"chat_completions", "responses", "mock"}:
            raise ToolError("INVALID_PROFILE", "Unknown API flavor")
        updating = profile_id is not None
        profile_id = profile_id or uid("ai_")
        with self.db.tx() as c:
            c.execute(
                sa.select(m.workspaces.c.id).where(m.workspaces.c.id == workspace).with_for_update()
            ).scalar_one()
            old = (
                c.execute(
                    sa.select(m.profiles).where(
                        m.profiles.c.id == profile_id, m.profiles.c.workspace_id == workspace
                    )
                )
                .mappings()
                .first()
            )
            if updating and not old:
                raise ToolError("NOT_FOUND", "Profile not found")
            if (
                not old
                and c.execute(
                    sa.select(m.profiles.c.id).where(m.profiles.c.id == profile_id)
                ).first()
            ):
                raise ToolError("NOT_FOUND", "Profile not found")
            secret_id = None
            if old:
                secret_id = c.execute(
                    sa.select(m.profile_revisions.c.secret_id).where(
                        m.profile_revisions.c.id == old["current_revision"]
                    )
                ).scalar_one()
            if key is not None:
                secret_id = uid("secret_")
                c.execute(
                    m.secrets.insert().values(
                        id=secret_id,
                        workspace_id=workspace,
                        ciphertext=self.cipher.encrypt(key.encode()).decode(),
                        key_id="local-v1",
                        created_at=time.time(),
                    )
                )
            revision = uid("air_")
            default = data.get("is_default", old["is_default"] if old else False)
            if default:
                c.execute(
                    m.profiles.update()
                    .where(m.profiles.c.workspace_id == workspace)
                    .values(is_default=False)
                )
            values = dict(
                name=data["name"].strip(),
                enabled=data.get("enabled", True),
                is_default=default,
                current_revision=revision,
            )
            if old:
                c.execute(
                    m.profiles.update()
                    .where(m.profiles.c.id == profile_id, m.profiles.c.workspace_id == workspace)
                    .values(**values)
                )
            else:
                c.execute(
                    m.profiles.insert().values(id=profile_id, workspace_id=workspace, **values)
                )
            c.execute(
                m.profile_revisions.insert().values(
                    id=revision,
                    workspace_id=workspace,
                    profile_id=profile_id,
                    config=config,
                    secret_id=secret_id,
                    created_at=time.time(),
                )
            )
        self.db.log(
            workspace,
            "ai_profile.saved",
            profile_id,
            {"revision": revision, "key_updated": key is not None},
        )
        return next(x for x in self.list(workspace) if x["id"] == profile_id)

    def resolve(self, workspace, profile_id=None):
        with self.db.tx() as c:
            q = (
                sa.select(m.profiles, m.profile_revisions.c.config)
                .join(
                    m.profile_revisions, m.profiles.c.current_revision == m.profile_revisions.c.id
                )
                .where(m.profiles.c.workspace_id == workspace, m.profiles.c.enabled.is_(True))
            )
            q = (
                q.where(m.profiles.c.id == profile_id)
                if profile_id
                else q.where(m.profiles.c.is_default.is_(True))
            )
            row = c.execute(q).mappings().first()
        if profile_id and not row:
            raise ToolError("NOT_FOUND", "Enabled profile not found")
        return dict(row) if row else None

    def test(self, workspace, profile_id):
        row = self.resolve(workspace, profile_id)
        if row["config"]["provider"] != "mock":
            raise ToolError(
                "UNSUPPORTED",
                "Profile is saved; live provider connectivity/requests are not enabled in this build",
            )
        call_id = uid("call_")
        with self.db.tx() as c:
            c.execute(
                m.ai_calls.insert().values(
                    id=call_id,
                    workspace_id=workspace,
                    profile_revision_id=row["current_revision"],
                    state="mock_verified",
                    tokens=None,
                    cost=None,
                    created_at=time.time(),
                    payload={"source": "mock", "network_called": False},
                )
            )
        return {
            "state": "mock_verified",
            "network_called": False,
            "profile_revision_id": row["current_revision"],
            "message": "本地mock协议验证通过，未调用外部API",
        }
