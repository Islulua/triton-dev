import sys
import threading

import pytest

from triton_dev.common.contracts import ToolError, run_process
from triton_dev.execution.records import RunStore, start, rerun, diff, execute_record


def test_recorded_pytest_phases_and_failed_rerun(tmp_path):
    tests = tmp_path / 'test_example.py'
    tests.write_text('import pytest\n'
                     '@pytest.fixture\ndef broken():\n    raise RuntimeError("setup failure")\n'
                     'def test_setup(broken): pass\n'
                     'def test_call(): assert False, "call failure"\n'
                     'def test_pass(): pass\n')
    store = RunStore(tmp_path / 'records')
    first = start(store, [tests.name], cwd=tmp_path, pytest=True)
    assert first['state'] == 'failed'
    assert {(x['when'], x['outcome']) for x in first['stages'] if x['type'] == 'stage'} >= {('setup', 'failed'), ('call', 'failed')}
    assert (store.directory(first['id']) / 'stdout.log').is_file()
    tests.write_text('def test_setup(): pass\ndef test_call(): pass\ndef test_pass(): pass\n')
    second = rerun(store, first['id'], failed=True)
    assert second['parent'] == first['id']
    assert second['state'] == 'passed'
    assert set(second['request']['argv']) == {'test_example.py::test_setup', 'test_example.py::test_call'}
    assert diff(store, first['id'], second['id'])['changes']
    assert store.read(first['id'])['state'] == 'failed'
    assert [e['id'] for e in store.events(first['id'], after=1)] == [2, 3]


def test_streaming_limits_timeout_and_cancellation(tmp_path):
    store = RunStore(tmp_path / 'records')
    request = {'argv': [sys.executable, '-c', 'import sys; print("x"*2000000); sys.stderr.write("y"*2000000)'],
               'cwd': str(tmp_path), 'timeout': 10}
    run_id = store.create(request)
    record = execute_record(store, run_id, log_limit=1024)
    assert record['state'] == 'passed'
    assert record['result']['output_truncated'] == {'stdout': True, 'stderr': True}
    assert (store.directory(run_id) / 'stdout.log').stat().st_size == 1024
    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set)
    timer.start()
    cancelled = store.create({'argv': [sys.executable, '-c', 'import time; print("first", flush=True); time.sleep(20)'],
                              'cwd': str(tmp_path), 'timeout': 10})
    result = execute_record(store, cancelled, cancel=cancel)
    timer.join()
    assert result['state'] == 'cancelled'
    assert 'first' in result['result']['stdout']
    timed = start(store, [sys.executable, '-c', 'import time; time.sleep(20)'], cwd=tmp_path, timeout=0.1)
    assert timed['state'] == 'timeout'


def test_process_tails_are_bounded_and_both_streams_drained():
    seen = []
    result = run_process([sys.executable, '-c', 'import sys; sys.stdout.write("a"*10000); sys.stderr.write("b"*10000)'],
                         max_output=64, on_chunk=lambda name, value: seen.append((name, len(value))))
    assert len(result['stdout']) == len(result['stderr']) == 64
    assert sum(n for _, n in seen) == 20000


def test_recovery_marks_interrupted_without_reexecuting(tmp_path):
    store = RunStore(tmp_path)
    run_id = store.create({'argv': ['never-executed']})
    assert store.recover() == [run_id]
    assert store.read(run_id)['state'] == 'interrupted'
    assert not store.recover()
    with pytest.raises(ToolError):
        store.read('../escape')


def test_real_teardown_and_collection_failure(tmp_path):
    test = tmp_path / 'test_teardown.py'
    test.write_text('import pytest\n@pytest.fixture\ndef resource():\n'
                    '    yield\n    raise RuntimeError("cleanup failure")\n'
                    'def test_cleanup(resource): pass\n')
    store = RunStore(tmp_path / 'records')
    result = start(store, [test.name], cwd=tmp_path, pytest=True)
    assert any(s.get('when') == 'teardown' and s.get('outcome') == 'failed' for s in result['stages'])
    test.write_text('raise RuntimeError("collection failure")\n')
    result = start(store, [test.name], cwd=tmp_path, pytest=True)
    assert result['state'] == 'failed'
    assert result['result']['returncode'] == 2
    assert 'collection failure' in result['result']['stdout']
    with pytest.raises(ToolError) as error:
        rerun(store, result['id'], failed=True)
    assert error.value.code == 'NO_FAILED_CASES'
