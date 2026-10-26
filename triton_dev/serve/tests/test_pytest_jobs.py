import json
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.serve.tasks import TaskManager
from triton_dev.serve.service import handler_factory
from triton_dev.serve.pytest_jobs import snapshot, artifact


def wait(manager, run_id, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = manager.read(run_id)
        if record['state'] not in {'queued', 'running'}:
            return record
        time.sleep(.03)
    pytest.fail('pytest task did not reach terminal state')


def manager_for(tmp_path, content):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'test_cases.py').write_text(content)
    return TaskManager(tmp_path / 'tasks', {'suite': {'kind': 'pytest', 'python': sys.executable,
        'cwd': str(project), 'argv': ['test_cases.py'], 'timeout': 30}}), project


def test_real_collection_phases_context_and_failed_rerun_use_frozen_source(tmp_path):
    manager, project = manager_for(tmp_path, '''import pytest
@pytest.fixture
def setup_error(): raise RuntimeError('SETUP_EVIDENCE')
@pytest.fixture
def teardown_error():
    yield
    raise RuntimeError('TEARDOWN_EVIDENCE')
@pytest.mark.parametrize('n', [1, 2])
def test_parameter(n, triton_dev_context, record_property, triton_dev_artifact_dir):
    triton_dev_context.update(shape=[n, 64], seed=42)
    record_property('component', 'compiler')
    (triton_dev_artifact_dir / 'input.json').write_text(str(n))
    print('CAPTURED_CASE_OUTPUT')
    assert n == 1, 'CALL_EVIDENCE'
def test_setup(setup_error): pass
def test_teardown(teardown_error): pass
@pytest.mark.skip(reason='unsupported device')
def test_skip(): pass
@pytest.mark.xfail(reason='known issue')
def test_xfail(): assert False
''')
    try:
        collected = wait(manager, manager.submit('suite', 'collect')['id'])
        assert collected['state'] == 'passed', collected
        cases = collected['collection']
        assert len(cases) == 6
        assert cases[0]['parameters'] == {'n': '1'}
        assert 'triton_dev_context' in cases[0]['fixtures']
        # Source edits after collection must not silently change the submitted experiment.
        (project / 'test_cases.py').write_text('raise RuntimeError("NEW_SOURCE_MUST_NOT_RUN")')
        selected = [c['nodeid'] for c in cases]
        submitted = manager.run_pytest(collected['id'], selected, 'case', 'run')
        assert manager.run_pytest(collected['id'], selected, 'case', 'run')['id'] == submitted['id']
        with pytest.raises(ToolError) as exc:
            manager.run_pytest(collected['id'], selected[:1], 'case', 'run')
        assert exc.value.code == 'IDEMPOTENCY_CONFLICT'
        result = wait(manager, submitted['id'])
        assert result['state'] == 'failed', result
        assert len(result['artifacts']) == 2
        assert artifact(manager.store, result['id'], result['artifacts'][0]['id']) in (b'1', b'2')
        assert result['summary']['failed'] == 3
        assert result['summary']['passed'] == 1
        assert result['summary']['skipped'] == 1
        assert result['summary']['xfailed'] == 1
        assert {r['failure_phase'] for r in result['test_results'] if r['outcome'] == 'failed'} == {'setup', 'call', 'teardown'}
        call = result['test_results'][1]['stages'][1]
        assert call['context'] == {'shape': [2, 64], 'seed': 42}
        assert 'CAPTURED_CASE_OUTPUT' in call['stdout']
        assert 'CALL_EVIDENCE' in call['longrepr']
        assert call['properties'] == [['component', 'compiler']]
        rerun = wait(manager, manager.rerun(result['id'], 'failed', 'retry')['id'])
        assert rerun['parent'] == result['id']
        assert all(c['before'] == c['after'] == 'failed' for c in rerun['comparison'])
        assert rerun['summary']['total'] == rerun['summary']['failed'] == 3
        assert result['source_snapshot'] == rerun['source_snapshot']
        assert manager.read(result['id'])['summary']['total'] == 6
        with pytest.raises(ToolError):
            manager.run_pytest(collected['id'], ['../outside.py'], 'case', 'invalid')
    finally:
        manager.close()


