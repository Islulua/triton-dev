import hmac
import json
import mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, unquote

from triton_dev.common.contracts import ToolError, envelope


def handler_factory(capabilities, manager=None, token=None, ui_root=None):
    from .profiling import ProfileStore, catalog, chrome_trace, html_report
    profiles = ProfileStore(manager.store.root / 'profiles') if manager is not None else None
    ui_root = Path(ui_root).resolve() if ui_root else None
    if ui_root is not None and not (ui_root / "index.html").is_file():
        raise ToolError("UI_NOT_BUILT", "Build the frontend and pass its dist/client directory")
    if manager is not None and (not isinstance(token, str) or len(token) < 16):
        raise ToolError('INVALID_ARGUMENT', 'Task API requires a token of at least 16 characters')

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value, *, content_type='application/json'):
            body = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
            self.end_headers()
            self.wfile.write(body)

        def checked(self):
            port = self.server.server_port
            host = self.headers.get('Host')
            origin = self.headers.get('Origin')
            if host not in {f'127.0.0.1:{port}', f'localhost:{port}'} or origin not in (None, f'http://{host}'):
                self.reply(403, envelope(error=ToolError('ORIGIN_REJECTED', 'Use a local non-cross-origin client')))
                return False
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode('utf-8'), ('Bearer ' + token).encode('utf-8')):
                self.reply(401, envelope(error=ToolError('UNAUTHORIZED', 'Bearer token required')))
                return False
            return True

        def do_GET(self):
            path = urlsplit(self.path)
            if ui_root is not None and not path.path.startswith('/api/'):
                host = self.headers.get('Host')
                if host not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
                    self.reply(403, envelope(error=ToolError('ORIGIN_REJECTED', 'Local host required')))
                    return
                relative = 'index.html' if path.path in ('/', '/index.html') else unquote(path.path).lstrip('/')
                if relative != 'index.html' and not relative.startswith('assets/'):
                    self.send_error(404)
                    return
                try:
                    file = (ui_root / relative).resolve()
                    if not file.is_relative_to(ui_root) or not file.is_file():
                        self.send_error(404)
                        return
                    self.reply(200, file.read_bytes(), content_type=mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                except (OSError, ValueError):
                    self.send_error(404)
                return
            if path.path == '/api/capabilities':
                self.reply(200, envelope(capabilities))
                return
            if manager is None:
                self.send_error(404)
                return
            if not self.checked():
                return
            try:
                parts = path.path.strip('/').split('/')
                if parts == ['api', 'regression', 'catalog']:
                    from triton_dev.agent.regression.service import catalog as regression_catalog
                    value = regression_catalog()
                elif parts == ['api', 'regression', 'tasks']:
                    value = manager.regressions.list()
                elif len(parts) in (4, 5, 6) and parts[:3] == ['api', 'regression', 'tasks']:
                    value = manager.regressions.read(parts[3])
                    if len(parts) == 5 and parts[4] == 'bundle':
                        from triton_dev.agent.regression.reporting import bundle
                        self.reply(200, bundle(manager.regressions._dir(parts[3]), value), content_type='application/gzip')
                        return
                    if len(parts) == 5 and parts[4] == 'report':
                        root = manager.regressions._dir(parts[3])
                        if not (root / 'report.md').exists():
                            raise ToolError('NOT_READY', 'Report is not ready')
                        value = {'markdown': (root / 'report.md').read_text(), 'html': (root / 'report.html').read_text(), 'record': value}
                    elif len(parts) == 6 and parts[4] == 'experiments':
                        value = manager.regressions.experiment(parts[3], parts[5])
                    elif len(parts) != 4:
                        raise ToolError('NOT_FOUND', 'Regression endpoint not found')
                elif parts == ['api', 'profiling', 'catalog']:
                    value = catalog()
                elif parts == ['api', 'profiling', 'reports']:
                    value = profiles.list()
                elif len(parts) in (4, 5) and parts[:3] == ['api', 'profiling', 'reports']:
                    value = profiles.read(parts[3])
                    if len(parts) == 5:
                        if parts[4] not in {'trace', 'html'}:
                            self.send_error(404)
                            return
                        value = chrome_trace(value) if parts[4] == 'trace' else {'html': html_report(value)}
                elif parts == ['api', 'pytest', 'extensions']:
                    from triton_dev.execution.options import describe_extensions
                    value = {'schema_version': 1, 'extensions': describe_extensions()}
                elif parts == ['api', 'jobs']:
                    from triton_dev.execution.options import describe_extensions
                    value = [{'job_id': name, 'kind': job.get('kind', 'command'),
                              'isolation': job.get('isolation', 'case') if job.get('kind') == 'pytest' else None,
                              'max_workers': job.get('max_workers', 8) if job.get('kind') == 'pytest' else 1,
                              'extensions': describe_extensions(job.get('allowed_extensions')) if job.get('kind') == 'pytest' else []}
                             for name, job in manager.jobs.items()]
                elif parts == ['api', 'tasks']:
                    value = manager.list()
                elif len(parts) == 3 and parts[:2] == ['api', 'tasks']:
                    value = manager.read(parts[2])
                elif len(parts) == 5 and parts[:2] == ['api', 'tasks'] and parts[3] == 'artifacts':
                    from .pytest_jobs import artifact
                    self.reply(200, artifact(manager.store, parts[2], parts[4]),
                               content_type='application/octet-stream')
                    return
                elif len(parts) == 4 and parts[:2] == ['api', 'tasks'] and parts[3] == 'events':
                    after = int(self.headers.get('Last-Event-ID') or parse_qs(path.query).get('after', ['0'])[0])
                    events = manager.store.events(parts[2], after)
                    body = ''.join(f"id: {e['id']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
                    # Finite SSE batches; authenticated clients reconnect using Last-Event-ID.
                    self.reply(200, body or ': no new events\n\n', content_type='text/event-stream')
                    return
                else:
                    self.send_error(404)
                    return
                self.reply(200, envelope(value))
            except (ToolError, ValueError) as exc:
                error = exc if isinstance(exc, ToolError) else ToolError('INVALID_ARGUMENT', str(exc))
                self.reply(400, envelope(error=error))

        def do_POST(self):
            if manager is None:
                self.send_error(404)
                return
            if not self.checked():
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ToolError('INVALID_ARGUMENT', 'JSON request size must be 1..65536 bytes')
                self.connection.settimeout(5)
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ToolError('INVALID_ARGUMENT', 'JSON object required')
                parts = urlsplit(self.path).path.strip('/').split('/')
                if parts == ['api', 'regression', 'tasks'] and set(data) == {'config', 'idempotency_key'}:
                    value = manager.regressions.start(data['config'], idempotency_key=data['idempotency_key'])
                elif len(parts) == 5 and parts[:3] == ['api', 'regression', 'tasks'] and parts[4] in {'cancel', 'resume'} and data == {}:
                    value = getattr(manager.regressions, parts[4])(parts[3])
                elif parts == ['api', 'profiling', 'reports']:
                    value = profiles.create(data)
                elif parts == ['api', 'tasks'] and set(data) == {'job_id', 'idempotency_key'}:
                    value = manager.submit(data['job_id'], data['idempotency_key'])
                elif (parts == ['api', 'pytest', 'runs']
                      and {'collection_id', 'nodeids', 'isolation', 'idempotency_key'} <= set(data)
                      and set(data) <= {'collection_id', 'nodeids', 'isolation', 'idempotency_key', 'workers', 'extensions'}):
                    value = manager.run_pytest(**data)
                elif (len(parts) == 4 and parts[:2] == ['api', 'tasks'] and parts[3] == 'rerun'
                      and set(data) == {'mode', 'idempotency_key'}):
                    value = manager.rerun(parts[2], **data)
                elif len(parts) == 4 and parts[:2] == ['api', 'tasks'] and parts[3] == 'cancel' and data == {}:
                    value = manager.cancel(parts[2])
                else:
                    raise ToolError('ACTION_NOT_ALLOWED', 'Only registered jobs or cancellation are accepted')
                self.reply(200, envelope(value))
            except (ToolError, ValueError, OSError) as exc:
                error = exc if isinstance(exc, ToolError) else ToolError('INVALID_ARGUMENT', str(exc))
                self.reply(400, envelope(error=error))

        def log_message(self, *args):
            pass
    return Handler


def serve(capabilities, port=8765, *, manager=None, token=None, ui_root=None):
    try:
        with ThreadingHTTPServer(('127.0.0.1', port), handler_factory(capabilities, manager, token, ui_root)) as server:
            server.serve_forever()
    finally:
        if manager:
            manager.close()
