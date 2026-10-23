import shutil
import sys
from zipfile import ZipFile

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.env import saved
from triton_dev.env.preflight import check, target
from triton_dev.env.service import plan


def test_saved_freezes_latest_and_detects_native_changes(make_sdk, tmp_path):
    sdk = make_sdk()
    cache = tmp_path / 'cache'
    first = saved.save(sdk.parent, cache, 'baseline')
    make_sdk('TX82_SDK_Daily_2026-10-24-02-52')
    assert saved.load(cache, 'baseline')['selector'] == sdk.name
    assert first['qualification'] == 'untested'
    with pytest.raises(ToolError, match='immutable'):
        saved.save(sdk.parent, cache, 'baseline')
    (sdk / 'lib/libchanged.so').write_text('synthetic')
    with pytest.raises(ToolError) as error:
        saved.load(cache, 'baseline')
    assert error.value.code == 'SOURCE_CHANGED'
    assert saved.load(cache, 'baseline', verify=False)['name'] == 'baseline'


def test_saved_overrides_and_safe_names(make_sdk, tmp_path):
    a = make_sdk()
    b = make_sdk('TX82_SDK_Daily_2026-10-24-02-52')
    cache = tmp_path / 'cache'
    saved.save(a.parent, cache, 'base', a.name)
    mixed = saved.save(a.parent, cache, 'mixed', a.name, overrides={'triton': b.name})
    assert mixed['overrides']['triton'] == b.name
    assert saved.diff(cache, 'base', 'mixed')['changed_wheels'] == ['triton']
    assert len(saved.listing(cache)) == 2
    with pytest.raises(ToolError):
        saved.load(cache, '../escape')
    shutil.rmtree(b)
    with pytest.raises(ToolError):
        saved.load(cache, 'mixed')


def test_wheel_tag_filter_uses_selected_interpreter(make_sdk):
    sdk = make_sdk()
    wheel = sdk / 'wheel/triton-0.1.0-py3-none-any.whl'
    shutil.copy(wheel, wheel.with_name('triton-0.1.0-cp999-cp999-manylinux_2_17_x86_64.whl'))
    result = plan(sdk.parent)
    assert len(result['wheels']) == 3
    assert result['preflight']['native_abi'] == 'not_checked'
    wheel.unlink()
    with pytest.raises(ToolError) as error:
        plan(sdk.parent)
    assert error.value.code == 'WHEEL_SELECTION_FAILED'


def test_dependencies_conflicts_markers_and_missing():
    context = target(sys.executable)
    selected = [{'name': 'triton', 'version': '1.0', 'requires_dist': ['torch>=3']},
                {'name': 'torch', 'version': '2.0'}]
    with pytest.raises(ToolError) as error:
        check(selected, context)
    assert error.value.code == 'DEPENDENCY_CONFLICT'
    selected[0]['requires_dist'] = ['absent>=1', 'ignored; python_version < "2"']
    result = check(selected, context)
    assert result['constraints'] == 'unknown'
    assert len(result['unresolved_dependencies']) == 1


def test_requires_python_checked_from_metadata(make_sdk):
    sdk = make_sdk()
    wheel = sdk / 'wheel/triton-0.1.0-py3-none-any.whl'
    with ZipFile(wheel) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    metadata = next(n for n in files if n.endswith('/METADATA'))
    files[metadata] += b'Requires-Python: >=99\n'
    with ZipFile(wheel, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    with pytest.raises(ToolError) as error:
        plan(sdk.parent)
    assert error.value.code == 'DEPENDENCY_CONFLICT'
