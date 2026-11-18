import json
import subprocess
import sys
from pathlib import Path

import pytest
from triton_dev import cli
from triton_dev.common.contracts import ToolError
from triton_dev.harness.catalog import catalog, execute_cli


def test_catalog_covers_cli_and_daily_routes():
    value = catalog()
    assert {c['command'] for c in value['commands']} == set(cli.CATALOG)
    routes = {(r['method'], r['path']) for r in value['routes']}
    assert ('POST', '/api/pytest/runs') in routes
    assert ('POST', '/api/profiling/reports') in routes
    assert ('GET', '/api/daily/v1/batches/{batch_id}/report') in routes
    assert ('POST', '/api/ir/compilations') in routes
    assert all('sdk_root' not in c['inputSchema']['properties'] for c in value['commands'])


def test_worker_real_subprocess_and_argument_validation(tmp_path):
    def call(request):
        p = subprocess.run([sys.executable, '-m', 'triton_dev.harness', '--sdk-root',
                            str(tmp_path/'sdks'), '--cache-root', str(tmp_path/'cache')],
                           input=json.dumps(request), text=True, capture_output=True)
        return p, json.loads(p.stdout)
    p, result = call({'command': 'capabilities'})
    assert p.returncode == 0 and result['status'] == 'ok'
    p, result = call({'command': 'env.exec', 'arguments': {'command': ['touch', str(tmp_path/'bad')]}})
    assert p.returncode == 2 and result['error']['code'] == 'REGISTERED_JOB_REQUIRED'
    assert not (tmp_path/'bad').exists()
    p, result = call({'command': 'doctor', 'arguments': {'cache_root': '/tmp/escape'}})
    assert p.returncode == 2 and result['error']['code'] == 'INVALID_ARGUMENT'


def test_unknown_and_real_local_sdk_query(tmp_path):
    kwargs = {'sdk_root': tmp_path/'sdks', 'cache_root': tmp_path/'cache'}
    kwargs['sdk_root'].mkdir()
    assert execute_cli('env.sdk.list', {}, **kwargs)['status'] == 'ok'
    with pytest.raises(ToolError, match='unknown.tool'):
        execute_cli('unknown.tool', {}, **kwargs)


def test_paths_are_data_not_shell(tmp_path):
    result = execute_cli('doctor', {}, sdk_root=tmp_path/'$(touch bad)', cache_root=tmp_path/'cache')
    assert result['status'] == 'ok'
    assert not Path('bad').exists()
