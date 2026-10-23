"""Single-owner, single-worker local task queue with registered execution recipes."""
import copy
import fcntl
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from triton_dev.common.contracts import ToolError, atomic_json
from triton_dev.execution.records import RunStore, execute_record


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
                    or not Path(request.get('cwd', '')).is_absolute()
                    or not 0 < request.get('timeout', 300) <= 3600):
                self.owner.close()
                raise ToolError('INVALID_RECIPE', 'Job requires argv, absolute cwd, timeout <=3600')
        self.store.recover()
        self.lock = threading.RLock()
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancellations = {}
        self.index = Path(root) / 'idempotency.json'
        self.keys = json.loads(self.index.read_text()) if self.index.exists() else {}

    def submit(self, job_id, idempotency_key):
        if (not isinstance(job_id, str) or job_id not in self.jobs or not isinstance(idempotency_key, str)
                or not 1 <= len(idempotency_key) <= 128):
            raise ToolError('INVALID_ARGUMENT', 'Registered job ID and idempotency key required')
        with self.lock:
            if self.closed:
                raise ToolError('SERVICE_CLOSED', 'Task manager is closing')
            if idempotency_key in self.keys:
                saved = self.keys[idempotency_key]
                if saved['job_id'] != job_id:
                    raise ToolError('IDEMPOTENCY_CONFLICT', 'Key belongs to a different job')
                return self.store.read(saved['run_id'])
            run_id = self.store.create(self.jobs[job_id])
            self.store.update(run_id, job_id=job_id)
            self.keys[idempotency_key] = {'job_id': job_id, 'run_id': run_id}
            atomic_json(self.index, self.keys)
            cancel = threading.Event()
            self.cancellations[run_id] = cancel
            self.pool.submit(self._run, run_id, cancel)
            return self.store.read(run_id)

    def _run(self, run_id, cancel):
        if cancel.is_set():
            self.store.update(run_id, state='cancelled')
            self.store.event(run_id, 'cancelled')
            return
        try:
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
