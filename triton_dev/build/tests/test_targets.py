import pytest

from triton_dev.build.service import plan_build, targets, workspace
from triton_dev.common.contracts import ToolError


def test_workspace_and_build_plan(tmp_path):
    (tmp_path / ".repo").mkdir()
    source = tmp_path / "programming/triton/tx82triton"
    source.mkdir(parents=True)
    assert workspace(source) == tmp_path
    result = plan_build(tmp_path, "triton")
    assert result["exists"] and not result["can_build"]
    assert result["will_modify_source"] is False
    assert len(targets(tmp_path)) == 6
    with pytest.raises(ToolError):
        plan_build(tmp_path, "cmodel")
