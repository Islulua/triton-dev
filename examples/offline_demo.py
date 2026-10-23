"""Run with the tool interpreter: python examples/offline_demo.py --workdir /new/demo-dir."""
import argparse
import json
import sys
from pathlib import Path

from triton_dev.agent.controller import ScriptedModel
from triton_dev.agent.workflow import run_workflow
from triton_dev.diagnosis.history import search
from triton_dev.diagnosis.predicates import FailurePredicate
from triton_dev.env import saved, service
from triton_dev.execution.records import RunStore, start
from triton_dev.execution.service import execute
from triton_dev.integrations.mock import create_sdk
from triton_dev.reporting.evidence import export_run, verify_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', type=Path, required=True)
    args = parser.parse_args()
    root = args.workdir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    sdks, cache = root / 'sdks', root / 'cache'
    a = create_sdk(sdks, 'TX82_SDK_Daily_2026-10-22-02-52')
    b = create_sdk(sdks, 'TX82_SDK_Daily_2026-10-23-02-52')
    for name, sdk in [('baseline', a), ('trial', b)]:
        saved.save(sdks, cache, name, sdk.name)
        service.prepare(sdks, cache, sdk.name)
    environments = {p.name: service.resolve(sdks, cache, p.name) for p in (a, b)}
    code = 'import os; print("MOCK_TARGET"); raise SystemExit(int("10-23" in os.environ["TRITON_DEV_SDK"]))'
    command = ['python', '-c', code]
    predicate = FailurePredicate('text', match='MOCK_TARGET')
    def evaluate(version):
        result = execute(environments[version], command)
        return {'classification': predicate.classify(result), 'result': result, 'source': 'mock_sdk_real_process'}
    history = search([a.name, b.name], evaluate)
    (root / 'history.json').write_text(json.dumps(history, indent=2))
    store = RunStore(cache / 'runs')
    run = start(store, command, cwd=root, environment=environments[b.name])
    export_run(store, run['id'], root / 'evidence.zip')
    assert verify_archive(root / 'evidence.zip')['valid']
    test = root / 'test_demo.py'
    test.write_text('def test_mock_pass(): pass\ndef test_mock_failure(): assert False, "MOCK_TARGET"\n')
    pytest_record = start(store, [test.name], cwd=root, python=sys.executable, pytest=True)
    assert pytest_record['state'] == 'failed'
    recipes = {name: {'role': role, 'request': {'argv': command, 'cwd': str(root),
                'environment': environments[sdk.name], 'timeout': 10}}
               for name, role, sdk in [('g1', 'good', a), ('g2', 'good', a), ('b1', 'bad', b), ('b2', 'bad', b)]}
    responses = [{'action': 'experiment', 'recipe_id': name} for name in recipes]
    responses.append({'action': 'finish', 'conclusion': 'change_associated', 'evidence_ids': list(recipes)})
    workflow = run_workflow(ScriptedModel(responses), store, root / 'workflow-state.json', recipes, predicate)
    assert workflow['state'] == 'finished'
    print(json.dumps({'source': 'mock', 'workdir': str(root), 'history': history['first_failure'],
                      'run_id': run['id'], 'pytest_run_id': pytest_record['id'],
                      'agent_conclusion': workflow['conclusion'], 'evidence_verified': True,
                      'limitation': 'No real Triton, native runtime, model API or devices tested'}, indent=2))


if __name__ == '__main__':
    main()
