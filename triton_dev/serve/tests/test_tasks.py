import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.serve.service import handler_factory
from triton_dev.serve.tasks import TaskManager


def wait_terminal(manager, run_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        record = manager.store.read(run_id)
        if record['state'] not in {'queued', 'running'}:
            return record
        time.sleep(0.02)
    pytest.fail('Task did not terminate')


def jobs(tmp_path):
    return {'quick': {'argv': [sys.executable, '-c', 'print("job complete")'], 'cwd': str(tmp_path)},
            'slow': {'argv': [sys.executable, '-c', 'import time;time.sleep(30)'], 'cwd': str(tmp_path)}}


def test_queue_idempotency_cancel_and_recovery(tmp_path):
    manager = TaskManager(tmp_path / 'tasks', jobs(tmp_path))
    try:
        with pytest.raises(ToolError) as error:
            TaskManager(tmp_path / 'tasks', jobs(tmp_path))
        assert error.value.code == 'SERVICE_BUSY'
        slow = manager.submit('slow', 'first')
        quick = manager.submit('quick', 'second')
        assert quick['job_id'] == 'quick'
        assert manager.submit('quick', 'second')['id'] == quick['id']
        with pytest.raises(ToolError):
            manager.submit('slow', 'second')
        manager.cancel(slow['id'])
        assert wait_terminal(manager, slow['id'])['state'] == 'cancelled'
        assert wait_terminal(manager, quick['id'])['state'] == 'passed'
        orphan = manager.store.create(jobs(tmp_path)['quick'])
    finally:
        manager.close()
    restored = TaskManager(tmp_path / 'tasks', jobs(tmp_path))
    try:
        assert restored.store.read(orphan)['state'] == 'interrupted'
        assert restored.submit('quick', 'second')['id'] == quick['id']
    finally:
        restored.close()


def test_http_auth_allowlist_and_sse_resume(tmp_path):
    manager = TaskManager(tmp_path / 'tasks', jobs(tmp_path))
    token = 'test-token-1234567890'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory([], manager, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def request(path, data=None, headers=None):
        return urllib.request.urlopen(urllib.request.Request(base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + token, **(headers or {})}))
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + '/api/tasks')
        assert error.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as error:
            request('/api/tasks', {'job_id': 'quick', 'idempotency_key': 'x'}, {'Origin': 'https://evil.invalid'})
        assert error.value.code == 403
        with pytest.raises(urllib.error.HTTPError):
            request('/api/tasks', {'argv': ['arbitrary'], 'job_id': 'quick', 'idempotency_key': 'x'})
        with request('/api/tasks', {'job_id': 'quick', 'idempotency_key': 'x'}) as response:
            run_id = json.load(response)['data']['id']
        assert wait_terminal(manager, run_id)['state'] == 'passed'
        with request(f'/api/tasks/{run_id}/events', headers={'Last-Event-ID': '1'}) as response:
            body = response.read().decode()
            assert response.headers['Content-Type'] == 'text/event-stream'
            assert 'id: 1\n' not in body
            assert 'event: passed' in body
        with pytest.raises(urllib.error.HTTPError):
            request('/api/tasks/invalid/cancel', {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        manager.close()
