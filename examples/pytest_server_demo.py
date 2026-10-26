"""Prepare a CPU-only, intentionally failing pytest project and registered job file."""
import argparse
import json
import sys
from pathlib import Path

SOURCE = '''import json
import pytest

@pytest.mark.case_id("demo.parameter")
@pytest.mark.parametrize("size", [64, 128])
def test_parameter(size, triton_dev_context, triton_dev_artifact_dir, record_property):
    triton_dev_context.update(shape=[size, size], dtype="fp16", seed=42, backend="CPU workflow demo")
    record_property("owner_hint", "unassigned; diagnosis required")
    (triton_dev_artifact_dir / "input.json").write_text(json.dumps({"size": size, "seed": 42}))
    print("CPU workflow demo: size=", size)
    assert size == 64, "DEMO_NUMERICAL_FAILURE: illustrative assertion, no kernel executed"

@pytest.fixture
def unavailable_resource():
    raise RuntimeError("DEMO_SETUP_FAILURE: simulated resource initialization")

def test_setup(unavailable_resource): pass

@pytest.fixture
def dirty_resource():
    yield
    raise RuntimeError("DEMO_TEARDOWN_FAILURE: simulated cleanup")

def test_cleanup(dirty_resource): pass

@pytest.mark.skip(reason="No real device attached to CPU workflow demo")
def test_device(): pass

@pytest.mark.xfail(reason="Demonstrate expected failure presentation")
def test_known_issue(): assert False

GLOBAL_STATE = []
def test_state_writer():
    GLOBAL_STATE.append("shared session state")

def test_state_reader():
    assert not GLOBAL_STATE, "DEMO_STATE_LEAK: use case isolation to remove process state"
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', type=Path, required=True)
    args = parser.parse_args()
    root = args.workdir.resolve()
    project = root / 'project'
    project.mkdir(parents=True, exist_ok=False)
    (project / 'test_demo.py').write_text(SOURCE)
    jobs = {'pytest-demo': {'kind': 'pytest', 'argv': ['test_demo.py'], 'cwd': str(project),
                            'python': sys.executable, 'timeout': 60, 'isolation': 'case'}}
    (root / 'jobs.json').write_text(json.dumps(jobs, indent=2))
    print(root / 'jobs.json')


if __name__ == '__main__':
    main()
