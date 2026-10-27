"""System-owned SDK catalog and durable daily batches. No fabricated SDK verification."""

import datetime as dt
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from triton_dev.common.contracts import ToolError
from .database import uid, fingerprint, SYSTEM
from . import models as m


class Daily:
    def __init__(self, db, queue):
        self.db, self.queue = db, queue

    def import_build(self, data):
        fields = {
            "source",
            "channel",
            "platform",
            "build_id",
            "build_date",
            "components",
            "source_kind",
        }
        if (
            not isinstance(data, dict)
            or set(data) != fields
            or data["source_kind"] not in {"mock", "declared"}
        ):
            raise ToolError(
                "INVALID_BUILD",
                "Exact source/channel/platform/build/date/components/source_kind required",
            )
        try:
            dt.date.fromisoformat(data["build_date"])
        except (ValueError, TypeError):
            raise ToolError("INVALID_BUILD", "ISO business date required") from None
        if any(
            not isinstance(data[k], str) or not 1 <= len(data[k]) <= 128
            for k in fields - {"components"}
        ):
            raise ToolError("INVALID_BUILD", "Bounded build metadata required")
        if not isinstance(data["components"], dict) or not data["components"]:
            raise ToolError("INVALID_BUILD", "Explicit components required")
        # Only metadata/declared hashes are imported. Downloads and readiness are separate.
        digest = fingerprint(data)
        with self.db.tx() as c:
            old = (
                c.execute(sa.select(m.sdk_builds).where(m.sdk_builds.c.manifest_digest == digest))
                .mappings()
                .first()
            )
            if old:
                return dict(old)
            row = dict(
                id=uid("sdk_"),
                source=data["source"],
                channel=data["channel"],
                platform=data["platform"],
                build_id=data["build_id"],
                build_date=data["build_date"],
                manifest_digest=digest,
                state="candidate",
                manifest=data,
            )
            c.execute(m.sdk_builds.insert().values(**row))
        self.db.log(SYSTEM, "sdk.import", row["id"], {"scope": "metadata_only"})
        return row

    def definition(self, name, job_id, hour=0, minute=0):
        if job_id not in self.queue.jobs:
            raise ToolError("INVALID_RECIPE", "Registered job required")
        if (
            not isinstance(name, str)
            or not 1 <= len(name) <= 128
            or type(hour) is not int
            or type(minute) is not int
            or not 0 <= hour < 24
            or not 0 <= minute < 60
        ):
            raise ToolError(
                "INVALID_ARGUMENT", "Name and valid Shanghai scheduled hour/minute required"
            )
        config = {
            "job_id": job_id,
            "hour": hour,
            "minute": minute,
            "timezone": "Asia/Shanghai",
            "scope": "registered_job_environment",
        }
        with self.db.tx() as c:
            old = (
                c.execute(sa.select(m.daily_definitions).where(m.daily_definitions.c.name == name))
                .mappings()
                .first()
            )
            if old:
                if old["config"] != config:
                    raise ToolError(
                        "DEFINITION_EXISTS",
                        "Create a new definition name instead of changing a historical recipe",
                    )
                return dict(old)
            row = dict(id=uid("daily_"), name=name, config=config, enabled=True)
            c.execute(m.daily_definitions.insert().values(**row))
        return row

    def tick(self, now=None):
        now = now or dt.datetime.now(dt.timezone.utc)
        local = now.astimezone(ZoneInfo("Asia/Shanghai"))
        with self.db.tx() as c:
            definitions = (
                c.execute(
                    sa.select(m.daily_definitions).where(m.daily_definitions.c.enabled.is_(True))
                )
                .mappings()
                .all()
            )
            builds = (
                c.execute(
                    sa.select(m.sdk_builds)
                    .order_by(m.sdk_builds.c.build_date.desc(), m.sdk_builds.c.id.desc())
                    .limit(1)
                )
                .mappings()
                .all()
            )
        if not builds:
            return []
        build = builds[0]
        result = []
        for definition in definitions:
            config = definition["config"]
            if (local.hour, local.minute) < (config["hour"], config["minute"]):
                continue
            signature = [definition["id"], local.date().isoformat(), build["id"]]
            key = "daily_" + fingerprint(signature)[:40]
            manager = self.queue.manager(SYSTEM)
            task = manager.submit(config["job_id"], key)
            try:
                with self.db.tx() as c:
                    old = (
                        c.execute(
                            sa.select(m.daily_batches).where(
                                m.daily_batches.c.definition_id == definition["id"],
                                m.daily_batches.c.business_date == local.date().isoformat(),
                                m.daily_batches.c.build_id == build["id"],
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if old:
                        result.append(dict(old))
                        continue
                    row = dict(
                        id=uid("batch_"),
                        definition_id=definition["id"],
                        business_date=local.date().isoformat(),
                        build_id=build["id"],
                        task_id=task["id"],
                        state="queued",
                        summary={"scope": "registered_job_environment", "sdk_installed": False},
                    )
                    c.execute(m.daily_batches.insert().values(**row))
                    result.append(row)
            except IntegrityError:
                continue
        return result

    def builds(self, source=None, start=None, end=None, limit=50):
        if not 1 <= limit <= 100:
            raise ToolError("INVALID_ARGUMENT", "limit must be 1..100")
        q = sa.select(m.sdk_builds)
        if source:
            q = q.where(m.sdk_builds.c.source == source)
        if start:
            q = q.where(m.sdk_builds.c.build_date >= start)
        if end:
            q = q.where(m.sdk_builds.c.build_date <= end)
        with self.db.tx() as c:
            return [
                dict(r)
                for r in c.execute(
                    q.order_by(m.sdk_builds.c.build_date.desc(), m.sdk_builds.c.id.desc()).limit(
                        limit
                    )
                ).mappings()
            ]

    def batches(self, limit=50):
        if not 1 <= limit <= 100:
            raise ToolError("INVALID_ARGUMENT", "limit must be 1..100")
        with self.db.tx() as c:
            rows = (
                c.execute(
                    sa.select(
                        m.daily_batches,
                        m.tasks.c.state.label("task_state"),
                        m.tasks.c.payload.label("task_payload"),
                    )
                    .join(m.tasks, m.tasks.c.id == m.daily_batches.c.task_id)
                    .order_by(m.daily_batches.c.business_date.desc(), m.daily_batches.c.id.desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        return [
            {k: v for k, v in dict(r).items() if k != "task_payload"}
            | {"state": r["task_state"], "task_summary": r["task_payload"].get("summary")}
            for r in rows
        ]
