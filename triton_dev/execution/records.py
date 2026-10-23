"""Opt-in local run records. Processes and pytest are real even for synthetic SDKs."""
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from triton_dev.common.contracts import ToolError, atomic_json, file_lock, run_process

TERMINAL = {'passed', 'failed', 'timeout', 'cancelled', 'interrupted', 'error'}


class RunStore:
    def __init__(self, root):
        self.root = Path(root)

    def directory(self, run_id):
        if not re.fullmatch(r'run_[a-f0-9]{32}', run_id):
            raise ToolError('INVALID_RUN_ID', str(run_id))
        path = self.root / run_id
        if not path.is_dir():
            raise ToolError('RUN_NOT_FOUND', run_id)
        return path

    def create(self, request, *, parent=None):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        run_id = 'run_' + uuid.uuid4().hex
        path = self.root / run_id
        path.mkdir(mode=0o700)
        atomic_json(path / 'record.json', {'schema_version': 1, 'id': run_id,
                    'state': 'queued', 'created_at': time.time(), 'request': request,
                    'parent': parent, 'result': None, 'stages': []})
        self.event(run_id, 'queued')
        return run_id

    def read(self, run_id):
        return json.loads((self.directory(run_id) / 'record.json').read_text())

    def update(self, run_id, **values):
        path = self.directory(run_id)
        with file_lock(path / '.lock'):
            record = self.read(run_id)
            record.update(values)
            atomic_json(path / 'record.json', record)
        return record

    def list(self):
        return [self.read(path.name) for path in sorted(self.root.glob('run_*')) if path.is_dir()]

    def event(self, run_id, kind):
        path = self.directory(run_id)
        with file_lock(path / '.events.lock'):
            events = self.events(run_id)
            event = {'id': len(events) + 1, 'type': kind, 'time': time.time()}
            with (path / 'events.jsonl').open('a') as stream:
                stream.write(json.dumps(event) + '\n')
        return event

    def events(self, run_id, after=0):
        path = self.directory(run_id) / 'events.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()
                if line.strip() and json.loads(line)['id'] > after] if path.exists() else []

    def recover(self):
        recovered = []
        for record in self.list():
            if record['state'] not in TERMINAL:
                self.update(record['id'], state='interrupted', finished_at=time.time())
                self.event(record['id'], 'interrupted')
                recovered.append(record['id'])
        return recovered


def _execute_record(store, run_id, *, cancel=None, log_limit=8 * 1024 * 1024):
    record = store.read(run_id)
    request = record['request']
    path = store.directory(run_id)
    env = os.environ.copy()
    environment = request.get('environment')
    if environment:
        from triton_dev.env.service import process_environment, variables
        env = process_environment(variables(environment))
    python = environment['interpreter'] if environment else request.get('python', sys.executable)
    argv = request['argv']
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
        raise ToolError('INVALID_ARGUMENT', 'argv must be a nonempty string array')
    if request.get('pytest'):
        if any(a.startswith('-') for a in argv):
            raise ToolError('INVALID_ARGUMENT', 'Recorded pytest accepts targets only; project config supplies options')
        argv = [python, '-m', 'pytest', '-p', 'triton_dev.pytest_plugin',
                '--triton-dev-events', str(path / 'pytest-events.jsonl'), *argv]
        # Explicit adapter import; never installs packages into the SDK.
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
    elif argv[0] in ('python', 'python3'):
        argv = [python, *argv[1:]]
    for key in ('cache', 'tmp'):
        (path / key).mkdir(exist_ok=True)
    env.update({'TRITON_CACHE_DIR': str(path / 'cache'), 'TMPDIR': str(path / 'tmp')})
    store.update(run_id, state='running', started_at=time.time())
    store.event(run_id, 'running')
    written = {'stdout': 0, 'stderr': 0}
    def output(name, text):
        data = text.encode('utf-8')[:max(0, log_limit - written[name])]
        if data:
            with (path / (name + '.log')).open('ab') as stream:
                stream.write(data)
            written[name] += len(data)
    state, error = 'error', None
    try:
        result = run_process(argv, env=env, cwd=request['cwd'],
                             timeout=request.get('timeout', 300), cancel=cancel, on_chunk=output)
        state = result['outcome']
    except ToolError as exc:
        state = {'TIMEOUT': 'timeout', 'CANCELLED': 'cancelled'}.get(exc.code, 'error')
        result, error = exc.details, {'code': exc.code, 'message': str(exc)}
    stages = []
    for file in path.glob('pytest-events*.jsonl'):
        for line in file.read_text().splitlines():
            try:
                stages.append(json.loads(line))
            except ValueError:
                stages.append({'type': 'incomplete_event'})
    if request.get('pytest') and not stages and state == 'passed':
        state, error = 'error', {'code': 'MISSING_PYTEST_EVENTS', 'message': 'Adapter produced no events'}
    record = store.update(run_id, state=state, finished_at=time.time(), result=result,
                          stages=stages, error=error,
                          logs={'limit_per_stream': log_limit, 'written_bytes': written,
                                'truncated': {key: result.get('output_bytes', {}).get(key, 0) > count
                                              for key, count in written.items()}})
    store.event(run_id, state)
    return record


def execute_record(store, run_id, **options):
    try:
        return _execute_record(store, run_id, **options)
    except (ToolError, OSError, ValueError, KeyError) as exc:
        code = exc.code if isinstance(exc, ToolError) else 'INVALID_REQUEST'
        record = store.update(run_id, state='error', finished_at=time.time(),
                              error={'code': code, 'message': str(exc)})
        store.event(run_id, 'error')
        return record


def start(store, argv, *, cwd=None, python=sys.executable, pytest=False, timeout=300,
          environment=None, parent=None):
    request = {'argv': argv, 'cwd': str(Path(cwd or os.getcwd()).resolve()),
               'python': str(python), 'pytest': pytest, 'timeout': timeout,
               'environment': environment}
    run_id = store.create(request, parent=parent)
    return execute_record(store, run_id)


def rerun(store, run_id, *, failed=False):
    record = store.read(run_id)
    request = dict(record['request'])
    if failed:
        if not request.get('pytest'):
            raise ToolError('INVALID_ARGUMENT', '--failed requires a pytest record')
        request['argv'] = sorted({s['nodeid'] for s in record['stages']
                                  if s.get('type') == 'stage' and s.get('outcome') == 'failed'})
        if not request['argv']:
            raise ToolError('NO_FAILED_CASES', 'No recorded failed pytest items; inspect collection/crash evidence')
    new_id = store.create(request, parent=run_id)
    return execute_record(store, new_id)


def diff(store, left, right):
    a, b = store.read(left), store.read(right)
    def outcomes(record):
        return {(s['nodeid'], s['when']): s['outcome'] for s in record['stages'] if s.get('type') == 'stage'}
    ao, bo = outcomes(a), outcomes(b)
    return {'left': left, 'right': right, 'request_changed': a['request'] != b['request'],
            'changes': [{'nodeid': key[0], 'when': key[1], 'left': ao.get(key), 'right': bo.get(key)}
                        for key in sorted(ao.keys() | bo.keys()) if ao.get(key) != bo.get(key)]}
