import json
import sys
import time
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

import pytest

from triton_dev.agent.regression.service import RegressionService, catalog, validate
from triton_dev.agent.regression.adapters import validate_decision
from triton_dev.common.contracts import ToolError, atomic_json, run_process
from triton_dev.serve.tasks import TaskManager
from triton_dev.serve.service import handler_factory


@pytest.mark.parametrize('scenario,expected,bad,supported', [
    ('component', 'component_supported', 'mock-sdk-20261015', ['cmodel']),
    ('interaction', 'group_supported', 'mock-sdk-20261015', ['llvm', 'cmodel']),
    ('nonmonotonic', 'component_supported', 'mock-sdk-20261013', ['cmodel']),
    ('unavailable', 'component_supported', 'mock-sdk-20261015', ['cmodel']),
    ('no_regression', 'no_regression', None, []),
    ('bad_baseline', 'baseline_invalid', None, []),
    ('flaky', 'unstable', None, []),
])
def test_real_pytest_scenarios(tmp_path, scenario, expected, bad, supported):
    service = RegressionService(tmp_path / 'regressions')
    try:
        r = service.start({'scenario': scenario}, background=False)
        assert r['state'] == 'completed', r
        assert r['result'] == expected
        assert r.get('supported_components', []) == supported
        if bad:
            assert r['boundary']['bad']['id'] == bad
            assert r['earliest_proven'] == (scenario != 'unavailable')
        if scenario == 'bad_baseline':
            assert not r['inventory'] and 'target' not in r
        if scenario == 'no_regression':
            assert not r['attribution'] and r['boundary'] is None
        for e in r['experiments']:
            proof = service.experiment(r['id'], e['id'])
            assert proof['process']['argv'][2:4] == ['-m', 'pytest']
            assert proof['stages'] and proof['observed_components'] == e['components']
        if scenario == 'component':
            replay = service.replay(r['id'], r['experiments'][2]['id'])
            assert not replay['model_called'] and replay['result']['classification'] == 'target_failure'
            report = service._dir(r['id'])
            assert (report / 'SHA256SUMS').exists()
            assert 'mock' in (report / 'report.md').read_text()
            assert run_process([sys.executable, '-m', 'pytest', '-q', 'reproduce.py'], cwd=report)['returncode'] == 1
    finally:
        service.close()


def test_budget_idempotency_recovery_and_no_reexecution(tmp_path):
    service = RegressionService(tmp_path)
    try:
        r = service.start({'max_experiments': 1}, idempotency_key='one', background=False)
        assert r['state'] == 'budget_exhausted' and len(r['experiments']) == 1
        assert service.start({'max_experiments': 1}, idempotency_key='one')['id'] == r['id']
        with pytest.raises(ToolError):
            service.start({}, idempotency_key='one')
        resumed = service.resume(r['id'], background=False)
        assert len(resumed['experiments']) == 1 and resumed['state'] == 'budget_exhausted'
        # Simulate death after result publication but before pending reconciliation.
        saved = service.read(r['id'])
        saved.update(state='interrupted', pending=saved['experiments'][0]['id'])
        saved['experiments'][0]['classification'] = 'pending'
        atomic_json(service._dir(r['id']) / 'task.json', saved)
        after = service.resume(r['id'], background=False)
        assert len(after['experiments']) == 1
        assert after['experiments'][0]['classification'] == 'passed'
    finally:
        service.close()


def test_cancel_and_restart(tmp_path):
    service = RegressionService(tmp_path)
    try:
        r = service.start({})
        service.cancel(r['id'])
        deadline = time.monotonic() + 10
        while service.read(r['id'])['state'] in {'queued', 'running'} and time.monotonic() < deadline:
            time.sleep(.02)
        assert service.read(r['id'])['state'] == 'cancelled'
        resumed = service.resume(r['id'], background=False)
        assert resumed['result'] == 'component_supported'
    finally:
        service.close()


@pytest.mark.parametrize('config', [{'argv': ['sh']}, {'adapter': 'real'}, {'repeats': True},
    {'max_seconds': float('nan')}, {'max_experiments': 0}, {'model_profile': {'provider': 'remote', 'api_key': 'unused'}},
    {'baseline': 'mock-sdk-20261019'}, {'scenario': []}])
def test_input_validation(config):
    with pytest.raises(ToolError):
        validate(config)


