import subprocess
import sys
import time

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.serve.tasks import TaskManager
from triton_dev.serve.tests.test_pytest_jobs import wait


def project_manager(tmp_path, content, **options):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'test_parallel.py').write_text(content)
    return TaskManager(tmp_path / 'tasks', {'parallel': {
        'kind': 'pytest', 'argv': ['test_parallel.py'], 'cwd': str(project),
        'python': sys.executable, 'timeout': 30, **options}})


def test_32_configurations_share_logical_id_and_one_can_run_alone(tmp_path):
    manager = project_manager(tmp_path, '''import pytest
@pytest.mark.parametrize('n', range(32), ids=lambda n: f'config-{n}')
def test_matrix(n):
    assert n == 17, 'unselected configuration executed'
''')
    try:
        collected = wait(manager, manager.submit('parallel', 'collect')['id'])
        assert len(collected['collection']) == 32
        assert {c['logical_nodeid'] for c in collected['collection']} == {'test_parallel.py::test_matrix'}
        selected = next(c for c in collected['collection'] if c['parameter_id'] == 'config-17')
        run = wait(manager, manager.run_pytest(collected['id'], [selected['nodeid']], 'session', 'run')['id'])
        assert run['summary']['total'] == run['summary']['passed'] == 1
        assert run['test_results'][0]['nodeid'] == selected['nodeid']
    finally:
        manager.close()


def test_40_configurations_really_run_on_four_xdist_workers_with_separate_logs(tmp_path):
    manager = project_manager(tmp_path, '''import os, time, sys, pytest
from pathlib import Path
@pytest.mark.parametrize('n', range(40))
def test_matrix(n, worker_id, triton_dev_log, triton_dev_artifact_dir):
    assert worker_id.startswith('gw')
    assert Path.home().parent.name == worker_id
    assert Path(os.environ['TRITON_CACHE_DIR']).parent.name == worker_id
    triton_dev_log(f'LIVE n={n} worker={worker_id}')
    print(f'CAPTURED n={n} worker={worker_id}')
    sys.stderr.write(f'STDERR n={n} worker={worker_id}\\n')
    (triton_dev_artifact_dir / 'worker.txt').write_text(worker_id)
    time.sleep(.03)
    assert n != 7, 'PARALLEL_FAILURE'
''')
    try:
        collected = wait(manager, manager.submit('parallel', 'collect')['id'])
        nodeids = [c['nodeid'] for c in collected['collection']]
        record = manager.run_pytest(collected['id'], nodeids, 'xdist', 'run', workers=4,
                                    extensions={'durations': 3, 'capture': 'fd'})
        result = wait(manager, record['id'])
        assert result['summary']['total'] == 40, result
        assert result['summary']['passed'] == 39 and result['summary']['failed'] == 1, result
        assert len([s for s in result['stages'] if s['type'] == 'stage']) == 120
        workers = [w for w in result['worker_reports'] if w['worker_id'].startswith('gw')]
        assert len(workers) == 4
        assert len({p for w in workers for p in w['pids']}) == 4
        assert sum(w['summary']['total'] for w in workers) == 40
        assert all(w['state'] == 'finished' and w['summary']['total'] > 0 for w in workers)
        for worker in workers:
            assert f"worker={worker['worker_id']}" in worker['log']
            assert 'LIVE' in worker['log'] and 'CAPTURED' in worker['log'] and 'STDERR' in worker['log']
            assert not worker['tail_truncated']
        assert len(result['artifacts']) == 40
        retry = wait(manager, manager.rerun(result['id'], 'failed', 'retry')['id'])
        assert retry['summary']['total'] == retry['summary']['failed'] == 1
        assert retry['request']['workers'] == 4
        assert retry['request']['extensions'] == result['request']['extensions']
        assert retry['parent'] == result['id']
    finally:
        manager.close()


def test_worker_limits_and_typed_extensions_reject_arbitrary_options(tmp_path):
    manager = project_manager(tmp_path, 'def test_ok(): pass\n', max_workers=2,
                              allowed_extensions=['max_failures', 'capture'])
    try:
        collected = wait(manager, manager.submit('parallel', 'collect')['id'])
        nodeids = [c['nodeid'] for c in collected['collection']]
        for workers, isolation in [(0, 'xdist'), (3, 'xdist'), (True, 'xdist'), ('2', 'xdist'), (2, 'case')]:
            with pytest.raises(ToolError) as error:
                manager.run_pytest(collected['id'], nodeids, isolation, str(workers), workers=workers)
            assert error.value.code == 'INVALID_WORKERS'
        for extensions in [{'argv': ['--pdb']}, {'durations': 1}, {'max_failures': True},
                           {'max_failures': -1}, {'capture': 'no'}, {'capture': '--pdb'}]:
            with pytest.raises(ToolError) as error:
                manager.run_pytest(collected['id'], nodeids, 'session', 'invalid', extensions=extensions)
            assert error.value.code == 'INVALID_EXTENSION'
    finally:
        manager.close()


