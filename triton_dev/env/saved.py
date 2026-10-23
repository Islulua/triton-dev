"""Immutable named selections, with source-content checks before restore."""
import json
import re
from pathlib import Path

from triton_dev.common.contracts import ToolError, atomic_json, digest, file_lock
from . import service
from .sdk import select


def named(cache, name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name):
        raise ToolError('INVALID_NAME', 'Use 1..64 letters, digits, underscores or hyphens')
    return Path(cache) / 'saved' / (name + '.json')


def inventory(directory):
    return {str(p.relative_to(directory)): digest(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}


def save(root, cache, name, selector='latest', *, overrides=None, python=None):
    options = {'overrides': overrides or {}}
    if python:
        options['python'] = python
    spec = service.plan(root, selector, **options)
    frozen = {key: select(root, value).name for key, value in (overrides or {}).items()}
    sources = {str(Path(spec['sdk']))} | {str(select(root, value)) for value in frozen.values()}
    record = {'schema_version': 1, 'name': name, 'sdk_root': str(Path(root).resolve()),
              'selector': Path(spec['sdk']).name, 'overrides': frozen, 'spec': spec,
              'sources': {source: inventory(Path(source)) for source in sorted(sources)},
              'qualification': 'untested', 'scope': 'sdk_and_python_wheels'}
    confirmed = service.plan(Path(record['sdk_root']), record['selector'],
                             overrides=frozen, python=spec['python'])
    if confirmed['key'] != spec['key']:
        raise ToolError('SOURCE_CHANGED', 'Selection changed while capturing the saved combination')
    path = named(cache, name)
    with file_lock(Path(cache) / 'locks' / ('saved-' + name + '.lock')):
        if path.exists():
            raise ToolError('NAME_EXISTS', 'Saved combinations are immutable; choose another name')
        atomic_json(path, record)
    return record


def load(cache, name, *, verify=True):
    path = named(cache, name)
    if not path.is_file():
        raise ToolError('SAVED_NOT_FOUND', name)
    record = json.loads(path.read_text())
    if record.get('schema_version') != 1 or record.get('name') != name:
        raise ToolError('INVALID_SAVED', 'Unsupported saved selection')
    if verify:
        for source, expected in record['sources'].items():
            if not Path(source).is_dir() or inventory(Path(source)) != expected:
                raise ToolError('SOURCE_CHANGED', 'Saved SDK content is missing or modified', details={'source': source})
        spec = service.plan(Path(record['sdk_root']), record['selector'],
                            overrides=record['overrides'], python=record['spec']['python'])
        if spec['key'] != record['spec']['key']:
            raise ToolError('SOURCE_CHANGED', 'Saved interpreter or wheel selection changed')
    return record


def listing(cache):
    root = Path(cache) / 'saved'
    return [{'name': p.stem} for p in sorted(root.glob('*.json'))]


def diff(cache, left, right):
    a, b = load(cache, left, verify=False), load(cache, right, verify=False)
    aw = {w['name']: w for w in a['spec']['wheels']}
    bw = {w['name']: w for w in b['spec']['wheels']}
    return {'left': left, 'right': right, 'base_changed': a['selector'] != b['selector'],
            'changed_wheels': [k for k in sorted(aw.keys() | bw.keys()) if aw.get(k) != bw.get(k)],
            'verification': 'untested', 'native_component_attribution': 'unknown'}
