"""Offline command definitions and dispatch. No model-supplied executable text."""
import argparse
import json
import os
import sys
from pathlib import Path

from triton_dev.common.contracts import ToolError


def register(sub, esub, cs, ds, ag, leaf, selection):
    p = leaf(esub, 'save', 'env.save', 'Save an immutable, hashed SDK/wheel combination', effects='write_cache')
    p.add_argument('name')
    selection(p, positional=False)
    saved = esub.add_parser('saved', help='Inspect saved combinations').add_subparsers(required=True)
    leaf(saved, 'list', 'env.saved.list', 'List saved combination names')
    p = leaf(saved, 'show', 'env.saved.show', 'Inspect a saved record without restoring it')
    p.add_argument('name')
    p = leaf(saved, 'diff', 'env.saved.diff', 'Compare saved wheel selections')
    p.add_argument('left')
    p.add_argument('right')
    p = leaf(esub, 'preflight', 'env.preflight', 'Check target wheel tags and selected dependency constraints')
    selection(p)
    for name in ('show', 'lint'):
        p = leaf(cs, name, 'cases.' + name, 'Inspect fixtures/locations or lint case IDs', effects='imports_test_code')
        p.add_argument('path')
        p.add_argument('--python', default=sys.executable)
        if name == 'show':
            p.add_argument('nodeid')
        else:
            p.add_argument('--require-id', action='store_true')
    runs = sub.add_parser('runs', help='Opt-in persistent execution and pytest results').add_subparsers(required=True)
    p = leaf(runs, 'start', 'runs.start', 'Execute and persist evidence; pytest accepts targets only', effects='execute_write_cache')
    p.add_argument('--cwd', type=Path, default=Path.cwd())
    p.add_argument('--python', default=sys.executable)
    p.add_argument('--pytest', action='store_true')
    p.add_argument('--saved', help='Use an already prepared saved environment')
    p.add_argument('--timeout', type=float, default=300)
    p.add_argument('command', nargs=argparse.REMAINDER)
    leaf(runs, 'list', 'runs.list', 'List locally persisted runs')
    p = leaf(runs, 'show', 'runs.show', 'Show one recorded run')
    p.add_argument('run_id')
    p = leaf(runs, 'rerun', 'runs.rerun', 'Create a new run using recorded configuration', effects='execute_write_cache')
    p.add_argument('run_id')
    p.add_argument('--failed', action='store_true')
    p = leaf(runs, 'diff', 'runs.diff', 'Compare requests and pytest stage outcomes')
    p.add_argument('left')
    p.add_argument('right')
    p = leaf(runs, 'export', 'runs.export', 'Export redacted logs/events with integrity manifest', effects='write_output')
    p.add_argument('run_id')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--redact-env', action='append', default=[], help='Read explicit secret literals from named environment variables')
    p = leaf(runs, 'verify-export', 'runs.verify-export', 'Verify archive integrity without extracting or executing')
    p.add_argument('input', type=Path)
    p = leaf(ds, 'classify', 'diagnose.classify', 'Apply a structured predicate to an existing run')
    p.add_argument('run_id')
    p.add_argument('--predicate', type=Path, required=True)
    p = leaf(ds, 'history', 'diagnose.history', 'Budgeted exhaustive artifact search; does not assume monotonic failures', effects='execute')
    p.add_argument('--versions', nargs='+', required=True, help='Explicit chronological SDK names, oldest first')
    p.add_argument('--predicate', type=Path, required=True)
    p.add_argument('--repeat', type=int, default=2)
    p.add_argument('--budget', type=int, default=40)
    p.add_argument('--native-only', action='store_true')
    p.add_argument('--timeout', type=float, default=300)
    p.add_argument('command', nargs=argparse.REMAINDER)
    p = leaf(ag, 'workflow', 'agent.workflow', 'Resume offline scripted experiments with registered recipes', effects='execute_write_cache')
    p.add_argument('config', type=Path, help='Trusted recipes, predicate and scripted responses')
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--max-turns', type=int, default=12)
    p.add_argument('--max-experiments', type=int, default=6)


def apply_saved(args):
    from triton_dev.env.saved import load
    if not getattr(args, 'saved', None) or args.command_id == 'runs.start':
        return
    if (getattr(args, 'sdk', None) or getattr(args, 'version', None)
            or any(getattr(args, name, None) for name in ('triton_sdk', 'torch_sdk', 'raops_sdk', 'cmodel_sdk'))
            or getattr(args, 'native_only', False)):
        raise ToolError('INVALID_ARGUMENT', '--saved cannot be combined with another selection or native-only')
    record = load(args.cache_root, args.saved)
    args.sdk_root = Path(record['sdk_root'])
    args.sdk = record['selector']
    args.python = record['spec']['python']
    for key, field in [('triton', 'triton_sdk'), ('torch_raisa', 'torch_sdk'), ('raops', 'raops_sdk')]:
        setattr(args, field, record['overrides'].get(key))


