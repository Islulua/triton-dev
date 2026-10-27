"""Durable mock-SDK Daily pipeline, real CPU pytest, SQL logs and strict quality."""

import ast
import calendar
import copy
import csv
import datetime as dt
import hashlib
import html
import io
import json
import math
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from triton_dev.common.contracts import ToolError, run_process
from triton_dev.serve.pytest_jobs import read_events
from .database import LEASE, SYSTEM, fingerprint, uid
from .repository import Repository
from . import models as m
from .daily_demo import SOURCE, CONFTEST, OPS, SIZES, SCENARIOS

STATES = ["PASS", "FAIL", "CRASH", "TIMEOUT", "SKIP", "XFAIL", "XPASS", "CANCELLED", "INCOMPLETE"]
ACTIVE = {"queued", "running"}
STEPS = ["sdk", "environment", "collect", "test", "report"]
PUBLIC_PLAN = "daily_mock_sdk"


def today():
    return dt.datetime.now(ZoneInfo("Asia/Shanghai")).date()


def date_value(value):
    try:
        result = dt.date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise ToolError("INVALID_ARGUMENT", "Use ISO date YYYY-MM-DD") from None


def summary(rows, state="completed", expected=None, elapsed=None):
    counts = {key: sum(r["status"] == key for r in rows) for key in STATES}
    n = len(rows) if expected is None else expected
    denominator = sum(counts[k] for k in ["PASS", "FAIL", "CRASH", "TIMEOUT", "XPASS"])
    finished = sum(
        counts[k] for k in ["PASS", "FAIL", "CRASH", "TIMEOUT", "XPASS", "XFAIL", "SKIP"]
    )
    quality = (
        "blue"
        if state in ACTIVE
        else "green"
        if state == "completed" and n > 0 and len(rows) == n and counts["PASS"] == n
        else "red"
    )
    return dict(
        counts=counts,
        total=n,
        strict_pass_ratio=counts["PASS"] / n if n else None,
        pass_rate=counts["PASS"] / denominator if denominator else None,
        coverage=finished / n if n else None,
        quality=quality,
        elapsed=elapsed,
        metrics_version=2,
        source="mock_sdk",
        hardware_verified=False,
    )


