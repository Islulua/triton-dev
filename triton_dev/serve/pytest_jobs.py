"""Registered pytest projects: source snapshots, case processes and report views.

This isolates cooperative tests, not hostile code, devices or the network.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from triton_dev.common.contracts import ToolError, run_process
from triton_dev.execution.records import RunStore, TERMINAL, execute_record, request_environment

EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
            '.ruff_cache', '.mypy_cache', '.tox', '.env', '.DS_Store'}
RUNTIME_PROBE = ('import json,sys,platform,importlib.metadata as m;'
                 'print(json.dumps({"python":sys.version,"platform":platform.platform(),'
                 '"packages":sorted({(d.metadata["Name"],d.version) for d in m.distributions()})}))')


def snapshot(source, destination):
    """Copy regular files with a bounded manifest; reject links instead of following them."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir() or destination.is_relative_to(source):
        raise ToolError('INVALID_PROJECT', 'Project must exist and exclude server state directory')
    destination.mkdir(parents=True, exist_ok=False)
    entries, size = [], 0
    for folder, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in [*dirs, *sorted(files)]:
            path = Path(folder) / name
            if path.is_symlink():
                raise ToolError('UNSUPPORTED', 'Project snapshots do not follow symlinks')
        for name in sorted(files):
            if name in EXCLUDED or name.startswith('.env.') or name.endswith('.pyc'):
                continue
            path = Path(folder) / name
            if not path.is_file():
                raise ToolError('UNSUPPORTED', 'Project snapshots require regular files')
            size += path.stat().st_size
            if size > 100 * 1024 * 1024 or len(entries) >= 10000:
                raise ToolError('PROJECT_TOO_LARGE', 'Snapshot budget is 100 MiB / 10000 files')
            relative = path.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            entries.append((relative.as_posix(), hashlib.sha256(target.read_bytes()).hexdigest()))
    digest = hashlib.sha256(json.dumps(entries).encode()).hexdigest()
    return {'sha256': digest, 'files': len(entries), 'bytes': size}


def read_events(directory):
    stages = []
    for file in sorted(Path(directory).glob('pytest-events*.jsonl')):
        for line in file.read_text(errors='replace').splitlines():
            try:
                stages.append(json.loads(line))
            except ValueError:
                # A live reader may see the last line before its write completes.
                continue
    return sorted(stages, key=lambda s: s.get('time', 0))


def summarize(stages, nodeids, terminal=False):
    """A failed teardown overrides a passed call; never turn missing reports into passes."""
    grouped = {nodeid: [] for nodeid in nodeids}
    for stage in stages:
        if stage.get('type') == 'stage':
            grouped.setdefault(stage['nodeid'], []).append(stage)
    results = []
    for nodeid, reports in grouped.items():
        by_phase = {r['when']: r for r in reports}
        failure = next((r for r in reports if r['outcome'] == 'failed'), None)
        skipped = next((r for r in reports if r['outcome'] == 'skipped'), None)
        call = by_phase.get('call')
        if failure:
            outcome = 'failed'
        elif skipped:
            outcome = 'xfailed' if skipped.get('wasxfail') else 'skipped'
        elif call and call.get('wasxfail'):
            outcome = 'xpassed'
        elif call and call['outcome'] == 'passed' and 'teardown' in by_phase:
            outcome = 'passed'
        else:
            outcome = 'incomplete' if terminal else 'running' if reports else 'pending'
        results.append({'nodeid': nodeid, 'outcome': outcome,
                        'failure_phase': failure['when'] if failure else None,
                        'duration': sum(r.get('duration', 0) for r in reports), 'stages': reports})
    counts = {name: sum(r['outcome'] == name for r in results) for name in
              ('passed', 'failed', 'skipped', 'xfailed', 'xpassed', 'incomplete', 'pending', 'running')}
    return results, {'total': len(results), **counts}


