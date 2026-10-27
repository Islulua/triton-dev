"""Daily command definitions and same-server HTTP client; no direct database access."""

import http.cookiejar
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

from triton_dev.common.contracts import ToolError


def register(sub, leaf):
    daily = sub.add_parser("daily", help="Mock SDK Daily pipeline, calendars, SQL logs and reruns")
    commands = daily.add_subparsers(required=True)
    definitions = commands.add_parser("plan", help="Personal mock Daily schedules").add_subparsers(
        required=True
    )

    def add(group, name, command, help, effects="read_only"):
        p = leaf(group, name, "daily." + command, help, effects=effects)
        p.add_argument(
            "--server",
            default="http://127.0.0.1:8765",
            help="Daily server origin, never a credentials-bearing URL",
        )
        p.add_argument(
            "--session-file",
            type=Path,
            default=Path.home() / ".cache/triton-dev/daily-session.json",
        )
        return p

    p = add(
        commands, "login", "login", "Name-only session for this server", effects="session_write"
    )
    p.add_argument("--name", required=True)
    add(
        commands,
        "demo",
        "demo",
        "Initialize explicit public mock history",
        effects="database_write",
    )
    add(definitions, "list", "plan.list", "List visible Daily plans")
    p = add(
        definitions,
        "create",
        "plan.create",
        "Create a personal bounded mock Daily plan",
        effects="database_write",
    )
    p.add_argument("--file", type=Path, required=True)
    p = add(
        definitions,
        "update",
        "plan.update",
        "Revise a personal plan; task snapshots remain fixed",
        effects="database_write",
    )
    p.add_argument("plan_id")
    p.add_argument("--file", type=Path, required=True)
    p = add(
        commands,
        "trigger",
        "trigger",
        "Queue actual CPU pytest with mock SDK/environment",
        effects="execute",
    )
    p.add_argument("--plan", required=True)
    p.add_argument("--date")
    p.add_argument("--scenario", choices=["all_pass", "mixed", "xfail_only", "build_failure"])
    p.add_argument("--idempotency-key", required=True)
    p.add_argument("--wait", action="store_true")
    p.add_argument("--timeout", type=int, default=300)
    for name in ["list", "calendar"]:
        p = add(commands, name, name, "Query Daily " + name)
        p.add_argument("--plan", required=name == "calendar")
        p.add_argument("--month", required=name == "calendar")
    for name in ["status", "report", "cases", "logs", "events", "cancel", "rerun", "export"]:
        p = add(
            commands,
            name,
            name,
            "Daily " + name,
            effects="execute" if name in ["cancel", "rerun"] else "read_only",
        )
        p.add_argument("batch_id")
        if name == "cases":
            for key in [
                "status",
                "operator",
                "worker",
                "phase",
                "dtype",
                "file",
                "search",
                "cursor",
            ]:
                p.add_argument("--" + key)
            p.add_argument("--limit", type=int, default=50)
            p.add_argument("--min-duration", type=float)
            p.add_argument("--max-duration", type=float)
        if name == "logs":
            for key in ["configuration-id", "worker", "phase", "step", "search", "level"]:
                p.add_argument("--" + key)
            p.add_argument("--after", type=int, default=0)
            p.add_argument("--limit", type=int, default=100)
        if name == "events":
            p.add_argument("--after", type=int, default=0)
        if name == "rerun":
            p.add_argument("--scope", choices=["all", "failed", "selected"], default="failed")
            p.add_argument("--selection-file", type=Path)
            p.add_argument("--idempotency-key", required=True)
        if name == "export":
            p.add_argument("--format", choices=["json", "csv", "html"], default="html")
            p.add_argument("--output", type=Path, required=True)
            for key in ["status", "operator", "search", "worker", "phase", "dtype", "file"]:
                p.add_argument("--" + key)
            p.add_argument("--min-duration", type=float)
            p.add_argument("--max-duration", type=float)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ToolError(
            "REDIRECT_REJECTED",
            "Daily client will not forward session credentials across redirects",
        )


