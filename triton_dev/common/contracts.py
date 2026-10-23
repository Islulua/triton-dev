from __future__ import annotations

import hashlib
import json
import os
import signal
import selectors
import time
import codecs
import math
import subprocess
import uuid
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
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
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


def run_process(argv, *, env=None, cwd=None, timeout=300, cancel=None,
                on_chunk=None, max_output=1024 * 1024):
    """Drain both pipes continuously; retain bounded tails and optional streamed evidence."""
    if not argv or not math.isfinite(timeout) or timeout <= 0 or max_output < 1:
        raise ToolError("INVALID_ARGUMENT", "Command, positive timeout/output budget required")
    try:
        proc = subprocess.Popen(list(argv), env=env, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        raise ToolError("PROCESS_START_FAILED", str(exc)) from exc
    started = time.monotonic()
    stopped = None
    reason = None
    tails = {"stdout": bytearray(), "stderr": bytearray()}
    totals = {"stdout": 0, "stderr": 0}
    decoders = {key: codecs.getincrementaldecoder("utf-8")("replace") for key in tails}
    def stop(sig):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
    try:
        with selectors.DefaultSelector() as selector:
            for key in tails:
                selector.register(getattr(proc, key), selectors.EVENT_READ, key)
            while selector.get_map() or proc.poll() is None:
                now = time.monotonic()
                if reason is None and ((cancel is not None and cancel.is_set()) or now - started >= timeout):
                    reason = "CANCELLED" if cancel is not None and cancel.is_set() else "TIMEOUT"
                    stopped = now
                    stop(signal.SIGTERM)
                if stopped is not None and now - stopped >= 2:
                    stop(signal.SIGKILL)
                if stopped is not None and now - stopped >= 3:
                    break
                for key, _ in selector.select(0.05):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    name = key.data
                    totals[name] += len(chunk)
                    tails[name].extend(chunk)
                    if len(tails[name]) > max_output:
                        del tails[name][:-max_output]
                    if on_chunk:
                        on_chunk(name, decoders[name].decode(chunk))
            proc.wait(timeout=3)
    except KeyboardInterrupt as exc:
        stop(signal.SIGKILL)
        proc.wait()
        raise ToolError("CANCELLED", "Process group stopped by interrupt", details={
            "returncode": proc.returncode,
            **{name: bytes(value).decode("utf-8", "replace") for name, value in tails.items()}
        }) from exc
    except BaseException:
        stop(signal.SIGKILL)
        proc.wait()
        raise
    finally:
        proc.stdout.close()
        proc.stderr.close()
    result = {"argv": list(argv), "returncode": proc.returncode,
              "outcome": "passed" if proc.returncode == 0 else "failed",
              **{name: bytes(value).decode("utf-8", "replace") for name, value in tails.items()},
              "output_bytes": totals,
              "output_truncated": {name: count > max_output for name, count in totals.items()}}
    if reason:
        raise ToolError(reason, "Process group stopped", details=result)
    return result
