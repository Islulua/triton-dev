"""Persistent regression state machine with bounded, real pytest experiments."""
import copy
import itertools
import importlib.util
import json
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from triton_dev.common.contracts import ToolError, atomic_json, file_lock, run_process
from .adapters import (MockSDKAdapter, MockModel, SCENARIOS, COMPONENTS, NODEID,
                       CASE_SOURCE, PLUGIN_SOURCE, digest, validate_decision)

ACTIVE = {'queued', 'running'}
DEFAULTS = dict(adapter='mock', scenario='component', baseline='mock-sdk-20261010',
                search_mode='earliest_verified', repeats=2, max_experiments=60,
                max_seconds=600, max_model_calls=12, model_profile={'provider': 'mock', 'model': 'mock-planner-v1'})


def catalog():
    return {'source': 'mock', 'scenarios': [{'id': k, 'name': v} for k, v in SCENARIOS.items()],
            'versions': MockSDKAdapter().inventory(), 'defaults': DEFAULTS, 'nodeid': NODEID,
            'limitations': ['模拟SDK与模型；真实CPU pytest；未执行板卡或真实包替换',
                            'HTTP仅接受登记mock场景，不接收自由命令或模型端点']}


def validate(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ToolError('INVALID_ARGUMENT', 'Unknown regression configuration field')
    spec = copy.deepcopy(DEFAULTS | data)
    if spec['adapter'] != 'mock':
        raise ToolError('UNSUPPORTED', 'Real SDK adapter is not configured')
    if not isinstance(spec['scenario'], str) or spec['scenario'] not in SCENARIOS:
        raise ToolError('INVALID_ARGUMENT', 'Registered scenario required')
    if spec['baseline'] not in [v['id'] for v in MockSDKAdapter().inventory()[:-1]]:
        raise ToolError('INVALID_ARGUMENT', 'Select a baseline before latest')
    if not isinstance(spec['search_mode'], str) or spec['search_mode'] not in {'boundary', 'earliest_verified'}:
        raise ToolError('INVALID_ARGUMENT', 'Invalid search mode')
    for key, low, high in [('repeats', 1, 5), ('max_experiments', 1, 200),
                           ('max_seconds', 1, 3600), ('max_model_calls', 0, 30)]:
        if type(spec[key]) is not int or not low <= spec[key] <= high:
            raise ToolError('INVALID_ARGUMENT', f'{key} must be {low}..{high}')
    if spec['model_profile'] != DEFAULTS['model_profile']:
        raise ToolError('UNSUPPORTED', 'Only mock-planner-v1 is enabled; no API credentials are accepted')
    return spec


class Halt(Exception):
    def __init__(self, state, result):
        self.state, self.result = state, result


class RegressionService:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='regression')
        self.lock = threading.RLock()
        self.events = {}
        self.closed = False
        # Startup recovery is serialized against active task controllers.
        for path in self.root.glob('reg_*/task.json'):
            import fcntl
            with (path.parent / '.run.lock').open('a') as owner:
                try:
                    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                state = json.loads(path.read_text())
                try:
                    if state.get('controller_pid', -1) <= 0:
                        raise ProcessLookupError()
                    os.kill(state['controller_pid'], 0)
                    live = True
                except (ProcessLookupError, PermissionError):
                    live = False
                if state['state'] in ACTIVE and not live:
                    state['state'] = 'interrupted'
                    state['result'] = 'incomplete'
                    atomic_json(path, state)

    def _persist(self, state):
        atomic_json(self._dir(state['id']) / 'task.json', state)

    def _dir(self, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r'reg_[0-9a-f]{32}', task_id):
            raise ToolError('INVALID_ARGUMENT', 'Invalid regression task ID')
        return self.root / task_id

    def read(self, task_id):
        path = self._dir(task_id) / 'task.json'
        if not path.exists():
            raise ToolError('NOT_FOUND', 'Regression task not found')
        return json.loads(path.read_text())

    def list(self):
        return sorted((json.loads(p.read_text()) for p in self.root.glob('reg_*/task.json')),
                      key=lambda x: x['created_at'], reverse=True)[:50]

    def start(self, data, *, idempotency_key=None, background=True):
        spec = validate(data)
        if idempotency_key is None:
            idempotency_key = uuid.uuid4().hex
        if not isinstance(idempotency_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', idempotency_key):
            raise ToolError('INVALID_ARGUMENT', 'Bounded idempotency key required')
        with self.lock, file_lock(self.root / '.create.lock'):
            if self.closed:
                raise ToolError('SERVICE_CLOSED', 'Regression service is closed')
            for path in self.root.glob('reg_*/task.json'):
                record = json.loads(path.read_text())
                if record['idempotency_key'] == idempotency_key:
                    if record['spec'] != spec:
                        raise ToolError('IDEMPOTENCY_CONFLICT', 'Key already used with different inputs')
                    return record
            task_id = 'reg_' + uuid.uuid4().hex
            state = dict(schema_version=1, id=task_id, state='queued', phase='created', result=None,
                         source='mock_sdk_real_cpu_pytest', spec=spec, created_at=time.time(),
                         idempotency_key=idempotency_key, controller_pid=os.getpid(), revision=0, elapsed_seconds=0,
                         experiments=[], decisions=[], events=[], model_calls=0,
                         inventory=[], boundary=None, attribution=[], earliest_proven=False,
                         limitations=catalog()['limitations'], scenario_sha256=digest(CASE_SOURCE), plugin_sha256=digest(PLUGIN_SOURCE),
                         runtime={'python': sys.version, 'executable': sys.executable}, pending=None)
            self._persist(state)
            return self._launch(state, background)

    def _launch(self, state, background):
        event = threading.Event()
        self.events[state['id']] = event
        if background:
            self.pool.submit(self._run, state['id'], event)
            return state
        self._run(state['id'], event)
        return self.read(state['id'])

    def resume(self, task_id, *, background=True):
        with self.lock:
            state = self.read(task_id)
            if self.closed or state['state'] in ACTIVE or state['state'] == 'completed':
                raise ToolError('INVALID_STATE', 'Only stopped tasks can resume; completed tasks are immutable')
            # A budget stop cannot gain a fresh budget on resume.
            (self._dir(task_id) / 'cancel.json').unlink(missing_ok=True)
            state.update(state='queued', controller_pid=os.getpid())
            self._persist(state)
            return self._launch(state, background)

    def cancel(self, task_id):
        with self.lock:
            record = self.read(task_id)
            if record['state'] in ACTIVE:
                atomic_json(self._dir(task_id) / 'cancel.json', {'requested_at': time.time()})
                if task_id in self.events:
                    self.events[task_id].set()
            return record

    def experiment(self, task_id, experiment_id):
        task = self.read(task_id)
        if experiment_id not in [e['id'] for e in task['experiments']]:
            raise ToolError('NOT_FOUND', 'Experiment not found')
        path = self._dir(task_id) / 'runs' / experiment_id
        value = json.loads((path / 'result.json').read_text()) if (path / 'result.json').exists() else {'classification': 'interrupted'}
        return value

    def _execute(self, directory, intent, cancel, timeout):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'test_regression.py').write_text(CASE_SOURCE)
        (directory / 'conftest.py').write_text(PLUGIN_SOURCE)
        atomic_json(directory / 'environment.json', intent)
        atomic_json(directory / 'request.json', {'argv': [sys.executable, '-I', '-m', 'pytest', '-q', NODEID],
                                               'environment': intent, 'source': 'mock'})
        home = directory / 'home'
        home.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k in {'PATH', 'SYSTEMROOT', 'LANG', 'LC_ALL', 'TMPDIR'}}
        env.update(HOME=str(home), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONHASHSEED='42',
                   TRITON_CACHE_DIR=str(home / 'triton'), XDG_CACHE_HOME=str(home / 'cache'))
        try:
            result = run_process([sys.executable, '-I', '-m', 'pytest', '-q', NODEID, '-o', 'addopts=',
                                  '--basetemp', str(directory / 'tmp')], cwd=directory, env=env,
                                 cancel=cancel, timeout=timeout, max_output=24000)
        except ToolError as exc:
            if exc.code not in {'CANCELLED', 'TIMEOUT'}:
                raise
            result = dict(exc.details, stop_reason=exc.code)
        stages = json.loads((directory / 'stages.json').read_text()) if (directory / 'stages.json').exists() else []
        calls = [s for s in stages if s['nodeid'] == NODEID and s['when'] == 'call']
        complete = {s['when'] for s in stages if s['nodeid'] == NODEID} == {'setup', 'call', 'teardown'}
        if result.get('stop_reason') or result.get('reason'):
            classification = 'unavailable'
        elif result['returncode'] == 0 and complete and len(calls) == 1 and calls[0]['outcome'] == 'passed':
            classification = 'passed'
        elif complete and len(calls) == 1 and calls[0]['outcome'] == 'failed' and 'MOCK_REGRESSION:' in calls[0]['longrepr']:
            classification = 'target_failure'
        elif any(s['outcome'] == 'skipped' for s in stages):
            classification = 'unavailable'
        else:
            classification = 'different_failure'
        value = dict(classification=classification, process=result, stages=stages,
                     observed_components=intent['components'], source='mock_manifest_not_native_load',
                     source_sha256=digest(CASE_SOURCE), environment_sha256=digest(intent))
        atomic_json(directory / 'result.json', value)
        return value

    def _run(self, task_id, cancel):
        import fcntl
        directory = self._dir(task_id)
        with (directory / '.run.lock').open('a') as owner:
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            state = self.read(task_id)
            spec = state['spec']
            started, elapsed = time.monotonic(), state['elapsed_seconds']
            def save():
                state['elapsed_seconds'] = elapsed + time.monotonic() - started
                state['revision'] += 1
                self._persist(state)
            def check():
                if cancel.is_set() or (directory / 'cancel.json').exists():
                    raise Halt('cancelled', 'incomplete')
                if elapsed + time.monotonic() - started >= spec['max_seconds']:
                    raise Halt('budget_exhausted', 'incomplete')
            def phase(name, message):
                check()
                if state['phase'] != name:
                    state['events'].append({'phase': name, 'message': message, 'time': time.time()})
                state['phase'] = name
                save()
            def evaluate(components, label):
                classifications = []
                for repeat in range(spec['repeats']):
                    check()
                    intent = dict(components=components, scenario=spec['scenario'], repeat=repeat,
                                  label=label, nodeid=NODEID)
                    key = digest(intent)
                    prior = next((e for e in reversed(state['experiments']) if e['key'] == key and e['classification'] not in {'pending', 'interrupted', 'cancelled'}), None)
                    if prior:
                        classifications.append(prior['classification'])
                        continue
                    if len(state['experiments']) >= spec['max_experiments']:
                        raise Halt('budget_exhausted', 'incomplete')
                    eid = f"exp_{len(state['experiments']) + 1:04d}"
                    entry = dict(id=eid, key=key, label=label, components=components, repeat=repeat,
                                 classification='pending', started_at=time.time())
                    state['experiments'].append(entry)
                    state['pending'] = eid
                    save()
                    remaining = spec['max_seconds'] - (elapsed + time.monotonic() - started)
                    value = self._execute(directory / 'runs' / eid, intent, cancel, max(.01, min(30, remaining)))
                    entry.update(classification='cancelled' if cancel.is_set() else value['classification'],
                                 finished_at=time.time(), returncode=value['process']['returncode'])
                    state['pending'] = None
                    save()
                    check()
                    classifications.append(entry['classification'])
                return classifications[0] if len(set(classifications)) == 1 else 'unstable'
            try:
                if importlib.util.find_spec('pytest') is None:
                    raise ToolError('PYTEST_UNAVAILABLE', 'Install pytest in the controller Python environment before running experiments')
                if state['scenario_sha256'] != digest(CASE_SOURCE) or state['plugin_sha256'] != digest(PLUGIN_SOURCE):
                    raise ToolError('SOURCE_CHANGED', 'Frozen recipe differs from current tool version')
                if state['runtime']['python'] != sys.version:
                    raise ToolError('RUNTIME_CHANGED', 'Controller Python differs from frozen runtime')
                # Reconcile a persisted intent without blindly repeating its side effect.
                if state['pending']:
                    e = next(e for e in state['experiments'] if e['id'] == state['pending'])
                    evidence = directory / 'runs' / e['id'] / 'result.json'
                    e['classification'] = json.loads(evidence.read_text())['classification'] if evidence.exists() else 'interrupted'
                    state['pending'] = None
                # Resume is explicit acknowledgement of a previous cancellation.
                state['state'] = 'running'
                phase('baseline', '冻结场景并校准baseline；未通过则不会update')
                adapter = MockSDKAdapter()
                inventory = state['inventory'] or adapter.inventory()
                base = next(i for i, v in enumerate(inventory) if v['id'] == spec['baseline'])
                baseline_result = evaluate(inventory[base]['components'], 'baseline')
                if baseline_result != 'passed':
                    raise Halt('completed', 'unstable' if baseline_result == 'unstable' else
                               'inconclusive' if baseline_result == 'unavailable' else 'baseline_invalid')
                phase('update', 'Mock update：锁定最新SDK清单和哈希，不修改活动环境')
                if not state['inventory']:
                    state['inventory'] = inventory
                    state['target'] = adapter.update()
                    atomic_json(directory / 'inventory.json', inventory)
                end = len(inventory) - 1
                phase('latest', '在同一case场景验证固定latest')
                latest = evaluate(inventory[end]['components'], 'latest')
                if latest == 'passed':
                    raise Halt('completed', 'no_regression')
                if latest != 'target_failure':
                    raise Halt('completed', 'unstable' if latest == 'unstable' else 'inconclusive')
                state['target_signature'] = 'call / AssertionError / MOCK_REGRESSION:'
                state['suggested_interval'] = [inventory[base]['id'], inventory[end]['id']]
                phase('search', '程序二分；UNKNOWN不当作好坏，保留未决区间')
                lo, hi, measured = base, end, {base: 'passed', end: 'target_failure'}
                def snapshot_search():
                    state['search_observations'] = [{'sdk': inventory[i]['id'], 'classification': v} for i, v in sorted(measured.items())]
                    state['boundary'] = dict(good=inventory[lo], bad=inventory[hi], adjacent=hi - lo == 1,
                                             earliest_proven=state['earliest_proven'])
                    save()
                snapshot_search()
                while hi - lo > 1:
                    middle = (lo + hi) // 2
                    outcome = evaluate(inventory[middle]['components'], inventory[middle]['id'])
                    measured[middle] = outcome
                    if outcome == 'passed':
                        lo = middle
                    elif outcome == 'target_failure':
                        hi = middle
                    else:
                        snapshot_search()
                        break
                    snapshot_search()
                if spec['search_mode'] == 'earliest_verified':
                    phase('audit_history', '从baseline向前补测，确认最早目标失败并保留缺失点')
                    for index in range(base + 1, hi + 1):
                        if index not in measured:
                            measured[index] = evaluate(inventory[index]['components'], inventory[index]['id'])
                        if measured[index] == 'target_failure':
                            hi = index
                            lo = max(i for i, result in measured.items() if i < hi and result == 'passed')
                            snapshot_search()
                            break
                        snapshot_search()
                    state['earliest_proven'] = all(measured.get(i) == 'passed' for i in range(base, hi))
                state['search_observations'] = [{'sdk': inventory[i]['id'], 'classification': v} for i, v in sorted(measured.items())]
                state['boundary'] = dict(good=inventory[lo], bad=inventory[hi], adjacent=hi - lo == 1,
                                         earliest_proven=state['earliest_proven'])
                phase('audit_boundary', '对边界执行独立fresh目录重复验证')
                if (evaluate(inventory[lo]['components'], 'audit_good') != 'passed'
                        or evaluate(inventory[hi]['components'], 'audit_bad') != 'target_failure'):
                    raise Halt('completed', 'unstable')
                phase('components', '合法mock组件闭包的双向替换；模型仅排序候选')
                good, bad = inventory[lo]['components'], inventory[hi]['components']
                groups = [(c,) for c in COMPONENTS] + list(itertools.combinations(COMPONENTS, 2)) + [tuple(COMPONENTS)]
                candidates = {','.join(group): group for group in groups}
                supported = []
                while candidates:
                    check()
                    if supported:
                        break
                    if state['model_calls'] >= spec['max_model_calls']:
                        raise Halt('budget_exhausted', 'boundary_found')
                    context = dict(task_id=task_id, state_revision=state['revision'], candidates=list(candidates),
                                   evidence_ids=[e['id'] for e in state['experiments'] if e['classification'] != 'pending'])
                    state['model_calls'] += 1
                    save()
                    decision = validate_decision(MockModel().respond(context), context)
                    if decision not in state['decisions']:
                        state['decisions'].append(decision)
                    group = candidates.pop(decision['candidate_id'])
                    forward = good | {c: bad[c] for c in group}
                    backward = bad | {c: good[c] for c in group}
                    a = evaluate(forward, 'forward:' + ','.join(group))
                    b = evaluate(backward, 'rollback:' + ','.join(group))
                    row = dict(components=list(group), forward=a, rollback=b,
                               supported=a == 'target_failure' and b == 'passed', scope='mock_component_intervention')
                    state['attribution'] = [r for r in state['attribution'] if r['components'] != list(group)] + [row]
                    save()
                    if row['supported']:
                        supported = list(group)
                state['supported_components'] = supported
                raise Halt('completed', 'component_supported' if len(supported) == 1 else 'group_supported' if supported else 'boundary_found')
            except Halt as stop:
                state.update(state=stop.state, result='boundary_found' if stop.result == 'incomplete' and state.get('boundary') else stop.result, finished_at=time.time())
            except Exception as exc:
                state.update(state='error', result='incomplete', error={'code': getattr(exc, 'code', 'REGRESSION_ERROR'), 'message': str(exc)})
            finally:
                save()
                from .reporting import materialize
                materialize(directory, state)

    def replay(self, task_id, experiment_id):
        task = self.read(task_id)
        self.experiment(task_id, experiment_id)
        if task['runtime']['python'] != sys.version:
            raise ToolError('RUNTIME_CHANGED', 'Replay requires the recorded Python runtime')
        original = self._dir(task_id) / 'runs' / experiment_id
        intent = json.loads((original / 'environment.json').read_text())
        entry = next(e for e in task['experiments'] if e['id'] == experiment_id)
        if ((original / 'test_regression.py').read_text() != CASE_SOURCE
                or (original / 'conftest.py').read_text() != PLUGIN_SOURCE
                or task['scenario_sha256'] != digest(CASE_SOURCE) or digest(intent) != entry['key']):
            raise ToolError('SOURCE_CHANGED', 'Replay source does not match frozen scenario')
        rid = 'replay_' + uuid.uuid4().hex
        value = self._execute(self._dir(task_id) / 'replays' / rid, intent, threading.Event(), 30)
        return {'id': rid, 'task_id': task_id, 'experiment_id': experiment_id, 'result': value, 'model_called': False}

    def close(self):
        with self.lock:
            self.closed = True
            for event in self.events.values():
                event.set()
        self.pool.shutdown(wait=True)
