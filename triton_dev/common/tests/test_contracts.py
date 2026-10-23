import sys

from triton_dev.common.contracts import ToolError, atomic_json, envelope, run_process


def test_result_and_atomic_json(tmp_path):
    value = envelope(error=ToolError("UNSUPPORTED", "not implemented"))
    assert value["status"] == "unsupported"
    output = tmp_path / "state.json"
    atomic_json(output, value)
    assert output.is_file()
    assert not list(tmp_path.glob("*.tmp"))
    assert run_process([sys.executable, "-c", "print('ok')"])["stdout"].strip() == "ok"
