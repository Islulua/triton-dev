"""Workspace-scoped SQL state, normalized query indexes and owned content-addressed blobs."""

import copy
import hashlib
import json
import os
import time
import math

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from triton_dev.common.contracts import ToolError
from . import models as m
from .database import uid, fingerprint, LEASE


class Repository:
    def __init__(self, db, workspace):
        self.db, self.workspace = db, workspace
        self.root = db.root / "workspaces" / workspace
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def task(self, task_id, hydrate=True):
        with self.db.tx() as c:
            row = (
                c.execute(
                    sa.select(m.tasks).where(
                        m.tasks.c.id == task_id, m.tasks.c.workspace_id == self.workspace
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise ToolError("NOT_FOUND", "Task not found in current workspace")
        value = copy.deepcopy(row["payload"])
        return self._hydrate(value) if hydrate else value

    def _hydrate(self, value):
        if isinstance(value, dict):
            if set(value) == {"__blob_text__"}:
                return self.blob(value["__blob_text__"])[0].decode("utf-8", errors="replace")
            return {k: self._hydrate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._hydrate(v) for v in value]
        return value

    def _externalize(self, value, task_id):
        if isinstance(value, dict):
            return {
                k: self.put_blob(v.encode(), task_id, k + ".txt", text=True)
                if isinstance(v, str) and (k in {"stdout", "stderr", "longrepr"} and len(v) > 2000)
                else self._externalize(v, task_id)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._externalize(v, task_id) for v in value]
        return value

    def put_blob(self, data, task_id, name, text=False):
        digest = hashlib.sha256(data).hexdigest()
        # Workspace-prefixed physical objects avoid cross-workspace existence leaks.
        key = f"blobs/{self.workspace}/{digest[:2]}/{digest}"
        path = self.db.root / key
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            temp = path.with_name(path.name + "." + uid() + ".tmp")
            temp.write_bytes(data)
            os.chmod(temp, 0o600)
            os.replace(temp, path)
        blob_id = fingerprint([self.workspace, task_id, name, digest])
        with self.db.tx() as c:
            if not c.execute(sa.select(m.blobs.c.id).where(m.blobs.c.id == blob_id)).first():
                c.execute(
                    m.blobs.insert().values(
                        id=blob_id,
                        workspace_id=self.workspace,
                        task_id=task_id,
                        sha256=digest,
                        size=len(data),
                        storage_key=key,
                        name=name,
                        created_at=time.time(),
                    )
                )
        return {"__blob_text__": blob_id} if text else blob_id

    def blob(self, blob_id):
        with self.db.tx() as c:
            row = (
                c.execute(
                    sa.select(m.blobs).where(
                        m.blobs.c.id == blob_id, m.blobs.c.workspace_id == self.workspace
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise ToolError("NOT_FOUND", "Artifact not found")
        path = self.db.root / row["storage_key"]
        if not path.is_file():
            raise ToolError("ARTIFACT_MISSING", "Indexed artifact file is missing")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ToolError("ARTIFACT_CORRUPT", "Artifact hash mismatch")
        return data, dict(row)

    def put(self, kind, value, *, key=None, request_digest=None, enqueue=False):
        value = copy.deepcopy(value)
        value["workspace_id"] = self.workspace
        payload = self._externalize(value, value["id"])
        now = time.time()
        lease = LEASE.get()
        with self.db.tx() as c:
            query = (
                sa.select(m.tasks)
                .where(m.tasks.c.id == value["id"], m.tasks.c.workspace_id == self.workspace)
                .with_for_update()
            )
            old = c.execute(query).mappings().first()
            if old:
                if (
                    lease
                    and lease["id"] == value["id"]
                    and (
                        old["generation"] != lease["generation"]
                        or old["worker_id"] != lease["worker_id"]
                    )
                ):
                    raise ToolError("STALE_LEASE", "Old worker cannot update this task")
                c.execute(
                    m.tasks.update()
                    .where(m.tasks.c.id == value["id"], m.tasks.c.workspace_id == self.workspace)
                    .values(
                        payload=payload,
                        state=value["state"],
                        phase=value.get("phase"),
                        updated_at=now,
                    )
                )
            else:
                if c.execute(sa.select(m.tasks.c.id).where(m.tasks.c.id == value["id"])).first():
                    raise ToolError("NOT_FOUND", "Task not found")
                if enqueue:
                    if self.db.engine.dialect.name == "postgresql":
                        c.execute(sa.text("SELECT pg_advisory_xact_lock(81724102)"))
                    c.execute(
                        sa.select(m.workspaces.c.id)
                        .where(m.workspaces.c.id == self.workspace)
                        .with_for_update()
                    ).scalar_one()
                    queued = c.execute(
                        sa.select(sa.func.count())
                        .select_from(m.tasks)
                        .where(
                            m.tasks.c.workspace_id == self.workspace,
                            m.tasks.c.queue_state.in_(["queued", "leased"]),
                        )
                    ).scalar_one()
                    total = c.execute(
                        sa.select(sa.func.count())
                        .select_from(m.tasks)
                        .where(m.tasks.c.queue_state.in_(["queued", "leased"]))
                    ).scalar_one()
                    if queued >= 20 or total >= 200:
                        raise ToolError(
                            "TASK_QUOTA",
                            "Queue budget: 20 active/queued per workspace, 200 globally",
                        )
                c.execute(
                    m.tasks.insert().values(
                        id=value["id"],
                        workspace_id=self.workspace,
                        kind=kind,
                        state=value["state"],
                        phase=value.get("phase"),
                        created_at=value.get("created_at", now),
                        updated_at=now,
                        job_id=value.get("job_id"),
                        parent_id=value.get("parent"),
                        payload=payload,
                        profile_revision_id=value.get("ai_profile_revision_id"),
                        idempotency_key=key,
                        request_digest=request_digest,
                        queue_state="queued" if enqueue else "none",
                        generation=0,
                        cancel_requested=False,
                    )
                )
            seq = (
                c.execute(
                    sa.select(sa.func.max(m.events.c.seq)).where(m.events.c.task_id == value["id"])
                ).scalar()
                or 0
            )
            c.execute(
                m.events.insert().values(
                    task_id=value["id"],
                    seq=seq + 1,
                    kind=value.get("phase", value["state"]),
                    created_at=now,
                    payload={"state": value["state"], "phase": value.get("phase")},
                )
            )
            if kind == "regression":
                c.execute(
                    m.experiments.delete().where(
                        m.experiments.c.task_id == value["id"],
                        m.experiments.c.workspace_id == self.workspace,
                    )
                )
                for e in value.get("experiments", []):
                    c.execute(
                        m.experiments.insert().values(
                            id=fingerprint([value["id"], e["id"]]),
                            task_id=value["id"],
                            workspace_id=self.workspace,
                            label=e["label"],
                            classification=e["classification"],
                            payload=e,
                        )
                    )
        return value

    def enqueue(self, kind, value, key, signature):
        def existing():
            with self.db.tx() as c:
                return (
                    c.execute(
                        sa.select(m.tasks).where(
                            m.tasks.c.workspace_id == self.workspace,
                            m.tasks.c.kind == kind,
                            m.tasks.c.idempotency_key == key,
                        )
                    )
                    .mappings()
                    .first()
                )

        row = existing()
        if row:
            if row["request_digest"] != signature:
                raise ToolError("IDEMPOTENCY_CONFLICT", "Key already used with different inputs")
            return self.task(row["id"])
        try:
            return self.put(kind, value, key=key, request_digest=signature, enqueue=True)
        except (IntegrityError, ToolError) as exc:
            row = existing()
            if not row:
                raise
            if row["request_digest"] != signature:
                raise ToolError(
                    "IDEMPOTENCY_CONFLICT", "Key already used with different inputs"
                ) from exc
            return self.task(row["id"])

    def query(self, kind=None, state=None, limit=50, cursor=None, job_id=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ToolError("INVALID_ARGUMENT", "limit must be 1..100")
        query = sa.select(m.tasks).where(m.tasks.c.workspace_id == self.workspace)
        if kind:
            query = query.where(m.tasks.c.kind == kind)
        if state:
            query = query.where(m.tasks.c.state == state)
        if job_id:
            query = query.where(m.tasks.c.job_id == job_id)
        if cursor:
            try:
                stamp, task_id = json.loads(bytes.fromhex(cursor).decode())
                if (
                    type(stamp) not in (int, float)
                    or not math.isfinite(stamp)
                    or not isinstance(task_id, str)
                    or len(task_id) > 64
                ):
                    raise ValueError("Invalid cursor types")
            except (ValueError, TypeError):
                raise ToolError("INVALID_CURSOR", "Invalid cursor") from None
            query = query.where(
                sa.or_(
                    m.tasks.c.created_at < stamp,
                    sa.and_(m.tasks.c.created_at == stamp, m.tasks.c.id < task_id),
                )
            )
        with self.db.tx() as c:
            rows = (
                c.execute(
                    query.order_by(m.tasks.c.created_at.desc(), m.tasks.c.id.desc()).limit(
                        limit + 1
                    )
                )
                .mappings()
                .all()
            )
        items = []
        for row in rows[:limit]:
            payload = copy.deepcopy(row["payload"])
            outcome = payload.pop("result", None)
            items.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "state": row["state"],
                    "created_at": row["created_at"],
                    "job_id": row["job_id"],
                    "phase": row["phase"],
                    "summary": payload.get("summary"),
                    "outcome": outcome if isinstance(outcome, str) else None,
                }
            )
        next_cursor = (
            json.dumps([rows[limit - 1]["created_at"], rows[limit - 1]["id"]]).encode().hex()
            if len(rows) > limit
            else None
        )
        return {"items": items, "next_cursor": next_cursor}

    def records(self, kind=None):
        # Compatibility for current UI; bounded. New clients use paginated query.
        result = self.query(kind=kind, limit=100)
        return [self.task(row["id"]) for row in reversed(result["items"])]

    def events(self, task_id, after=0):
        self.task(task_id, hydrate=False)
        with self.db.tx() as c:
            rows = (
                c.execute(
                    sa.select(m.events)
                    .where(m.events.c.task_id == task_id, m.events.c.seq > after)
                    .order_by(m.events.c.seq)
                    .limit(500)
                )
                .mappings()
                .all()
            )
        return [
            {"id": r["seq"], "type": r["kind"], "time": r["created_at"], **r["payload"]}
            for r in rows
        ]

    def normalize_results(self, record):
        task_id = record["id"]
        self.task(task_id, hydrate=False)
        with self.db.tx() as c:
            c.execute(
                m.stage_results.delete().where(
                    m.stage_results.c.task_id == task_id,
                    m.stage_results.c.workspace_id == self.workspace,
                )
            )
            for row in record.get("test_results", []):
                for stage in row.get("stages", []):
                    c.execute(
                        m.stage_results.insert().values(
                            id=fingerprint(
                                [
                                    task_id,
                                    row["nodeid"],
                                    stage.get("when"),
                                    stage.get("time"),
                                    stage.get("worker_id"),
                                ]
                            ),
                            workspace_id=self.workspace,
                            task_id=task_id,
                            nodeid=row["nodeid"],
                            phase=stage.get("when"),
                            outcome=stage.get("outcome"),
                            duration=stage.get("duration"),
                            worker_id=stage.get("worker_id"),
                        )
                    )

        with self.db.tx() as c:
            c.execute(
                m.case_results.delete().where(
                    m.case_results.c.task_id == task_id,
                    m.case_results.c.workspace_id == self.workspace,
                )
            )
            for row in record.get("test_results", []):
                case_key = fingerprint([record.get("job_id"), row["nodeid"]])
                failures = [
                    (s.get("when"), s.get("outcome"), (s.get("longrepr") or "")[:500])
                    for s in row.get("stages", [])
                    if s.get("outcome") == "failed"
                ]
                c.execute(
                    m.case_results.insert().values(
                        id=fingerprint([task_id, row["nodeid"]]),
                        workspace_id=self.workspace,
                        task_id=task_id,
                        nodeid=row["nodeid"],
                        case_key=case_key,
                        outcome=row["outcome"],
                        duration=row.get("duration"),
                        failure_phase=row.get("failure_phase"),
                        finished_at=record.get("finished_at"),
                        failure_fingerprint=fingerprint([row.get("failure_phase"), failures]),
                        payload={
                            "worker_ids": list(
                                {
                                    s.get("worker_id")
                                    for s in row.get("stages", [])
                                    if s.get("worker_id")
                                }
                            )
                        },
                    )
                )

    def result_query(self, nodeid=None, outcome=None, limit=50):
        if not 1 <= limit <= 100:
            raise ToolError("INVALID_ARGUMENT", "limit must be 1..100")
        q = sa.select(m.case_results).where(m.case_results.c.workspace_id == self.workspace)
        if nodeid:
            q = q.where(m.case_results.c.nodeid == nodeid)
        if outcome:
            q = q.where(m.case_results.c.outcome == outcome)
        with self.db.tx() as c:
            return [
                dict(r)
                for r in c.execute(
                    q.order_by(m.case_results.c.finished_at.desc()).limit(limit)
                ).mappings()
            ]


class DatabaseRunStore:
    def __init__(self, repository):
        self.repo = repository
        self.root = repository.root / "runs"
        self.root.mkdir(exist_ok=True, mode=0o700)

    def directory(self, run_id):
        self.repo.task(run_id, hydrate=False)
        path = self.root / run_id
        path.mkdir(exist_ok=True, mode=0o700)
        return path

    def create(self, request, parent=None):
        if parent:
            self.repo.task(parent, hydrate=False)
        run_id = uid("run_")
        self.repo.put(
            "pytest",
            dict(
                schema_version=1,
                id=run_id,
                state="queued",
                created_at=time.time(),
                request=request,
                parent=parent,
                result=None,
                stages=[],
            ),
        )
        self.directory(run_id)
        return run_id

    def read(self, run_id):
        return self.repo.task(run_id)

    def update(self, run_id, **values):
        record = self.read(run_id)
        record.update(values)
        return self.repo.put("pytest", record)

    def list(self):
        return self.repo.records("pytest")

    def event(self, run_id, kind):
        record = self.read(run_id)
        # put persists event/checkpoint in one transaction.
        return self.repo.put("pytest", record)

    def events(self, run_id, after=0):
        return self.repo.events(run_id, after)
