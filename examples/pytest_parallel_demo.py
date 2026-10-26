"""Generate a CPU workflow project: 32 configurations + 8, for xdist UI checks."""
import argparse
import json
import sys
from pathlib import Path

SOURCE = '''import json, time, pytest

@pytest.mark.case_id("cpu-demo.matrix")
@pytest.mark.parametrize("config", range(32), ids=lambda value: f"cfg-{value:02d}")
def test_matrix(config, triton_dev_context, triton_dev_log, triton_dev_artifact_dir):
    triton_dev_context.update(config=config, shape=[16 + config, 64], seed=42, backend="CPU workflow demo")
    triton_dev_log(f"CPU demo matrix config={config}: preparing input")
    (triton_dev_artifact_dir / "input.json").write_text(json.dumps({"config": config, "seed": 42}))
    print(f"CPU demo captured output: matrix config={config}")
    time.sleep(.12)
    assert config != 7, "DEMO_ASSERTION: deliberate workflow failure; no Triton kernel executed"

@pytest.mark.parametrize("config", range(8), ids=lambda value: f"extra-{value:02d}")
def test_extra(config, triton_dev_log):
    triton_dev_log(f"CPU demo extra config={config}")
    time.sleep(.12)
    assert config >= 0
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', type=Path, required=True)
    root = parser.parse_args().workdir.resolve()
    project = root / 'project'
    project.mkdir(parents=True, exist_ok=False)
    (project / 'test_parallel_demo.py').write_text(SOURCE)
    (root / 'jobs.json').write_text(json.dumps({'pytest-parallel-demo': {
        'kind': 'pytest', 'argv': ['test_parallel_demo.py'], 'cwd': str(project),
        'python': sys.executable, 'timeout': 60, 'max_workers': 8}}, indent=2))
    print(root / 'jobs.json')


if __name__ == '__main__':
    main()
