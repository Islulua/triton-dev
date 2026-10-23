"""Explicitly loaded collection adapter; it is not auto-enabled for user's pytest."""
import json
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--triton-dev-collection-output", default=None)
    parser.addoption("--triton-dev-events", default=None)


def pytest_collection_finish(session):
    output = session.config.getoption("--triton-dev-collection-output")
    if output:
        data = [{"nodeid": item.nodeid, "path": str(item.path),
                 "markers": sorted({m.name for m in item.iter_markers()}),
                 "fixtures": sorted(item.fixturenames), "line": item.location[1] + 1,
                 "case_id": next((m.args[0] for m in item.iter_markers("case_id") if m.args), None)}
                for item in session.items]
        Path(output).write_text(json.dumps(data), encoding="utf-8")


def event(config, data):
    import os
    import time
    output = config.getoption('--triton-dev-events')
    if output:
        # Separate worker files prevent interleaved JSON and duplicate controller reports.
        target = Path(output)
        if hasattr(config, 'workerinput'):
            target = target.with_name(target.stem + f'.{os.getpid()}' + target.suffix)
        data['time'] = time.time()
        with target.open('a') as stream:
            stream.write(json.dumps(data, default=str) + '\n')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    event(item.config, {'type': 'stage', 'nodeid': report.nodeid, 'when': report.when,
                       'outcome': report.outcome, 'duration': report.duration,
                       'wasxfail': getattr(report, 'wasxfail', None),
                       'longrepr': str(report.longrepr)[:32768] if report.failed else None})


def pytest_sessionfinish(session, exitstatus):
    event(session.config, {'type': 'session', 'exitstatus': int(exitstatus),
                          'collection_errors': session.testsfailed if session.testscollected == 0 else None})