def test_case_process_and_filesystem_isolation_versus_session(tmp_path, monkeypatch):
    monkeypatch.setenv('TRITON_DEV_SERVER_TOKEN', 'must-not-reach-test-process')
    manager, project = manager_for(tmp_path, '''import os
from pathlib import Path
STATE = []
def test_a():
    STATE.append('leak')
    Path('leaked.txt').write_text('leak')
    (Path.home() / 'leak').write_text('leak')
    assert os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
    assert 'TRITON_DEV_SERVER_TOKEN' not in os.environ
def test_b():
    assert not STATE
    assert not Path('leaked.txt').exists()
    assert not (Path.home() / 'leak').exists()
''')
    try:
        collection = wait(manager, manager.submit('suite', 'collect')['id'])
        ids = [c['nodeid'] for c in collection['collection']]
        isolated = wait(manager, manager.run_pytest(collection['id'], ids, 'case', 'case')['id'])
        assert isolated['state'] == 'passed', isolated
        assert isolated['summary']['passed'] == 2
        assert not (project / 'leaked.txt').exists()
        session = wait(manager, manager.run_pytest(collection['id'], ids, 'session', 'session')['id'])
        assert session['summary']['failed'] == 1
        assert session['test_results'][1]['failure_phase'] == 'call'
    finally:
        manager.close()


def test_collection_failure_and_runtime_drift_are_explicit(tmp_path):
    manager, project = manager_for(tmp_path, 'raise RuntimeError("COLLECTION_BROKEN")\n')
    try:
        broken = wait(manager, manager.submit('suite', 'broken')['id'])
        assert broken['error']['code'] == 'COLLECTION_FAILED'
        assert any(s['type'] == 'collection_error' and 'COLLECTION_BROKEN' in s['longrepr'] for s in broken['stages'])
        (project / 'test_cases.py').write_text('def test_ok(): pass\n')
        good = wait(manager, manager.submit('suite', 'good')['id'])
        manager.store.update(good['id'], runtime={'unexpected': 'drift'})
        result = wait(manager, manager.run_pytest(good['id'], ['test_cases.py::test_ok'], 'case', 'drift')['id'])
        assert result['error']['code'] == 'ENVIRONMENT_CHANGED'
        assert result['summary']['incomplete'] == 1
        assert not result['summary']['passed']
    finally:
        manager.close()


def test_cancel_keeps_live_stage_and_marks_unfinished_cases(tmp_path):
    manager, _ = manager_for(tmp_path, '''import time
def test_slow():
    time.sleep(20)
def test_next(): pass
''')
    try:
        collection = wait(manager, manager.submit('suite', 'collect')['id'])
        ids = [c['nodeid'] for c in collection['collection']]
        run_id = manager.run_pytest(collection['id'], ids, 'case', 'run')['id']
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            live = manager.read(run_id)
            if any(s.get('when') == 'setup' for s in live['stages']):
                break
            time.sleep(.03)
        else:
            pytest.fail('no live setup event')
        assert live['summary']['passed'] == 0
        manager.cancel(run_id)
        record = wait(manager, run_id)
        assert record['state'] == 'cancelled'
        assert record['summary']['incomplete'] == 2
        assert len(record['attempts']) == 1
        with pytest.raises(ToolError) as error:
            manager.rerun(run_id, 'failed', 'invalid-failed')
        assert error.value.code == 'NO_FAILED_CASES'
        assert manager.rerun(run_id, 'all', 'all')['parent'] == run_id
    finally:
        manager.close()


