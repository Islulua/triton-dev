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


def test_timeout_kills_descendants_in_same_process_group(tmp_path):
    import time
    import pytest
    marker = tmp_path / 'child-survived'
    child = f'import time;from pathlib import Path;time.sleep(0.8);Path({str(marker)!r}).touch()'
    parent = f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{child!r}]);print("started",flush=True);time.sleep(20)'
    with pytest.raises(ToolError) as error:
        run_process([sys.executable, '-c', parent], timeout=0.2)
    assert error.value.code == 'TIMEOUT'
    assert 'started' in error.value.details['stdout']
    time.sleep(0.9)
    assert not marker.exists()