def dispatch(args):
    command = args.command_id.removeprefix("daily.")
    server = args.server.rstrip("/")
    parsed = urlsplit(server)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ToolError("INVALID_SERVER", "Use a server origin without credentials, query or path")
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar), NoRedirect())
    auth = {}
    if command != "login":
        if not args.session_file.is_file():
            raise ToolError("UNAUTHORIZED", "Run triton-dev daily login first")
        if args.session_file.stat().st_mode & 0o077:
            raise ToolError("INSECURE_SESSION", "Session file must be mode 0600")
        auth = json.loads(args.session_file.read_text())
        if auth.get("server") != server:
            raise ToolError("UNAUTHORIZED", "Session belongs to a different server")

    def request(path, method="GET", body=None, raw=False):
        headers = {}
        if auth:
            headers["Cookie"] = "td_session=" + auth["session"]
            if method != "GET":
                headers["X-CSRF-Token"] = auth["csrf"]
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            server + "/api" + path,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
        )
        try:
            with opener.open(req, timeout=30) as response:
                content = response.read()
        except HTTPError as exc:
            try:
                err = json.loads(exc.read())["error"]
            except (ValueError, KeyError):
                raise ToolError("HTTP_ERROR", f"Daily HTTP {exc.code}") from None
            raise ToolError(err["code"], err["message"]) from None
        except URLError:
            raise ToolError("SERVER_UNAVAILABLE", "Daily server cannot be reached") from None
        return content if raw else json.loads(content)["data"]

    if command == "login":
        user = request("/sessions", "POST", {"name": args.name})
        token = next((cookie.value for cookie in jar if cookie.name == "td_session"), None)
        if not token:
            raise ToolError("UNAUTHORIZED", "Server did not issue a session")
        args.session_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if args.session_file.is_symlink():
            raise ToolError("INVALID_ARGUMENT", "Session file cannot be a symlink")
        fd = os.open(args.session_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump({"server": server, "session": token, "csrf": user["csrf_token"]}, out)
        return {k: v for k, v in user.items() if k != "csrf_token"}
    root = "/daily/v1"
    if command == "demo":
        return request(root + "/demo", "POST", {})
    if command == "plan.list":
        return request(root + "/definitions")
    if command in {"plan.create", "plan.update"}:
        return request(
            root + "/definitions" + ("/" + args.plan_id if command == "plan.update" else ""),
            "PATCH" if command == "plan.update" else "POST",
            json.loads(args.file.read_text()),
        )
    if command == "trigger":
        if args.wait and not 1 <= args.timeout <= 86400:
            raise ToolError("INVALID_ARGUMENT", "--timeout must be 1..86400 seconds")
        data = {"plan_id": args.plan, "idempotency_key": args.idempotency_key}
        if args.date:
            data["business_date"] = args.date
        if args.scenario:
            data["scenario"] = args.scenario
        task = request(root + "/batches", "POST", data)
        if args.wait:
            if not 1 <= args.timeout <= 86400:
                raise ToolError("INVALID_ARGUMENT", "--timeout must be 1..86400 seconds")
            deadline = time.monotonic() + args.timeout
            while task["state"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(0.3)
                task = request(root + "/batches/" + task["id"])
            task["returncode"] = (
                3
                if task["state"] in {"queued", "running"}
                else 0
                if task["summary"]["quality"] == "green"
                else 1
            )
        return task
    if command in {"calendar", "list"}:
        query = {k: v for k, v in {"plan_id": args.plan, "month": args.month}.items() if v}
        return request(
            root + ("/calendar" if command == "calendar" else "/batches") + "?" + urlencode(query)
        )
    path = root + "/batches/" + args.batch_id
    if command == "cancel":
        return request(path + "/cancel", "POST", {})
    if command == "rerun":
        data = {"scope": args.scope, "idempotency_key": args.idempotency_key}
        if args.selection_file:
            data["selected"] = json.loads(args.selection_file.read_text())
        return request(path + "/reruns", "POST", data)
    if command == "status":
        return request(path)
    if command == "report":
        return request(path + "/report")
    fields = {
        "cases": [
            "status",
            "operator",
            "worker",
            "phase",
            "dtype",
            "file",
            "search",
            "cursor",
            "limit",
            "min_duration",
            "max_duration",
        ],
        "logs": [
            "configuration_id",
            "worker",
            "phase",
            "step",
            "search",
            "level",
            "after",
            "limit",
        ],
        "events": ["after"],
        "export": [
            "format",
            "status",
            "operator",
            "search",
            "worker",
            "phase",
            "dtype",
            "file",
            "min_duration",
            "max_duration",
        ],
    }[command]
    query = {key: getattr(args, key) for key in fields if getattr(args, key, None) is not None}
    target = path + "/" + command + "?" + urlencode(query)
    if command == "export":
        content = request(target, raw=True)
        args.output.write_bytes(content)
        return {"output": str(args.output), "bytes": len(content), "format": args.format}
    return request(target)
