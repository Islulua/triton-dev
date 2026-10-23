import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.diagnosis.predicates import FailurePredicate
from triton_dev.diagnosis.history import ScriptedEvaluator, search


def test_structured_stage_and_numerical_predicates():
    stage = FailurePredicate('stage', phase='teardown', match='cleanup')
    record = {'result': {'returncode': 1}, 'stages': [
        {'when': 'teardown', 'outcome': 'failed', 'longrepr': 'cleanup failed'}]}
    assert stage.classify(record) == 'target_failure'
    assert FailurePredicate('stage', phase='call').classify(record) == 'different_failure'
    numerical = FailurePredicate('numerical', phase='execute', atol=0.01, rtol=0.01)
    raw = {'returncode': 0, 'structured': {'phase': 'execute', 'actual': [1.5], 'expected': [1.0]}}
    assert numerical.classify(raw) == 'target_failure'
    raw['structured']['actual'] = [1.001]
    assert numerical.classify(raw) == 'passed'
    raw['structured']['actual'] = [float('nan')]
    assert numerical.classify(raw) == 'insufficient_evidence'
    assert numerical.classify({'returncode': 1, 'stdout': 'not JSON'}) == 'insufficient_evidence'
    assert FailurePredicate('text', match='lost').classify({'returncode': 1, 'stdout': '', 'output_truncated': {'stdout': True}}) == 'insufficient_evidence'


@pytest.mark.parametrize('value', [{'kind': 'unknown'}, {'kind': 'text'}, {'kind': 'exit', 'exit_code': 0},
                                  {'kind': 'numerical', 'atol': -1}])
def test_invalid_predicates_rejected(value):
    with pytest.raises(ToolError):
        FailurePredicate.parse(value)


def test_history_handles_nonmonotonic_and_marks_mock_scope():
    evaluator = ScriptedEvaluator({'a': ['passed'] * 2, 'b': ['target_failure'] * 2, 'c': ['passed'] * 2})
    result = search(['a', 'b', 'c'], evaluator)
    assert result['complete'] and result['nonmonotonic']
    assert result['first_failure'] == 'b'
    assert result['source'] == 'mock'


def test_history_unknown_flaky_and_budget_never_claim_earliest():
    for outcomes, budget in [({'a': ['passed'] * 2, 'b': ['unavailable'] * 2, 'c': ['target_failure'] * 2}, 10),
                             ({'a': ['passed', 'target_failure'], 'b': ['target_failure'] * 2}, 10),
                             ({'a': ['passed'] * 2, 'b': ['target_failure'] * 2}, 3)]:
        result = search(list(outcomes), ScriptedEvaluator(outcomes), budget=budget)
        assert not result['complete']
        assert result['first_failure'] is None
        assert result['conclusion'] == 'insufficient_evidence'
