"""Derive callable capabilities from the actual CLI and HTTP route definitions."""
import argparse
import ast
from pathlib import Path

from triton_dev import cli
from triton_dev.common.contracts import ToolError, envelope

# These require a terminal or arbitrary executable. Registered jobs are the AI equivalent.
TERMINAL = {"shell-init", "env.shell", "env.use", "env.deactivate", "env.exec",
            "runs.start", "diagnose.compare", "diagnose.history", "serve"}
CONTROL = {"json", "interactive", "non_interactive", "sdk_root", "cache_root"}


def catalog():
    cli.parser_factory()
    commands = []
    for command, item in cli.CATALOG.items():
        description = cli.describe(command)
        schema = description["input_schema"]
        schema.pop("$schema", None)
        for key in CONTROL:
            schema["properties"].pop(key, None)
        schema["required"] = [k for k in schema["required"] if k not in CONTROL]
        commands.append({"name": "triton_cli_" + command.replace(".", "_").replace("-", "_"),
                         "command": command, "description": description["summary"],
                         "inputSchema": schema, "effects": item["effects"],
                         "available": command not in TERMINAL,
                         "reason": "Use registered jobs; interactive shells and model-produced argv are not accepted"
                                   if command in TERMINAL else None})
    routes = []
    base = Path(__file__).parents[1]
    for module in ("platform/app.py", "platform/daily_api.py", "ir/api.py"):
        tree = ast.parse((base / module).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                        and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app"
                        and decorator.func.attr in {"get", "post", "patch", "delete"}):
                    continue
                expr = decorator.args[0]
                if isinstance(expr, ast.Constant):
                    path = expr.value
                elif isinstance(expr, ast.BinOp) and isinstance(expr.right, ast.Constant):
                    path = "/api/daily/v1" + expr.right.value
                else:
                    continue
                if not path.startswith("/api/") or path in {"/api/sessions", "/api/session"}:
                    continue
                # Document the literal request keys already validated by the domain handler.
                keys = sorted({sub.slice.value for sub in ast.walk(node)
                               if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name)
                               and sub.value.id == "data" and isinstance(sub.slice, ast.Constant)
                               and isinstance(sub.slice.value, str)})
                routes.append({"method": decorator.func.attr.upper(), "path": path,
                               "description": node.name.replace("_", " "), "bodyFields": keys})
    return {"schema_version": 1, "commands": commands, "routes": routes}


def execute_cli(command, arguments, *, sdk_root, cache_root):
    cli.parser_factory()
    if command not in cli.CATALOG:
        raise ToolError("UNKNOWN_TOOL", command)
    if command in TERMINAL:
        raise ToolError("REGISTERED_JOB_REQUIRED", "Use a registered job instead of shell/argv execution")
    if not isinstance(arguments, dict):
        raise ToolError("INVALID_ARGUMENT", "arguments must be an object")
    item = cli.CATALOG[command]
    actions = {a.dest: a for a in item["parser"]._actions if a.dest != "help"}
    unknown = set(arguments) - (set(actions) - CONTROL)
    if unknown:
        raise ToolError("INVALID_ARGUMENT", "Unknown or reserved arguments: " + ", ".join(sorted(unknown)))
    # Parse through the leaf parser so required fields, choices and types stay authoritative.
    argv = []
    for name, action in actions.items():
        if name not in arguments:
            continue
        value = arguments[name]
        if isinstance(action, argparse._StoreTrueAction):
            if not isinstance(value, bool):
                raise ToolError("INVALID_ARGUMENT", name + " requires boolean")
            if value:
                argv.extend(action.option_strings[:1])
            continue
        if isinstance(value, (dict, bool)) or value is None:
            raise ToolError("INVALID_ARGUMENT", name + " has invalid type")
        values = value if isinstance(value, list) else [value]
        if action.option_strings:
            for v in values:
                if isinstance(action, argparse._AppendAction):
                    argv.extend([action.option_strings[0], str(v)])
                else:
                    argv.append(action.option_strings[0] + "=" + str(v))
        else:
            argv.extend(str(v) for v in values)
    args = item["parser"].parse_args(argv + ["--non-interactive", "--json",
                                           "--sdk-root", str(sdk_root), "--cache-root", str(cache_root)])
    value = cli.dispatch(args)
    # Preserve CLI envelopes and explicit unsupported outcomes.
    return envelope(value) if not isinstance(value, str) else envelope({"text": value})
