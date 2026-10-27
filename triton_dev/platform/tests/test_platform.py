import datetime as dt
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from triton_dev.common.contracts import ToolError
from triton_dev.platform import models as m
from triton_dev.platform.app import create_app
from triton_dev.platform.database import LEASE, SYSTEM
from triton_dev.platform.repository import Repository
from triton_dev.platform.service import Platform

BACKENDS = ["sqlite"] + (["postgresql"] if os.getenv("TRITON_DEV_TEST_DATABASE_URL") else [])


@pytest.fixture(params=BACKENDS)
def platform(tmp_path, request):
    cleanup = None
    if request.param == "postgresql":
        base = os.environ["TRITON_DEV_TEST_DATABASE_URL"]
        engine = sa.create_engine(base)
        schema = "test_" + uuid.uuid4().hex
        with engine.begin() as c:
            c.execute(sa.text("CREATE SCHEMA " + schema))
        url = (
            sa.engine.make_url(base)
            .update_query_dict({"options": "-csearch_path=" + schema})
            .render_as_string(hide_password=False)
        )

        def cleanup():
            with engine.begin() as c:
                c.execute(sa.text("DROP SCHEMA " + schema + " CASCADE"))
            engine.dispose()
    else:
        url = "sqlite:///" + str(tmp_path / "db.sqlite")
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_sample.py").write_text(
        'import pytest\n@pytest.mark.parametrize("n", [1,2])\ndef test_value(n):\n assert n == 1\n'
    )
    jobs = {
        "quick": {"argv": [sys.executable, "-c", 'print("hello")'], "cwd": str(tmp_path)},
        "slow": {
            "argv": [sys.executable, "-c", "import time;time.sleep(10)"],
            "cwd": str(tmp_path),
        },
        "pytest": {
            "kind": "pytest",
            "argv": ["test_sample.py"],
            "cwd": str(project),
            "timeout": 15,
        },
    }
    value = Platform(url, tmp_path / "state", jobs, allowed_endpoints=["http://127.0.0.1:9901/v1"])
    yield value
    value.close()
    if cleanup:
        cleanup()


def enter(client, name):
    r = client.post("/api/sessions", json={"name": name})
    assert r.status_code == 200, r.text
    user = r.json()["data"]
    client.headers["X-CSRF-Token"] = user["csrf_token"]
    return user


def finished(p, actor, task_id):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        task = p.manager(actor).repo.task(task_id)
        with p.db.tx() as c:
            queue = c.execute(
                sa.select(m.tasks.c.queue_state).where(m.tasks.c.id == task_id)
            ).scalar_one()
        if queue == "done":
            return task
        time.sleep(0.03)
    pytest.fail("Task did not complete: " + str(task))