def artifacts(store, record):
    found = []
    path = store.directory(record['id'])
    for attempt in record.get('attempts', []):
        base = path / 'attempts' / attempt / 'artifacts'
        if not base.is_dir() or base.is_symlink():
            continue
        for folder, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
            for name in sorted(files):
                file = Path(folder) / name
                if file.is_symlink() or not file.resolve().is_relative_to(base) or not file.is_file():
                    continue
                relative = file.relative_to(path).as_posix()
                found.append({'id': hashlib.sha256(relative.encode()).hexdigest(),
                              'path': relative, 'size': file.stat().st_size})
                if len(found) >= 1000:
                    return found
    return found


def artifact(store, run_id, artifact_id):
    record = store.read(run_id)
    for item in artifacts(store, record):
        if item['id'] == artifact_id:
            if item['size'] > 10 * 1024 * 1024:
                raise ToolError('ARTIFACT_TOO_LARGE', 'Download budget is 10 MiB per file')
            return (store.directory(run_id) / item['path']).read_bytes()
    raise ToolError('ARTIFACT_NOT_FOUND', 'No registered artifact with this ID')


def log_tail(file, limit=65536):
    if not file.is_file():
        return '', False
    with file.open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        return stream.read(limit).decode('utf-8', 'replace'), size > limit


def worker_views(store, record):
    terminal = record['state'] in TERMINAL
    workers = {}
    def ensure(name):
        return workers.setdefault(name, {'worker_id': name, 'pids': set(), 'state': 'pending',
                                         'events': [], 'nodeids': set(), 'log': '',
                                         'tail_truncated': False, 'disk_truncated': False})
    if record['request'].get('isolation') == 'xdist':
        for n in range(record['request'].get('workers', 1)):
            ensure(f'gw{n}')
    for event in record['stages']:
        name = event.get('worker_id')
        if not isinstance(name, str) or not re.fullmatch(r'(gw[0-9]+|main|controller)', name):
            continue
        worker = ensure(name)
        if event.get('pid'):
            worker['pids'].add(event['pid'])
        worker['events'].append(event)
        if event.get('nodeid') and event['type'] in {'stage', 'test_started'}:
            worker['nodeids'].add(event['nodeid'])
        if event['type'] == 'worker_started':
            worker['state'] = 'running'
        elif event['type'] == 'session':
            worker['state'] = 'finished'
        elif event['type'] == 'worker_exit':
            target = ensure(event['target_worker_id'])
            target['state'] = 'crashed' if event.get('error') else 'finished'
            target['error'] = event.get('error')
    path = store.directory(record['id'])
    for name, worker in workers.items():
        for attempt in record.get('attempts', []):
            file = path / 'attempts' / attempt / f'worker-{name}.log'
            text, truncated = log_tail(file)
            combined = worker['log'] + text
            worker['log'] = combined[-65536:]
            worker['tail_truncated'] |= truncated or len(combined) > 65536
            worker['disk_truncated'] |= file.with_suffix('.truncated').exists()
        if terminal and worker['state'] == 'running':
            worker['state'] = record['state'] if record['state'] in {'cancelled', 'timeout'} else 'interrupted'
        elif terminal and worker['state'] == 'pending':
            worker['state'] = 'not_started'
        _, worker['summary'] = summarize(worker['events'], sorted(worker['nodeids']), terminal)
        worker['pids'] = sorted(worker['pids'])
        worker['nodeids'] = sorted(worker['nodeids'])
        del worker['events']
    return sorted(workers.values(), key=lambda w: (w['worker_id'] == 'controller', w['worker_id']))


