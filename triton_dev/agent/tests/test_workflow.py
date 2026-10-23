import sys

import pytest

from triton_dev.agent.controller import ScriptedModel
from triton_dev.agent.workflow import run_workflow
from triton_dev.common.contracts import ToolError
from triton_dev.diagnosis.predicates import FailurePredicate
from triton_dev.execution.records import RunStore


def recipes(tmp_path):
    return {name: {'role': role, 'request': {'argv': [sys.executable, '-c', code],
                    'cwd': str(tmp_path), 'timeout': 5}}
            for name, role, code in [('g1', 'good', 'pass'), ('g2', 'good', 'pass'),
                                    ('b1', 'bad', 'print("TARGET");raise SystemExit(1)'),
                                    ('b2', 'bad', 'print("TARGET");raise SystemExit(1)')]}


def test_workflow_real_experiments_resume_and_finish(tmp_path):
    store = RunStore(tmp_path / 'runs')
    checkpoint = tmp_path / 'checkpoint.json'
    registered = recipes(tmp_path)
    predicate = FailurePredicate('text', match='TARGET')
    first = run_workflow(ScriptedModel([{'action': 'experiment', 'recipe_id': 'g1'}]),
                         store, checkpoint, registered, predicate, max_turns=1)
    assert first['state'] == 'stopped'
    assert len(store.list()) == 1
    messages = [{'action': 'experiment', 'recipe_id': name} for name in ('g2', 'b1', 'b2')]
    messages.append({'action': 'finish', 'conclusion': 'change_associated', 'evidence_ids': list(registered)})
    result = run_workflow(ScriptedModel(messages), store, checkpoint, registered, predicate)
    assert result['state'] == 'finished'
    assert result['experiments'] == 4
    assert len(store.list()) == 4
    assert result['scope'] == 'registered_experiments'
    assert run_workflow(ScriptedModel([]), store, checkpoint, registered, predicate) == result


@pytest.mark.parametrize('message,code', [
    ({'action': 'experiment', 'recipe_id': 'shell'}, 'ACTION_NOT_ALLOWED'),
    ({'action': 'experiment', 'recipe_id': 'g1', 'command': 'touch pwned'}, 'MODEL_PROTOCOL_ERROR'),
    ({'action': 'finish', 'conclusion': 'change_associated'}, 'FINISH_REJECTED'),
    ({'action': 'finish', 'conclusion': 'insufficient_evidence', 'evidence_ids': ['fake']}, 'UNKNOWN_EVIDENCE'),
])
def test_workflow_rejects_untrusted_actions_and_attribution(tmp_path, message, code):
    with pytest.raises(ToolError) as error:
        run_workflow(ScriptedModel([message]), RunStore(tmp_path / 'runs'), tmp_path / 'state.json',
                     recipes(tmp_path), FailurePredicate('text', match='TARGET'))
    assert error.value.code == code


def test_workflow_budget_ask_and_plan_changes(tmp_path):
    registered = recipes(tmp_path)
    store = RunStore(tmp_path / 'runs')
    checkpoint = tmp_path / 'state.json'
    predicate = FailurePredicate('text', match='TARGET')
    result = run_workflow(ScriptedModel([{'action': 'experiment', 'recipe_id': 'g1'},
                                       {'action': 'experiment', 'recipe_id': 'g2'}]),
                          store, checkpoint, registered, predicate, max_experiments=1)
    assert result['experiments'] == 1
    assert len(store.list()) == 1
    changed = recipes(tmp_path)
    changed['g1']['request']['argv'][-1] = 'print("changed")'
    with pytest.raises(ToolError) as error:
        run_workflow(ScriptedModel([]), store, checkpoint, changed, predicate)
    assert error.value.code == 'WORKFLOW_CHANGED'
    result = run_workflow(ScriptedModel([{'action': 'ask_user', 'question': 'Which baseline?'}]),
                          store, tmp_path / 'ask.json', registered, predicate)
    assert result['state'] == 'needs_input'


def test_pending_experiment_is_not_replayed_after_crash(tmp_path, monkeypatch):
    import triton_dev.agent.workflow as workflow
    store = RunStore(tmp_path / 'runs')
    checkpoint = tmp_path / 'pending.json'
    registered = recipes(tmp_path)
    predicate = FailurePredicate('text', match='TARGET')
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()
    with monkeypatch.context() as context:
        context.setattr(workflow, 'execute_record', interrupted)
        with pytest.raises(KeyboardInterrupt):
            run_workflow(ScriptedModel([{'action': 'experiment', 'recipe_id': 'g1'}]),
                         store, checkpoint, registered, predicate)
    result = run_workflow(ScriptedModel([{'action': 'finish', 'conclusion': 'baseline_invalid',
                                        'evidence_ids': ['g1']}]),
                          store, checkpoint, registered, predicate)
    assert result['observations']['g1']['classification'] == 'unavailable'
    assert len(store.list()) == 1
    assert store.list()[0]['state'] == 'interrupted'
