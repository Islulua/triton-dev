"""Argparse definitions are the source for help, describe and capabilities."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from triton_dev.common.contracts import ToolError, envelope
from triton_dev.env import settings

CATALOG = {}


class CommandParser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError("ARGUMENT_ERROR", message)


def common(parser):
    parser.add_argument("--json", action="store_true", help="Return the versioned result envelope")
    parser.add_argument("--interactive", "-i", action="store_true", help="Discover real candidates and prompt on stderr")
    parser.add_argument("--non-interactive", action="store_true", help="Never prompt; missing required inputs fail")
    parser.add_argument("--sdk-root", type=Path, default=settings.SDK_ROOT, help="Advanced/test override of compiled SDK root")
    parser.add_argument("--cache-root", type=Path, default=settings.CACHE_ROOT, help="Advanced/test override of internal cache")


def leaf(sub, name, command_id, summary, *, effects="read_only", status="implemented"):
    parser = sub.add_parser(name, help=summary, description=summary)
    common(parser)
    parser.set_defaults(command_id=command_id)
    CATALOG[command_id] = {"parser": parser, "summary": summary, "effects": effects, "status": status}
    return parser


def selection(parser, *, positional=True):
    if positional:
        parser.add_argument("version", nargs="?", help="SDK full name or YYYYMMDD; latest means local latest")
    parser.add_argument("--saved", help="Restore a verified immutable saved combination")
    parser.add_argument("--sdk", help="Explicit SDK full name, YYYYMMDD or local latest")
    parser.add_argument("--python", default=sys.executable, help="Executable path or PATH name used to create and identity-check the isolated venv")
    parser.add_argument("--triton-sdk", help="SDK source of the Triton wheel")
    parser.add_argument("--torch-sdk", help="SDK source of the torch_raisa wheel")
    parser.add_argument("--raops-sdk", help="SDK source of the raops wheel")
    parser.add_argument("--cmodel-sdk", help="Reserved: rejected until native component mapping is confirmed")
    parser.add_argument("--native-only", action="store_true", help="Only set native paths; do NOT claim wheel/runtime verification")


def parser_factory():
    CATALOG.clear()
    root = CommandParser(prog="triton-dev", description="SDK environments and evidence-driven workflows")
    sub = root.add_subparsers(dest="group", required=True)
    p = leaf(sub, "capabilities", "capabilities", "List commands actually supported by this installation")
    p = leaf(sub, "describe", "describe", "Describe command arguments, result contract and side effects")
    p.add_argument("command", help="Stable command ID, e.g. env.prepare")
    p = leaf(sub, "candidates", "candidates", "Search actual local SDK/component/build candidates")
    p.add_argument("kind", choices=["env.sdk", "env.component", "build.target"])
    p.add_argument("--workspace", type=Path)
    p = leaf(sub, "shell-init", "shell-init", "Print trusted bash/zsh current-terminal integration")
    p.add_argument("shell", choices=["bash", "zsh"])
    env = sub.add_parser("env", help="Download, prepare, inspect and use SDK environments")
    esub = env.add_subparsers(dest="env_action", required=True)
    sdk = esub.add_parser("sdk", help="Inspect SDK files without executing native code")
    ss = sdk.add_subparsers(dest="sdk_action", required=True)
    leaf(ss, "list", "env.sdk.list", "List SDK directories; incomplete latest is never silently skipped")
    p = leaf(ss, "inspect", "env.sdk.inspect", "Read selected wheel metadata and hashes")
    selection(p)
    p = leaf(ss, "diff", "env.sdk.diff", "Compare SDK file content; unknown component attribution remains unknown")
    p.add_argument("--left")
    p.add_argument("--right")
    for name in ("plan", "prepare", "export", "status", "verify", "exec", "shell", "use"):
        effects = "read_only" if name in ("plan", "export", "status") else "prepare_or_execute"
        p = leaf(esub, name, "env." + name, {
            "plan": "Resolve exact wheel files and build the environment identity without installation",
            "prepare": "Create an isolated venv and install selected wheels offline; does not activate",
            "export": "Export current or selected environment variables; never silently prepares",
            "status": "Show inherited terminal configuration; no native loading claim",
            "verify": "Run an isolated Python import probe; native functional checks remain TODO",
            "exec": "Execute a command in a selected environment; return its raw exit code",
            "shell": "Enter a configured child shell; exit restores the parent terminal",
            "use": "Current-shell operation requiring shell-init; direct calls return guidance",
        }[name], effects=effects)
        selection(p, positional=name != "exec")
        if name == "export":
            p.add_argument("--current", action="store_true", help="Read inherited exported variables, not shell-local state")
            p.add_argument("--format", choices=["sh", "json"], default="sh")
            p.add_argument("--output", type=Path)
            p.add_argument("--include", action="append", default=[])
            p.add_argument("--all", action="store_true", dest="all_variables", help="Explicitly include all inherited values, including possible secrets")
            p.add_argument("--prepare", action="store_true", help="Explicitly allow venv preparation before export")
        if name in ("exec", "shell"):
            p.add_argument("--timeout", type=float, default=300)
        if name == "exec":
            p.add_argument("command", nargs=argparse.REMAINDER)
    p = leaf(esub, "deactivate", "env.deactivate", "Restore previous terminal state through shell-init", effects="terminal")
    for name in ("download", "update"):
        p = leaf(esub, name, "env." + name,
                 "Fetch remote daily SDK" if name == "download" else "Prepare remote latest; shell-init applies it only after success",
                 effects="network_and_cache")
        p.add_argument("date", nargs="?", help="YYYYMMDD or YYYYMMDDHHMM (download only)")
        p.add_argument("--base-url", default=settings.SDK_URL, help="Directory listing URL; credentials from TRITON_DEV_TOKEN")
        p.add_argument("--sha256", help="Expected trusted archive digest")
        if name == "update":
            p.add_argument("--format", choices=["json", "sh"], default="json")
    p = leaf(sub, "build", "build", "Discover source targets and preview inputs; actual recipes are TODO")
    p.add_argument("target", nargs="?", help="list or a target name; omitted: interactive selection")
    p.add_argument("--workspace", type=Path)
    p.add_argument("--plan", action="store_true", help="Preview without compiling")
    cases = sub.add_parser("cases", help="Real pytest collection")
    cs = cases.add_subparsers(required=True)
    p = leaf(cs, "list", "cases.list", "Collect node IDs and markers in a separate pytest process", effects="imports_test_code")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("-m", "--marker")
    p = leaf(sub, "run", "run", "Execute pytest in a prepared SDK environment", effects="execute")
    selection(p, positional=False)
    p.add_argument("--case", required=True)
    p.add_argument("--timeout", type=float, default=300)
    diag = sub.add_parser("diagnose", help="Deterministic comparisons")
    ds = diag.add_subparsers(required=True)
    p = leaf(ds, "compare", "diagnose.compare", "Repeat good/bad runs and compare an explicit failure signature", effects="execute")
    p.add_argument("--good", required=True)
    p.add_argument("--bad", required=True)
    p.add_argument("--match", required=True, help="Nonzero exit AND this output fragment defines the target failure")
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--native-only", action="store_true")
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("command", nargs=argparse.REMAINDER)
    agent = sub.add_parser("agent", help="Bounded controller; live provider integration is TODO")
    ag = agent.add_subparsers(required=True)
    p = leaf(ag, "scripted", "agent.scripted", "Exercise the AI protocol offline using explicit scripted responses", effects="read_only_cli")
    p.add_argument("responses", type=Path)
    p.add_argument("--max-turns", type=int, default=5)
    p = leaf(ag, "regression", "agent.regression", "Persistent mock SDK regression with real CPU pytest; no live model", effects="execute_write_cache")
    p.add_argument("operation", choices=["catalog", "start", "status", "resume", "cancel", "report", "replay"])
    p.add_argument("task_id", nargs="?")
    p.add_argument("--config", type=Path, help="Trusted regression JSON; only mock adapters currently enabled")
    p.add_argument("--experiment", help="Recorded experiment ID to replay without a model")
    p.add_argument("--format", choices=["json", "md", "html"], default="json")
    p = leaf(sub, "report", "report", "Summarize a previously exported comparison without rerunning it")
    p.add_argument("input", type=Path)
    leaf(sub, "doctor", "doctor", "Read-only platform, SDK, cache and shell preflight")
    p = leaf(sub, "serve", "serve", "Loopback task API with registered pytest collection, isolation and reruns", effects="listen_loopback")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--ui", type=Path, help="Built frontend dist/client directory, served on the same local origin")
    p.add_argument("--jobs", type=Path, help="Trusted local JSON registry; command or kind=pytest projects")
    p.add_argument("--token-env", default="TRITON_DEV_SERVER_TOKEN", help="Token variable required when --jobs is set")
    p.add_argument("--multi-user", action="store_true", help="ASGI name-only sessions and database-backed user workspaces")
    p.add_argument("--database-url-env", default="TRITON_DEV_DATABASE_URL", help="Database URL environment variable (never printed)")
    p.add_argument("--allowed-host", action="append", default=[], help="Allowed hostnames for the ASGI deployment")
    p.add_argument("--model-endpoint", action="append", default=[], help="Administrator-registered model endpoint; live calls remain disabled")
    p.add_argument("--secure-cookies", action="store_true", help="Use Secure session cookies behind HTTPS")
    platform_parser=sub.add_parser("platform",help="Local administrator database/data maintenance")
    platform_commands=platform_parser.add_subparsers(required=True)
    p=leaf(platform_commands,"manage","platform.manage","Database migration, legacy import and system daily registration",effects="database_write")
    p.add_argument("operation",choices=["migrate","import-legacy","import-build","daily-plan","daily-tick"])
    p.add_argument("--input",type=Path)
    p.add_argument("--database-url-env",default="TRITON_DEV_DATABASE_URL")
    p.add_argument("--jobs",type=Path)
    from .daily import register as register_daily
    register_daily(sub, leaf)
    from .offline import register
    register(sub, esub, cs, ds, ag, leaf, selection)
    return root


def describe(command):
    if command not in CATALOG:
        raise ToolError("COMMAND_NOT_FOUND", command)
    item = CATALOG[command]
    arguments = []
    for action in item["parser"]._actions:
        if action.dest == "help":
            continue
        arguments.append({"name": action.dest, "flags": action.option_strings,
                          "required": action.required, "nargs": action.nargs,
                          "repeatable": isinstance(action, argparse._AppendAction),
                          "choices": list(action.choices) if action.choices else None,
                          "default": str(action.default) if isinstance(action.default, Path) else action.default,
                          "type": "integer" if action.type is int else "number" if action.type is float else
                                  "boolean" if isinstance(action, argparse._StoreTrueAction) else "string",
                          "help": action.help})
    properties, required = {}, []
    for argument in arguments:
        schema = {"type": argument["type"], "description": argument["help"] or ""}
        if argument["choices"]:
            schema["enum"] = argument["choices"]
        if (argument["repeatable"] or argument["nargs"] in ("+", "*", argparse.REMAINDER)
                or isinstance(argument["nargs"], int) and argument["nargs"] > 0):
            schema = {"type": "array", "items": schema}
            if argument["nargs"] == "+":
                schema["minItems"] = 1
        properties[argument["name"]] = schema
        if argument["required"]:
            required.append(argument["name"])
    input_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object", "properties": properties,
                    "required": required, "additionalProperties": False}
    output_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                     "type": "object", "required": ["schema_version", "status", "data", "error", "evidence"],
                     "additionalProperties": False, "properties": {
                         "schema_version": {"const": 1},
                         "status": {"enum": ["ok", "failed", "unsupported"]},
                         "data": {}, "error": {"type": ["object", "null"]},
                         "evidence": {"type": "array"}}}
    return {"command_id": command, "summary": item["summary"], "status": item["status"],
            "side_effects": item["effects"], "arguments": arguments,
            "input_schema": input_schema, "output_schema": output_schema,
            "result_schema": {"schema_version": 1, "fields": ["status", "data", "error", "evidence"]},
            "interaction": {"explicit_and_candidates_share_service": True,
                            "non_interactive_never_prompts": True}}


def capabilities():
    return [describe(command) for command in sorted(CATALOG)]


def prompt(candidates, title, args):
    if args.non_interactive or not sys.stdin.isatty():
        raise ToolError("NEEDS_INPUT", f"{title}: explicit input required in non-interactive mode",
                        details={"candidates": candidates})
    if not candidates:
        raise ToolError("NO_CANDIDATES", title)
    print(title, file=sys.stderr)
    for index, candidate in enumerate(candidates, 1):
        print(f"  {index}. {candidate}", file=sys.stderr)
    print("Select number: ", end="", file=sys.stderr, flush=True)
    try:
        choice = int(input())
        if not 1 <= choice <= len(candidates):
            raise ValueError
        return candidates[choice - 1]
    except (ValueError, EOFError) as exc:
        raise ToolError("INVALID_SELECTION", "Choose a listed number") from exc


def selected(args, *, allow_default=True):
    from triton_dev.env.sdk import discover
    version = getattr(args, "version", None)
    sdk = getattr(args, "sdk", None)
    if version and sdk and version != sdk:
        raise ToolError("INVALID_ARGUMENT", "Positional SDK and --sdk disagree")
    chosen = sdk or version
    if args.interactive and not chosen:
        chosen = prompt([x["name"] for x in discover(args.sdk_root) if x["complete"]], "Choose SDK", args)
    if not chosen and not allow_default:
        return None
    return chosen or "latest"


def overrides(args):
    return {name: value for name, value in {
        "triton": getattr(args, "triton_sdk", None), "torch_raisa": getattr(args, "torch_sdk", None),
        "raops": getattr(args, "raops_sdk", None), "cmodel": getattr(args, "cmodel_sdk", None),
    }.items() if value}


def shell_init():
    installed = Path(sys.executable).parent / "triton-dev"
    executable = shlex.quote(str(installed) if installed.is_file() else (shutil.which("triton-dev") or "triton-dev"))
    return f'''# Generated by triton-dev; bash/zsh only.
triton-dev() {{
    local _td_code _td_before _td_rc
    if [ "$1" = "env" ] && [ "$2" = "use" ]; then
        shift 2
        if [ "$#" -eq 0 ]; then set -- --interactive; fi
        _td_before="$({executable} env export --current --format sh)" || return $?
        _td_code="$({executable} env export --prepare "$@" --format sh)"
        _td_rc=$?
        if [ "$_td_rc" -ne 0 ]; then printf '%s\\n' "$_td_code" >&2; return "$_td_rc"; fi
        if [ -z "${{_TRITON_DEV_RESTORE+x}}" ]; then
            _TRITON_DEV_RESTORE="$_td_before"
        fi
        eval "$_td_code"
    elif [ "$1" = "env" ] && [ "$2" = "update" ]; then
        shift 2
        _td_before="$({executable} env export --current --format sh)" || return $?
        _td_code="$({executable} env update "$@" --format sh)"
        _td_rc=$?
        if [ "$_td_rc" -ne 0 ]; then printf '%s\\n' "$_td_code" >&2; return "$_td_rc"; fi
        if [ -z "${{_TRITON_DEV_RESTORE+x}}" ]; then
            _TRITON_DEV_RESTORE="$_td_before"
        fi
        eval "$_td_code"
    elif [ "$1" = "env" ] && [ "$2" = "deactivate" ]; then
        if [ -n "${{_TRITON_DEV_RESTORE+x}}" ]; then
            eval "$_TRITON_DEV_RESTORE"
            unset _TRITON_DEV_RESTORE
        fi
    else
        {executable} "$@"
    fi
}}
'''


def dispatch(args):
    from triton_dev.env import sdk as sdk_service
    from triton_dev.env import service as env_service
    command = args.command_id
    if args.interactive and args.non_interactive:
        raise ToolError("INVALID_ARGUMENT", "--interactive and --non-interactive are mutually exclusive")
    from .offline import apply_saved, dispatch as offline_dispatch
    apply_saved(args)
    handled, result = offline_dispatch(args, selected, overrides)
    if handled:
        return result
    if command.startswith("daily."):
        from .daily import dispatch as daily_dispatch
        return daily_dispatch(args)
    if command == "capabilities":
        return capabilities()
    if command == "describe":
        return describe(args.command)
    if command == "shell-init":
        return shell_init()
    if command == "candidates":
        if args.kind == "env.sdk":
            return sdk_service.discover(args.sdk_root)
        if args.kind == "env.component":
            return [{"name": x, "available": True} for x in settings.PACKAGES] + [
                {"name": "cmodel", "available": False, "reason": "native file ownership unknown"}]
        from triton_dev.build.service import targets, workspace
        return targets(args.workspace or workspace(Path.cwd()))
    if command == "env.sdk.list":
        return sdk_service.discover(args.sdk_root)
    if command == "env.sdk.inspect":
        return sdk_service.inspect_sdk(sdk_service.select(args.sdk_root, selected(args)))
    if command == "env.sdk.diff":
        names = [x["name"] for x in sdk_service.discover(args.sdk_root)]
        left = args.left or prompt(names, "Choose left SDK", args)
        right = args.right or prompt(names, "Choose right SDK", args)
        return sdk_service.sdk_diff(sdk_service.select(args.sdk_root, left), sdk_service.select(args.sdk_root, right))
    if command in ("env.download", "env.update"):
        if command == "env.update" and args.date:
            raise ToolError("INVALID_ARGUMENT", "update always selects remote latest; use download for a date")
        headers = {"Authorization": "Bearer " + os.environ["TRITON_DEV_TOKEN"]} if os.getenv("TRITON_DEV_TOKEN") else {}
        result = sdk_service.download(args.sdk_root, args.base_url, args.date, headers=headers, expected_sha256=args.sha256)
        if command == "env.download":
            return result
        ready = env_service.prepare(args.sdk_root, args.cache_root, Path(result["sdk"]).name)
        observed = env_service.probe(ready)
        if any("error" in value for value in observed["modules"].values()):
            raise ToolError("IMPORT_FAILED", "Prepared packages did not pass import probe", details=observed)
        # Native loading is not proven; this is never reported as full qualification.
        data = env_service.variables(ready)
        return env_service.render_shell(data) if args.format == "sh" else {**result, "environment": ready, "probe": observed}
    if command == "env.plan":
        return env_service.plan(args.sdk_root, selected(args), overrides=overrides(args), python=args.python)
    if command == "env.prepare":
        if args.native_only:
            return env_service.resolve(args.sdk_root, args.cache_root, selected(args), overrides=overrides(args), native_only=True, python=args.python)
        return env_service.prepare(args.sdk_root, args.cache_root, selected(args), overrides=overrides(args), python=args.python)
    if command == "env.status":
        return env_service.current_variables()
    if command == "env.export":
        explicit = selected(args, allow_default=False)
        if args.current and (explicit or overrides(args) or args.native_only or args.prepare):
            raise ToolError("INVALID_ARGUMENT", "--current cannot be combined with SDK/preparation selection")
        if overrides(args) and not explicit:
            raise ToolError("INVALID_ARGUMENT", "Component overrides require an explicit base SDK")
        if args.current or not explicit:
            if args.prepare or args.native_only:
                raise ToolError("INVALID_ARGUMENT", "Preparation/native-only requires a selected SDK")
            data = env_service.current_variables(args.include, args.all_variables)
        else:
            if args.all_variables or args.include:
                raise ToolError("INVALID_ARGUMENT", "--all/--include apply only to current environment export")
            if args.prepare and not args.native_only:
                env_service.prepare(args.sdk_root, args.cache_root, explicit, overrides=overrides(args), python=args.python)
            environment = env_service.resolve(args.sdk_root, args.cache_root, explicit, overrides=overrides(args), native_only=args.native_only, python=args.python)
            data = env_service.variables(environment)
        if args.output:
            args.output.write_text(env_service.render_shell(data) if args.format == "sh" else json.dumps(data, indent=2), encoding="utf-8")
            args.output.chmod(0o600)
            return {"output": str(args.output), "format": args.format}
        return env_service.render_shell(data) if args.format == "sh" else data
    if command in ("env.use", "env.deactivate"):
        raise ToolError("SHELL_INTEGRATION_REQUIRED", 'Run eval "$(triton-dev shell-init bash)" or use env shell')
    if command in ("env.exec", "env.shell", "env.verify", "run"):
        environment = env_service.resolve(args.sdk_root, args.cache_root, selected(args), overrides=overrides(args), native_only=args.native_only, python=args.python)
        if command == "env.verify":
            observed = env_service.probe(environment)
            if any("error" in value for value in observed["modules"].values()):
                raise ToolError("IMPORT_FAILED", "Python import verification failed", details=observed)
            return observed
        from triton_dev.execution.service import execute
        if command == "run":
            argv = ["python", "-m", "pytest", args.case]
        elif command == "env.shell":
            # No rc file can silently replace the controlled SDK path.
            shell = os.environ.get("SHELL", "/bin/bash")
            argv = [shell, "--noprofile", "--norc"] if Path(shell).name == "bash" else [shell, "-f"]
            import subprocess
            rc = subprocess.call(argv, env=env_service.process_environment(env_service.variables(environment)))
            return {"returncode": rc}
        else:
            argv = args.command[1:] if args.command[:1] == ["--"] else args.command
        return execute(environment, argv, timeout=args.timeout)
    if command == "build":
        from triton_dev.build.service import targets, workspace, plan_build
        root = args.workspace or workspace(Path.cwd())
        if args.target == "list":
            return targets(root)
        target = args.target or prompt([x["name"] for x in targets(root) if x["exists"]], "Choose build target", args)
        plan = plan_build(root, target)
        if args.plan:
            return plan
        raise ToolError("UNSUPPORTED", "Project-specific build recipes are TODO; --plan is available", details=plan)
    if command == "cases.list":
        from triton_dev.cases.service import collect
        return collect(args.path, python=args.python, marker=args.marker)
    if command == "diagnose.compare":
        from triton_dev.diagnosis.service import compare
        argv = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not argv:
            raise ToolError("INVALID_ARGUMENT", "Specify the command after --")
        return compare(args.sdk_root, args.cache_root, args.good, args.bad, argv,
                       match=args.match, repeat=args.repeat, native_only=args.native_only, timeout=args.timeout)
    if command == "agent.scripted":
        from triton_dev.agent.controller import ScriptedModel, CliBridge, run_controller
        return run_controller(ScriptedModel(json.loads(args.responses.read_text())),
                              CliBridge(args.sdk_root, args.cache_root), max_turns=args.max_turns)
    if command == "agent.regression":
        from triton_dev.agent.regression.service import RegressionService, catalog
        if args.operation == 'catalog':
            return catalog()
        service = RegressionService(args.cache_root / 'regressions')
        try:
            if args.operation == 'start':
                return service.start(json.loads(args.config.read_text()) if args.config else {}, background=False)
            if not args.task_id:
                raise ToolError('INVALID_ARGUMENT', 'Task ID is required')
            if args.operation == 'report':
                service.read(args.task_id)
                path = service._dir(args.task_id) / ('report.' + args.format)
                if not path.exists():
                    raise ToolError('NOT_READY', 'Report is not ready')
                return json.loads(path.read_text()) if args.format == 'json' else {'content': path.read_text(), 'format': args.format}
            if args.operation == 'replay':
                return service.replay(args.task_id, args.experiment)
            if args.operation == 'resume':
                return service.resume(args.task_id, background=False)
            return getattr(service, 'read' if args.operation == 'status' else 'cancel')(args.task_id)
        finally:
            service.close()
    if command == "report":
        from triton_dev.reporting.service import summarize
        data = json.loads(args.input.read_text())
        return summarize(data.get("data", data))
    if command == "doctor":
        from triton_dev.doctor.service import check

        return check(args.sdk_root, args.cache_root)
    if command == "platform.manage":
        from triton_dev.platform.service import Platform

        url = os.environ.get(args.database_url_env)
        if not url:
            raise ToolError("DATABASE_REQUIRED", "Set the database URL environment variable")
        platform = Platform(
            url,
            args.cache_root / "platform",
            json.loads(args.jobs.read_text()) if args.jobs else {},
            start_worker=False,
        )
        try:
            if args.operation == "migrate":
                return {"schema": "0003_daily", "database": platform.db.engine.dialect.name}
            if args.operation == "import-legacy":
                if not args.input:
                    raise ToolError("INVALID_ARGUMENT", "--input directory required")
                return platform.import_legacy(args.input)
            if args.operation == "daily-tick":
                return platform.daily.tick()
            if not args.input:
                raise ToolError("INVALID_ARGUMENT", "--input JSON required")
            data = json.loads(args.input.read_text())
            return (
                platform.daily.import_build(data)
                if args.operation == "import-build"
                else platform.daily.definition(**data)
            )
        finally:
            platform.close()
    if command == "serve":
        if args.multi_user:
            from triton_dev.platform.service import Platform
            from triton_dev.platform.app import create_app
            import uvicorn

            url = os.environ.get(args.database_url_env)
            if not url:
                raise ToolError("DATABASE_REQUIRED", "Set the database URL environment variable")
            platform = Platform(
                url,
                args.cache_root / "platform",
                json.loads(args.jobs.read_text()) if args.jobs else {},
                args.model_endpoint,
            )
            app = create_app(
                platform,
                capabilities(),
                args.ui,
                allowed_hosts=tuple({"127.0.0.1", "localhost", *args.allowed_host}),
                secure_cookie=args.secure_cookies,
            )
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
            return {"state": "stopped"}
        from triton_dev.serve.service import serve

        if args.jobs:
            from triton_dev.serve.tasks import TaskManager

            token = os.environ.get(args.token_env)
            if not token or len(token) < 16:
                raise ToolError(
                    "INVALID_ARGUMENT", "Set the task API token variable (at least 16 characters)"
                )
            manager = TaskManager(args.cache_root / "tasks", json.loads(args.jobs.read_text()))
            return serve(capabilities(), args.port, manager=manager, token=token, ui_root=args.ui)
        return serve(capabilities(), args.port, ui_root=args.ui)
    raise ToolError("COMMAND_NOT_FOUND", command)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = parser_factory()
    try:
        args = parser.parse_args(argv)
        data = dispatch(args)
        if isinstance(data, str):
            print(data, end="")
        else:
            print(json.dumps(envelope(data), ensure_ascii=False, indent=2))
        if isinstance(data, dict) and "returncode" in data:
            rc = data["returncode"]
            return rc if rc >= 0 else 128 - rc
        return 0
    except ToolError as exc:
        print(json.dumps(envelope(error=exc), ensure_ascii=False), file=sys.stdout)
        return 2
    except (OSError, ValueError) as exc:
        print(json.dumps(envelope(error=ToolError("INPUT_OR_IO_ERROR", str(exc)))), file=sys.stdout)
        return 2


def entrypoint():
    raise SystemExit(main())


def legacy_entrypoint():
    raise SystemExit(main(["env", *sys.argv[1:]]))
