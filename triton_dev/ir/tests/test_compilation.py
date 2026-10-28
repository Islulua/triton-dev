import sys
import time

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.ir.compilation import CompilerRegistry, CompilationService, validate_spec
from triton_dev.platform.service import Platform


def spec(**overrides):
    return {"compiler_id": "fixture", "code": "def kernel(x):\n    return x + 1\n", "entry": "kernel",
            "signature": {"x": "i32"}, "constexprs": {}, "target": {"backend": "txda", "arch": "tx82", "warp_size": 32},
            "options": {}, "revision": 1, **overrides}


def test_unknown_compiler_and_invalid_specs_fail_before_running_source():
    with pytest.raises(ToolError, match="compiler"):
        CompilerRegistry({}).get("missing")
    for bad in [spec(code=""), spec(entry="not valid"), spec(signature={"x": "bad type"}), spec(revision=True), spec(options={"external_libs": "/etc/passwd"})]:
        with pytest.raises(ToolError):
            validate_spec(bad)


def test_real_subprocess_boundary_keeps_service_secrets_out_and_persists_private_results(tmp_path, monkeypatch):
    runner = tmp_path / "fixture_runner.py"
    runner.write_text('''import json, os
from pathlib import Path
assert "SERVICE_SECRET_FOR_TEST" not in os.environ
spec = json.loads(Path("spec.json").read_text())
source = str(Path("kernel.py").resolve())
ir = '%0 = arith.addi %a, %b : i32 loc(#loc1)\\n#loc1 = loc("' + source + '":2:5)'
Path("artifacts.json").write_text(json.dumps({"source_path": source, "files": {"k.ttir": ir}, "metadata": {"name": spec["entry"]}}))
print("fixture subprocess completed")
''')
    registry = CompilerRegistry({"fixture": {"label": "Test subprocess fixture", "launcher": [sys.executable, str(runner)], "isolation": "external", "timeout": 10}})
    monkeypatch.setenv("SERVICE_SECRET_FOR_TEST", "must-not-leak")
    platform = Platform("sqlite:///" + str(tmp_path / "db.sqlite"), tmp_path / "state", ir_compilers=registry)
    try:
        actor, _ = platform.auth.login("alice")
        other, _ = platform.auth.login("bob")
        service = CompilationService(platform.db, registry)
        record = service.submit(actor, spec(), "one")
        assert service.submit(actor, spec(), "one")["id"] == record["id"]
        with pytest.raises(ToolError, match="different"):
            service.submit(actor, spec(revision=2), "one")
        with pytest.raises(ToolError):
            service.read(other, record["id"])
        for _ in range(200):
            record = service.read(actor, record["id"])
            if record["state"] not in {"queued", "running"}:
                break
            time.sleep(.03)
        assert record["state"] == "passed", record
        assert record["document"]["stages"][0]["mapping"]["1"]["line"] == 2
        assert record["document"]["source"]["code"] == spec()["code"]
        assert "fixture subprocess completed" in record["diagnostics"]
        assert record["spec"]["revision"] == 1
    finally:
        platform.close()


def test_queued_cancel_never_runs_launcher(tmp_path):
    registry = CompilerRegistry({"fixture": {"launcher": [sys.executable, "-c", "raise Exception('must not run')"], "isolation": "external"}})
    p = Platform("sqlite:///" + str(tmp_path / "db.sqlite"), tmp_path / "state", ir_compilers=registry, start_worker=False)
    try:
        actor, _ = p.auth.login("alice")
        service = CompilationService(p.db, registry)
        record = service.submit(actor, spec(), "cancel")
        assert service.cancel(actor, record["id"])["state"] == "cancelled"
        assert p.queue.claim() is None
    finally:
        p.close()


def test_cancel_after_claim_before_execute_never_launches(tmp_path):
    marker = tmp_path / 'launched'
    registry = CompilerRegistry({'fixture': {'launcher': [sys.executable, '-c', f'from pathlib import Path;Path({str(marker)!r}).touch()'], 'isolation': 'external'}})
    p = Platform('sqlite:///' + str(tmp_path / 'db.sqlite'), tmp_path / 'state', ir_compilers=registry, start_worker=False)
    try:
        actor, _ = p.auth.login('alice')
        service = CompilationService(p.db, registry)
        record = service.submit(actor, spec(), 'claimed-cancel')
        row = p.queue.claim()
        service.cancel(actor, record['id'])
        p.queue.execute(row)
        assert service.read(actor, record['id'])['state'] == 'cancelled'
        assert not marker.exists()
    finally:
        p.close()


def test_compiler_cannot_return_artifact_symlink(tmp_path):
    external = tmp_path / 'external.json'
    external.write_text('{"source_path":"kernel.py","files":{"k.ttir":"module {}"}}')
    runner = tmp_path / 'runner.py'
    runner.write_text(f'import os;os.symlink({str(external)!r}, "artifacts.json")')
    registry = CompilerRegistry({'fixture': {'launcher': [sys.executable, str(runner)], 'isolation': 'external'}})
    p = Platform('sqlite:///' + str(tmp_path / 'db.sqlite'), tmp_path / 'state', ir_compilers=registry, start_worker=False)
    try:
        actor, _ = p.auth.login('alice')
        service = CompilationService(p.db, registry)
        record = service.submit(actor, spec(), 'symlink')
        p.queue.execute(p.queue.claim())
        record = service.read(actor, record['id'])
        assert record['state'] == 'error'
        assert record['document'] is None
    finally:
        p.close()