def test_name_sessions_csrf_and_private_profiles(platform):
    app = create_app(platform)
    a, b = TestClient(app), TestClient(app)
    alice = enter(a, " Alice ")
    bob = enter(b, "Bob")
    assert alice["workspace_id"] != bob["workspace_id"]
    assert not alice["identity_verified"]
    same = TestClient(app)
    assert enter(same, "alice")["workspace_id"] == alice["workspace_id"]
    assert a.get("/api/me").json()["data"]["name"] == "Alice"
    assert (
        a.post(
            "/api/me/ai-profiles",
            json={
                "name": "mock",
                "provider": "mock",
                "api_key": "FAKE_SECRET_FOR_TEST",
                "is_default": True,
            },
        ).status_code
        == 200
    )
    profile = a.get("/api/me/ai-profiles").json()["data"][0]
    assert profile["has_key"] and "FAKE_SECRET" not in json.dumps(profile)
    with platform.db.tx() as c:
        secret = c.execute(sa.select(m.secrets.c.ciphertext)).scalar_one()
        assert "FAKE_SECRET_FOR_TEST" not in secret
        assert platform.profiles.cipher.decrypt(secret.encode()).decode() == "FAKE_SECRET_FOR_TEST"
    assert b.get("/api/me/ai-profiles").json()["data"] == []
    assert (
        b.patch(
            "/api/me/ai-profiles/" + profile["id"], json={"name": "steal", "provider": "mock"}
        ).status_code
        == 404
    )
    assert b.post("/api/me/ai-profiles/" + profile["id"] + "/test", json={}).status_code == 404
    old = profile["current_revision"]
    updated = a.patch(
        "/api/me/ai-profiles/" + profile["id"],
        json={"name": "mock", "provider": "mock", "model": "mock-planner-v1"},
    ).json()["data"]
    assert updated["current_revision"] != old and updated["has_key"]
    assert (
        a.post("/api/me/ai-profiles/" + profile["id"] + "/test", json={}).json()["data"][
            "network_called"
        ]
        is False
    )
    stranger = TestClient(app)
    assert (
        stranger.get(
            "/api/tasks", headers={"Authorization": "Bearer legacy-token-cannot-bypass"}
        ).status_code
        == 401
    )
    assert (
        a.post(
            "/api/tasks",
            json={"job_id": "quick", "idempotency_key": "x"},
            headers={"X-CSRF-Token": "bad"},
        ).status_code
        == 403
    )
    assert a.request("DELETE", "/api/session", json={}).status_code == 200
    assert a.get("/api/me").status_code == 401
    assert a.get("/api/tasks", headers={"Origin": "http://attacker.example"}).status_code == 403


def test_task_isolation_real_pytest_and_index(platform):
    a, b = TestClient(create_app(platform)), TestClient(create_app(platform))
    alice, bob = enter(a, "A"), enter(b, "B")
    first = a.post("/api/tasks", json={"job_id": "pytest", "idempotency_key": "same-key"}).json()[
        "data"
    ]
    second = b.post("/api/tasks", json={"job_id": "pytest", "idempotency_key": "same-key"}).json()[
        "data"
    ]
    assert first["id"] != second["id"]
    collection = finished(platform, alice, first["id"])
    assert collection["state"] == "passed" and len(collection["collection"]) == 2, collection
    assert b.get("/api/tasks/" + first["id"]).status_code == 404
    assert b.get("/api/tasks/" + first["id"] + "/events").status_code == 404
    assert b.get("/api/tasks/" + first["id"] + "/artifacts/not-found").status_code == 404
    selection = {
        "collection_id": first["id"],
        "nodeids": [r["nodeid"] for r in collection["collection"]],
        "isolation": "session",
        "idempotency_key": "run",
    }
    assert b.post("/api/pytest/runs", json=selection).status_code == 404
    run = a.post("/api/pytest/runs", json=selection).json()["data"]
    result = finished(platform, alice, run["id"])
    assert result["state"] == "failed", result
    rows = a.get("/api/case-results").json()["data"]
    assert sorted(r["outcome"] for r in rows) == ["failed", "passed"]
    assert b.get("/api/case-results").json()["data"] == []
    with platform.db.tx() as c:
        assert (
            c.execute(
                sa.select(sa.func.count())
                .select_from(m.stage_results)
                .where(m.stage_results.c.task_id == run["id"])
            ).scalar_one()
            == 6
        )
    assert (
        b.post(
            "/api/tasks/" + run["id"] + "/rerun", json={"mode": "all", "idempotency_key": "steal"}
        ).status_code
        == 404
    )
    assert str(platform.manager(alice).store.directory(first["id"])).startswith(
        str(platform.db.root / "workspaces" / alice["workspace_id"])
    )
    finished(platform, bob, second["id"])


