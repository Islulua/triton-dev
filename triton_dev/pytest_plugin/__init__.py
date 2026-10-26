"""Explicitly loaded collection adapter; it is not auto-enabled for user's pytest."""
import json
import hashlib
import os
import tempfile
import time
import threading
from pathlib import Path

import pytest

_LOG_LOCK = threading.Lock()


def pytest_addoption(parser):
    parser.addoption("--triton-dev-collection-output", default=None)
    parser.addoption("--triton-dev-events", default=None)
    parser.addoption("--triton-dev-durations", type=int, default=None)


def pytest_configure(config):
    durations = config.getoption('--triton-dev-durations')
    if durations is not None:
        config.option.durations = durations or None
    config.addinivalue_line("markers", "case_id(value): stable logical test identifier")
    if hasattr(config, 'workerinput') and config.getoption('--triton-dev-events'):
        worker = worker_identity(config)
        root = Path(config.getoption('--triton-dev-events')).parent / 'workers' / worker
        mapping = {'HOME': 'home', 'TMPDIR': 'tmp', 'TMP': 'tmp', 'TEMP': 'tmp',
                   'XDG_CACHE_HOME': 'cache', 'TRITON_CACHE_DIR': 'triton-cache',
                   'CUDA_CACHE_PATH': 'cuda-cache'}
        for key, folder in mapping.items():
            target = root / folder
            target.mkdir(parents=True, exist_ok=True)
            os.environ[key] = str(target)
        artifacts = os.environ.get('TRITON_DEV_ARTIFACTS')
        if artifacts:
            os.environ['TRITON_DEV_ARTIFACTS'] = str(Path(artifacts) / worker)
        tempfile.tempdir = None
    event(config, {'type': 'worker_started'})


def pytest_collection_finish(session):
    output = session.config.getoption("--triton-dev-collection-output")
    if output:
        data = [{"nodeid": item.nodeid, "path": str(item.path),
                 "markers": sorted({m.name for m in item.iter_markers()}),
                 "fixtures": sorted(item.fixturenames), "line": item.location[1] + 1,
                 "logical_nodeid": item.nodeid.rsplit('::', 1)[0] + '::' + (getattr(item, 'originalname', None) or item.name),
                 "parameter_id": getattr(getattr(item, 'callspec', None), 'id', None),
                 "parameters": {k: repr(v)[:512] for k, v in getattr(getattr(item, "callspec", None), "params", {}).items()},
                 "case_id": next((m.args[0] for m in item.iter_markers("case_id") if m.args), None)}
                for item in session.items]
        Path(output).write_text(json.dumps(data), encoding="utf-8")


def event(config, data):
    output = config.getoption('--triton-dev-events')
    if output:
        # Separate worker files prevent interleaved JSON and duplicate controller reports.
        target = Path(output)
        if hasattr(config, 'workerinput'):
            target = target.with_name(target.stem + f'.{worker_identity(config)}.{os.getpid()}' + target.suffix)
        data['worker_id'] = worker_identity(config)
        data['pid'] = os.getpid()
        data['time'] = time.time()
        with target.open('a') as stream:
            stream.write(json.dumps(data, default=str) + '\n')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    worker_log(item.config, f"[{report.when}] {report.nodeid}: {report.outcome}\n")
    for title, text in report.sections:
        if title.endswith(' ' + report.when):
            worker_log(item.config, f'--- {title} ---\n{text}\n')
    if report.failed:
        worker_log(item.config, str(report.longrepr)[:32768] + '\n')
    event(item.config, {'type': 'stage', 'nodeid': report.nodeid, 'when': report.when,
                       'outcome': report.outcome, 'duration': report.duration,
                       'wasxfail': getattr(report, 'wasxfail', None),
                       'longrepr': str(report.longrepr)[:32768] if report.failed or report.skipped else None,
                       'stdout': report.capstdout[-16384:], 'stderr': report.capstderr[-16384:],
                       'sections': [(name, text[-16384:]) for name, text in report.sections[-8:]],
                       'properties': list(report.user_properties),
                       'context': getattr(item, '_triton_dev_context', {})})


def pytest_sessionfinish(session, exitstatus):
    event(session.config, {'type': 'session', 'exitstatus': int(exitstatus),
                          'collection_errors': session.testsfailed if session.testscollected == 0 else None})


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        event(collector.config, {'type': 'collection_error', 'nodeid': report.nodeid,
                                'longrepr': str(report.longrepr)[:32768]})


@pytest.fixture
def triton_dev_context(request):
    """Optional structured debug evidence; no tensor upload or model calls."""
    request.node._triton_dev_context = {}
    return request.node._triton_dev_context


@pytest.fixture
def triton_dev_artifact_dir(request, tmp_path):
    """A case-specific directory for explicitly written debug artifacts."""
    root = os.environ.get('TRITON_DEV_ARTIFACTS')
    if not root:
        directory = tmp_path / 'artifacts'
        directory.mkdir(exist_ok=True)
        return directory
    directory = Path(root) / hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:20]
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def worker_identity(config):
    if hasattr(config, 'workerinput'):
        return config.workerinput.get('workerid', 'worker')
    return 'controller' if getattr(config.option, 'numprocesses', 0) else 'main'


def worker_log(config, text):
    output = config.getoption('--triton-dev-events')
    if not output:
        return
    with _LOG_LOCK:
        target = Path(output).parent / f'worker-{worker_identity(config)}.log'
        size = target.stat().st_size if target.exists() else 0
        data = str(text).encode('utf-8', 'replace')
        remaining = max(0, 8 * 1024 * 1024 - size)
        if len(data) > remaining:
            target.with_suffix('.truncated').touch()
        if remaining:
            with target.open('ab') as stream:
                stream.write(data[:remaining])


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    event(item.config, {'type': 'test_started', 'nodeid': item.nodeid})
    worker_log(item.config, f'[start] {item.nodeid}\n')
    yield


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    event(node.config, {'type': 'worker_exit', 'target_worker_id': node.gateway.id,
                        'error': str(error) if error else None})


@pytest.fixture
def triton_dev_log(request):
    """Write explicit progress to this worker's bounded file while the test is running."""
    return lambda message: worker_log(request.config, f'[{time.time():.3f}] {request.node.nodeid}: {message}\n')
