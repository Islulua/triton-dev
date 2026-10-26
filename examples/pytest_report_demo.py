"""Generate a two-file CPU report suite and a separate process-crash demonstration."""
import argparse
import json
import sys
from pathlib import Path

from pytest_statistics_demo import SOURCE

CRASH = '''import os, time, pytest
@pytest.mark.operator("native-process-demo")
@pytest.mark.parametrize("config", range(8))
def test_native_process(config):
    if config == 0: os._exit(17)  # exits only this isolated pytest worker
    time.sleep(.02)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', type=Path, required=True)
    root = parser.parse_args().workdir.resolve()
    project = root / 'project'
    project.mkdir(parents=True, exist_ok=False)
    split = SOURCE.index('@pytest.mark.operator("transpose")')
    prefix = SOURCE[:SOURCE.index('@pytest.mark.operator("matmul")')]
    (project / 'test_math.py').write_text(SOURCE[:split])
    (project / 'test_memory.py').write_text(prefix + SOURCE[split:])
    (project / 'test_process_exit.py').write_text(CRASH)
    common = {'kind': 'pytest', 'cwd': str(project), 'python': sys.executable,
              'timeout': 60, 'max_workers': 8}
    jobs = {'pytest-report-demo': {**common, 'argv': ['test_math.py', 'test_memory.py']},
            'pytest-report-crash-demo': {**common, 'argv': ['test_process_exit.py']}}
    (root / 'jobs.json').write_text(json.dumps(jobs, indent=2))
    print(root / 'jobs.json')


if __name__ == '__main__':
    main()
