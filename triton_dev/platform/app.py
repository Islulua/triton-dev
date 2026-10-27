"""ASGI transport for name-only workspaces. Legacy Bearer routes never bypass sessions."""

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, FileResponse
from sqlalchemy.exc import IntegrityError

from triton_dev.common.contracts import ToolError, envelope
from triton_dev.execution.options import describe_extensions
from triton_dev.serve.profiling import (
    ProfileStore,
    catalog as profile_catalog,
    chrome_trace,
    html_report,
)
from .service import Platform
from .repository import Repository


def create_app(
    platform: Platform,
    capabilities=None,
    ui_root=None,
    allowed_hosts=("127.0.0.1", "localhost", "testserver"),
    secure_cookie=False,
):
    root = Path(ui_root).resolve() if ui_root else None
    if root and not (root / "index.html").is_file():
        raise ToolError("UI_NOT_BUILT", "Build the frontend first")

    @asynccontextmanager
    async def lifespan(app):
        stopped = threading.Event()

        def daily_loop():
            while not stopped.wait(30):
                try:
                    for tick in (platform.daily.tick, platform.daily_v2.tick):
                        try:
                            tick()
                        except Exception as exc:
                            app.state.daily_error = {
                                "code": getattr(exc, "code", "DAILY_SCHEDULER_ERROR")
                            }

                except Exception:
                    pass

        thread = threading.Thread(target=daily_loop, daemon=True)
        thread.start()
        yield
        stopped.set()
        thread.join(timeout=5)
        platform.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.platform = platform

    @app.middleware("http")
    async def boundaries(request, call_next):
        host = request.url.hostname
        origin = request.headers.get("origin")
        valid_origin = not origin or (
            urlsplit(origin).netloc == request.headers.get("host")
            and urlsplit(origin).scheme in {"http", "https"}
        )
        if host not in allowed_hosts or not valid_origin:
            return JSONResponse(
                envelope(error=ToolError("ORIGIN_REJECTED", "Use a configured same-origin host")),
                403,
            )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                length = 0
            if (
                not 0 < length <= 65536
                or request.headers.get("content-type", "").split(";")[0] != "application/json"
            ):
                return JSONResponse(
                    envelope(error=ToolError("INVALID_ARGUMENT", "Bounded JSON body required")), 400
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.exception_handler(ToolError)
    async def tool_error(request, exc):
        status = {
            "UNAUTHORIZED": 401,
            "CSRF_REJECTED": 403,
            "NOT_FOUND": 404,
            "IDEMPOTENCY_CONFLICT": 409,
            "INVALID_STATE": 409,
            "RECONCILIATION_REQUIRED": 409,
        }.get(exc.code, 400)
        return JSONResponse(envelope(error=exc), status)

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse(
            envelope(
                error=ToolError("CONFLICT", "An object with the same name or key already exists")
            ),
            409,
        )

    def actor(request, write=False):
        return platform.auth.actor(
            request.cookies.get("td_session"), request.headers.get("x-csrf-token"), write
        )

    async def body(request, fields=None):
        try:
            value = await request.json()
        except (ValueError, UnicodeError):
            raise ToolError("INVALID_ARGUMENT", "JSON object required") from None
        if not isinstance(value, dict) or (fields is not None and set(value) != set(fields)):
            raise ToolError("INVALID_ARGUMENT", "Unexpected or missing request fields")
        return value

    def ok(value):
        return envelope(value)

    from .daily_api import register_daily

    register_daily(app, platform, actor, body, ok)

    @app.get("/api/capabilities")
    def cap():
        return ok(
            {
                "platform": {
                    "mode": "multi-user",
                    "database": platform.db.engine.dialect.name,
                    "auth": "name-only",
                    "live_ai": False,
                },
                "commands": capabilities or {},
            }
        )

    @app.post("/api/sessions")
    async def login(request: Request):
        data = await body(request, ["name"])
        user, token = platform.auth.login(data["name"])
        response = JSONResponse(ok(user))
        response.set_cookie(
            "td_session",
            token,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            max_age=86400,
        )
        response.set_cookie(
            "td_csrf",
            user["csrf_token"],
            httponly=False,
            secure=secure_cookie,
            samesite="strict",
            max_age=86400,
        )
        return response

    @app.get("/api/me")
    def me(request: Request):
        return ok(actor(request) | {"csrf_token": request.cookies.get("td_csrf", "")})

    @app.delete("/api/session")
    async def logout(request: Request):
        actor(request, True)
        await body(request, [])
        platform.auth.logout(request.cookies["td_session"])
        response = JSONResponse(ok({"logged_out": True}))
        response.delete_cookie("td_session")
        response.delete_cookie("td_csrf")
        return response

    @app.get("/api/me/ai-profiles")
    def profiles(request: Request):
        return ok(platform.profiles.list(actor(request)["workspace_id"]))

    @app.post("/api/me/ai-profiles")
    async def save_profile(request: Request):
        user = actor(request, True)
        return ok(platform.profiles.save(user["workspace_id"], await body(request)))

    @app.patch("/api/me/ai-profiles/{profile_id}")
    async def edit_profile(profile_id: str, request: Request):
        user = actor(request, True)
        return ok(platform.profiles.save(user["workspace_id"], await body(request), profile_id))

    @app.post("/api/me/ai-profiles/{profile_id}/test")
    async def test_profile(profile_id: str, request: Request):
        user = actor(request, True)
        await body(request, [])
        return ok(platform.profiles.test(user["workspace_id"], profile_id))

    @app.get("/api/me/usage")
    def usage(request: Request):
        return ok(platform.usage(actor(request)["workspace_id"]))

    @app.get("/api/jobs")
    def jobs(request: Request):
        actor(request)
        return ok(
            [
                {
                    "job_id": name,
                    "kind": job.get("kind", "command"),
                    "isolation": job.get("isolation", "case"),
                    "max_workers": job.get("max_workers", 8),
                    "extensions": describe_extensions(job.get("allowed_extensions"))
                    if job.get("kind") == "pytest"
                    else [],
                }
                for name, job in platform.queue.jobs.items()
            ]
        )

    @app.get("/api/pytest/extensions")
    def extensions(request: Request):
        actor(request)
        return ok({"extensions": describe_extensions(), "schema_version": 1})

    @app.get("/api/tasks")
    def tasks(request: Request):
        return ok(platform.manager(actor(request)).list())

    @app.get("/api/data/tasks")
    def query_tasks(
        request: Request,
        kind: str | None = None,
        state: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        job_id: str | None = None,
    ):
        return ok(
            Repository(platform.db, actor(request)["workspace_id"]).query(
                kind, state, limit, cursor, job_id
            )
        )

    @app.get("/api/case-results")
    def results(
        request: Request, nodeid: str | None = None, outcome: str | None = None, limit: int = 50
    ):
        return ok(
            Repository(platform.db, actor(request)["workspace_id"]).result_query(
                nodeid, outcome, limit
            )
        )

    @app.post("/api/tasks")
    async def submit(request: Request):
        user = actor(request, True)
        data = await body(request, ["job_id", "idempotency_key"])
        return ok(platform.manager(user).submit(**data))

    @app.post("/api/pytest/runs")
    async def run_pytest(request: Request):
        user = actor(request, True)
        data = await body(request)
        if not {"collection_id", "nodeids", "isolation", "idempotency_key"} <= set(data) or set(
            data
        ) - {"collection_id", "nodeids", "isolation", "idempotency_key", "workers", "extensions"}:
            raise ToolError("INVALID_ARGUMENT", "Invalid pytest selection")
        return ok(platform.manager(user).run_pytest(**data))

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str, request: Request):
        return ok(platform.manager(actor(request)).read(task_id))

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel(task_id: str, request: Request):
        user = actor(request, True)
        await body(request, [])
        return ok(platform.manager(user).cancel(task_id))

    @app.post("/api/tasks/{task_id}/rerun")
    async def rerun(task_id: str, request: Request):
        user = actor(request, True)
        data = await body(request, ["mode", "idempotency_key"])
        return ok(platform.manager(user).rerun(task_id, **data))

    @app.get("/api/tasks/{task_id}/events")
    def task_events(task_id: str, request: Request, after: int = 0):
        events = Repository(platform.db, actor(request)["workspace_id"]).events(task_id, after)
        return Response(
            "".join(
                f"id: {e['id']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events
            ),
            media_type="text/event-stream",
        )

    @app.get("/api/tasks/{task_id}/artifacts/{artifact_id}")
    def task_artifact(task_id: str, artifact_id: str, request: Request):
        manager = platform.manager(actor(request))
        from triton_dev.serve.pytest_jobs import artifact

        data = artifact(manager.store, task_id, artifact_id)
        manager.repo.put_blob(data, task_id, artifact_id)
        return Response(data, media_type="application/octet-stream")

    @app.get("/api/regression/catalog")
    def regression_catalog(request: Request):
        actor(request)
        from triton_dev.agent.regression.service import catalog

        return ok(catalog())

    @app.get("/api/regression/tasks")
    def regressions(request: Request):
        return ok(platform.manager(actor(request)).regressions.list())

    @app.post("/api/regression/tasks")
    async def regression_start(request: Request):
        user = actor(request, True)
        data = await body(request)
        if not {"config", "idempotency_key"} <= set(data) or set(data) - {
            "config",
            "idempotency_key",
            "profile_id",
        }:
            raise ToolError("INVALID_ARGUMENT", "Invalid regression request")
        return ok(
            platform.regression_start(
                user, data["config"], data["idempotency_key"], data.get("profile_id")
            )
        )

    @app.get("/api/regression/tasks/{task_id}")
    def regression(task_id: str, request: Request):
        return ok(platform.manager(actor(request)).regressions.read(task_id))

    @app.post("/api/regression/tasks/{task_id}/{operation}")
    async def regression_action(task_id: str, operation: str, request: Request):
        user = actor(request, True)
        await body(request, [])
        manager = platform.manager(user)
        manager.regressions.read(task_id)
        if operation == "cancel":
            manager.cancel(task_id)
            return ok(manager.regressions.read(task_id))
        if operation == "resume":
            return ok(platform.queue.resume(user["workspace_id"], task_id))
        raise ToolError("NOT_FOUND", "Unknown regression action")

    @app.get("/api/regression/tasks/{task_id}/experiments/{experiment_id}")
    def experiment(task_id: str, experiment_id: str, request: Request):
        return ok(platform.manager(actor(request)).regressions.experiment(task_id, experiment_id))

    @app.get("/api/regression/tasks/{task_id}/report")
    def regression_report(task_id: str, request: Request):
        manager = platform.manager(actor(request))
        record = manager.regressions.read(task_id)
        directory = manager.regressions._dir(task_id)
        if not (directory / "report.md").is_file():
            raise ToolError("NOT_READY", "Report is not ready")
        return ok(
            {
                "markdown": (directory / "report.md").read_text(),
                "html": (directory / "report.html").read_text(),
                "record": record,
            }
        )

    @app.get("/api/regression/tasks/{task_id}/bundle")
    def regression_bundle(task_id: str, request: Request):
        from triton_dev.agent.regression.reporting import bundle

        manager = platform.manager(actor(request))
        record = manager.regressions.read(task_id)
        data = bundle(manager.regressions._dir(task_id), record)
        manager.repo.put_blob(data, task_id, "evidence.tar.gz")
        return Response(data, media_type="application/gzip")

    def profile_store(user):
        return ProfileStore(Repository(platform.db, user["workspace_id"]).root / "profiles")

    @app.get("/api/profiling/catalog")
    def profiling_catalog(request: Request):
        actor(request)
        return ok(profile_catalog())

    @app.get("/api/profiling/reports")
    def profiling_reports(request: Request):
        return ok(Repository(platform.db, actor(request)["workspace_id"]).records("profiling"))

    @app.post("/api/profiling/reports")
    async def profiling_start(request: Request):
        user = actor(request, True)
        data = await body(request)
        report = await asyncio.to_thread(profile_store(user).create, data)
        repo = Repository(platform.db, user["workspace_id"])
        repo.put("profiling", report)
        repo.put_blob(json.dumps(report).encode(), report["id"], "profiling.json")
        return ok(report)

    @app.get("/api/profiling/reports/{report_id}")
    def profiling_report(report_id: str, request: Request):
        return ok(Repository(platform.db, actor(request)["workspace_id"]).task(report_id))

    @app.get("/api/profiling/reports/{report_id}/{kind}")
    def profiling_export(report_id: str, kind: str, request: Request):
        record = Repository(platform.db, actor(request)["workspace_id"]).task(report_id)
        if kind == "trace":
            return ok(chrome_trace(record))
        if kind == "html":
            return ok({"html": html_report(record)})
        raise ToolError("NOT_FOUND", "Unknown profiling artifact")

    @app.get("/api/artifacts/{artifact_id}/download")
    def artifact_download(artifact_id: str, request: Request):
        data, _ = Repository(platform.db, actor(request)["workspace_id"]).blob(artifact_id)
        return Response(data, media_type="application/octet-stream")

    @app.get("/api/sdk-builds")
    def sdk_builds(
        request: Request,
        source: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 50,
    ):
        actor(request)
        return ok(platform.daily.builds(source, start, end, limit))

    @app.get("/api/daily-batches")
    def batches(request: Request, limit: int = 50):
        actor(request)
        return ok(platform.daily.batches(limit))

    @app.get("/api/daily-batches/{batch_id}/task")
    def daily_task(batch_id: str, request: Request):
        actor(request)
        # Only the system-owned tasks explicitly published by a daily batch are public.
        import sqlalchemy as sa
        from . import models as m
        from .database import SYSTEM

        with platform.db.tx() as c:
            task_id = c.execute(
                sa.select(m.daily_batches.c.task_id).where(m.daily_batches.c.id == batch_id)
            ).scalar_one_or_none()
        if not task_id:
            raise ToolError("NOT_FOUND", "Daily batch not found")
        return ok(platform.queue.manager(SYSTEM).read(task_id))

    if root:

        @app.get("/{path:path}")
        def static(path: str):
            if path.startswith("api/"):
                raise ToolError("NOT_FOUND", "API not found")
            if path in {"", "index.html"}:
                return FileResponse(root / "index.html")
            file = (root / path).resolve()
            if (
                not path.startswith("assets/")
                or not file.is_relative_to(root)
                or not file.is_file()
            ):
                raise ToolError("NOT_FOUND", "File not found")
            return FileResponse(file)

    return app
