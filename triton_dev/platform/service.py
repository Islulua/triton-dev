"""Facade shared by ASGI, CLI and scheduling; no user-controlled execution recipes."""

import json
from pathlib import Path

import sqlalchemy as sa
from triton_dev.common.contracts import ToolError
from .database import Database, LEGACY
from .auth import Auth
from .ai import ModelProfiles
from .runtime import Queue
from .daily import Daily
from .repository import Repository
from . import models as m


class Platform:
    def __init__(self, url, root, jobs=None, allowed_endpoints=(), start_worker=True):
        self.db = Database(url, root)
        self.auth = Auth(self.db)
        self.profiles = ModelProfiles(self.db, root, allowed_endpoints)
        self.queue = Queue(self.db, jobs or {}, start_worker=start_worker)
        self.daily = Daily(self.db, self.queue)

    def manager(self, actor):
        return self.queue.manager(actor["workspace_id"])

    def regression_start(self, actor, config, key, profile_id=None):
        profile = self.profiles.resolve(actor["workspace_id"], profile_id)
        if profile and profile["config"]["provider"] != "mock":
            raise ToolError(
                "UNSUPPORTED",
                "Live provider is saved but not enabled; select a mock profile for the current regression adapter",
            )
        return self.manager(actor).regressions.start(
            config,
            idempotency_key=key,
            profile_revision=profile["current_revision"] if profile else None,
        )

    def usage(self, workspace):
        with self.db.tx() as c:
            tasks = c.execute(
                sa.select(sa.func.count())
                .select_from(m.tasks)
                .where(m.tasks.c.workspace_id == workspace)
            ).scalar_one()
            calls = c.execute(
                sa.select(sa.func.count())
                .select_from(m.ai_calls)
                .where(m.ai_calls.c.workspace_id == workspace)
            ).scalar_one()
            storage = c.execute(
                sa.select(sa.func.coalesce(sa.func.sum(m.blobs.c.size), 0)).where(
                    m.blobs.c.workspace_id == workspace
                )
            ).scalar_one()
        return {
            "tasks": tasks,
            "profile_tests": calls,
            "indexed_storage_bytes": storage,
            "billed_cost": None,
            "cost_status": "not_recorded",
            "scope": "current_workspace",
        }

    def import_legacy(self, path):
        path = Path(path).resolve()
        repo = Repository(self.db, LEGACY)
        count = 0
        pending = {}
        for pattern in ["run_*/record.json", "regressions/reg_*/task.json"]:
            for file in path.glob(pattern):
                data = json.loads(file.read_text())
                data.update(legacy_evidence_path=str(file.parent), legacy_unassigned=True)
                if data["state"] in {"queued", "running"}:
                    data["state"] = "interrupted"
                pending[data["id"]] = data
        # Import parents before reruns, independent of directory enumeration order.
        while pending:
            progressed = False
            for task_id, data in list(pending.items()):
                parent = data.get("parent")
                if parent in pending:
                    continue
                if parent:
                    try:
                        repo.task(parent, hydrate=False)
                    except ToolError:
                        data.update(legacy_missing_parent=parent, parent=None)
                try:
                    repo.task(task_id, hydrate=False)
                except ToolError:
                    kind = "regression" if task_id.startswith("reg_") else "pytest"
                    repo.put(kind, data)
                    count += 1
                del pending[task_id]
                progressed = True
            if not progressed:
                raise ToolError(
                    "INVALID_LINEAGE", "Legacy task parent cycle; source files are unchanged"
                )
        self.db.log(LEGACY, "legacy.import", "legacy", {"count": count, "source": str(path)})
        return {"imported": count, "workspace_id": LEGACY, "execution_started": False}

    def close(self):
        self.queue.close()
        self.db.dispose()
