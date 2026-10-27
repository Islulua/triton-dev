"""Daily HTTP transport. CLI uses these identical scoped services."""

from fastapi import Request
from fastapi.responses import Response
from triton_dev.common.contracts import ToolError


def register_daily(app, platform, actor, body, ok):
    service = platform.daily_v2
    prefix = "/api/daily/v1"

    @app.get(prefix + "/definitions")
    def plans(request: Request):
        return ok(service.plans(actor(request)))

    @app.post(prefix + "/definitions")
    async def create(request: Request):
        return ok(service.save_plan(actor(request, True), await body(request)))

    @app.patch(prefix + "/definitions/{plan_id}")
    async def revise(plan_id: str, request: Request):
        return ok(service.save_plan(actor(request, True), await body(request), plan_id))

    @app.post(prefix + "/demo")
    async def demo(request: Request):
        actor(request, True)
        await body(request, [])
        service.seed_demo()
        return ok({"source": "mock_history", "real_tests_executed": False})

    @app.get(prefix + "/calendar")
    def calendar(request: Request, plan_id: str, month: str):
        return ok(service.calendar(actor(request), plan_id, month))

    @app.get(prefix + "/batches")
    def batches(
        request: Request, plan_id: str | None = None, month: str | None = None, limit: int = 100
    ):
        return ok(service.list(actor(request), plan_id, month, limit))

    @app.post(prefix + "/batches", status_code=202)
    async def trigger(request: Request):
        user = actor(request, True)
        data = await body(request)
        if not {"plan_id", "idempotency_key"} <= set(data) or set(data) - {
            "plan_id",
            "business_date",
            "idempotency_key",
            "scenario",
        }:
            raise ToolError("INVALID_ARGUMENT", "Invalid Daily trigger fields")
        return ok(service.trigger(user, **data))

    @app.get(prefix + "/batches/{batch_id}")
    def status(batch_id: str, request: Request):
        return ok(service.read(actor(request), batch_id))

    @app.get(prefix + "/batches/{batch_id}/report")
    def report(batch_id: str, request: Request):
        return ok(service.report(actor(request), batch_id))

    @app.get(prefix + "/batches/{batch_id}/events")
    def events(batch_id: str, request: Request, after: int = 0):
        from .repository import Repository

        record = service.read(actor(request), batch_id)
        return ok(Repository(platform.db, record["workspace_id"]).events(batch_id, after))

    @app.post(prefix + "/batches/{batch_id}/cancel")
    async def cancel(batch_id: str, request: Request):
        user = actor(request, True)
        await body(request, [])
        return ok(service.cancel(user, batch_id))

    @app.post(prefix + "/batches/{batch_id}/reruns", status_code=202)
    async def rerun(batch_id: str, request: Request):
        user = actor(request, True)
        data = await body(request)
        if not {"scope", "idempotency_key"} <= set(data) or set(data) - {
            "scope",
            "idempotency_key",
            "selected",
        }:
            raise ToolError("INVALID_ARGUMENT", "Invalid rerun selection")
        return ok(
            service.rerun(
                user, batch_id, data["scope"], data["idempotency_key"], data.get("selected")
            )
        )

    @app.get(prefix + "/batches/{batch_id}/cases")
    def cases(
        batch_id: str,
        request: Request,
        status: str | None = None,
        operator: str | None = None,
        worker: str | None = None,
        phase: str | None = None,
        dtype: str | None = None,
        file: str | None = None,
        search: str | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ):
        return ok(
            service.cases(
                actor(request),
                batch_id,
                status,
                operator,
                worker,
                phase,
                dtype,
                search,
                min_duration,
                max_duration,
                cursor,
                limit,
                file,
            )
        )

    @app.get(prefix + "/batches/{batch_id}/logs")
    def logs(
        batch_id: str,
        request: Request,
        after: int = 0,
        configuration_id: str | None = None,
        worker: str | None = None,
        phase: str | None = None,
        step: str | None = None,
        search: str | None = None,
        level: str | None = None,
        limit: int = 100,
    ):
        return ok(
            service.logs(
                actor(request),
                batch_id,
                after,
                configuration_id,
                worker,
                phase,
                step,
                search,
                level,
                limit,
            )
        )

    @app.get(prefix + "/batches/{batch_id}/export")
    def export(
        batch_id: str,
        request: Request,
        format: str = "json",
        status: str | None = None,
        operator: str | None = None,
        search: str | None = None,
        worker: str | None = None,
        phase: str | None = None,
        dtype: str | None = None,
        file: str | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
    ):
        filters = {
            k: v
            for k, v in dict(
                status=status,
                operator=operator,
                search=search,
                worker=worker,
                phase=phase,
                dtype=dtype,
                file=file,
                min_duration=min_duration,
                max_duration=max_duration,
            ).items()
            if v is not None
        }
        text, mime = service.export(actor(request), batch_id, format, **filters)
        return Response(
            text,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{batch_id}.{format}"'},
        )