def dispatch(args, selected, overrides):
    from triton_dev.env import saved, service
    from triton_dev.execution.records import RunStore, start, rerun, diff
    command = args.command_id
    if command in {'env.save', 'env.preflight'} and args.native_only:
        raise ToolError('INVALID_ARGUMENT', 'Wheel combination operations do not support --native-only')
    if command == 'env.save':
        return True, saved.save(args.sdk_root, args.cache_root, args.name, selected(args), overrides=overrides(args), python=args.python)
    if command == 'env.saved.list':
        return True, saved.listing(args.cache_root)
    if command == 'env.saved.show':
        return True, saved.load(args.cache_root, args.name, verify=False)
    if command == 'env.saved.diff':
        return True, saved.diff(args.cache_root, args.left, args.right)
    if command == 'env.preflight':
        return True, service.plan(args.sdk_root, selected(args), overrides=overrides(args), python=args.python)
    if command in {'cases.show', 'cases.lint'}:
        from triton_dev.cases.service import show, lint
        result = (show(args.path, args.nodeid, python=args.python) if command == 'cases.show'
                  else lint(args.path, require_id=args.require_id, python=args.python))
        if command == 'cases.lint':
            result['returncode'] = 0 if result['valid'] else 1
        return True, result
    if command.startswith('runs.') or command in {'diagnose.classify', 'agent.workflow'}:
        store = RunStore(args.cache_root / 'runs')
        if command == 'runs.list':
            return True, store.list()
        if command == 'runs.show':
            return True, store.read(args.run_id)
        if command == 'runs.diff':
            return True, diff(store, args.left, args.right)
        if command == 'runs.export':
            from triton_dev.reporting.evidence import export_run
            if any(key not in os.environ for key in args.redact_env):
                raise ToolError('INVALID_ARGUMENT', 'A requested redaction environment variable is missing')
            return True, export_run(store, args.run_id, args.output, secrets=[os.environ[k] for k in args.redact_env])
        if command == 'runs.verify-export':
            from triton_dev.reporting.evidence import verify_archive
            return True, verify_archive(args.input)
        if command == 'diagnose.classify':
            from triton_dev.diagnosis.predicates import FailurePredicate
            return True, {'run_id': args.run_id, 'classification': FailurePredicate.parse(json.loads(args.predicate.read_text())).classify(store.read(args.run_id))}
        if command == 'agent.workflow':
            from triton_dev.agent.controller import ScriptedModel
            from triton_dev.agent.workflow import run_workflow
            from triton_dev.diagnosis.predicates import FailurePredicate
            config = json.loads(args.config.read_text())
            return True, run_workflow(ScriptedModel(config['responses']), store, args.checkpoint,
                                     config['recipes'], FailurePredicate.parse(config['predicate']),
                                     max_turns=args.max_turns, max_experiments=args.max_experiments)
        if command == 'runs.start':
            environment = None
            if args.saved:
                record = saved.load(args.cache_root, args.saved)
                environment = service.resolve(Path(record['sdk_root']), args.cache_root, record['selector'],
                                              overrides=record['overrides'], python=record['spec']['python'])
            argv = args.command[1:] if args.command[:1] == ['--'] else args.command
            record = start(store, argv, cwd=args.cwd, python=args.python, pytest=args.pytest,
                           timeout=args.timeout, environment=environment)
        else:
            record = rerun(store, args.run_id, failed=args.failed)
        exitcode = {'timeout': 124, 'cancelled': 130, 'error': 2, 'interrupted': 2}.get(record['state'])
        if exitcode is None:
            exitcode = record['result'].get('returncode', 2) if record.get('result') else 2
        return True, {**record, 'returncode': exitcode}
    if command == 'diagnose.history':
        from triton_dev.diagnosis.predicates import FailurePredicate
        from triton_dev.diagnosis.history import search
        from triton_dev.execution.service import execute
        predicate = FailurePredicate.parse(json.loads(args.predicate.read_text()))
        argv = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not argv:
            raise ToolError('INVALID_ARGUMENT', 'Command after -- required')
        # Freeze selectors before running; dates/latest must not alias the same SDK.
        from triton_dev.env.sdk import select
        versions = [select(args.sdk_root, value).name for value in args.versions]
        def evaluate(version):
            try:
                environment = service.resolve(args.sdk_root, args.cache_root, version, native_only=args.native_only)
                result = execute(environment, argv, timeout=args.timeout)
                return {'classification': predicate.classify(result), 'result': result}
            except ToolError as exc:
                return {'classification': 'unavailable', 'error': {'code': exc.code, 'message': str(exc)}}
        return True, search(versions, evaluate, repeat=args.repeat, budget=args.budget)
    return False, None
