import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.reporting.service import summarize


def test_summary_preserves_scope_and_evidence():
    data = summarize({"scope": "sdk", "conclusion": "sdk_change_associated", "evidence": [
        {"id": "a", "classification": "passed"}, {"id": "b", "classification": "target_failure"}]})
    assert data["counts"] == {"passed": 1, "target_failure": 1}
    assert data["evidence_ids"] == ["a", "b"]
    assert data["scope"] == "sdk"
    with pytest.raises(ToolError):
        summarize({})
