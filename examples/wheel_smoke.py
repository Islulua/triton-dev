"""Validate an installed wheel outside the checkout; --test-python has pytest installed."""
import argparse
import json
from importlib.metadata import version
import subprocess
import sys
import tempfile
from pathlib import Path

import triton_dev
from triton_dev.integrations.mock import create_sdk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-python', required=True)
    args = parser.parse_args()
    assert 'site-packages' in triton_dev.__file__, triton_dev.__file__
    assert version('triton-dev') == triton_dev.__version__ == '0.2.0'
    cli = Path(sys.executable).parent / 'triton-dev'
    with tempfile.TemporaryDirectory(prefix='triton-dev-wheel-') as directory:
        root = Path(directory)
        sdk = create_sdk(root / 'sdks', 'TX82_SDK_Daily_2026-10-23-02-52')
        cache = root / 'cache'
        common = ['--cache-root', str(cache), '--sdk-root', str(sdk.parent), '--non-interactive']
        def call(argv, expected=0):
            result = subprocess.run([str(cli), *argv, *common], cwd=root, capture_output=True, text=True)
            assert result.returncode == expected, result.stdout + result.stderr
            return json.loads(result.stdout)['data']
        call(['capabilities'])
        call(['describe', 'runs.start'])
        call(['doctor'])
        call(['env', 'save', 'baseline', '--sdk', sdk.name])
        call(['env', 'plan', '--saved', 'baseline'])
        call(['env', 'prepare', '--saved', 'baseline'])
        call(['env', 'verify', '--saved', 'baseline'])
        def execute(argv, expected=0):
            result = subprocess.run([str(cli), *argv], cwd=root, capture_output=True, text=True)
            assert result.returncode == expected, result.stdout + result.stderr
            return json.loads(result.stdout)['data']
        run = execute(['runs', 'start', *common, '--cwd', str(root), '--saved', 'baseline', '--',
                       'python', '-c', 'import triton;assert triton.SYNTHETIC_TEST_PACKAGE'])
        assert run['state'] == 'passed'
        (root / 'test_smoke.py').write_text('def test_smoke(): assert False, "MOCK_TARGET"\n')
        run = execute(['runs', 'start', *common, '--cwd', str(root), '--python', args.test_python,
                       '--pytest', '--', 'test_smoke.py'], expected=1)
        assert any(s.get('when') == 'call' and s.get('outcome') == 'failed' for s in run['stages'])
        exported = root / 'evidence.zip'
        call(['runs', 'export', run['id'], '--output', str(exported)])
        assert call(['runs', 'verify-export', str(exported)])['valid']
    print('Installed-wheel smoke passed: offline SDK save/prepare/verify, execution, pytest stages and evidence')


if __name__ == '__main__':
    main()