def test_failure_threshold_stops_serial_cases_and_preserves_unfinished_items(tmp_path):
    manager = project_manager(tmp_path, '''import pytest
@pytest.mark.parametrize('n', range(5))
def test_failure(n): assert False
''')
    try:
        collection = wait(manager, manager.submit('parallel', 'collect')['id'])
        run = wait(manager, manager.run_pytest(collection['id'], [c['nodeid'] for c in collection['collection']],
                   'case', 'run', extensions={'max_failures': 2})['id'])
        assert run['summary']['failed'] == 2 and run['summary']['incomplete'] == 3
        assert run['stopped_reason'] == 'max_failures'
        assert len(run['attempts']) == 2
    finally:
        manager.close()


def test_xdist_worker_crash_is_not_reported_as_success_or_silently_restarted(tmp_path):
    manager = project_manager(tmp_path, '''import os, time, pytest
@pytest.mark.parametrize('n', range(8))
def test_crash(n):
    if n == 0: os._exit(17)
    time.sleep(.05)
''')
    try:
        collection = wait(manager, manager.submit('parallel', 'collect')['id'])
        result = wait(manager, manager.run_pytest(collection['id'], [c['nodeid'] for c in collection['collection']],
                      'xdist', 'run', workers=2)['id'])
        assert result['state'] != 'passed'
        assert result['summary']['incomplete'] >= 1
        assert any(w['state'] == 'crashed' and w.get('error') for w in result['worker_reports'])
    finally:
        manager.close()


def test_cancel_xdist_stops_all_started_worker_processes(tmp_path):
    manager = project_manager(tmp_path, '''import time, pytest
@pytest.mark.parametrize('n', range(12))
def test_slow(n, triton_dev_log):
    triton_dev_log('LIVE_BEFORE_CANCEL')
    time.sleep(20)
''')
    try:
        collection = wait(manager, manager.submit('parallel', 'collect')['id'])
        run = manager.run_pytest(collection['id'], [c['nodeid'] for c in collection['collection']], 'xdist', 'run', workers=4)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            live = manager.read(run['id'])
            workers = [w for w in live['worker_reports'] if w['worker_id'].startswith('gw')]
            if len(workers) == 4 and all('LIVE_BEFORE_CANCEL' in w['log'] for w in workers):
                break
            time.sleep(.03)
        else:
            pytest.fail('four live worker logs did not appear')
        pids = [pid for worker in workers for pid in worker['pids']]
        manager.cancel(run['id'])
        result = wait(manager, run['id'])
        assert result['state'] == 'cancelled'
        assert result['summary']['passed'] == 0
        assert result['summary']['incomplete'] == 12
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            running = []
            for pid in pids:
                state = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True).stdout.strip()
                if state and not state.startswith('Z'):
                    running.append(pid)
            if not running:
                break
            time.sleep(.05)
        assert not running, f'worker processes survived cancellation: {running}'
    finally:
        manager.close()


def test_extension_registration_is_server_owned_and_versioned(tmp_path):
    code = """from triton_dev.execution.options import RunExtension,register_extension,describe_extensions,validate_extensions,compile_extensions
from triton_dev.common.contracts import ToolError
register_extension(RunExtension('traceback_style','Traceback','Trusted built-in pytest option',
 {'type':'string','enum':['short','long']},'short',lambda value:['--tb',value],version=2))
assert describe_extensions(['traceback_style'])[0]['version']==2
assert compile_extensions(validate_extensions({'traceback_style':'long'},['traceback_style']),{'traceback_style':2})==['--tb','long']
try: compile_extensions({'traceback_style':'long'},{'traceback_style':1})
except ToolError as error: assert error.code=='EXTENSION_CHANGED'
else: raise AssertionError('old extension version was silently accepted')
"""
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_http_worker_options_and_extension_discovery(tmp_path):
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from triton_dev.serve.service import handler_factory
    manager = project_manager(tmp_path, 'import pytest\n@pytest.mark.parametrize("n",range(4))\ndef test_ok(n): pass\n', max_workers=4)
    token = 'test-only-xdist-http-token'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory([], manager, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def api(path, data=None):
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api' + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req) as response:
            return json.load(response)['data']
    try:
        assert api('/jobs')[0]['max_workers'] == 4
        assert {item['name'] for item in api('/pytest/extensions')['extensions']} >= {'max_failures', 'capture', 'durations'}
        collection = wait(manager, api('/tasks', {'job_id':'parallel','idempotency_key':'collect'})['id'])
        result = wait(manager, api('/pytest/runs', {'collection_id':collection['id'],
            'nodeids':[c['nodeid'] for c in collection['collection']], 'isolation':'xdist',
            'workers':4, 'extensions':{'durations':2}, 'idempotency_key':'run'})['id'])
        assert result['summary']['passed'] == 4
        assert result['request']['workers'] == 4
        assert result['request']['extensions']['durations'] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        manager.close()
