from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
from contextlib import contextmanager
from pathlib import Path


class ToolError(Exception):
    def __init__(self, code: str, message: str, *, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def envelope(data=None, error: ToolError | None = None):
    return {
        "schema_version": 1,
        "status": "unsupported" if error and error.code == "UNSUPPORTED" else (
            "failed" if error else "ok"
        ),
        "data": data,
        "error": None if not error else {
            "code": error.code, "message": str(error), "details": error.details,
        },
        "evidence": [],
    }


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def file_lock(path: Path):
    # POSIX is the target platform; avoid lock-file deletion races.
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run_process(argv, *, env=None, cwd=None, timeout=300):
    if not argv or timeout <= 0:
        raise ToolError("INVALID_ARGUMENT", "A command and positive timeout are required")
    try:
        proc = subprocess.Popen(
            list(argv), env=env, cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True,
        )
    except OSError as exc:
        raise ToolError("PROCESS_START_FAILED", str(exc)) from exc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        raise ToolError(
            "TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "CANCELLED",
            "Process group stopped", details={"stdout": stdout, "stderr": stderr},
        ) from exc
    return {
        "argv": list(argv), "returncode": proc.returncode,
        "outcome": "passed" if proc.returncode == 0 else "failed",
        "stdout": stdout, "stderr": stderr,
    }
