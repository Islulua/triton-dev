from triton_dev.agent.controller import ScriptedModel, run_controller


def test_offline_provider_uses_context_and_has_no_execution_authority():
    contexts = []
    class Model:
        def respond(self, context):
            contexts.append(context)
            return {"schema_version": 1, "task_id": context["task_id"],
                    "turn_id": context["turn_id"], "type": "ask_user", "question": "Which case?"}
    result = run_controller(Model(), None)
    assert contexts[0]["remaining_turns"] == 5
    assert result["state"] == "needs_input"
    assert callable(ScriptedModel([]).respond)
