"""Bounded, packaged CPU-only fixture. No SDK installation or hardware access."""

OPS = ["matmul", "softmax", "reduce", "transpose"]
SIZES = [64, 128, 256, 512, 1024, 2048, 4096, 8192]
SCENARIOS = ["all_pass", "mixed", "xfail_only", "build_failure"]
SOURCE = """import os, time, pytest
@pytest.mark.parametrize("op", ["matmul", "softmax", "reduce", "transpose"])
@pytest.mark.parametrize("size", [64,128,256,512,1024,2048,4096,8192])
def test_operator(op, size, triton_dev_log):
    scenario = os.environ['TRITON_DAILY_SCENARIO']
    triton_dev_log(f"CPU daily fixture: {op} shape={size} dtype={'fp16' if size < 1024 else 'bf16'}; no device kernel executed")
    time.sleep(0.002)
    if scenario != 'all_pass' and op == 'reduce' and size == 128:
        pytest.xfail('MOCK_KNOWN_ISSUE: expected CPU fixture failure')
    if scenario == 'mixed':
        if op == 'transpose' and size == 64:
            pytest.skip('MOCK_UNSUPPORTED_SHAPE')
        if op == 'softmax' and size == 256:
            pytest.xfail('handled by parametrization mark')
        assert not (op == 'matmul' and size == 512), 'MOCK_ASSERTION: simulated SDK regression, no board tested'
"""
# XPASS must be a real pytest xfail mark, not a manufactured passed outcome.
CONFTEST = """import os, pytest
def pytest_collection_modifyitems(items):
    if os.environ['TRITON_DAILY_SCENARIO'] == 'mixed':
        for item in items:
            if item.callspec.params['op'] == 'softmax' and item.callspec.params['size'] == 256:
                item.add_marker(pytest.mark.xfail(reason='MOCK_XPASS', strict=False))
"""
# Remove the xfail call for that case so it actually XPASSes.
SOURCE = SOURCE.replace(
    "        if op == 'softmax' and size == 256:\n            pytest.xfail('handled by parametrization mark')\n",
    "",
)