def test_regression_queue_profile_pin_and_scoped_reports(platform):
    a, b = TestClient(create_app(platform)), TestClient(create_app(platform))
    alice, bob = enter(a, "Agent-A"), enter(b, "Agent-B")
    profile = a.post(
        "/api/me/ai-profiles", json={"name": "private mock", "provider": "mock", "is_default": True}
    ).json()["data"]
    body = {
        "config": {"scenario": "no_regression", "repeats": 1},
        "idempotency_key": "reg",
        "profile_id": profile["id"],
    }
    task = a.post("/api/regression/tasks", json=body).json()["data"]
    assert task["ai_profile_revision_id"] == profile["current_revision"]
    done = finished(platform, alice, task["id"])
    assert done["result"] == "no_regression", done
    for suffix in ["", "/report", "/bundle", "/experiments/exp_0001"]:
        assert b.get("/api/regression/tasks/" + task["id"] + suffix).status_code == 404
    assert b.post("/api/regression/tasks/" + task["id"] + "/cancel", json={}).status_code == 404
    assert a.get("/api/regression/tasks/" + task["id"] + "/report").status_code == 200
    assert a.get("/api/regression/tasks/" + task["id"] + "/bundle").content.startswith(b"\x1f\x8b")
    assert b.get("/api/regression/tasks").json()["data"] == []
    assert a.post("/api/regression/tasks", json=body).json()["data"]["id"] == task["id"]
    assert (
        a.post(
            "/api/regression/tasks", json=body | {"config": {"scenario": "bad_baseline"}}
        ).status_code
        == 409
    )
    assert (
        a.get("/api/data/tasks?kind=regression&limit=1").json()["data"]["items"][0]["id"]
        == task["id"]
    )
    assert platform.usage(bob["workspace_id"])["tasks"] == 0


def test_queue_cancel_concurrent_claim_and_fencing(platform):
    user, _ = platform.auth.login("queue")
    task = platform.manager(user).submit("slow", "slow")
    platform.manager(user).cancel(task["id"])
    assert finished(platform, user, task["id"])["state"] == "cancelled"
    platform.queue.stop.set()
    platform.queue.thread.join(timeout=3)
    manager = platform.manager(user)
    waiting = manager.submit("quick", "claim")
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: platform.queue.claim(), range(2)))
    assert sum(x is not None for x in claims) == 1
    row = next(x for x in claims if x)
    token = LEASE.set(
        {"id": row["id"], "generation": row["generation"] - 1, "worker_id": row["worker_id"]}
    )
    try:
        with pytest.raises(ToolError, match="Old worker"):
            manager.repo.put("pytest", manager.repo.task(waiting["id"]))
    finally:
        LEASE.reset(token)


def test_blob_hash_query_pagination_and_legacy(platform, tmp_path):
    a, _ = platform.auth.login("storage A")
    b, _ = platform.auth.login("storage B")
    ar, br = Repository(platform.db, a["workspace_id"]), Repository(platform.db, b["workspace_id"])
    blob = ar.put_blob(b"private proof", None, "proof.txt")
    assert ar.blob(blob)[0] == b"private proof"
    with pytest.raises(ToolError):
        br.blob(blob)
    for i in range(3):
        ar.put(
            "pytest",
            {
                "id": "run_" + uuid.uuid4().hex,
                "state": "passed",
                "created_at": 100 + i,
                "request": {},
                "result": None,
                "stages": [],
            },
        )
    first = ar.query(limit=2)
    second = ar.query(limit=2, cursor=first["next_cursor"])
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert not br.query()["items"]
    legacy = tmp_path / "old"
    record = legacy / ("run_" + "b" * 32)
    record.mkdir(parents=True)
    (record / "record.json").write_text(
        json.dumps(
            {
                "id": record.name,
                "state": "passed",
                "created_at": 1,
                "request": {},
                "result": None,
                "stages": [],
            }
        )
    )
    child = legacy / ("run_" + "a" * 32)
    child.mkdir()
    (child / "record.json").write_text(
        json.dumps(
            {
                "id": child.name,
                "parent": record.name,
                "state": "passed",
                "created_at": 2,
                "request": {},
                "result": None,
                "stages": [],
            }
        )
    )
    assert platform.import_legacy(legacy)["imported"] == 2
    assert platform.import_legacy(legacy)["imported"] == 0
    assert len(ar.query()["items"]) == 3


