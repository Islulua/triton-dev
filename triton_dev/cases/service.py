import json
import os
import sys
import tempfile
from pathlib import Path

from triton_dev.common.contracts import ToolError, run_process


def collect(path, *, python=sys.executable, marker=None, timeout=60):
    path = Path(path).resolve()
    with tempfile.TemporaryDirectory(prefix="triton-dev-collect-") as directory:
        output = Path(directory) / "collection.json"
        argv = [str(python), "-m", "pytest", "--collect-only", "-q", "-p",
                "triton_dev.pytest_plugin", "--triton-dev-collection-output", str(output), str(path)]
        if marker:
            argv.extend(["-m", marker])
        env = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = package_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        result = run_process(argv, env=env, cwd=path if path.is_dir() else path.parent, timeout=timeout)
        if result["returncode"] not in (0, 5):
            raise ToolError("COLLECTION_FAILED", "pytest collection failed", details=result)
        if not output.exists():
            raise ToolError("COLLECTION_FAILED", "Collection adapter produced no result", details=result)
        return {"cases": json.loads(output.read_text()), "returncode": result["returncode"]}
