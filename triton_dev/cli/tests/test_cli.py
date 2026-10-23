import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from triton_dev.cli import CATALOG, describe, main, parser_factory


def test_capability_definitions_match_actual_parsers():
    parser_factory()
    for name in CATALOG:
        description = describe(name)
        actual = {a.dest for a in CATALOG[name]["parser"]._actions if a.dest != "help"}
        assert {x["name"] for x in description["arguments"]} == actual
        assert description["summary"]
    assert describe("agent.regression")["status"] == "unsupported"


def test_cli_discovery_and_describe(make_sdk, capsys):
    sdk = make_sdk()
    assert main(["env", "sdk", "list", "--sdk-root", str(sdk.parent), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"][0]["name"] == sdk.name
    assert main(["describe", "env.export", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["command_id"] == "env.export"


def test_invalid_modes_and_missing_input(capsys, tmp_path):
    assert main(["doctor", "--interactive", "--non-interactive"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INVALID_ARGUMENT"
    assert main(["env", "sdk", "diff", "--sdk-root", str(tmp_path), "--non-interactive"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "NEEDS_INPUT"


def test_current_export_and_no_implicit_prepare(monkeypatch, capsys, make_sdk, tmp_path):
    monkeypatch.setenv("RAISA_CMODEL_PATH", "path with ' quotes $HOME")
    assert main(["env", "export", "--current", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["variables"]["RAISA_CMODEL_PATH"] == "path with ' quotes $HOME"
    sdk = make_sdk()
    assert main(["env", "export", "--sdk", sdk.name, "--sdk-root", str(sdk.parent),
                 "--cache-root", str(tmp_path / "cache")]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "ENV_NOT_PREPARED"
    assert not (tmp_path / "cache").exists()


def test_exec_argument_boundary_and_exit_code(make_sdk, tmp_path, capsys):
    sdk = make_sdk()
    assert main(["env", "exec", "--native-only", "--sdk-root", str(sdk.parent),
                 "--cache-root", str(tmp_path / "cache"), "--", "python", "-c", "print('exact'); raise SystemExit(7)"]) == 7
    result = json.loads(capsys.readouterr().out)["data"]
    assert result["stdout"].strip() == "exact"
    assert result["returncode"] == 7


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_real_shell_switch_and_restore(shell, make_sdk, tmp_path):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} not available on this platform")
    sdk = make_sdk()
    other = make_sdk("TX82_SDK_Daily_2026-10-23-02-52")
    cli = Path(sys.executable).parent / "triton-dev"
    assert cli.is_file(), "Install package before running CLI integration tests"
    # Invoked under an installed CLI; generated wrapper captures its stable absolute path.
    script = f'''
eval "$({cli} shell-init {shell})"
triton-dev env use --sdk {sdk.name} --sdk-root '{sdk.parent}' --native-only --non-interactive || exit 11
[ "$RAISA_CMODEL_PATH" = '{sdk}/' ] || exit 12
triton-dev env use --sdk {other.name} --sdk-root '{sdk.parent}' --native-only --non-interactive || exit 13
[ "$RAISA_CMODEL_PATH" = '{other}/' ] || exit 14
triton-dev env use --sdk NO_SUCH_SDK --sdk-root '{sdk.parent}' --native-only --non-interactive && exit 17
[ "$RAISA_CMODEL_PATH" = '{other}/' ] || exit 18
triton-dev env deactivate || exit 15
[ "$RAISA_CMODEL_PATH" = 'original value' ] || exit 16
printf '%s' "$PATH"
'''
    env = {**os.environ, "RAISA_CMODEL_PATH": "original value"}
    result = subprocess.run([executable, "-f" if shell == "zsh" else "--noprofile", "-c", script],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == env["PATH"]


def test_argument_errors_use_result_protocol(capsys):
    assert main(["diagnose", "compare", "--json", "--non-interactive"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "ARGUMENT_ERROR"


def test_subprocess_json_is_clean(make_sdk):
    sdk = make_sdk()
    result = subprocess.run([sys.executable, "-m", "triton_dev", "env", "sdk", "list",
                             "--sdk-root", str(sdk.parent), "--json", "--non-interactive"],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["status"] == "ok"
    assert result.stderr == ""