def test_daily_public_catalog_idempotency_and_candidate_scope(platform):
    manifest = {
        "source": "team-sdk",
        "channel": "daily",
        "platform": "cpu-demo",
        "build_id": "build1",
        "build_date": "2026-10-27",
        "components": {"llvm": {"version": "mock-v1", "sha256": "f" * 64}},
        "source_kind": "mock",
    }
    build = platform.daily.import_build(manifest)
    assert (
        platform.daily.import_build(manifest)["id"] == build["id"] and build["state"] == "candidate"
    )
    changed = platform.daily.import_build(
        manifest | {"components": {"llvm": {"version": "mock-v1", "sha256": "a" * 64}}}
    )
    assert changed["id"] != build["id"]
    platform.daily.definition("CPU daily", "quick")
    batch = platform.daily.tick(dt.datetime(2026, 10, 27, 12, tzinfo=dt.timezone.utc))[0]
    assert (
        platform.daily.tick(dt.datetime(2026, 10, 27, 12, tzinfo=dt.timezone.utc))[0]["id"]
        == batch["id"]
    )
    finished(platform, {"workspace_id": SYSTEM}, batch["task_id"])
    client = TestClient(create_app(platform))
    enter(client, "Daily reader")
    assert len(client.get("/api/sdk-builds").json()["data"]) == 2
    public = client.get("/api/daily-batches").json()["data"][0]
    assert public["summary"]["sdk_installed"] is False
    assert client.get("/api/daily-batches/" + batch["id"] + "/task").status_code == 200
    assert client.get("/api/tasks/" + batch["task_id"]).status_code == 404
    assert client.get("/api/tasks").json()["data"] == []


def test_quota_idempotency_profile_revision_and_lease_recovery(platform):
    platform.queue.close()
    client = TestClient(create_app(platform))
    actor = enter(client, "Recovery owner")
    workspace = actor["workspace_id"]
    profile = platform.profiles.save(workspace, {"name": "Planner", "is_default": True})
    task = platform.regression_start(actor, {"scenario": "no_regression"}, "frozen-profile")
    updated = platform.profiles.save(
        workspace, {"name": "Planner", "model": "mock-v2"}, profile["id"]
    )
    assert updated["current_revision"] != profile["current_revision"]
    with platform.db.tx() as c:
        assert (
            c.execute(
                sa.select(m.tasks.c.profile_revision_id).where(m.tasks.c.id == task["id"])
            ).scalar_one()
            == profile["current_revision"]
        )
    claimed = platform.queue.claim()
    assert claimed["id"] == task["id"]
    with platform.db.tx() as c:
        c.execute(
            m.tasks.update().where(m.tasks.c.id == task["id"]).values(lease_until=time.time() - 1)
        )
    platform.queue.reconcile()
    assert Repository(platform.db, workspace).task(task["id"])["state"] == "interrupted"
    stale = LEASE.set(
        {"id": task["id"], "generation": claimed["generation"], "worker_id": claimed["worker_id"]}
    )
    try:
        with pytest.raises(ToolError, match="Old worker cannot"):
            Repository(platform.db, workspace).put("regression", task)
    finally:
        LEASE.reset(stale)
    with pytest.raises(ToolError, match="Old worker"):
        platform.queue.resume(workspace, task["id"])
    # A completed process is proved with a real child PID, not a guessed PID.
    import subprocess

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    with platform.db.tx() as c:
        c.execute(m.tasks.update().where(m.tasks.c.id == task["id"]).values(worker_pid=child.pid))
    assert platform.queue.resume(workspace, task["id"])["state"] == "queued"
    manager = platform.manager(actor)
    for i in range(19):
        manager.submit("quick", "quota_" + str(i))
    existing = manager.submit("quick", "quota_0")
    assert existing["id"] == manager.submit("quick", "quota_0")["id"]
    with pytest.raises(
        ToolError, match="quota|limit|budget|capacity", check=lambda e: e.code == "TASK_QUOTA"
    ):
        manager.submit("quick", "over_quota")
