"""Budgeted exhaustive history search; no monotonicity assumption or fabricated culprit."""
from triton_dev.common.contracts import ToolError


class ScriptedEvaluator:
    """Explicit offline double: classifications only, never proof about a real SDK."""
    source = 'mock'

    def __init__(self, outcomes):
        self.outcomes = {key: iter(value) for key, value in outcomes.items()}

    def __call__(self, version):
        try:
            return {'classification': next(self.outcomes[version]), 'source': 'mock'}
        except (KeyError, StopIteration) as exc:
            raise ToolError('MOCK_EXHAUSTED', version) from exc


def search(versions, evaluator, *, repeat=2, budget=40):
    if (not versions or len(set(versions)) != len(versions) or not 1 <= repeat <= 20
            or not 1 <= budget <= 1000):
        raise ToolError('INVALID_ARGUMENT', 'Distinct ordered versions, repeat=1..20, budget=1..1000 required')
    evidence, states, spent = [], [], 0
    allowed = {'passed', 'target_failure', 'different_failure', 'unavailable', 'insufficient_evidence'}
    for version in versions:
        outcomes = []
        for attempt in range(repeat):
            if spent >= budget:
                break
            observation = evaluator(version)
            if observation.get('classification') not in allowed:
                raise ToolError('INVALID_OBSERVATION', 'Evaluator returned unknown classification')
            evidence.append({'id': f'history-{spent + 1}', 'version': version,
                             'attempt': attempt + 1, **observation})
            outcomes.append(observation['classification'])
            spent += 1
        state = outcomes[0] if len(outcomes) == repeat and len(set(outcomes)) == 1 else 'unstable_or_incomplete'
        states.append({'version': version, 'state': state})
        if spent >= budget:
            break
    complete = len(states) == len(versions) and all(s['state'] in {'passed', 'target_failure'} for s in states)
    sequence = [s['state'] for s in states]
    nonmonotonic = any(a == 'target_failure' and 'passed' in sequence[i + 1:] for i, a in enumerate(sequence))
    targets = [s['version'] for s in states if s['state'] == 'target_failure']
    return {'schema_version': 1, 'strategy': 'exhaustive', 'evidence': evidence, 'states': states,
            'budget_used': spent, 'complete': complete, 'nonmonotonic': nonmonotonic,
            'first_observed_failure': targets[0] if targets else None,
            'first_failure': targets[0] if complete and targets and sequence[0] == 'passed' else None,
            'conclusion': 'history_characterized' if complete else 'insufficient_evidence',
            'scope': 'ordered_artifacts', 'source': getattr(evaluator, 'source', 'execution'),
            'limitations': ['First failing artifact is not proof of repository/commit root cause']}