class DailyWorkflow:
    def __init__(self, db, queue):
        self.db, self.queue = db, queue

    def plans(self, actor):
        with self.db.tx() as c:
            return [
                dict(r)
                for r in c.execute(
                    sa.select(m.daily_plans)
                    .where(m.daily_plans.c.workspace_id.in_([SYSTEM, actor["workspace_id"]]))
                    .order_by(m.daily_plans.c.created_at)
                ).mappings()
            ]

    def plan(self, actor, plan_id):
        return next((p for p in self.plans(actor) if p["id"] == plan_id), None) or self._missing()

    @staticmethod
    def _missing():
        raise ToolError("NOT_FOUND", "Daily object not found")

    def save_plan(self, actor, data, plan_id=None):
        allowed = {"name", "scenario", "workers", "hour", "minute", "enabled", "operators"}
        if (
            not isinstance(data, dict)
            or set(data) - allowed
            or not isinstance(data.get("name"), str)
            or not 1 <= len(data["name"].strip()) <= 100
        ):
            raise ToolError(
                "INVALID_ARGUMENT", "Daily name and bounded mock configuration required"
            )
        config = dict(
            source="mock_sdk",
            suite="packaged_cpu_operators_v1",
            scenario=data.get("scenario", "mixed"),
            workers=data.get("workers", 4),
            hour=data.get("hour", 8),
            minute=data.get("minute", 0),
            timezone="Asia/Shanghai",
            operators=data.get("operators", OPS),
        )
        if (
            config["scenario"] not in SCENARIOS
            or any(type(config[k]) is not int for k in ["workers", "hour", "minute"])
            or not 1 <= config["workers"] <= 8
            or not 0 <= config["hour"] <= 23
            or not 0 <= config["minute"] <= 59
            or type(data.get("enabled", False)) is not bool
        ):
            raise ToolError("INVALID_ARGUMENT", "Invalid scenario, schedule or workers (1..8)")
        operators = config["operators"]
        if (
            not isinstance(operators, list)
            or not operators
            or not all(isinstance(op, str) for op in operators)
            or not set(operators) <= set(OPS)
            or len(set(operators)) != len(operators)
        ):
            raise ToolError(
                "INVALID_ARGUMENT", "Select a nonempty subset of registered CPU operators"
            )
        if plan_id:
            old = self.plan(actor, plan_id)
            if old["workspace_id"] != actor["workspace_id"]:
                raise ToolError(
                    "FORBIDDEN", "Public demo plan is server-owned; create a personal plan"
                )
        row = dict(
            id=plan_id or uid("plan_"),
            workspace_id=actor["workspace_id"],
            name=data["name"].strip(),
            revision=fingerprint(config),
            config=config,
            enabled=data.get("enabled", False),
            created_at=time.time(),
        )
        with self.db.tx() as c:
            if plan_id:
                c.execute(
                    m.daily_plans.update()
                    .where(
                        m.daily_plans.c.id == plan_id,
                        m.daily_plans.c.workspace_id == actor["workspace_id"],
                    )
                    .values(
                        **{
                            k: v
                            for k, v in row.items()
                            if k not in {"id", "workspace_id", "created_at"}
                        }
                    )
                )
            else:
                c.execute(m.daily_plans.insert().values(**row))
        self.db.log(
            actor["workspace_id"],
            "daily.plan.saved",
            row["id"],
            {"revision": row["revision"], "config": config},
        )
        return row

    def read(self, actor, task_id):
        with self.db.tx() as c:
            row = c.execute(
                sa.select(m.tasks.c.workspace_id).where(
                    m.tasks.c.id == task_id,
                    m.tasks.c.kind == "daily",
                    m.tasks.c.workspace_id.in_([SYSTEM, actor["workspace_id"]]),
                )
            ).first()
        if not row:
            self._missing()
        record = Repository(self.db, row[0]).task(task_id)
        if record["state"] not in ACTIVE and record.get("summary", {}).get("quality") == "blue":
            record["summary"]["quality"] = "red"
        return record

    def trigger(
        self,
        actor,
        plan_id,
        business_date=None,
        idempotency_key=None,
        scenario=None,
        source_id=None,
        scope="all",
        selected=None,
    ):
        plan = self.plan(actor, plan_id)
        date = business_date or today().isoformat()
        date_value(date)
        if date > today().isoformat():
            raise ToolError("INVALID_ARGUMENT", "Future Daily execution is not supported")
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 100:
            raise ToolError("INVALID_ARGUMENT", "idempotency_key (1..100) required")
        config = copy.deepcopy(plan["config"])
        if scenario is not None:
            if scenario not in SCENARIOS:
                raise ToolError("INVALID_ARGUMENT", "Unknown mock scenario")
            config["scenario"] = scenario
        source = self.read(actor, source_id) if source_id else None
        if source:
            if source["state"] in ACTIVE:
                raise ToolError("INVALID_STATE", "Wait until the source run stops")
            spec = copy.deepcopy(source["spec"])
            spec.update(scope=scope)
            rows = self.cases(actor, source_id, limit=100)["items"]
            if scope == "failed":
                selected = [
                    r["nodeid"]
                    for r in rows
                    if r["status"] in {"FAIL", "CRASH", "TIMEOUT", "XPASS", "INCOMPLETE"}
                ]
            elif scope == "all":
                selected = source["spec"].get("nodeids")
            elif scope != "selected":
                raise ToolError("INVALID_ARGUMENT", "scope is failed, all or selected")
            if selected is not None and (
                not isinstance(selected, list) or not all(isinstance(x, str) for x in selected)
            ):
                raise ToolError("INVALID_ARGUMENT", "Selection must contain nodeid strings")
            if scope != "all" and (
                not isinstance(selected, list)
                or not selected
                or not set(selected) <= {r["nodeid"] for r in rows}
            ):
                raise ToolError(
                    "INVALID_ARGUMENT", "Select a nonempty subset of source configurations"
                )
            if selected is not None and (
                not isinstance(selected, list)
                or not all(isinstance(x, str) for x in selected)
                or len(selected) > 32
            ):
                raise ToolError("INVALID_ARGUMENT", "Use at most 32 nodeids")
            spec["nodeids"] = selected
            # Only private parent links live in tasks.parent; public source is an explicit reference.
            date = source["business_date"]
        else:
            spec = dict(
                plan_id=plan_id,
                plan_revision=plan["revision"],
                config=config,
                scope="all",
                nodeids=None,
                sdk={
                    "id": "mock-sdk-" + date.replace("-", ""),
                    "manifest_sha256": fingerprint(["mock-sdk", date]),
                    "source": "mock_sdk",
                },
                environment={
                    "revision": fingerprint([date, SOURCE, sys.version]),
                    "python_version": sys.version.split()[0],
                    "sdk_installed": False,
                    "source": "mock_environment",
                },
                source_sha256=fingerprint([SOURCE, CONFTEST]),
            )
        record = dict(
            id=uid("day_"),
            state="queued",
            created_at=time.time(),
            business_date=date,
            job_id=plan_id,
            spec=spec,
            source_daily_batch_id=source_id,
            requested_by=actor.get("user_id", "scheduler"),
            steps=[],
            summary=summary([], state="queued"),
            source="cpu_pytest_mock_sdk",
            parent=source_id
            if source and source["workspace_id"] == actor["workspace_id"]
            else None,
        )
        signature = fingerprint(
            {"plan_id": plan_id, "date": date, "spec": spec, "source_id": source_id}
        )
        return Repository(self.db, actor["workspace_id"]).enqueue(
            "daily", record, idempotency_key, signature
        )

    def rerun(self, actor, task_id, scope, key, selected=None):
        source = self.read(actor, task_id)
        return self.trigger(
            actor,
            source["spec"]["plan_id"],
            idempotency_key=key,
            source_id=task_id,
            scope=scope,
            selected=selected,
        )

    def cancel(self, actor, task_id):
        row = self.read(actor, task_id)
        if row["workspace_id"] != actor["workspace_id"]:
            raise ToolError("FORBIDDEN", "Cannot cancel a public scheduled Daily")
        with self.db.tx() as c:
            c.execute(
                m.tasks.update()
                .where(m.tasks.c.id == task_id, m.tasks.c.workspace_id == actor["workspace_id"])
                .values(cancel_requested=True)
            )
        return {"id": task_id, "cancel_requested": True}

    @contextmanager
    def write(self, task):
        with self.db.tx() as c:
            row = (
                c.execute(
                    sa.select(m.tasks)
                    .where(
                        m.tasks.c.id == task["id"], m.tasks.c.workspace_id == task["workspace_id"]
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            lease = LEASE.get()
            if (
                lease
                and lease["id"] == task["id"]
                and (
                    row["generation"] != lease["generation"]
                    or row["worker_id"] != lease["worker_id"]
                )
            ):
                raise ToolError("STALE_LEASE", "Stale Daily worker cannot write logs or results")
            yield c

    def log(
        self,
        task,
        text,
        step="test",
        configuration_id=None,
        worker=None,
        phase=None,
        stream="event",
        level="INFO",
    ):
        # Bounded chunks; logs are DB contents, not references to filesystem paths.
        text = re.sub(
            r"(?i)(authorization\s*[:=]\s*|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*)[^\s]+",
            r"\1[REDACTED]",
            str(text),
        )
        for offset in range(0, len(text), 8192):
            chunk = text[offset : offset + 8192]
            with self.write(task) as c:
                seq = (
                    c.execute(
                        sa.select(sa.func.max(m.daily_logs.c.seq)).where(
                            m.daily_logs.c.task_id == task["id"]
                        )
                    ).scalar()
                    or 0
                ) + 1
                if seq > 10000:
                    raise ToolError(
                        "LOG_QUOTA",
                        "Daily database log quota reached; report cannot be fully green",
                    )
                c.execute(
                    m.daily_logs.insert().values(
                        task_id=task["id"],
                        workspace_id=task["workspace_id"],
                        seq=seq,
                        created_at=time.time(),
                        step=step,
                        configuration_id=configuration_id,
                        worker=worker,
                        phase=phase,
                        stream=stream,
                        level=level,
                        text=chunk,
                        sha256=hashlib.sha256(chunk.encode()).hexdigest(),
                    )
                )

    def persist_cases(self, task, rows):
        with self.write(task) as c:
            c.execute(m.daily_cases.delete().where(m.daily_cases.c.task_id == task["id"]))
            for row in rows:
                cols = {
                    k: row.get(k)
                    for k in [
                        "configuration_id",
                        "nodeid",
                        "file",
                        "operator",
                        "dtype",
                        "shape",
                        "status",
                        "worker",
                        "failure_phase",
                        "duration",
                        "started_at",
                        "ended_at",
                    ]
                }
                c.execute(
                    m.daily_cases.insert().values(
                        task_id=task["id"], workspace_id=task["workspace_id"], payload=row, **cols
                    )
                )

    def cases(
        self,
        actor,
        task_id,
        status=None,
        operator=None,
        worker=None,
        phase=None,
        dtype=None,
        search=None,
        min_duration=None,
        max_duration=None,
        cursor=None,
        limit=50,
        file=None,
    ):
        self.read(actor, task_id)
        if not 1 <= limit <= 100:
            raise ToolError("INVALID_ARGUMENT", "limit must be 1..100")
        q = sa.select(m.daily_cases).where(m.daily_cases.c.task_id == task_id)
        for col, value in [
            ("operator", operator),
            ("worker", worker),
            ("failure_phase", phase),
            ("dtype", dtype),
            ("file", file),
        ]:
            if value:
                q = q.where(m.daily_cases.c[col] == value)
        if status:
            values = status.split(",")
            if not set(values) <= set(STATES):
                raise ToolError("INVALID_ARGUMENT", "Invalid case status")
            q = q.where(m.daily_cases.c.status.in_(values))
        if search:
            q = q.where(m.daily_cases.c.nodeid.contains(search, autoescape=True))
        for bound in [min_duration, max_duration]:
            if bound is not None and (not math.isfinite(bound) or bound < 0):
                raise ToolError(
                    "INVALID_ARGUMENT", "Duration bounds must be finite and nonnegative"
                )
        if min_duration is not None:
            q = q.where(m.daily_cases.c.duration >= min_duration)
        if max_duration is not None:
            q = q.where(m.daily_cases.c.duration <= max_duration)
        if cursor:
            q = q.where(m.daily_cases.c.configuration_id > cursor)
        with self.db.tx() as c:
            rows = (
                c.execute(q.order_by(m.daily_cases.c.configuration_id).limit(limit + 1))
                .mappings()
                .all()
            )
        return {
            "items": [dict(r["payload"]) for r in rows[:limit]],
            "next_cursor": rows[limit - 1]["configuration_id"] if len(rows) > limit else None,
        }

    def logs(
        self,
        actor,
        task_id,
        after=0,
        configuration_id=None,
        worker=None,
        phase=None,
        step=None,
        search=None,
        level=None,
        limit=100,
    ):
        self.read(actor, task_id)
        if after < 0 or not 1 <= limit <= 200:
            raise ToolError("INVALID_ARGUMENT", "Invalid log cursor or limit")
        q = sa.select(m.daily_logs).where(
            m.daily_logs.c.task_id == task_id, m.daily_logs.c.seq > after
        )
        for col, value in [
            ("configuration_id", configuration_id),
            ("worker", worker),
            ("phase", phase),
            ("step", step),
            ("level", level),
        ]:
            if value:
                q = q.where(m.daily_logs.c[col] == value)
        if search:
            q = q.where(m.daily_logs.c.text.contains(search, autoescape=True))
        with self.db.tx() as c:
            rows = [
                dict(r)
                for r in c.execute(q.order_by(m.daily_logs.c.seq).limit(limit + 1)).mappings()
            ]
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["seq"] if len(rows) > limit else None,
            "last_seq": rows[min(len(rows), limit) - 1]["seq"] if rows else after,
        }

    def list(self, actor, plan_id=None, month=None, limit=100):
        if not 1 <= limit <= 100:
            raise ToolError("INVALID_ARGUMENT", "limit must be 1..100")
        q = sa.select(m.tasks).where(
            m.tasks.c.kind == "daily", m.tasks.c.workspace_id.in_([SYSTEM, actor["workspace_id"]])
        )
        if plan_id:
            self.plan(actor, plan_id)
            q = q.where(m.tasks.c.job_id == plan_id)
        if month:
            date_value(month + "-01")
            q = q.where(
                m.tasks.c.payload["business_date"].as_string().startswith(month, autoescape=True)
            )
        with self.db.tx() as c:
            rows = [
                dict(r["payload"])
                for r in c.execute(q.order_by(m.tasks.c.created_at.desc()).limit(limit)).mappings()
            ]
        for row in rows:
            if row["state"] not in ACTIVE and row.get("summary", {}).get("quality") == "blue":
                row["summary"]["quality"] = "red"
        return rows

    def calendar(self, actor, plan_id, month):
        self.plan(actor, plan_id)
        date = date_value(month + "-01")
        base = [
            m.tasks.c.kind == "daily",
            m.tasks.c.job_id == plan_id,
            m.tasks.c.workspace_id.in_([SYSTEM, actor["workspace_id"]]),
            m.tasks.c.payload["business_date"].as_string().startswith(month, autoescape=True),
        ]
        date_col = m.tasks.c.payload["business_date"].as_string()
        parent_col = m.tasks.c.payload["source_daily_batch_id"].as_string()
        with self.db.tx() as c:
            totals = {
                r[0]: (r[1], r[2])
                for r in c.execute(
                    sa.select(
                        date_col,
                        sa.func.count(),
                        sa.func.sum(sa.case((parent_col.is_not(None), 1), else_=0)),
                    )
                    .where(*base)
                    .group_by(date_col)
                )
            }
            days = []
            for day in range(1, calendar.monthrange(date.year, date.month)[1] + 1):
                stamp = f"{month}-{day:02d}"
                row = c.execute(
                    sa.select(m.tasks.c.payload)
                    .where(*base, date_col == stamp, parent_col.is_(None))
                    .order_by(
                        sa.case((m.tasks.c.workspace_id == SYSTEM, 0), else_=1),
                        m.tasks.c.created_at,
                        m.tasks.c.id,
                    )
                    .limit(1)
                ).first()
                primary = dict(row[0]) if row else None
                quality = (
                    "blue"
                    if primary and primary["state"] in ACTIVE
                    else primary["summary"]["quality"]
                    if primary
                    else "gray"
                )
                if primary and primary["state"] not in ACTIVE and quality == "blue":
                    quality = "red"
                if primary:
                    primary["summary"] = {**primary["summary"], "quality": quality}
                count, reruns = totals.get(stamp, (0, 0))
                days.append(
                    {
                        "date": stamp,
                        "quality": quality,
                        "batch_id": primary["id"] if primary else None,
                        "summary": primary.get("summary") if primary else None,
                        "source": primary.get("source") if primary else None,
                        "attempts": count,
                        "reruns": reruns,
                    }
                )
        return {
            "month": month,
            "plan_id": plan_id,
            "days": days,
            "policy": "strict_all_pass",
            "timezone": "Asia/Shanghai",
        }

    def report(self, actor, task_id):
        task = self.read(actor, task_id)
        rows = self.cases(actor, task_id, limit=100)["items"]
        operators = {
            op: summary([r for r in rows if r["operator"] == op])
            for op in sorted({r["operator"] for r in rows})
        }
        durations = sorted(r["duration"] for r in rows if r.get("duration") is not None)
        timings = {
            "p50": durations[len(durations) // 2] if durations else None,
            "p95": durations[max(0, (95 * len(durations) + 99) // 100 - 1)] if durations else None,
            "cumulative_case_seconds": sum(durations),
        }
        return {
            **task,
            "operators": operators,
            "timings": timings,
            "case_count": len(rows),
            "capabilities": {"real_sdk": False, "board": False, "live_ai": False},
            "selection": task["spec"].get("nodeids"),
            "limits": {"suite_max_configurations": 32, "log_chunks": 10000},
        }

    def export(self, actor, task_id, format="json", **filters):
        report = self.report(actor, task_id)
        rows = self.cases(actor, task_id, limit=100, **filters)["items"]
        if format == "json":
            return json.dumps(
                {"report": report, "cases": rows, "scope": "filtered" if filters else "all"},
                ensure_ascii=False,
                indent=2,
            ), "application/json"
        fields = [
            "nodeid",
            "operator",
            "dtype",
            "shape",
            "status",
            "duration",
            "worker",
            "failure_phase",
        ]
        if format == "csv":
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(fields)
            for r in rows:
                writer.writerow(
                    [
                        "'" + str(r.get(k, ""))
                        if str(r.get(k, "")).startswith(("=", "+", "-", "@"))
                        else r.get(k, "")
                        for k in fields
                    ]
                )
            return stream.getvalue(), "text/csv; charset=utf-8"
        if format != "html":
            raise ToolError("INVALID_ARGUMENT", "format must be json, csv or html")

        def esc(x):
            return html.escape(str(x))

        head = "".join("<th>" + esc(k) + "</th>" for k in fields)
        body = "".join(
            "<tr>"
            + "".join(
                "<td>"
                + (
                    '<span class="result ' + esc(r[k]) + '">' + esc(r[k]) + "</span>"
                    if k == "status"
                    else esc(r.get(k, "—"))
                )
                + "</td>"
                for k in fields
            )
            + "</tr>"
            for r in rows
        )
        return (
            '<!doctype html><meta charset="utf-8"><title>Daily report</title><style>body{font:14px system-ui;margin:32px;color:#243847}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #e4e9ed;text-align:left}.result{display:inline-block;color:white;padding:3px 7px;border-radius:4px;background:#687684}.PASS{background:#23765e}.FAIL{background:#b64448}.CRASH,.XPASS{background:#7548a4}.XFAIL,.TIMEOUT{background:#8c641f}</style><h1>'
            + esc(report["business_date"])
            + " Daily</h1><p>Mock SDK/environment · "
            + esc(report["source"])
            + " · no board validation</p><pre>"
            + esc(json.dumps(report["summary"], ensure_ascii=False, indent=2))
            + "</pre><table><thead>"
            + head
            + "</thead><tbody>"
            + body
            + "</tbody></table>",
            "text/html; charset=utf-8",
        )

    def tick(self, now=None):
        local = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("Asia/Shanghai"))
        with self.db.tx() as c:
            plans = [
                dict(r)
                for r in c.execute(
                    sa.select(m.daily_plans).where(m.daily_plans.c.enabled.is_(True))
                ).mappings()
            ]
        results = []
        for plan in plans:
            if (local.hour, local.minute) < (plan["config"]["hour"], plan["config"]["minute"]):
                continue
            actor = {"workspace_id": plan["workspace_id"]}
            results.append(
                self.trigger(
                    actor,
                    plan["id"],
                    local.date().isoformat(),
                    "scheduled:" + plan["id"] + ":" + local.date().isoformat(),
                )
            )
        return results

    def execute(self, claimed, cancel):
        repo = Repository(self.db, claimed["workspace_id"])
        task = repo.task(claimed["id"])
        task.update(state="running", started_at=time.time())
        repo.put("daily", task)
        root = repo.root / "daily" / task["id"]
        root.mkdir(parents=True, exist_ok=True)
        rows = []
        collection = []

        def step(name, action):
            if cancel.is_set():
                raise ToolError("CANCELLED", "Daily cancelled")
            item = {
                "name": name,
                "state": "running",
                "started_at": time.time(),
                "source": "mock" if name in {"sdk", "environment"} else "cpu_pytest",
            }
            task["steps"].append(item)
            task.update(phase=name)
            repo.put("daily", task)
            self.log(task, "Starting " + name, name)
            try:
                result = action()
            except Exception:
                item.update(state="failed", finished_at=time.time())
                raise
            item.update(state="passed", finished_at=time.time())
            item["elapsed"] = item["finished_at"] - item["started_at"]
            repo.put("daily", task)
            return result

        env = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "SYSTEMROOT", "LANG", "LC_ALL", "DYLD_LIBRARY_PATH"}
        }
        env.update(
            PYTHONPATH=str(Path(__file__).resolve().parents[2]),
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONNOUSERSITE="1",
            TRITON_DAILY_SCENARIO=task["spec"]["config"]["scenario"],
        )
        for key, folder in [("HOME", "home"), ("TMPDIR", "tmp"), ("XDG_CACHE_HOME", "cache")]:
            p = root / folder
            p.mkdir(exist_ok=True)
            env[key] = str(p)
        (root / "test_daily.py").write_text(SOURCE)
        (root / "conftest.py").write_text(CONFTEST)

        def process(collect=False):
            args = [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "triton_dev.pytest_plugin",
                "-q",
                "--triton-dev-collection-output",
                str(root / "collection.json"),
            ]
            if collect:
                args += ["--collect-only", "test_daily.py"]
            else:
                args += ["--triton-dev-events", str(root / "pytest-events.jsonl")]
                workers = task["spec"]["config"]["workers"]
                if workers > 1:
                    args += ["-p", "xdist.plugin", "-n", str(workers)]
                args += task["spec"].get("nodeids") or ["test_daily.py"]
            return run_process(
                args,
                cwd=root,
                env=env,
                timeout=120,
                cancel=cancel,
                on_chunk=lambda stream, text: self.log(
                    task, text, "collect" if collect else "test", stream=stream
                ),
            )

        try:
            if (
                task["spec"]["source_sha256"] != fingerprint([SOURCE, CONFTEST])
                or task["spec"]["environment"]["python_version"] != sys.version.split()[0]
            ):
                raise ToolError(
                    "SOURCE_CHANGED",
                    "Frozen Daily source/interpreter changed; do not silently rerun latest",
                )
            step(
                "sdk",
                lambda: self.log(
                    task,
                    "MOCK: frozen "
                    + task["spec"]["sdk"]["id"]
                    + "; no network/download/board access",
                    "sdk",
                ),
            )

            def environment():
                if task["spec"]["config"]["scenario"] == "build_failure":
                    raise ToolError(
                        "MOCK_BUILD_FAILED",
                        "Simulated environment preparation failure; no SDK installed",
                    )
                self.log(
                    task,
                    "MOCK environment receipt "
                    + task["spec"]["environment"]["revision"]
                    + "; CPU interpreter "
                    + sys.version.split()[0],
                    "environment",
                )

            step("environment", environment)
            collected = step("collect", lambda: process(True))
            if collected["returncode"]:
                raise ToolError("COLLECTION_FAILED", "CPU suite could not collect")
            collection = json.loads((root / "collection.json").read_text())
            if task["spec"].get("nodeids"):
                collection = [r for r in collection if r["nodeid"] in task["spec"]["nodeids"]]
            collection = [
                item
                for item in collection
                if ast.literal_eval(item["parameters"]["op"])
                in task["spec"]["config"].get("operators", OPS)
            ]
            task["spec"]["nodeids"] = [item["nodeid"] for item in collection]
            if not collection:
                raise ToolError("EMPTY_COLLECTION", "No configurations selected")
            task["collection_sha256"] = fingerprint(collection)
            task["expected_count"] = len(collection)
            task["summary"] = summary([], state="running", expected=len(collection))
            repo.put("daily", task)
            rows = [
                dict(
                    configuration_id=fingerprint(item["nodeid"])[:24],
                    nodeid=item["nodeid"],
                    file="test_daily.py",
                    operator=ast.literal_eval(item["parameters"]["op"]),
                    shape=str(ast.literal_eval(item["parameters"]["size"])),
                    dtype="fp16" if ast.literal_eval(item["parameters"]["size"]) < 1024 else "bf16",
                    status="INCOMPLETE",
                    worker=None,
                    failure_phase=None,
                    duration=None,
                    started_at=None,
                    ended_at=None,
                    parameters={k: ast.literal_eval(v) for k, v in item["parameters"].items()},
                    reason="尚未收到完整报告",
                    stages=[],
                )
                for item in collection
            ]
            self.persist_cases(task, rows)
            result = step("test", process)
            rows = []
            stages = read_events(root)
            task["returncode"] = result["returncode"]
            for item in collection:
                reports = [
                    s
                    for s in stages
                    if s.get("type") == "stage" and s.get("nodeid") == item["nodeid"]
                ]
                call = next((r for r in reports if r.get("when") == "call"), None)
                failed = [r for r in reports if r["outcome"] == "failed"]
                skipped = [r for r in reports if r["outcome"] == "skipped"]
                complete = any(r.get("when") == "teardown" for r in reports)
                status = (
                    "INCOMPLETE"
                    if not complete
                    else "FAIL"
                    if failed
                    else "XFAIL"
                    if any(r.get("wasxfail") and r["outcome"] == "skipped" for r in reports)
                    else "XPASS"
                    if call and call.get("wasxfail") and call["outcome"] == "passed"
                    else "SKIP"
                    if skipped
                    else "PASS"
                    if call and call["outcome"] == "passed"
                    else "INCOMPLETE"
                )
                params = {k: ast.literal_eval(v) for k, v in item["parameters"].items()}
                op = params["op"]
                size = params["size"]
                config = fingerprint(item["nodeid"])[:24]
                row = dict(
                    configuration_id=config,
                    nodeid=item["nodeid"],
                    file="test_daily.py",
                    operator=op,
                    shape=str(size),
                    dtype="fp16" if size < 1024 else "bf16",
                    status=status,
                    worker=reports[0]["worker_id"] if reports else None,
                    failure_phase=failed[0]["when"] if failed else None,
                    duration=sum(r["duration"] for r in reports),
                    started_at=min((r["time"] - r["duration"] for r in reports), default=None),
                    ended_at=max((r["time"] for r in reports), default=None),
                    stages=reports,
                    parameters=params,
                    reason=next((r.get("longrepr") for r in reports if r.get("longrepr")), ""),
                )
                rows.append(row)
                for stage in reports:
                    self.log(
                        task,
                        stage["outcome"]
                        + " "
                        + item["nodeid"]
                        + "\n"
                        + (stage.get("longrepr") or stage.get("stdout") or ""),
                        "test",
                        config,
                        stage.get("worker_id"),
                        stage.get("when"),
                        level="ERROR" if stage["outcome"] == "failed" else "INFO",
                    )
            self.persist_cases(task, rows)
            known = {r["nodeid"]: r["configuration_id"] for r in rows}
            for file in sorted(root.glob("worker-*.log")):
                current = None
                worker = file.stem.removeprefix("worker-")
                for line in file.read_text(errors="replace").splitlines(keepends=True):
                    if line.startswith("[start] "):
                        current = known.get(line[len("[start] ") :].strip())
                    self.log(task, line, "test", current, worker, stream="worker_log")
            if list(root.glob("worker-*.truncated")):
                raise ToolError("LOG_INCOMPLETE", "Worker log retention limit reached")
            if result["returncode"] not in (0, 1):
                raise ToolError("PYTEST_EXECUTION_ERROR", "Unexpected pytest process status")
            step(
                "report",
                lambda: self.log(
                    task, "Results and case-associated logs persisted to database", "report"
                ),
            )
            task.update(state="completed", finished_at=time.time())
        except Exception as exc:
            if isinstance(exc, ToolError) and exc.code == "STALE_LEASE":
                raise
            task.update(
                state="cancelled" if getattr(exc, "code", None) == "CANCELLED" else "error",
                error={"code": getattr(exc, "code", "DAILY_ERROR"), "message": str(exc)},
                finished_at=time.time(),
            )
            self.log(task, str(exc), task.get("phase", "report"), level="ERROR")
        task["summary"] = summary(
            rows,
            task["state"],
            task.get("expected_count"),
            task["finished_at"] - task["started_at"],
        )
        task["summary"]["tests_elapsed"] = next(
            (s.get("elapsed") for s in task["steps"] if s["name"] == "test"), None
        )
        repo.put("daily", task)

    def seed_demo(self):
        """Historical samples are explicit generated data, never labelled as executed tests."""
        with self.db.tx() as c:
            if not c.execute(
                sa.select(m.daily_plans.c.id).where(m.daily_plans.c.id == PUBLIC_PLAN)
            ).first():
                config = {
                    "source": "mock_sdk",
                    "suite": "packaged_cpu_operators_v1",
                    "scenario": "mixed",
                    "workers": 4,
                    "hour": 8,
                    "minute": 0,
                    "timezone": "Asia/Shanghai",
                }
                try:
                    c.execute(
                        m.daily_plans.insert().values(
                            id=PUBLIC_PLAN,
                            workspace_id=SYSTEM,
                            name="Mock SDK Daily",
                            revision=fingerprint(config),
                            config=config,
                            enabled=False,
                            created_at=time.time(),
                        )
                    )
                except IntegrityError:
                    pass
        actor = {"workspace_id": SYSTEM}
        plan = self.plan(actor, PUBLIC_PLAN)
        repo = Repository(self.db, SYSTEM)
        date = today()
        for day in range(1, date.day):
            stamp = date.replace(day=day).isoformat()
            task_id = "day_demo_" + stamp.replace("-", "")
            with self.db.tx() as c:
                if c.execute(sa.select(m.tasks.c.id).where(m.tasks.c.id == task_id)).first():
                    continue
            scenario = (
                "build_failure"
                if day % 11 == 0
                else "xfail_only"
                if day % 5 == 0
                else "mixed"
                if day % 3 == 0
                else "all_pass"
            )
            config = {**plan["config"], "scenario": scenario}
            start = dt.datetime(
                date.year, date.month, day, 8, tzinfo=ZoneInfo("Asia/Shanghai")
            ).timestamp()
            task = dict(
                id=task_id,
                state="completed" if scenario != "build_failure" else "error",
                created_at=start,
                started_at=start,
                finished_at=start + 120,
                business_date=stamp,
                job_id=PUBLIC_PLAN,
                source="mock_history",
                workspace_id=SYSTEM,
                steps=[
                    {"name": s, "state": "passed", "elapsed": 20, "source": "mock_history"}
                    for s in STEPS
                ],
                spec={
                    "plan_id": PUBLIC_PLAN,
                    "plan_revision": plan["revision"],
                    "scope": "all",
                    "nodeids": None,
                    "config": config,
                    "sdk": {
                        "id": "mock-sdk-" + stamp.replace("-", ""),
                        "manifest_sha256": fingerprint(stamp),
                        "source": "mock_sdk",
                    },
                    "environment": {
                        "revision": fingerprint([stamp, SOURCE, sys.version]),
                        "python_version": sys.version.split()[0],
                        "sdk_installed": False,
                        "source": "mock_environment",
                    },
                    "source_sha256": fingerprint([SOURCE, CONFTEST]),
                },
            )
            rows = []
            if scenario != "build_failure":
                for op in OPS:
                    for size in SIZES:
                        node = f"test_daily.py::test_operator[{size}-{op}]"
                        status = "PASS"
                        if scenario != "all_pass" and op == "reduce" and size == 128:
                            status = "XFAIL"
                        if scenario == "mixed":
                            if op == "matmul" and size == 512:
                                status = "FAIL"
                            if op == "transpose" and size == 64:
                                status = "SKIP"
                            if op == "softmax" and size == 256:
                                status = "XPASS"
                        rows.append(
                            dict(
                                configuration_id=fingerprint(node)[:24],
                                nodeid=node,
                                file="test_daily.py",
                                operator=op,
                                dtype="fp16" if size < 1024 else "bf16",
                                shape=str(size),
                                status=status,
                                worker="gw" + str(SIZES.index(size) % 4),
                                failure_phase="call" if status == "FAIL" else None,
                                duration=0.01 + size / 100000,
                                started_at=start + 40,
                                ended_at=start + 41,
                                parameters={"op": op, "size": size},
                                reason="演示历史样例；未执行pytest或板卡测试",
                                stages=[],
                            )
                        )
            else:
                task.update(
                    error={"code": "MOCK_BUILD_FAILED", "message": "演示环境构建失败"},
                    steps=[
                        {"name": "sdk", "state": "passed", "elapsed": 20, "source": "mock_history"},
                        {
                            "name": "environment",
                            "state": "failed",
                            "elapsed": 10,
                            "source": "mock_history",
                        },
                    ],
                )
            task["summary"] = summary(rows, task["state"], elapsed=120)
            task["summary"]["tests_elapsed"] = 60 if rows else None
            repo.put("daily", task)
            self.persist_cases(task, rows)
            self.log(task, "演示历史：模拟SDK和环境，未实际执行pytest或设备测试", "sdk")
            for row in rows:
                self.log(
                    task,
                    f"演示历史 {row['status']} {row['nodeid']}；非实际执行日志",
                    "test",
                    row["configuration_id"],
                    row["worker"],
                    "call",
                    level="ERROR" if row["status"] == "FAIL" else "INFO",
                )
