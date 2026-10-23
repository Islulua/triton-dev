"""Explicit synthetic SDK builder for offline demos; never a usable native runtime."""
import json
from pathlib import Path
from zipfile import ZipFile

from triton_dev.common.contracts import ToolError


def create_sdk(root, name):
    from triton_dev.env.sdk import sdk_time
    if sdk_time(name) is None:
        raise ToolError('INVALID_ARGUMENT', 'Use a valid SDK directory name')
    sdk = Path(root) / name
    if sdk.exists():
        raise ToolError('NAME_EXISTS', 'Mock SDK creation never overwrites existing files')
    for part in ('bin', 'lib', 'wheel'):
        (sdk / part).mkdir(parents=True, exist_ok=True)
    for package in ('triton', 'raops', 'torch_raisa'):
        metadata = f'{package}-0.1.0.dist-info'
        files = {
            f'{package}/__init__.py': 'SYNTHETIC_TEST_PACKAGE = True\n__version__ = "0.1.0"\n',
            f'{metadata}/METADATA': f'Metadata-Version: 2.1\nName: {package}\nVersion: 0.1.0\n',
            f'{metadata}/WHEEL': 'Wheel-Version: 1.0\nGenerator: triton-dev-mock\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        }
        record = f'{metadata}/RECORD'
        files[record] = '\n'.join(f'{key},,' for key in [*files, record]) + '\n'
        with ZipFile(sdk / 'wheel' / f'{package}-0.1.0-py3-none-any.whl', 'x') as archive:
            for key, value in files.items():
                archive.writestr(key, value)
    (sdk / 'MOCK_ONLY.json').write_text(json.dumps({
        'source': 'mock', 'native_runtime': False, 'description': 'Synthetic Python packages only'}))
    return sdk
