import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
import uvicorn

from triton_dev.common.contracts import ToolError
from triton_dev.platform import models as m
from triton_dev.platform.app import create_app
from triton_dev.platform.daily_v2 import summary, today, PUBLIC_PLAN
from triton_dev.platform.tests.test_platform import platform as platform_fixture, enter, finished


platform = platform_fixture


def test_daily_strict_quality_never_treats_xfail_or_empty_as_green():
    assert summary([])["quality"] == "red"
    for status in ["FAIL", "CRASH", "TIMEOUT", "XFAIL", "XPASS", "SKIP", "INCOMPLETE", "CANCELLED"]:
        assert summary([{"status": "PASS"}, {"status": status}])["quality"] == "red"
    assert summary([{"status": "PASS"}])["quality"] == "green"
    assert summary([{"status": "PASS"}], state="running")["quality"] == "blue"
    assert summary([{"status": "PASS"}], expected=2)["quality"] == "red"
    assert summary([{"status": "XFAIL"}])["pass_rate"] is None


def test_daily_cpu_report_sql_logs_filters_export_and_rerun(platform):
    a, b = TestClient(create_app(platform)), TestClient(create_app(platform))
    owner = enter(a, "Daily A")
    enter(b, "Daily B")
    plan = a.post(
        "/api/daily/v1/definitions", json={"name": "CPU suite", "scenario": "mixed", "workers": 4}
    ).json()["data"]
    path = "/api/daily/v1/batches"
    data = {"plan_id": plan["id"], "idempotency_key": "daily-mixed"}
    task = a.post(path, json=data).json()["data"]
    done = finished(platform, owner, task["id"])
    assert done["state"] == "completed", done
    assert done["summary"]["counts"] == {
        "PASS": 28,
        "FAIL": 1,
        "CRASH": 0,
        "TIMEOUT": 0,
        "SKIP": 1,
        "XFAIL": 1,
        "XPASS": 1,
        "CANCELLED": 0,
        "INCOMPLETE": 0,
    }
    assert done["summary"]["quality"] == "red" and done["summary"]["coverage"] == 1
    assert a.post(path, json=data).json()["data"]["id"] == task["id"]
    assert a.post(path, json=data | {"scenario": "all_pass"}).status_code == 409
    for suffix in ["", "/report", "/cases", "/logs", "/events", "/export"]:
        assert b.get(path + "/" + task["id"] + suffix).status_code == 404
    rows = a.get(path + "/" + task["id"] + "/cases?status=FAIL,XPASS").json()["data"]["items"]
    assert len(rows) == 2
    selected = rows[0]
    logs = a.get(
        path + "/" + task["id"] + "/logs", params={"configuration_id": selected["configuration_id"]}
    ).json()["data"]["items"]
    assert logs and all(line["configuration_id"] == selected["configuration_id"] for line in logs)
    assert any("CPU daily fixture" in line["text"] or "MOCK_" in line["text"] for line in logs)
    first = a.get(path + "/" + task["id"] + "/cases?limit=7").json()["data"]
    second = a.get(
        path + "/" + task["id"] + "/cases", params={"limit": 7, "cursor": first["next_cursor"]}
    ).json()["data"]
    assert not {r["configuration_id"] for r in first["items"]} & {
        r["configuration_id"] for r in second["items"]
    }
    assert a.get(path + "/" + task["id"] + "/cases?min_duration=nan").status_code == 400
    html = a.get(path + "/" + task["id"] + "/export?format=html").text
    assert "Mock SDK/environment" in html and "test_operator" in html
    csv = a.get(path + "/" + task["id"] + "/export?format=csv&status=FAIL").text
    assert len(csv.strip().splitlines()) == 2
    child = a.post(
        path + "/" + task["id"] + "/reruns", json={"scope": "failed", "idempotency_key": "rerun"}
    ).json()["data"]
    rerun = finished(platform, owner, child["id"])
    assert rerun["source_daily_batch_id"] == task["id"] and rerun["summary"]["total"] == 2
    assert rerun["spec"]["environment"] == done["spec"]["environment"]
    assert rerun["spec"]["source_sha256"] == done["spec"]["source_sha256"]
    assert platform.daily_v2.read(owner, task["id"])["summary"]["total"] == 32
    with platform.db.tx() as c:
        assert (
            c.execute(
                sa.select(sa.func.count())
                .select_from(m.daily_cases)
                .where(m.daily_cases.c.task_id == task["id"])
            ).scalar_one()
            == 32
        )
        assert (
            c.execute(
                sa.select(sa.func.count())
                .select_from(m.daily_logs)
                .where(m.daily_logs.c.task_id == task["id"])
            ).scalar_one()
            > 32
        )


