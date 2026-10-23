import json
import sys

from triton_dev.common.contracts import ToolError, run_process
from .protocol import validate


class ScriptedModel:
    """Offline test double with the same request/response shape intended for a provider."""
    def __init__(self, messages):
        self.messages = iter(messages)

    def respond(self, context):
        try:
            return next(self.messages)
        except StopIteration as exc:
            raise ToolError("MODEL_EXHAUSTED", "Scripted responses exhausted") from exc


class CliBridge:
    def __init__(self, root, cache):
        self.root, self.cache = root, cache

    def query_sdk_list(self):
        # A fixed argv array. No model text is evaluated as shell code.
        result = run_process([
            sys.executable, "-m", "triton_dev", "env", "sdk", "list",
            "--sdk-root", str(self.root), "--cache-root", str(self.cache),
            "--json", "--non-interactive",
        ], timeout=30)
        if result["returncode"]:
            raise ToolError("CLI_ACTION_FAILED", result["stderr"] or result["stdout"])
        return json.loads(result["stdout"])


def run_controller(model, bridge, *, task_id="scripted-task", max_turns=5):
    if not 1 <= max_turns <= 20:
        raise ToolError("INVALID_ARGUMENT", "max_turns must be 1..20")
    observations = {}
    queried = False
    for turn in range(1, max_turns + 1):
        context = {"schema_version": 1, "task_id": task_id, "turn_id": turn,
                   "observations": observations, "allowed_actions": ["env.sdk.list"] if not queried else [],
                   "remaining_turns": max_turns - turn + 1}
        message = validate(model.respond(context), task_id, turn, observations)
        if message["type"] == "ask_user":
            return {"state": "needs_input", "question": message["question"], "evidence": observations}
        if message["type"] == "finish":
            return {"state": "finished", "conclusion": message["conclusion"], "evidence": observations}
        if queried:
            raise ToolError("NO_PROGRESS", "Repeated identical query is not a new experiment")
        observations["sdk-list-1"] = bridge.query_sdk_list()
        queried = True
    return {"state": "stopped", "reason": "budget_exhausted", "evidence": observations}
