from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from triton_dev.common.contracts import ToolError, atomic_json, file_lock, run_process
from .sdk import normalize, select, wheels
from .settings import MANAGED


def python_identity(python):
    result = run_process([str(python), "-I", "-c",
                          "import sys,sysconfig; print(sys.version); print(sysconfig.get_platform())"])
    if result["returncode"]:
        raise ToolError("PYTHON_UNAVAILABLE", "Interpreter identity probe failed", details=result)
    return result["stdout"]


def plan(root, selector="latest", *, overrides=None, python=sys.executable):
    overrides = overrides or {}
    unknown = set(overrides) - {"triton", "torch_raisa", "raops"}
    if unknown:
        raise ToolError("UNSUPPORTED", "Native component mapping is not confirmed", details={"components": sorted(unknown)})
    from .preflight import target, check
    executable = shutil.which(str(python))
    if executable is None:
        raise ToolError("PYTHON_UNAVAILABLE", f"Interpreter not found or executable: {python}")
    context = target(executable)
    sdk = select(root, selector)
    selected = {normalize(item["name"]).replace("-", "_"): item for item in wheels(sdk, context=context)}
    for component, version in overrides.items():
        source = select(root, version)
        candidates = {normalize(item["name"]).replace("-", "_"): item for item in wheels(source, context=context)}
        selected[component] = candidates[component]
    # Preserve venv symlinks: resolving them can change interpreter context.
    executable = os.path.abspath(executable)
    data = {"sdk": str(sdk), "python": executable,
            "python_identity": python_identity(executable), "wheels": list(selected.values()),
            "preparation_version": 3, "preflight": check(list(selected.values()), context)}
    data["key"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:24]
    data["native_loading"] = "not_checked"
    return data


def install(python, wheel_paths, wheel_dirs):
    command = [str(python), "-m", "pip", "install", "--no-index"]
    for path in sorted(set(wheel_dirs)):
        command.extend(["--find-links", path])
    result = run_process(command + list(wheel_paths), timeout=1800)
    if result["returncode"]:
        raise ToolError("INSTALL_FAILED", "Offline wheel installation failed", details=result)


def prepare(root, cache, selector="latest", *, overrides=None, python=sys.executable,
            installer=None, creator=None):
    spec = plan(root, selector, overrides=overrides, python=python)
    destination = cache / "environments" / spec["key"]
    receipt = destination / "ready.json"
    with file_lock(cache / "locks" / (spec["key"] + ".lock")):
        if receipt.is_file():
            recorded = json.loads(receipt.read_text())
            if recorded["key"] == spec["key"] and (destination / "venv/bin/python").exists():
                return {**recorded, "reused": True}
        if destination.exists():
            # Never overwrite an environment that could be used by another process.
            raise ToolError("INCOMPLETE_ENVIRONMENT", f"Inspect/remove failed preparation explicitly: {destination}")
        destination.mkdir(parents=True)
        venv_path = destination / "venv"
        if creator:
            creator(venv_path)
        else:
            result = run_process([spec["python"], "-I", "-m", "venv", str(venv_path)],
                                 timeout=300)
            if result["returncode"]:
                raise ToolError("VENV_CREATION_FAILED", "Selected Python could not create venv",
                                details=result)
        wheel_python = venv_path / "bin/python"
        if python_identity(wheel_python) != spec["python_identity"]:
            raise ToolError("PYTHON_IDENTITY_MISMATCH", "Created venv differs from selected Python")
        (installer or install)(wheel_python, [w["path"] for w in spec["wheels"]],
                               [str(Path(w["path"]).parent) for w in spec["wheels"]])
        # Re-resolve after installation to avoid publishing a changed source combination.
        if plan(root, selector, overrides=overrides, python=python)["key"] != spec["key"]:
            raise ToolError("SOURCE_CHANGED", "SDK changed during preparation")
        ready = {**spec, "venv": str(venv_path), "interpreter": str(wheel_python),
                 "state": "installed", "native_loading": "not_checked"}
        atomic_json(receipt, ready)
        return {**ready, "reused": False}


