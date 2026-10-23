"""Target-interpreter wheel checks. This does not verify native ABI or hardware."""
import json
from pathlib import Path

import packaging
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

from triton_dev.common.contracts import ToolError, run_process


def target(python):
    library = str(Path(packaging.__file__).parent.parent)
    script = ("import sys,json; sys.path.insert(0,sys.argv[1]); "
              "from packaging.tags import sys_tags; "
              "from packaging.markers import default_environment; "
              "print(json.dumps({'tags':[str(t) for t in sys_tags()],"
              "'markers':default_environment()}))")
    result = run_process([str(python), '-I', '-c', script, library])
    if result['returncode']:
        raise ToolError('PREFLIGHT_UNAVAILABLE', 'Cannot inspect target wheel tags', details=result)
    return json.loads(result['stdout'])


def compatible(path, context):
    try:
        _, _, _, tags = parse_wheel_filename(Path(path).name)
    except ValueError as exc:
        raise ToolError('INVALID_WHEEL', str(exc)) from exc
    return bool({str(t) for t in tags} & set(context['tags']))


def check(items, context):
    selected = {canonicalize_name(w['name']): w for w in items}
    missing, conflicts = [], []
    for item in items:
        requires_python = item.get('requires_python')
        if requires_python and not SpecifierSet(requires_python).contains(context['markers']['python_full_version']):
            conflicts.append({'package': item['name'], 'requires_python': requires_python})
        for text in item.get('requires_dist', []):
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate({**context['markers'], 'extra': ''}):
                continue
            dependency = selected.get(canonicalize_name(requirement.name))
            if dependency is None:
                missing.append({'package': item['name'], 'requirement': text})
            elif requirement.url or requirement.extras:
                missing.append({'package': item['name'], 'requirement': text,
                                'reason': 'Direct URL/extras need full resolver verification'})
            elif Version(dependency['version']) not in requirement.specifier:
                conflicts.append({'package': item['name'], 'requirement': text,
                                  'selected': dependency['version']})
    if conflicts:
        raise ToolError('DEPENDENCY_CONFLICT', 'Selected wheel requirements conflict', details={'conflicts': conflicts})
    return {'constraints': 'unknown' if missing else 'valid', 'unresolved_dependencies': missing,
            'verification': 'untested', 'native_abi': 'not_checked',
            'limitation': 'Selected distributions only; pip resolves remaining offline dependency closure'}
