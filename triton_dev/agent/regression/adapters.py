"""Deterministic mock artifacts/model; real subprocesses do not validate hardware."""
import hashlib
import json
from typing import Protocol

from triton_dev.common.contracts import ToolError

SCENARIOS = {
    'component': '单组件回归：cmodel 变更',
    'interaction': '双组件交互：LLVM + cmodel',
    'no_regression': '最新版本通过',
    'bad_baseline': '基线无效',
    'nonmonotonic': '历史曾失败后恢复',
    'unavailable': '历史制品缺失',
    'flaky': '最新版本偶现',
}
COMPONENTS = ['llvm', 'cmodel', 'torch']


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class SDKAdapter(Protocol):
    def inventory(self) -> list: ...
    def update(self) -> dict: ...


class MockSDKAdapter:
    source = 'mock_artifacts'

    def inventory(self):
        artifacts = [dict(id=f'mock-sdk-202610{10 + i}', date=f'2026-10-{10 + i}',
                          components={c: i for c in COMPONENTS}, source=self.source) for i in range(10)]
        return [dict(item, sha256=digest(item)) for item in artifacts]

    def update(self):
        return self.inventory()[-1]


class MockModel:
    """Selects a registered candidate. Has no execution or filesystem authority."""
    def respond(self, context):
        return {'type': 'select_candidate', 'task_id': context['task_id'],
                'state_revision': context['state_revision'],
                'candidate_id': context['candidates'][0],
                'evidence_ids': context['evidence_ids'],
                'reason_summary': 'Mock模型按登记顺序选择合法组件实验；结论由实际实验矩阵决定。'}


def validate_decision(value, context):
    if (not isinstance(value, dict) or set(value) != {'type', 'task_id', 'state_revision',
            'candidate_id', 'evidence_ids', 'reason_summary'}
            or value['type'] != 'select_candidate' or value['task_id'] != context['task_id']
            or type(value['state_revision']) is not int or value['state_revision'] != context['state_revision']
            or value['candidate_id'] not in context['candidates']
            or not isinstance(value['evidence_ids'], list)
            or any(not isinstance(e, str) or e not in context['evidence_ids'] for e in value['evidence_ids'])
            or not isinstance(value['reason_summary'], str) or not 0 < len(value['reason_summary']) <= 1000):
        raise ToolError('MODEL_PROTOCOL_ERROR', 'Model must select a current candidate and existing evidence')
    return value


CASE_SOURCE = '''import json
from pathlib import Path
import pytest

@pytest.mark.parametrize("dtype", ["fp16"])
def test_regression(dtype):
    e = json.loads(Path("environment.json").read_text())
    c, scenario = e["components"], e["scenario"]
    if scenario == "unavailable" and c["cmodel"] == 4:
        pytest.skip("MOCK_ARTIFACT_UNAVAILABLE")
    if scenario == "flaky" and c["cmodel"] == 9:
        bad = e["repeat"] % 2 == 0
    elif scenario == "bad_baseline":
        bad = True
    elif scenario == "no_regression":
        bad = False
    elif scenario == "interaction":
        bad = c["cmodel"] >= 5 and c["llvm"] >= 5
    elif scenario == "nonmonotonic":
        bad = c["cmodel"] == 3 or c["cmodel"] >= 6
    else:
        bad = c["cmodel"] >= 5
    assert not bad, "MOCK_REGRESSION: simulated SDK behavior; no device kernel executed"
'''
PLUGIN_SOURCE = '''import json
from pathlib import Path
reports = []
def pytest_runtest_logreport(report):
    reports.append({"nodeid": report.nodeid, "when": report.when,
                    "outcome": report.outcome, "duration": report.duration,
                    "longrepr": str(report.longrepr) if report.longrepr else ""})
def pytest_sessionfinish(session, exitstatus):
    Path("stages.json").write_text(json.dumps(reports))
'''
NODEID = 'test_regression.py::test_regression[fp16]'