def resolve(root, cache, selector="latest", *, overrides=None, native_only=False, python=sys.executable):
    if native_only:
        if overrides:
            raise ToolError("INVALID_ARGUMENT", "--native-only cannot select Python wheel overrides")
        return {"sdk": str(select(root, selector)), "interpreter": str(python),
                "state": "native_paths_only", "native_loading": "not_checked"}
    spec = plan(root, selector, overrides=overrides, python=python)
    receipt = cache / "environments" / spec["key"] / "ready.json"
    if not receipt.exists():
        raise ToolError("ENV_NOT_PREPARED", "Run env prepare first; export/exec never silently install packages")
    data = json.loads(receipt.read_text())
    if not Path(data["interpreter"]).exists():
        raise ToolError("ENV_NOT_PREPARED", "Prepared interpreter no longer exists")
    return data


def variables(environment, inherited=None):
    inherited = dict(os.environ if inherited is None else inherited)
    sdk = environment["sdk"]
    base_path = inherited.get("TRITON_DEV_BASE_PATH", inherited.get("PATH", os.defpath))
    values = {
        "ENABLE_CMODEL": "1", "RAISA_FW_PATH": sdk + "/",
        "RAISA_C_TOOLCHAIN_PATH": sdk + "/", "RAISA_CMODEL_PATH": sdk + "/",
        "LD_LIBRARY_PATH": sdk + "/lib", "TRITON_DEV_SDK": sdk,
        "TRITON_DEV_BASE_PATH": base_path,
    }
    unset = ["PYTHONHOME", "PYTHONPATH", "TRITON_CACHE_DIR"]
    if environment.get("venv"):
        values.update({"VIRTUAL_ENV": environment["venv"],
                       "PATH": str(Path(environment["venv"]) / "bin") + os.pathsep + base_path})
    else:
        # Native-only is explicit: it does not claim SDK wheel isolation.
        values["PATH"] = base_path
        unset.append("VIRTUAL_ENV")
    return {"variables": values, "unset": unset, "state": environment["state"],
            "native_loading": environment["native_loading"]}


def current_variables(include=(), all_variables=False):
    keys = set(os.environ) if all_variables else set(MANAGED) | set(include)
    return {"variables": {k: os.environ[k] for k in sorted(keys) if k in os.environ},
            "unset": sorted(k for k in keys if k not in os.environ), "source": "inherited"}


def render_shell(data):
    lines = []
    for name in data.get("unset", []):
        if not name.isidentifier() or not name.isascii():
            raise ToolError("INVALID_VARIABLE", name)
        lines.append(f"unset {name}")
    for name, value in sorted(data["variables"].items()):
        if not name.isidentifier() or not name.isascii():
            raise ToolError("INVALID_VARIABLE", name)
        lines.append(f"export {name}={shlex.quote(value)}")
    return "\n".join(lines) + "\n"


def process_environment(data):
    env = os.environ.copy()
    for key in data.get("unset", []):
        env.pop(key, None)
    env.update(data["variables"])
    env["PYTHONNOUSERSITE"] = "1"
    return env


def probe(environment):
    script = (
        "import importlib,json; out={}; "
        "exec(\"for name in ('raops','torch_raisa','triton'):\\n"
        " try:\\n  m=importlib.import_module(name); out[name]={'path':getattr(m,'__file__',None)}\\n"
        " except Exception as e:\\n  out[name]={'error':type(e).__name__+': '+str(e)}\"); "
        "print(json.dumps(out))"
    )
    result = run_process([environment["interpreter"], "-c", script],
                         env=process_environment(variables(environment)), timeout=60)
    if result["returncode"]:
        raise ToolError("PROBE_FAILED", "Import probe failed", details=result)
    return {"modules": json.loads(result["stdout"]), "native_loading": "not_checked",
            "limitation": "Import paths are observations, not native ABI or functional verification"}