def test_daily_schedule_green_build_failure_and_lineage(platform):
    actor, _ = platform.auth.login("Daily scheduler")
    service = platform.daily_v2
    plan = service.save_plan(
        actor,
        {
            "name": "scheduled",
            "scenario": "all_pass",
            "workers": 1,
            "enabled": True,
            "hour": 0,
            "operators": ["matmul"],
        },
    )
    tick = service.tick()
    again = service.tick()
    task = next(r for r in tick if r["spec"]["plan_id"] == plan["id"])
    assert task["id"] == next(r for r in again if r["spec"]["plan_id"] == plan["id"])["id"]
    done = finished(platform, actor, task["id"])
    assert done["summary"]["quality"] == "green", done
    assert done["summary"]["total"] == 8
    cal = service.calendar(actor, plan["id"], today().strftime("%Y-%m"))
    assert next(d for d in cal["days"] if d["date"] == today().isoformat())["quality"] == "green"
    bad = service.trigger(actor, plan["id"], idempotency_key="build-fail", scenario="build_failure")
    bad = finished(platform, actor, bad["id"])
    assert bad["summary"]["quality"] == "red" and bad["summary"]["total"] == 0
    assert service.cases(actor, bad["id"])["items"] == []
    assert any("preparation failure" in r["text"] for r in service.logs(actor, bad["id"])["items"])
    service.save_plan(
        actor,
        {"name": "scheduled", "scenario": "mixed", "workers": 1, "enabled": False},
        plan["id"],
    )
    assert service.read(actor, task["id"])["spec"]["config"]["scenario"] == "all_pass"
    with pytest.raises(ToolError):
        service.trigger(actor, plan["id"], business_date="2099-01-01", idempotency_key="future")


def test_daily_history_public_and_private_rerun(platform):
    service = platform.daily_v2
    service.seed_demo()
    service.seed_demo()
    actor, _ = platform.auth.login("Public reader")
    records = service.list(actor, PUBLIC_PLAN)
    if not records:
        pytest.skip("No prior day in current month")
    assert all(r["source"] == "mock_history" for r in records)
    parent = records[0]
    child = service.rerun(actor, parent["id"], "all", "public-rerun")
    assert child["workspace_id"] == actor["workspace_id"] and child.get("parent") is None
    assert child["source_daily_batch_id"] == parent["id"]
    other, _ = platform.auth.login("Other reader")
    with pytest.raises(ToolError):
        service.read(other, child["id"])
    assert service.read(other, parent["id"])["source"] == "mock_history"
    finished(platform, actor, child["id"])
    cal = service.calendar(actor, PUBLIC_PLAN, parent["business_date"][:7])
    day = next(d for d in cal["days"] if d["date"] == parent["business_date"])
    assert day["batch_id"] == parent["id"] and day["reruns"] == 1


def test_daily_cli_actual_http_server(platform, tmp_path):
    # Real HTTP, Cookie/CSRF authentication and CLI subprocess, not a mocked request.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(platform), host="127.0.0.1", port=port, log_level="error", lifespan="off"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    root = Path(__file__).resolve().parents[3]
    env = dict(os.environ, PYTHONPATH=str(root))
    session = tmp_path / "cli-session.json"
    base = ["--server", f"http://127.0.0.1:{port}", "--session-file", str(session), "--json"]

    def cli(*args, rc=0):
        result = subprocess.run(
            [sys.executable, "-m", "triton_dev", "daily", *args, *base],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == rc, result.stdout + result.stderr
        return json.loads(result.stdout)["data"]

    try:
        assert cli("login", "--name", "CLI Daily")["name"] == "CLI Daily"
        assert session.stat().st_mode & 0o077 == 0
        config = tmp_path / "plan.json"
        config.write_text(json.dumps({"name": "cli suite", "scenario": "all_pass", "workers": 1}))
        plan = cli("plan", "create", "--file", str(config))
        task = cli(
            "trigger",
            "--plan",
            plan["id"],
            "--idempotency-key",
            "cli-test",
            "--wait",
            "--timeout",
            "20",
        )
        assert task["summary"]["quality"] == "green"
        assert cli("report", task["id"])["case_count"] == 32
        assert cli("logs", task["id"])["items"]
        target = tmp_path / "report.csv"
        cli("export", task["id"], "--format", "csv", "--output", str(target))
        assert len(target.read_text().splitlines()) == 33
    finally:
        server.should_exit = True
        thread.join(timeout=5)
