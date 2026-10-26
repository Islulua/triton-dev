import json
import math
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.serve.profiling import ProfileStore, MockBoardProfiler, chrome_trace, summarize, catalog, html_report
from triton_dev.serve.service import handler_factory
from triton_dev.serve.tasks import TaskManager


def selection(**changes):
    return dict(case_id='matmul-1024', environment_id='mock-baseline', warmup=3,
                repeats=20, seed=42, adapter='mock', idempotency_key='profile-test') | changes


def test_capture_statistics_trace_and_restart(tmp_path):
    store = ProfileStore(tmp_path)
    report = store.create(selection())
    capture, summary = report['capture'], report['summary']
    assert report['state'] == 'generated' and report['correctness'] == 'not_checked'
    assert capture == MockBoardProfiler().capture(selection())
    assert len(capture['samples']) == 20 and len(capture['events']) == 1160
    assert capture['warmup_excluded'] == 3
    values = sorted(s['device_us'] for s in capture['samples'])
    assert summary['p95_us'] == values[18]
    assert summary['mean_us'] == pytest.approx(sum(values) / 20)
    assert summary['tflops'] == pytest.approx(2 * 1024**3 / (summary['mean_us'] * 1e6))
    assert sum(k['share_pct'] for k in summary['kernels']) == pytest.approx(100)
    assert sum(k['total_us'] for k in summary['kernels']) / 20 == pytest.approx(summary['kernel_work_mean_us'])
    assert summary['wall_mean_us'] > summary['mean_us']
    assert ProfileStore(tmp_path).read(report['id']) == report
    assert store.create(selection())['id'] == report['id']
    with pytest.raises(ToolError, match='already used'):
        store.create(selection(repeats=21))
    trace = chrome_trace(report)
    slices = [e for e in trace['traceEvents'] if e['ph'] == 'X']
    assert len(slices) == 1160 and len({e['tid'] for e in slices}) == 11
    assert sum(e['dur'] for e in slices if e['cat'] == 'kernel') == pytest.approx(summary['category_us']['kernel'])
    assert all(e['ts'] >= 0 and e['dur'] > 0 for e in slices)
    assert trace['metadata']['source'] == 'mock_board'


def test_environment_changes_and_single_sample(tmp_path):
    store = ProfileStore(tmp_path)
    a = store.create(selection(repeats=1))
    b = store.create(selection(repeats=1, environment_id='mock-candidate', idempotency_key='candidate'))
    assert b['summary']['kernel_work_mean_us'] / a['summary']['kernel_work_mean_us'] == pytest.approx(1.23, abs=.001)
    assert a['summary']['p95_us'] == a['summary']['mean_us']
    assert b['capture']['environment']['revision'] != a['capture']['environment']['revision']
    c = store.create(selection(case_id='softmax-4096', idempotency_key='softmax'))
    assert c['summary']['bound_hint'] == 'memory'
    assert math.isfinite(c['summary']['roof_efficiency_pct'])
    with pytest.raises(ToolError):
        store.read('../../outside')


@pytest.mark.parametrize('changes', [dict(repeats=0), dict(repeats=101), dict(repeats=True),
    dict(seed=-1), dict(warmup=21), dict(repeats='20'), dict(adapter='real'),
    dict(case_id='../x'), dict(environment_id='latest'), dict(idempotency_key='x' * 101),
    dict(argv=['python']), dict(seed=3.5)])
def test_invalid_selection_never_writes_report(tmp_path, changes):
    store = ProfileStore(tmp_path)
    with pytest.raises(ToolError):
        store.create(selection(**changes))
    assert not list(tmp_path.glob('profile_*'))


def test_fixture_matches_backend_contract():
    preview = json.loads((Path(__file__).parents[3] / 'frontend/src/profiling-preview.json').read_text())
    assert preview['catalog'] == catalog()
    assert preview['report']['capture'] == MockBoardProfiler().capture(preview['report']['request'])
    assert preview['report']['summary'] == summarize(preview['report']['capture'])
    assert preview['trace'] == chrome_trace(preview['report'])
    assert preview['html'] == html_report(preview['report'])


