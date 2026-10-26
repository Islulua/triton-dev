"""Single-owner, single-worker local task queue with registered execution recipes."""
import copy
import fcntl
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from triton_dev.common.contracts import ToolError, atomic_json
from triton_dev.execution.records import RunStore, execute_record
from triton_dev.execution.options import describe_extensions, validate_extensions


class TaskManager:
    def __init__(self, root, jobs):
        self.store = RunStore(root)
        Path(root).mkdir(parents=True, exist_ok=True, mode=0o700)
        self.owner = (Path(root) / '.owner.lock').open('a')
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.owner.close()
            raise ToolError('SERVICE_BUSY', 'Another task service owns this state directory') from exc
        if not isinstance(jobs, dict):
            self.owner.close()
            raise ToolError('INVALID_RECIPE', 'Job registry must be a JSON object')
        self.jobs = copy.deepcopy(jobs)
        for name, request in self.jobs.items():
            if (not isinstance(name, str) or not isinstance(request, dict)
                    or not isinstance(request.get('argv'), list) or not request['argv']
                    or any(not isinstance(a, str) for a in request['argv'])
                    or not isinstance(request.get('cwd'), str)
                    or not Path(request['cwd']).is_absolute()
                    or request.get('kind', 'command') not in {'command', 'pytest'}
                    or not isinstance(request.get('timeout', 300), (int, float))
                    or not math.isfinite(request.get('timeout', 300))
                    or not 0 < request.get('timeout', 300) <= 3600):
                self.owner.close()
                raise ToolError('INVALID_RECIPE', 'Job requires argv, absolute cwd, timeout <=3600')
            if request.get('kind') == 'pytest':
                if (type(request.get('max_workers', 8)) is not int
                        or not 1 <= request.get('max_workers', 8) <= 32
                        or not isinstance(request.get('plugins', []), list)
                        or any(not isinstance(p, str) or not p or p.startswith('-') for p in request.get('plugins', []))
                        or any(a.startswith('-') or Path(a.split('::')[0]).is_absolute()
                        or '..' in Path(a.split('::')[0]).parts for a in request['argv'])
                        or request.get('isolation', 'case') not in {'case', 'session', 'xdist'}):
                    self.owner.close()
                    raise ToolError('INVALID_RECIPE', 'Invalid pytest targets, plugins or worker limit')
                try:
                    describe_extensions(request.get('allowed_extensions'))
                except ToolError:
                    self.owner.close()
                    raise
        self.store.recover()
        self.lock = threading.RLock()
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancellations = {}
        self.index = Path(root) / 'idempotency.json'
        self.keys = json.loads(self.index.read_text()) if self.index.exists() else {}

    def read(self, run_id):
        from .pytest_jobs import view
        return view(self.store, self.store.read(run_id))

    def list(self):
        return sorted((self.read(r['id']) for r in self.store.list()), key=lambda r: r['created_at'])

    def submit(self, job_id, idempotency_key):
        if not isinstance(job_id, str) or job_id not in self.jobs:
            raise ToolError('INVALID_ARGUMENT', 'Registered job ID required')
        request = copy.deepcopy(self.jobs[job_id])
        if request.get('kind') == 'pytest':
            request.update(operation='collect', nodeids=[], pytest=True)
        return self._enqueue(job_id, idempotency_key, request)

    def run_pytest(self, collection_id, nodeids, isolation, idempotency_key, workers=1, extensions=None):
        collection = self.store.read(collection_id)
        original = collection['request']
        if (original.get('operation') != 'collect' or collection['state'] != 'passed'
                or not collection.get('source_snapshot') or not collection.get('runtime')):
            raise ToolError('INVALID_COLLECTION', 'Successful collection snapshot required')
        allowed = {c['nodeid'] for c in collection.get('collection', [])}
        if (not isinstance(nodeids, list) or not 1 <= len(nodeids) <= 500
                or any(not isinstance(n, str) or n not in allowed for n in nodeids)
                or len(set(nodeids)) != len(nodeids) or not isinstance(isolation, str)
                or isolation not in {'case', 'session', 'xdist'}):
            raise ToolError('INVALID_SELECTION', 'Select 1..500 unique collected nodeids and case/session isolation')
        job = self.jobs.get(collection['job_id'], {})
        limit = job.get('max_workers', 8)
        if type(workers) is not int or not 1 <= workers <= limit:
            raise ToolError('INVALID_WORKERS', f'workers must be an integer in 1..{limit}')
        if workers > 1 and isolation != 'xdist':
            raise ToolError('INVALID_WORKERS', 'Multiple workers require explicit xdist isolation')
        options = validate_extensions(extensions, job.get('allowed_extensions'))
        versions = {d['name']: d['version'] for d in describe_extensions(list(options))}
        request = {**original, 'workers': workers, 'extensions': options, 'extension_versions': versions, 'operation': 'run', 'nodeids': nodeids, 'argv': nodeids,
                   'isolation': isolation, 'source_id': collection_id,
                   'source_sha256': collection['source_snapshot']['sha256'],
                   'expected_runtime': collection['runtime']}
        return self._enqueue(collection['job_id'], idempotency_key, request)

    def rerun(self, run_id, mode, idempotency_key):
        record = self.read(run_id)
        if (record['request'].get('operation') != 'run' or record['state'] not in
                {'passed', 'failed', 'cancelled', 'timeout', 'interrupted', 'error'}
                or not isinstance(mode, str) or mode not in {'all', 'failed'}):
            raise ToolError('INVALID_RERUN', 'Terminal pytest run and all/failed mode required')
        request = copy.deepcopy(record['request'])
        job = self.jobs.get(record['job_id'], {})
        if request.get('workers', 1) > job.get('max_workers', 8):
            raise ToolError('INVALID_WORKERS', 'Saved worker count exceeds current project limit')
        validate_extensions(request.get('extensions'), job.get('allowed_extensions'))
        if mode == 'failed':
            request['nodeids'] = [r['nodeid'] for r in record['test_results'] if r['outcome'] == 'failed']
            if not request['nodeids']:
                raise ToolError('NO_FAILED_CASES', 'No failed setup/call/teardown; use all for incomplete/crashed cases')
            request['argv'] = request['nodeids']
        return self._enqueue(record['job_id'], idempotency_key, request, parent=run_id)

    def _enqueue(self, job_id, idempotency_key, request, parent=None):
        if (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128):
            raise ToolError('INVALID_ARGUMENT', 'Idempotency key required')
        signature = json.dumps({'job_id': job_id, 'request': request, 'parent': parent}, sort_keys=True)
        with self.lock:
            if self.closed:
                raise ToolError('SERVICE_CLOSED', 'Task manager is closing')
            if idempotency_key in self.keys:
                saved = self.keys[idempotency_key]
                if saved['job_id'] != job_id or saved.get('signature', signature) != signature:
                    raise ToolError('IDEMPOTENCY_CONFLICT', 'Key belongs to a different request')
                return self.read(saved['run_id'])
            run_id = self.store.create(request, parent=parent)
            self.store.update(run_id, job_id=job_id)
            self.keys[idempotency_key] = {'job_id': job_id, 'run_id': run_id, 'signature': signature}
            atomic_json(self.index, self.keys)
            cancel = threading.Event()
            self.cancellations[run_id] = cancel
            self.pool.submit(self._run, run_id, cancel)
            return self.read(run_id)

    def _run(self, run_id, cancel):
        if cancel.is_set():
            self.store.update(run_id, state='cancelled')
            self.store.event(run_id, 'cancelled')
            return
        try:
            if self.store.read(run_id)['request'].get('kind') == 'pytest':
                from .pytest_jobs import execute
                execute(self.store, run_id, cancel)
            else:
                execute_record(self.store, run_id, cancel=cancel)
        except Exception as exc:
            self.store.update(run_id, state='error', error={'code': 'TASK_ERROR', 'message': str(exc)})
            self.store.event(run_id, 'error')

    def cancel(self, run_id):
        with self.lock:
            record = self.store.read(run_id)
            event = self.cancellations.get(run_id)
            if event and record['state'] in {'queued', 'running'}:
                event.set()
                self.store.event(run_id, 'cancel_requested')
            return self.store.read(run_id)

    def close(self):
        with self.lock:
            self.closed = True
            for event in self.cancellations.values():
                event.set()
        self.pool.shutdown(wait=True)
        self.owner.close()
