"""IR trace conversion and authenticated same-server compilation client."""

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from triton_dev.common.contracts import ToolError
from .daily import NoRedirect


def register(sub, leaf):
    commands = sub.add_parser('ir', help='Kernel source/IR documents and isolated server compilation').add_subparsers(required=True)
    p = leaf(commands, 'import', 'ir.import', 'Parse embedded TritonParse JSON/NDJSON/gzip into normalized IR documents')
    p.add_argument('input', type=Path)
    p.add_argument('--output', type=Path)
    for name in ['compilers', 'list', 'compile', 'status', 'cancel']:
        p = leaf(commands, name, 'ir.' + name, 'IR ' + name + ' using the existing multi-user session', effects='execute' if name in {'compile', 'cancel'} else 'read_only')
        p.add_argument('--server', default='http://127.0.0.1:8765')
        p.add_argument('--session-file', type=Path, default=Path.home() / '.cache/triton-dev/daily-session.json')
        if name == 'compile':
            p.add_argument('--file', type=Path, required=True, help='Frozen compile specification JSON')
            p.add_argument('--idempotency-key', required=True)
        if name in {'status', 'cancel'}:
            p.add_argument('task_id')


def dispatch(args):
    command = args.command_id.removeprefix('ir.')
    if command == 'import':
        from triton_dev.ir.documents import import_trace
        with args.input.open('rb') as stream:
            documents = import_trace(stream.read(2 * 1024 * 1024 + 1))
        if args.output:
            args.output.write_text(json.dumps(documents, ensure_ascii=False, indent=2))
            return {'documents': len(documents), 'output': str(args.output)}
        return {'documents': documents}
    origin = args.server.rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ToolError('INVALID_SERVER', 'Use a server origin without credentials or path')
    if not args.session_file.is_file() or args.session_file.stat().st_mode & 0o077:
        raise ToolError('UNAUTHORIZED', 'Run triton-dev daily login first; session file must have mode 0600')
    auth = json.loads(args.session_file.read_text())
    if auth.get('server') != origin:
        raise ToolError('UNAUTHORIZED', 'Session belongs to a different server')
    path, method, body = '/ir/compilers', 'GET', None
    if command == 'list':
        path = '/ir/compilations'
    elif command == 'compile':
        path, method = '/ir/compilations', 'POST'
        body = {'spec': json.loads(args.file.read_text()), 'idempotency_key': args.idempotency_key}
    elif command in {'status', 'cancel'}:
        import re
        if not re.fullmatch(r'ir_[a-f0-9]{32}', args.task_id):
            raise ToolError('INVALID_ARGUMENT', 'Invalid compilation task ID')
        path = '/ir/compilations/' + args.task_id
        if command == 'cancel':
            path, method, body = path + '/cancel', 'POST', {}
    headers = {'Cookie': 'td_session=' + auth['session'], 'X-CSRF-Token': auth['csrf']}
    data = None
    if body is not None:
        data = json.dumps(body, allow_nan=False).encode()
        headers['Content-Type'] = 'application/json'
    try:
        with build_opener(NoRedirect()).open(Request(origin + '/api' + path, data=data, headers=headers, method=method), timeout=30) as response:
            return json.load(response)['data']
    except HTTPError as exc:
        try:
            error = json.load(exc)['error']
            raise ToolError(error['code'], error['message']) from exc
        except (ValueError, KeyError, TypeError):
            raise ToolError('SERVER_ERROR', f'IR server returned HTTP {exc.code}') from exc
    except URLError as exc:
        raise ToolError('SERVER_UNAVAILABLE', 'Cannot reach configured IR server') from exc
