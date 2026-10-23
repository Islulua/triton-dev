"""Deterministic failure definitions shared by CLI, history and agent."""
import json
import math
from dataclasses import dataclass

from triton_dev.common.contracts import ToolError


@dataclass(frozen=True)
class FailurePredicate:
    kind: str
    match: str = ''
    exit_code: int | None = None
    phase: str = ''
    atol: float = 0.0
    rtol: float = 0.0

    def __post_init__(self):
        if self.kind not in {'text', 'exit', 'stage', 'numerical'}:
            raise ToolError('INVALID_PREDICATE', 'Unknown predicate kind')
        if (not isinstance(self.match, str) or not isinstance(self.phase, str)
                or self.kind == 'text' and not self.match
                or self.kind == 'exit' and (type(self.exit_code) is not int or self.exit_code == 0)
                or self.kind == 'stage' and not self.phase
                or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in (self.atol, self.rtol))):
            raise ToolError('INVALID_PREDICATE', 'Invalid failure signature or tolerance')

    @classmethod
    def parse(cls, value):
        try:
            return cls(**value)
        except (TypeError, ValueError) as exc:
            raise ToolError('INVALID_PREDICATE', str(exc)) from exc

    def classify(self, result):
        if result.get('state') in {'timeout', 'cancelled', 'interrupted', 'error'}:
            return 'unavailable'
        raw = result.get('result') or result
        if 'returncode' not in raw:
            return 'unavailable'
        failed = raw['returncode'] != 0
        if self.kind == 'text':
            if not failed:
                return 'passed'
            if self.match in (raw.get('stdout', '') + raw.get('stderr', '')):
                return 'target_failure'
            if any(raw.get('output_truncated', {}).values()):
                return 'insufficient_evidence'
            return 'different_failure'
        if self.kind == 'exit':
            return 'target_failure' if raw['returncode'] == self.exit_code else ('different_failure' if failed else 'passed')
        if self.kind == 'stage':
            stages = result.get('stages', [])
            if any(s.get('when') == self.phase and s.get('outcome') == 'failed'
                   and (not self.match or self.match in (s.get('longrepr') or '')) for s in stages):
                return 'target_failure'
            return 'different_failure' if failed else 'passed'
        try:
            values = raw.get('structured') or json.loads(raw['stdout'])
            if self.phase and values.get('phase') != self.phase:
                return 'different_failure'
            actual, expected = values['actual'], values['expected']
            if not isinstance(actual, list) or not isinstance(expected, list) or not actual or len(actual) != len(expected):
                return 'insufficient_evidence'
            if any(type(x) not in (float, int) or not math.isfinite(x) for x in actual + expected):
                return 'insufficient_evidence'
            mismatch = any(abs(a - b) > self.atol + self.rtol * abs(b) for a, b in zip(actual, expected))
            return 'target_failure' if mismatch else ('different_failure' if failed else 'passed')
        except (KeyError, TypeError, ValueError, AttributeError):
            return 'insufficient_evidence'