def test_snapshot_rejects_links_and_server_state_inside_source(tmp_path):
    source = tmp_path / 'project'
    source.mkdir()
    with pytest.raises(ToolError):
        snapshot(source, source / 'recursive-state')
    (source / 'outside').symlink_to(tmp_path / 'outside')
    with pytest.raises(ToolError) as error:
        snapshot(source, tmp_path / 'snapshot')
    assert error.value.code == 'UNSUPPORTED'


def test_pytest_http_collection_selection_and_rerun(tmp_path):
    manager, _ = manager_for(tmp_path, 'def test_failure(): assert False, "HTTP_EVIDENCE"\n')
    token = 'test-only-local-token-12345'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory([], manager, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, body=None):
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req) as response:
            return json.load(response)['data']
    try:
        assert request('/jobs')[0]['kind'] == 'pytest'
        collected = wait(manager, request('/tasks', {'job_id': 'suite', 'idempotency_key': 'c'})['id'])
        run = request('/pytest/runs', {'collection_id': collected['id'], 'nodeids': ['test_cases.py::test_failure'],
            'isolation': 'case', 'idempotency_key': 'r'})
        wait(manager, run['id'])
        result = request('/tasks/' + run['id'])
        assert result['summary']['failed'] == 1
        retry = request('/tasks/' + run['id'] + '/rerun', {'mode': 'failed', 'idempotency_key': 'retry'})
        assert retry['parent'] == run['id']
        assert wait(manager, retry['id'])['summary']['failed'] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        manager.close()


def test_artifact_listing_cannot_follow_case_created_symlink(tmp_path):
    manager, _ = manager_for(tmp_path, '''from pathlib import Path
def test_artifact(triton_dev_artifact_dir):
    (triton_dev_artifact_dir / "safe.txt").write_text("explicit case artifact")
    (triton_dev_artifact_dir / "escape").symlink_to("/etc/hosts")
''')
    try:
        collection = wait(manager, manager.submit('suite', 'collect')['id'])
        run = wait(manager, manager.run_pytest(collection['id'], ['test_cases.py::test_artifact'], 'case', 'run')['id'])
        assert len(run['artifacts']) == 1
        assert artifact(manager.store, run['id'], run['artifacts'][0]['id']) == b'explicit case artifact'
        with pytest.raises(ToolError):
            artifact(manager.store, run['id'], '../../etc/hosts')
    finally:
        manager.close()


def test_nested_targets_with_spaces_produce_replayable_nodeids(tmp_path):
    manager, project = manager_for(tmp_path, 'def test_root(): pass\n')
    nested = project / 'tests with spaces'
    nested.mkdir()
    (nested / 'test_nested.py').write_text('import pytest\n@pytest.mark.xfail(reason="known")\ndef test_xpass(): pass\n@pytest.mark.xfail(strict=True)\ndef test_strict(): pass\n')
    manager.jobs['suite']['argv'] = ['tests with spaces']
    try:
        collection = wait(manager, manager.submit('suite', 'collect')['id'])
        ids = [c['nodeid'] for c in collection['collection']]
        # Duplicate metadata search roots are not a dependency version change.
        runtime = collection['runtime']
        runtime['packages'].append(runtime['packages'][0])
        manager.store.update(collection['id'], runtime=runtime)
        assert all(n.startswith('tests with spaces/test_nested.py::') for n in ids)
        result = wait(manager, manager.run_pytest(collection['id'], ids, 'case', 'run')['id'])
        assert result['summary']['xpassed'] == 1
        assert result['summary']['failed'] == 1
        assert result['summary']['incomplete'] == 0
    finally:
        manager.close()


def test_state_and_project_directory_aliases_keep_nodeids_relative(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    manager, _ = manager_for(alias, 'def test_alias(): pass\n')
    try:
        collection = wait(manager, manager.submit('suite', 'collect')['id'])
        assert [c['nodeid'] for c in collection['collection']] == ['test_cases.py::test_alias']
        result = wait(manager, manager.run_pytest(collection['id'], ['test_cases.py::test_alias'], 'case', 'run')['id'])
        assert result['summary']['passed'] == 1
    finally:
        manager.close()