def view(store, record):
    if record['request'].get('kind') != 'pytest':
        return record
    record = dict(record)
    path = store.directory(record['id'])
    stages = read_events(path)
    for attempt in record.get('attempts', []):
        stages.extend(read_events(path / 'attempts' / attempt))
    record['stages'] = stages
    record['artifacts'] = artifacts(store, record) if record['state'] in TERMINAL else []
    nodeids = record['request'].get('nodeids', [])
    record['test_results'], record['summary'] = summarize(stages, nodeids, record['state'] in TERMINAL)
    record['worker_reports'] = worker_views(store, record)
    for item in record['test_results']:
        item['workers'] = sorted({s['worker_id'] for s in item['stages'] if s.get('worker_id')})
    if record.get('parent'):
        previous = store.read(record['parent'])
        before = read_events(store.directory(previous['id']))
        for attempt in previous.get('attempts', []):
            before.extend(read_events(store.directory(previous['id']) / 'attempts' / attempt))
        previous_results, _ = summarize(before, previous['request'].get('nodeids', []), True)
        lookup = {r['nodeid']: r for r in previous_results}
        record['comparison'] = [{'nodeid': r['nodeid'],
                                 'before': lookup.get(r['nodeid'], {}).get('outcome'),
                                 'after': r['outcome'],
                                 'before_phase': lookup.get(r['nodeid'], {}).get('failure_phase'),
                                 'after_phase': r['failure_phase']} for r in record['test_results']]
    if record['state'] in {'queued', 'running'}:
        for stream in ('stdout', 'stderr'):
            files = [path / (stream + '.log'), *[
                path / 'attempts' / a / (stream + '.log') for a in record.get('attempts', [])]]
            record.setdefault('live_logs', {})[stream] = ''.join(
                file.read_bytes()[-65536:].decode('utf-8', 'replace') for file in files if file.exists())[-65536:]
    return record


def canonical_runtime(runtime):
    result = dict(runtime)
    if 'packages' in result:
        result['packages'] = sorted({(re.sub(r'[-_.]+', '-', name).lower(), version)
                                     for name, version in result['packages']})
    return result


def _runtime(request, cancel):
    environment = request.get('environment')
    env = request_environment(request)
    python = environment['interpreter'] if environment else request.get('python', sys.executable)
    env['PYTHONNOUSERSITE'] = '1'
    result = run_process([python, '-c', RUNTIME_PROBE], env=env, timeout=30, cancel=cancel)
    if result['returncode']:
        raise ToolError('RUNTIME_PROBE_FAILED', 'Cannot inspect registered interpreter', details=result)
    return json.loads(result['stdout'])


