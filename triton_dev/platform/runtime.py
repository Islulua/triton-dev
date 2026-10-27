"""Database-owned task lifecycle, per-workspace adapters and a persistent global queue."""

import copy
import os
import socket
import threading
import time
from pathlib import Path

import sqlalchemy as sa
from triton_dev.common.contracts import ToolError
from triton_dev.serve.tasks import TaskManager
from triton_dev.agent.regression.service import RegressionService, validate
from triton_dev.agent.regression.adapters import CASE_SOURCE, PLUGIN_SOURCE, digest
from . import models as m
from .database import uid, fingerprint, LEASE
from .repository import Repository, DatabaseRunStore


class SQLRegression(RegressionService):
    def __init__(self, repository):
        self.repo = repository
        self.root = repository.root / "regressions"
        self.root.mkdir(exist_ok=True, mode=0o700)

    def read(self, task_id):
        self._dir(task_id)  # Validate generated task ID, never a filesystem input.
        value = self.repo.task(task_id)
        if value.get("platform_kind") != "regression":
            raise ToolError("NOT_FOUND", "Regression task not found")
        return value

    def list(self):
        return list(reversed(self.repo.records("regression")))

    def _persist(self, state):
        self.repo.put("regression", state)
        # Exported checkpoint is evidence; the database remains the state authority.
        super()._persist(state)

    def start(self, data, *, idempotency_key=None, background=True, profile_revision=None):
        import re
        import sys

        spec = validate(data)
        key = idempotency_key or uid()
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key):
            raise ToolError("INVALID_ARGUMENT", "Invalid idempotency key")
        task_id = uid("reg_")
        state = dict(
            schema_version=1,
            id=task_id,
            platform_kind="regression",
            state="queued",
            phase="created",
            result=None,
            source="mock_sdk_real_cpu_pytest",
            ai_profile_revision_id=profile_revision,
            spec=spec,
            created_at=time.time(),
            idempotency_key=key,
            controller_pid=os.getpid(),
            revision=0,
            elapsed_seconds=0,
            experiments=[],
            decisions=[],
            events=[],
            model_calls=0,
            inventory=[],
            boundary=None,
            attribution=[],
            earliest_proven=False,
            pending=None,
            limitations=["Mock SDK/model, real CPU pytest; no board/native verification"],
            scenario_sha256=digest(CASE_SOURCE),
            plugin_sha256=digest(PLUGIN_SOURCE),
            runtime={"python": sys.version, "executable": sys.executable},
        )
        self._dir(task_id).mkdir(parents=True, exist_ok=True, mode=0o700)
        result = self.repo.enqueue(
            "regression",
            state,
            key,
            fingerprint({"spec": spec, "profile_revision": profile_revision}),
        )
        return result

    def close(self):
        pass


class ScopedManager(TaskManager):
    def __init__(self, repository, jobs):
        self.repo = repository
        self.store = DatabaseRunStore(repository)
        self.jobs = copy.deepcopy(jobs)
        self.regressions = SQLRegression(repository)
        self.closed = False

    def read(self, run_id):
        record = self.repo.task(run_id)
        if record.get("request", {}).get("kind") == "pytest":
            from triton_dev.serve.pytest_jobs import view

            return view(self.store, record)
        return record

    def _enqueue(self, job_id, idempotency_key, request, parent=None):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise ToolError("INVALID_ARGUMENT", "Idempotency key required")
        if parent:
            self.repo.task(parent, hydrate=False)
        request = copy.deepcopy(request)
        request["private_environment"] = True
        run_id = uid("run_")
        state = dict(
            schema_version=1,
            id=run_id,
            state="queued",
            created_at=time.time(),
            request=request,
            parent=parent,
            result=None,
            stages=[],
            job_id=job_id,
        )
        result = self.repo.enqueue(
            "pytest",
            state,
            idempotency_key,
            fingerprint({"job_id": job_id, "request": request, "parent": parent}),
        )
        self.store.directory(result["id"])
        return result

    def cancel(self, run_id):
        self.repo.task(run_id, hydrate=False)
        with self.repo.db.tx() as c:
            c.execute(
                m.tasks.update()
                .where(m.tasks.c.id == run_id, m.tasks.c.workspace_id == self.repo.workspace)
                .values(cancel_requested=True)
            )
        return self.read(run_id)

    def close(self):
        pass


class Cancel:
    def __init__(self, queue, task, generation):
        self.queue, self.task, self.generation = queue, task, generation
        self.checked = 0
        self.value = False

    def is_set(self):
        if self.queue.stop.is_set():
            return True
        if time.monotonic() - self.checked < 0.15:
            return self.value
        self.checked = time.monotonic()
        with self.queue.db.tx() as c:
            row = c.execute(
                sa.select(m.tasks.c.cancel_requested, m.tasks.c.generation).where(
                    m.tasks.c.id == self.task
                )
            ).first()
        self.value = not row or row.cancel_requested or row.generation != self.generation
        return self.value


