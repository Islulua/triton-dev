"""Create a real CPU pytest workflow with seven labelled operators; no kernels/devices."""
import argparse
import json
import sys
from pathlib import Path

SOURCE = '''import time
import pytest

@pytest.fixture(autouse=True)
def demo_context(triton_dev_context):
    triton_dev_context.update(backend="CPU statistics workflow demo", native_verification="not_checked")

@pytest.mark.operator("matmul")
@pytest.mark.parametrize("size", [64,128,256,512,1024,2048,4096,8192])
def test_matmul(size):
    time.sleep(.01 + size / 100000)
    assert size not in (512,4096), "CPU_DEMO_ASSERTION: no matmul kernel executed"

@pytest.mark.operator("softmax")
@pytest.mark.parametrize("dtype", ["fp16","bf16","fp32"])
@pytest.mark.parametrize("width", [128,1024])
def test_softmax(dtype,width):
    time.sleep(.018)
    assert not (dtype == "bf16" and width == 1024), "CPU_DEMO_ASSERTION: illustrative dtype failure"

@pytest.mark.operator("reduce")
@pytest.mark.parametrize("axis", range(6))
def test_reduce(axis): time.sleep(.009)

@pytest.mark.operator("transpose")
@pytest.mark.parametrize("size", [64,128,256,512])
def test_transpose(size):
    if size == 512: pytest.skip("CPU workflow demo: device branch unavailable")
    time.sleep(.012)

@pytest.fixture
def setup_slot(request):
    if request.param == 2: raise RuntimeError("CPU_DEMO_SETUP_FAILURE")
    return request.param

@pytest.mark.operator("gather")
@pytest.mark.parametrize("setup_slot", range(4), indirect=True)
def test_gather(setup_slot): time.sleep(.014)

@pytest.fixture
def cleanup_slot(request):
    yield request.param
    if request.param == 1: raise RuntimeError("CPU_DEMO_TEARDOWN_FAILURE")

@pytest.mark.operator("layernorm")
@pytest.mark.parametrize("cleanup_slot", range(4), indirect=True)
def test_layernorm(cleanup_slot): time.sleep(.025)

@pytest.mark.operator("add")
@pytest.mark.xfail(reason="CPU workflow demo: expected failure and unexpected pass",strict=False)
@pytest.mark.parametrize("known", [0,1])
def test_add(known):
    time.sleep(.005)
    assert known == 1
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', type=Path, required=True)
    root = parser.parse_args().workdir.resolve()
    project = root / 'project'
    project.mkdir(parents=True, exist_ok=False)
    (project / 'test_statistics.py').write_text(SOURCE)
    (root / 'jobs.json').write_text(json.dumps({'pytest-statistics-demo': {
        'kind': 'pytest', 'argv': ['test_statistics.py'], 'cwd': str(project),
        'python': sys.executable, 'timeout': 60, 'max_workers': 8}}, indent=2))
    print(root / 'jobs.json')


if __name__ == '__main__':
    main()
