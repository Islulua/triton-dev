import json
import os
import subprocess
import sys

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.env.service import plan, prepare, probe, render_shell, resolve, variables


def test_native_override_explicitly_unsupported(make_sdk):
    sdk = make_sdk()
    with pytest.raises(ToolError) as error:
        plan(sdk.parent, overrides={"cmodel": sdk.name})
    assert error.value.code == "UNSUPPORTED"


def test_real_offline_install_of_synthetic_wheels(make_sdk, tmp_path):
    sdk = make_sdk()
    cache = tmp_path / "cache"
    ready = prepare(sdk.parent, cache)
    assert ready["state"] == "installed"
    assert prepare(sdk.parent, cache)["reused"] is True
    observed = probe(resolve(sdk.parent, cache))
    assert all("error" not in value for value in observed["modules"].values())
    assert all(ready["venv"] in value["path"] for value in observed["modules"].values())
    assert observed["native_loading"] == "not_checked"


def test_failed_install_never_ready(make_sdk, tmp_path):
    sdk = make_sdk()
    def creator(path):
        (path / "bin").mkdir(parents=True)
        (path / "bin/python").symlink_to(sys.executable)
    def installer(*args):
        raise ToolError("INSTALL_FAILED", "simulated")
    with pytest.raises(ToolError):
        prepare(sdk.parent, tmp_path / "cache", creator=creator, installer=installer)
    assert not list((tmp_path / "cache").rglob("ready.json"))
    with pytest.raises(ToolError, match="prepare first"):
        resolve(sdk.parent, tmp_path / "cache")


def test_shell_serialization_does_not_execute_values(tmp_path):
    marker = tmp_path / "injected"
    value = f"space ' quote $HOME $(touch {marker})\nnext"
    code = render_shell({"variables": {"TEST_VALUE": value}, "unset": ["OLD_VAR"]})
    script = code + '\n' + '"$PYTHON" -c \'import os,json; print(json.dumps([os.environ["TEST_VALUE"],os.getenv("OLD_VAR")]))\''
    result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                            env={**os.environ, "PYTHON": sys.executable, "OLD_VAR": "old"},
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [value, None]
    assert not marker.exists()


def test_variables_do_not_mutate_parent_or_accumulate_path(make_sdk):
    sdk = make_sdk()
    environment = {"sdk": str(sdk), "venv": "/tmp/test-venv", "state": "installed", "native_loading": "not_checked"}
    inherited = {"PATH": "/usr/bin"}
    first = variables(environment, inherited)
    second = variables(environment, {**inherited, **first["variables"]})
    assert first["variables"]["PATH"] == second["variables"]["PATH"]
    assert inherited == {"PATH": "/usr/bin"}