def test_model_no_shell_no_invented_evidence():
    c = dict(task_id='task', state_revision=1, candidates=['cmodel'], evidence_ids=['exp_1'])
    for decision in [dict(type='shell', argv=['echo']),
                     dict(type='select_candidate', task_id='task', state_revision=1, candidate_id='cmodel',
                          evidence_ids=['invented'], reason_summary='invalid')]:
        with pytest.raises(ToolError):
            validate_decision(decision, c)
    assert len(catalog()['versions']) == 10


def test_http_async_auth_and_report(tmp_path):
    manager = TaskManager(tmp_path / 'tasks', {})
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory([], manager, 'test-regression-token'))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def api(path, data=None, auth=True):
        return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/regression' + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer test-regression-token'} if auth else {}))
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            api('/catalog', auth=False)
        assert exc.value.code == 401
        with api('/tasks', {'config': {'scenario': 'no_regression', 'repeats': 1}, 'idempotency_key': 'http'}) as response:
            r = json.load(response)['data']
        deadline = time.monotonic() + 10
        while manager.regressions.read(r['id'])['state'] in {'queued', 'running'} and time.monotonic() < deadline:
            time.sleep(.03)
        with api('/tasks/' + r['id'] + '/report') as response:
            assert 'no_regression' in json.load(response)['data']['markdown']
        with api('/tasks/' + r['id'] + '/bundle') as response:
            assert response.headers['Content-Type'] == 'application/gzip'
            assert response.read()[:2] == b'\x1f\x8b'
        with pytest.raises(urllib.error.HTTPError):
            api('/tasks', {'config': {'argv': ['echo']}, 'idempotency_key': 'bad'})
    finally:
        server.shutdown()
        server.server_close()
        manager.close()


def test_cli_and_rendered_replay_command(tmp_path):
    import subprocess
    import shlex
    from triton_dev.agent.regression.reporting import markdown
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'scenario': 'no_regression', 'repeats': 1}))
    r = subprocess.run([sys.executable, '-m', 'triton_dev', 'agent', 'regression', 'start',
                        '--cache-root', str(tmp_path), '--config', str(config)], capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)['data']
    assert data['result'] == 'no_regression'
    data['experiments'][0]['classification'] = 'target_failure'
    text = markdown(data, tmp_path / 'regressions' / data['id'])
    command = shlex.split(text.split('```bash\n')[1].split('\n```')[0])
    from triton_dev.cli import parser_factory
    parsed = parser_factory().parse_args(command[1:])
    assert parsed.operation == 'replay' and parsed.cache_root == tmp_path


def test_portable_bundle_and_source_integrity(tmp_path):
    import io
    import tarfile
    import hashlib
    from triton_dev.agent.regression.reporting import bundle
    service = RegressionService(tmp_path / 'regressions')
    try:
        r = service.start({'scenario': 'bad_baseline', 'repeats': 1}, background=False)
        with tarfile.open(fileobj=io.BytesIO(bundle(service._dir(r['id']), r))) as tar:
            output = tmp_path / 'export'
            tar.extractall(output, filter='data')
            names = tar.getnames()
        assert 'reproduce.py' in names and not any('home' in n or '.lock' in n for n in names)
        for line in (output / 'SHA256SUMS').read_text().splitlines():
            sha, name = line.split('  ', 1)
            assert hashlib.sha256((output / name).read_bytes()).hexdigest() == sha
        result = run_process([sys.executable, '-m', 'pytest', '-q', 'reproduce.py'], cwd=output)
        assert result['returncode'] == 1 and 'MOCK_REGRESSION' in result['stdout']
        environment = service._dir(r['id']) / 'runs' / 'exp_0001' / 'environment.json'
        value = json.loads(environment.read_text())
        value['components']['cmodel'] = 100
        environment.write_text(json.dumps(value))
        with pytest.raises(ToolError, match='source'):
            service.replay(r['id'], 'exp_0001')
    finally:
        service.close()


def test_missing_pytest_is_infrastructure_error(tmp_path, monkeypatch):
    import triton_dev.agent.regression.service as module
    monkeypatch.setattr(module.importlib.util, 'find_spec', lambda name: None)
    service = RegressionService(tmp_path)
    try:
        task = service.start({}, background=False)
        assert task['state'] == 'error' and task['error']['code'] == 'PYTEST_UNAVAILABLE'
        assert task['result'] == 'incomplete' and not task['experiments']
    finally:
        service.close()