def test_real_http_profile_flow_and_auth(tmp_path):
    manager = TaskManager(tmp_path / 'tasks', {'noop': {'argv': ['true'], 'cwd': str(tmp_path)}})
    token = 'test-profiling-only-token'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory([], manager, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def api(path, data=None, authorized=True):
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/profiling/' + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + token} if authorized else {})
        with urllib.request.urlopen(req) as response:
            return json.load(response)['data']
    try:
        with pytest.raises(urllib.error.HTTPError) as failure:
            api('catalog', authorized=False)
        assert failure.value.code == 401
        assert len(api('catalog')['cases']) == 3
        report = api('reports', selection())
        assert api('reports')[0]['id'] == report['id']
        assert api('reports/' + report['id']) == report
        assert api('reports/' + report['id'] + '/trace') == chrome_trace(report)
        assert api('reports/' + report['id'] + '/html')['html'] == html_report(report)
        with pytest.raises(urllib.error.HTTPError) as failure:
            api('reports', selection(adapter='board'))
        assert failure.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        manager.close()


def test_portable_html_escapes_capture_strings(tmp_path):
    report = ProfileStore(tmp_path).create(selection())
    report['capture']['case']['name'] = '<script>alert(1)</script>'
    report['capture']['environment']['revision'] = '<img src=x onerror=alert(1)>'
    exported = html_report(report)
    assert '<script>' not in exported and '<img' not in exported
    assert '&lt;script&gt;' in exported and 'mock_board' in exported
    assert '<svg' in exported and '<link' not in exported


@pytest.mark.parametrize('case_id', ['matmul-1024', 'matmul-4096', 'softmax-4096'])
def test_pipeline_dependencies_resources_and_elapsed_time(case_id):
    capture = MockBoardProfiler().capture(selection(case_id=case_id, repeats=2))
    events = capture['events']
    lookup = {e['id']: e for e in events}
    for event in events:
        assert event['duration_us'] > 0
        for parent_id in event['depends_on']:
            parent = lookup[parent_id]
            assert parent['iteration'] == event['iteration']
            assert parent['start_us'] + parent['duration_us'] <= event['start_us'] + .001
    for track in {e['track'] for e in events}:
        lane = sorted([e for e in events if e['track'] == track], key=lambda e: e['start_us'])
        assert all(a['start_us'] + a['duration_us'] <= b['start_us'] + .001 for a, b in zip(lane, lane[1:]))
    summary = summarize(capture)
    assert summary['timing_basis'] == 'device_pipeline_span'
    assert summary['concurrency']['max_active_engines'] >= 2
    assert 0 < summary['concurrency']['overlap_pct'] <= 100
    assert all(0 <= engine['window_pct'] <= 100.001 for engine in summary['engines'])
    for sample in capture['samples']:
        device = [e for e in events if e['iteration'] == sample['iteration'] and e['category'] in {'kernel', 'transfer', 'sync'}]
        span = max(e['start_us'] + e['duration_us'] for e in device) - min(e['start_us'] for e in device)
        assert sample['device_us'] == pytest.approx(span, abs=.001)
        assert sum(e['duration_us'] for e in device) > span
        # A buffer slot is not reused before the earlier tile releases its output.
        for tile in range(2, 8):
            prefetch = next(e for e in device if e['tile'] == tile and e['name'] == 'prefetch_input')
            release = next(e for e in device if e['tile'] == tile - 2 and e['name'] == 'signal_buffer_reuse')
            assert release['id'] in prefetch['depends_on']
    report = {'id': 'test-pipeline', 'capture': capture}
    trace = chrome_trace(report)
    starts = {e['id']: e for e in trace['traceEvents'] if e['ph'] == 's'}
    finishes = {e['id']: e for e in trace['traceEvents'] if e['ph'] == 'f'}
    assert starts.keys() == finishes.keys() and len(starts) > 80
    assert all(starts[key]['ts'] <= finishes[key]['ts'] + .001 for key in starts)
