"""Scoped persistent compilation tasks; only registered isolation launchers execute code."""

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time

import sqlalchemy as sa
from triton_dev.common.contracts import ToolError, run_process, atomic_json
from triton_dev.platform.database import uid, fingerprint
from triton_dev.platform.repository import Repository
from triton_dev.platform import models as m
from .documents import make_document, MAX_EXPANDED

OPTIONS = {"num_warps", "num_stages", "num_ctas", "enable_fp_fusion", "debug", "enable_warp_specialization", "sanitize_overflow"}


def validate_spec(data):
    required = {"compiler_id", "code", "entry", "signature", "constexprs", "target", "options", "revision"}
    if not isinstance(data, dict) or set(data) != required:
        raise ToolError("INVALID_ARGUMENT", "Expected compiler, code, entry, signature, constexprs, target, options, revision")
    if not isinstance(data["code"], str) or not 0 < len(data["code"].encode()) <= 48000:
        raise ToolError("INVALID_ARGUMENT", "Kernel source must be 1..48000 bytes")
    if not isinstance(data["entry"], str) or not re.fullmatch(r"[A-Za-z_]\w{0,127}", data["entry"]):
        raise ToolError("INVALID_ARGUMENT", "Invalid kernel entry")
    if type(data["revision"]) is not int or not 0 <= data["revision"] <= 10**9:
        raise ToolError("INVALID_ARGUMENT", "Invalid source revision")
    for field in ("signature", "constexprs", "target", "options"):
        if not isinstance(data[field], dict):
            raise ToolError("INVALID_ARGUMENT", f"{field} must be an object")
    if not data["signature"] or any(not isinstance(k, str) or not k.isidentifier() or not isinstance(v, str)
                                   or not re.fullmatch(r"\*?(?:fp(?:8\w*|16|32|64)|bf16|[iu](?:1|8|16|32|64))", v)
                                   for k, v in data["signature"].items()):
        raise ToolError("INVALID_ARGUMENT", "Invalid compiler argument signature")
    if any(not isinstance(k, str) or not k.isidentifier() or type(v) not in {int, float, str, bool, type(None)} for k, v in data["constexprs"].items()):
        raise ToolError("INVALID_ARGUMENT", "constexprs must contain named scalar constants")
    target = data["target"]
    if set(target) != {"backend", "arch", "warp_size"} or not isinstance(target["backend"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", target["backend"]) or type(target["arch"]) not in {str, int} or type(target["warp_size"]) is not int or not 1 <= target["warp_size"] <= 128:
        raise ToolError("INVALID_ARGUMENT", "Invalid explicit compilation target")
    if set(data["options"]) - OPTIONS or any(type(v) not in {bool, int} for v in data["options"].values()):
        raise ToolError("INVALID_ARGUMENT", "Only registered scalar compiler options are accepted")
    if not isinstance(data["compiler_id"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", data["compiler_id"]):
        raise ToolError("INVALID_ARGUMENT", "Invalid registered compiler ID")
    try:
        # Syntax validation only. Edited Python executes exclusively inside the configured sandbox.
        ast.parse(data["code"])
        return json.loads(json.dumps(data, allow_nan=False))
    except (SyntaxError, ValueError) as exc:
        raise ToolError("INVALID_SOURCE", str(exc)) from exc


class CompilerRegistry:
    def __init__(self, entries=None):
        self.entries = json.loads(json.dumps(entries or {}))
        for key, config in self.entries.items():
            launcher = config.get("launcher") if isinstance(config, dict) else None
            if (not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key) or not isinstance(launcher, list)
                    or not launcher or any(not isinstance(a, str) or "\x00" in a for a in launcher)
                    or not Path(launcher[0]).is_absolute() or config.get("isolation") != "external"):
                raise ToolError("INVALID_COMPILER", "Register an absolute isolation launcher with isolation=external")
            if type(config.get("timeout", 60)) is not int or not 1 <= config.get("timeout", 60) <= 300:
                raise ToolError("INVALID_COMPILER", "Compiler timeout must be 1..300 seconds")
            if not isinstance(config.get("env", {}), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in config.get("env", {}).items()):
                raise ToolError("INVALID_COMPILER", "Compiler env must contain administrator-owned strings")

    @classmethod
    def from_environment(cls):
        path = os.environ.get("TRITON_DEV_IR_COMPILERS")
        return cls(json.loads(Path(path).read_text()) if path else {})

    def get(self, key):
        if not isinstance(key, str) or key not in self.entries:
            raise ToolError("COMPILER_UNAVAILABLE", "No isolated compiler registered for this environment")
        return self.entries[key]

    def catalog(self):
        return {"compilers": [{"id": key, "label": value.get("label", key), "timeout": value.get("timeout", 60)} for key, value in self.entries.items()],
                "available": bool(self.entries), "requires": "administrator_registered_isolation_launcher"}


class CompilationService:
    def __init__(self, db, registry):
        self.db, self.registry = db, registry

    def read(self, actor, task_id):
        record = Repository(self.db, actor["workspace_id"]).task(task_id)
        if record.get("platform_kind") != "ir":
            raise ToolError("NOT_FOUND", "Compilation not found")
        return record

    def list(self, actor):
        return Repository(self.db, actor["workspace_id"]).query(kind="ir")

    def submit(self, actor, data, key):
        spec = validate_spec(data)
        compiler = self.registry.get(spec["compiler_id"])
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key):
            raise ToolError("INVALID_ARGUMENT", "Idempotency key required")
        # Freeze administrator configuration too; a changed launcher never silently executes an old task.
        record = {"id": uid("ir_"), "platform_kind": "ir", "state": "queued", "phase": "queued", "created_at": time.time(),
                  "spec": spec, "compiler_digest": fingerprint(compiler), "document": None, "diagnostics": "", "error": None,
                  "source_hash": hashlib.sha256(spec["code"].encode()).hexdigest(), "source": "compiler_task"}
        return Repository(self.db, actor["workspace_id"]).enqueue("ir", record, key, fingerprint({"spec": spec, "compiler": compiler}))

    def cancel(self, actor, task_id):
        self.read(actor, task_id)
        with self.db.tx() as c:
            row = c.execute(sa.select(m.tasks).where(m.tasks.c.id == task_id, m.tasks.c.workspace_id == actor["workspace_id"]).with_for_update()).mappings().one()
            value = row["payload"]
            if row["queue_state"] == "queued":
                value = {**value, "state": "cancelled", "phase": "cancelled"}
                c.execute(m.tasks.update().where(m.tasks.c.id == task_id).values(cancel_requested=True, state="cancelled", queue_state="done", payload=value))
            elif row["queue_state"] == "leased" and row["state"] in {"queued", "running"}:
                c.execute(m.tasks.update().where(m.tasks.c.id == task_id).values(cancel_requested=True))
        return self.read(actor, task_id)

    def execute(self, row, cancel):
        repo = Repository(self.db, row["workspace_id"])
        record = self.read({"workspace_id": row["workspace_id"]}, row["id"])
        if cancel.is_set():
            record.update(state="cancelled", phase="cancelled", completed_at=time.time())
            repo.put("ir", record)
            return
        record.update(state="running", phase="compiling")
        repo.put("ir", record)
        root = repo.root / "compilations" / row["id"]
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
        spec = record["spec"]
        compiler = self.registry.get(spec["compiler_id"])
        if fingerprint(compiler) != record["compiler_digest"]:
            raise ToolError("SOURCE_CHANGED", "Registered compiler configuration changed after submission")
        (root / "kernel.py").write_text(spec["code"])
        atomic_json(root / "spec.json", spec)
        shutil.copyfile(Path(__file__).with_name("worker.py"), root / "worker.py")
        launcher = [arg.replace("{workdir}", str(root)) for arg in compiler["launcher"]]
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(root), "TMPDIR": str(root),
               "PYTHONNOUSERSITE": "1", "TRITON_CACHE_DIR": str(root / "cache"),
               "TRITON_DEBUG": "1", **compiler.get("env", {})}
        try:
            process = run_process(launcher, env=env, cwd=root, timeout=compiler.get("timeout", 60), cancel=cancel, max_output=256000)
            record["diagnostics"] = process["stdout"] + "\n" + process["stderr"]
            if process["returncode"]:
                raise ToolError("COMPILE_FAILED", "Compiler failed; inspect compilation diagnostics")
            artifact = root / "artifacts.json"
            # The compiler workdir is untrusted. Never follow an output symlink,
            # read a device/FIFO, or race an unbounded stat-then-read operation.
            fd = os.open(artifact, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_EXPANDED:
                    raise ValueError('Compiler must produce a bounded regular artifacts.json')
                raw = stream.read(MAX_EXPANDED + 1)
            if len(raw) > MAX_EXPANDED:
                raise ValueError('Compiler artifacts exceed size limit')
            def invalid_constant(value):
                raise ValueError('Nonfinite compiler metadata')
            data = json.loads(raw, parse_constant=invalid_constant)
            record["document"] = make_document({"code": spec["code"], "file_path": data["source_path"], "start_line": 1},
                                                data["files"], metadata={**data.get("metadata", {}), "name": spec["entry"], "target": spec["target"], "signature": spec["signature"], "constexprs": spec["constexprs"], "options": spec["options"], "compiler_id": spec["compiler_id"]}, source_kind="compiled")
            record.update(state="passed", phase="completed")
        except ToolError as exc:
            record.update(state={"CANCELLED": "cancelled", "TIMEOUT": "timeout"}.get(exc.code, "failed"), phase="completed", error={"code": exc.code, "message": str(exc)})
            if exc.details:
                record["diagnostics"] = exc.details.get("stdout", "") + "\n" + exc.details.get("stderr", "")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            record.update(state="error", phase="completed", error={"code": "INVALID_COMPILER_OUTPUT", "message": str(exc)})
        record["completed_at"] = time.time()
        repo.put("ir", record)