class Queue:
    def __init__(self, db, jobs, start_worker=True):
        self.db, self.jobs = db, copy.deepcopy(jobs)
        # Validate trusted registry with the existing validator, in a separate temporary scope.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            validator = TaskManager(Path(tmp), jobs)
            validator.close()
        self.stop = threading.Event()
        self.last_error = None
        self.worker_id = uid("worker_")
        self.host = socket.gethostname()
        self.thread = threading.Thread(target=self.loop, name="platform-worker", daemon=True)
        if start_worker:
            self.thread.start()

    def manager(self, workspace):
        return ScopedManager(Repository(self.db, workspace), self.jobs)

    def claim(self):
        now = time.time()
        with self.db.tx() as c:
            if self.db.engine.dialect.name == "sqlite":
                # SQLite's dev adapter serializes its claim transaction.
                c.exec_driver_sql("UPDATE tasks SET generation=generation WHERE 1=0")
            row = (
                c.execute(
                    sa.select(m.tasks)
                    .where(m.tasks.c.queue_state == "queued")
                    .order_by(m.tasks.c.created_at, m.tasks.c.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            generation = row["generation"] + 1
            changed = c.execute(
                m.tasks.update()
                .where(
                    m.tasks.c.id == row["id"],
                    m.tasks.c.queue_state == "queued",
                    m.tasks.c.generation == row["generation"],
                )
                .values(
                    queue_state="leased",
                    generation=generation,
                    worker_id=self.worker_id,
                    worker_pid=os.getpid(),
                    worker_host=self.host,
                    lease_until=now + 30,
                )
            )
            return (
                dict(row, generation=generation, worker_id=self.worker_id)
                if changed.rowcount
                else None
            )

    def reconcile(self):
        with self.db.tx() as c:
            expired = (
                c.execute(
                    sa.select(m.tasks)
                    .where(m.tasks.c.queue_state == "leased", m.tasks.c.lease_until < time.time())
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            for row in expired:
                payload = copy.deepcopy(row["payload"])
                payload.update(
                    state="interrupted", recovery_reason="lease_expired_requires_reconciliation"
                )
                c.execute(
                    m.tasks.update()
                    .where(m.tasks.c.id == row["id"], m.tasks.c.generation == row["generation"])
                    .values(
                        queue_state="reconcile_required",
                        state="interrupted",
                        payload=payload,
                        generation=row["generation"] + 1,
                    )
                )

    def resume(self, workspace, task_id):
        repo = Repository(self.db, workspace)
        record = repo.task(task_id)
        with self.db.tx() as c:
            row = (
                c.execute(
                    sa.select(m.tasks)
                    .where(m.tasks.c.id == task_id, m.tasks.c.workspace_id == workspace)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["state"] in {"queued", "running", "completed", "passed"}:
                raise ToolError("INVALID_STATE", "Task cannot resume")
            if row["queue_state"] == "reconcile_required":
                alive = True
                if row["worker_host"] == self.host:
                    try:
                        os.kill(row["worker_pid"], 0)
                    except ProcessLookupError:
                        alive = False
                if alive:
                    raise ToolError(
                        "RECONCILIATION_REQUIRED",
                        "Old worker may still be running; reconcile before resume",
                    )
            if row["kind"] != "regression":
                raise ToolError(
                    "UNSUPPORTED", "Use an explicit pytest rerun to preserve original results"
                )
            record.update(state="queued", controller_pid=os.getpid())
            c.execute(
                m.tasks.update()
                .where(m.tasks.c.id == task_id, m.tasks.c.workspace_id == workspace)
                .values(
                    state="queued",
                    payload=record,
                    queue_state="queued",
                    cancel_requested=False,
                    worker_id=None,
                    lease_until=None,
                )
            )
        (repo.root / "regressions" / task_id / "cancel.json").unlink(missing_ok=True)
        return record

    def execute(self, row):
        task_id = row["id"]
        generation = row["generation"]
        cancel = Cancel(self, task_id, generation)
        ended = threading.Event()

        def heartbeat():
            while not ended.wait(3):
                try:
                    with self.db.tx() as c:
                        c.execute(
                            m.tasks.update()
                            .where(
                                m.tasks.c.id == task_id,
                                m.tasks.c.worker_id == self.worker_id,
                                m.tasks.c.generation == generation,
                            )
                            .values(lease_until=time.time() + 30)
                        )
                except Exception:
                    cancel.value = True

        pulse = threading.Thread(target=heartbeat, daemon=True)
        pulse.start()
        token = LEASE.set({"id": task_id, "generation": generation, "worker_id": self.worker_id})
        manager = self.manager(row["workspace_id"])
        try:
            if row["kind"] == "regression":
                manager.regressions._run(task_id, cancel)
            elif row["kind"] == "pytest":
                manager._run(task_id, cancel)
                final = manager.read(task_id)
                manager.repo.normalize_results(final)
                manager.repo.put("pytest", final)
            else:
                raise ToolError("UNSUPPORTED", "Unknown queue task kind")
        except Exception as exc:
            record = manager.repo.task(task_id)
            record.update(
                state="error",
                error={"code": getattr(exc, "code", "EXECUTION_ERROR"), "message": str(exc)},
            )
            manager.repo.put(row["kind"], record)
        finally:
            ended.set()
            pulse.join(timeout=5)
            LEASE.reset(token)
            with self.db.tx() as c:
                c.execute(
                    m.tasks.update()
                    .where(
                        m.tasks.c.id == task_id,
                        m.tasks.c.worker_id == self.worker_id,
                        m.tasks.c.generation == generation,
                    )
                    .values(queue_state="done", lease_until=None)
                )

    def loop(self):
        while not self.stop.is_set():
            try:
                self.reconcile()
                task = self.claim()
                if task:
                    self.execute(task)
                else:
                    self.stop.wait(0.15)
            except Exception as exc:
                self.last_error = {
                    "code": getattr(exc, "code", "QUEUE_STEP_ERROR"),
                    "time": time.time(),
                }
                # Never restart a possibly active experiment automatically.
                self.stop.wait(0.5)

    def close(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=45)
        if self.thread.is_alive():
            raise ToolError("WORKER_BUSY", "Worker shutdown did not finish")
