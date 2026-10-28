"""Same-origin IR routes using the existing workspace and CSRF boundaries."""

import base64
import binascii
import asyncio
from fastapi import Request
from triton_dev.common.contracts import ToolError
from .compilation import CompilationService
from .documents import import_trace


def register_ir(app, platform, actor, body, ok):
    service = CompilationService(platform.db, platform.ir_compilers)
    import_slots = asyncio.Semaphore(2)

    @app.get('/api/ir/compilers')
    def compilers(request: Request):
        actor(request)
        return ok(platform.ir_compilers.catalog())

    @app.post('/api/ir/import')
    async def trace_import(request: Request):
        actor(request, True)
        data = await body(request, ['data'])
        try:
            raw = base64.b64decode(data['data'], validate=True)
        except (ValueError, TypeError, binascii.Error):
            raise ToolError('INVALID_TRACE', 'Expected base64 encoded JSON/NDJSON/gzip') from None
        async with import_slots:
            documents = await asyncio.to_thread(import_trace, raw)
        return ok({'documents': documents, 'parser': 'tritonparse', 'upstream_revision': 'a573a10384ec519dcc485a9c3c7354f35538f4e8'})

    @app.get('/api/ir/compilations')
    def compilations(request: Request):
        return ok(service.list(actor(request)))

    @app.post('/api/ir/compilations', status_code=202)
    async def compile_kernel(request: Request):
        user = actor(request, True)
        data = await body(request, ['spec', 'idempotency_key'])
        return ok(service.submit(user, data['spec'], data['idempotency_key']))

    @app.get('/api/ir/compilations/{task_id}')
    def compilation(task_id: str, request: Request):
        return ok(service.read(actor(request), task_id))

    @app.post('/api/ir/compilations/{task_id}/cancel')
    async def cancel(task_id: str, request: Request):
        user = actor(request, True)
        await body(request, [])
        return ok(service.cancel(user, task_id))