def execute(store, run_id, cancel):
    record = store.read(run_id)
    request = record['request']
    path = store.directory(run_id)
    store.update(run_id, state='running', started_at=time.time())
    store.event(run_id, 'running')
    try:
        runtime = _runtime(request, cancel)
        store.update(run_id, runtime=runtime)
        expected = request.get('expected_runtime')
        if expected is not None and canonical_runtime(runtime) != canonical_runtime(expected):
            old, new = canonical_runtime(expected), canonical_runtime(runtime)
            before = set(old.get('packages', []))
            after = set(new.get('packages', []))
            raise ToolError('ENVIRONMENT_CHANGED', 'Interpreter packages differ from collection snapshot; recollect explicitly',
                            details={'packages_removed': sorted(before - after),
                                     'packages_added': sorted(after - before),
                                     'python_changed': old.get('python') != new.get('python'),
                                     'platform_changed': old.get('platform') != new.get('platform')})
        source = store.directory(request['source_id']) / 'source' if request.get('source_id') else Path(request['cwd'])
        frozen = path / 'source'
        manifest = snapshot(source, frozen)
        if request.get('source_sha256') and manifest['sha256'] != request['source_sha256']:
            raise ToolError('SOURCE_CHANGED', 'Stored collection source snapshot changed')
        store.update(run_id, source_snapshot=manifest, runtime=runtime,
                     isolation={'process': request.get('isolation', 'session'), 'workspace': 'copied',
                                'workers': request.get('workers', 1),
                                'worker_workspace': 'shared_source_within_run' if request.get('isolation') == 'xdist' else 'per_invocation',
                                'home_tmp_cache': 'private', 'devices_network': 'shared',
                                'python_packages': 'registered interpreter, version checked; not copied'})
        is_collect = request['operation'] == 'collect'
        if not is_collect and request.get('isolation') == 'xdist':
            packages = dict(canonical_runtime(runtime)['packages'])
            if 'pytest-xdist' not in packages:
                raise ToolError('PYTEST_XDIST_MISSING', 'Install pytest-xdist in the registered test interpreter before collecting this environment')
        targets = [request['argv']] if is_collect or request.get('isolation') in {'session', 'xdist'} else [[n] for n in request['nodeids']]
        if manifest['bytes'] * (len(targets) + 1) > 1024 * 1024 * 1024:
            raise ToolError('WORKSPACE_BUDGET_EXCEEDED', 'Copied workspaces exceed 1 GiB; use a smaller project or session isolation')
        attempts, results = [], []
        started = time.monotonic()
        children = RunStore(path / 'attempts')
        for index, selection in enumerate(targets):
            if cancel.is_set():
                raise ToolError('CANCELLED', 'Stopped before next pytest process')
            remaining = request.get('timeout', 300) - (time.monotonic() - started)
            if remaining <= 0:
                raise ToolError('TIMEOUT', 'Run timeout exhausted between cases')
            workspace = path / f'workspace-{index}'
            snapshot(frozen, workspace)
            child = {**request, 'argv': selection, 'cwd': str(workspace), 'pytest': True,
                     'collect_only': is_collect, 'private_environment': True, 'timeout': remaining}
            attempt = children.create(child)
            attempts.append(attempt)
            store.update(run_id, attempts=attempts)
            result = execute_record(children, attempt, cancel=cancel)
            results.append(result)
            if is_collect:
                output = children.directory(attempt) / 'collection.json'
                if result['result'] and result['result'].get('returncode') in (0, 5) and output.exists():
                    cases = json.loads(output.read_text())
                    if len(cases) > 2000:
                        raise ToolError('TOO_MANY_CASES', 'Collection budget is 2000 cases')
                    store.update(run_id, collection=cases)
                else:
                    store.update(run_id, result=result.get('result'))
                    raise ToolError('COLLECTION_FAILED', 'Inspect collection events and process log')
            threshold = request.get('extensions', {}).get('max_failures', 0)
            if not is_collect and threshold:
                partial = view(store, store.read(run_id))
                if partial['summary']['failed'] >= threshold:
                    store.update(run_id, stopped_reason='max_failures')
                    break
            if result['state'] in {'timeout', 'cancelled', 'error'}:
                break
        state = next((r['state'] for r in results if r['state'] in {'timeout', 'cancelled', 'error'}), None)
        state = state or ('failed' if any(r['state'] == 'failed' for r in results) else 'passed')
        # pytest uses exit code 5 for a valid empty collection, not a passed test run.
        if is_collect and 'collection' in store.read(run_id):
            state = 'passed'
        codes = [(r.get('result') or {}).get('returncode') for r in results]
        aggregate = {'returncode': next((code for code in codes if code),
                                        0 if codes and all(code is not None for code in codes) else None),
                     'process_returncodes': codes,
                     'stdout': '\n'.join((r.get('result') or {}).get('stdout', '') for r in results)[-1048576:],
                     'stderr': '\n'.join((r.get('result') or {}).get('stderr', '') for r in results)[-1048576:]}
        store.update(run_id, state=state, finished_at=time.time(), result=aggregate)
        store.event(run_id, state)
    except (ToolError, OSError, ValueError, KeyError) as exc:
        state = {'CANCELLED': 'cancelled', 'TIMEOUT': 'timeout'}.get(getattr(exc, 'code', ''), 'error')
        if isinstance(exc, ToolError) and exc.details.get('returncode') is not None:
            store.update(run_id, result=exc.details)
        store.update(run_id, state=state, finished_at=time.time(), error={
            'code': getattr(exc, 'code', 'PYTEST_JOB_ERROR'), 'message': str(exc),
            'details': exc.details if isinstance(exc, ToolError) else {}})
        store.event(run_id, state)
    return view(store, store.read(run_id))
