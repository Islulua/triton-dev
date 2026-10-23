import pytest

from triton_dev.agent.controller import CliBridge, ScriptedModel, run_controller
from triton_dev.agent.protocol import validate
from triton_dev.common.contracts import ToolError


def message(turn, kind, **kwargs):
    return {"schema_version": 1, "task_id": "scripted-task", "turn_id": turn, "type": kind, **kwargs}


def test_scripted_model_uses_real_cli(make_sdk, tmp_path):
    sdk = make_sdk()
    model = ScriptedModel([
        message(1, "query", action_id="env.sdk.list", args={}),
        message(2, "finish", conclusion="insufficient_evidence", evidence_ids=["sdk-list-1"]),
    ])
    result = run_controller(model, CliBridge(sdk.parent, tmp_path))
    assert result["state"] == "finished"
    assert result["evidence"]["sdk-list-1"]["data"][0]["name"] == sdk.name


@pytest.mark.parametrize("bad", [
    message(1, "query", action_id="shell", args={"command": "sudo true"}),
    message(1, "finish", conclusion="cmodel_is_buggy"),
    message(1, "finish", conclusion="insufficient_evidence", evidence_ids=["fake"]),
    message(1, "experiment", action_id="change_assertion", args={}),
    message(1, {}, action_id="env.sdk.list", args={}),
    message(1, "query", action_id="env.sdk.list", args={}, conclusion="unexpected"),
])
def test_unsafe_or_unproven_proposals_are_rejected(bad):
    with pytest.raises(ToolError):
        validate(bad, "scripted-task", 1, {})


def test_needs_input_and_budget():
    result = run_controller(ScriptedModel([message(1, "ask_user", question="Which baseline?")]), None)
    assert result["state"] == "needs_input"
