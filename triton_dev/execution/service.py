import os
import tempfile
from pathlib import Path

from triton_dev.common.contracts import run_process
from triton_dev.env.service import process_environment, variables


def execute(environment, command, *, cwd=None, timeout=300):
    # No persistent per-run report files by default. Cache lives only for this execution.
    with tempfile.TemporaryDirectory(prefix="triton-dev-run-") as directory:
        env = process_environment(variables(environment))
        cache = Path(directory) / "cache"
        temporary = Path(directory) / "tmp"
        cache.mkdir()
        temporary.mkdir()
        env.update({"TRITON_CACHE_DIR": str(cache), "TMPDIR": str(temporary)})
        # Resolve `python` by the selected environment rather than the manager's interpreter.
        argv = list(command)
        if argv and argv[0] in ("python", "python3"):
            argv[0] = environment["interpreter"]
        return {**run_process(argv, env=env, cwd=cwd or os.getcwd(), timeout=timeout),
                "environment": environment}
