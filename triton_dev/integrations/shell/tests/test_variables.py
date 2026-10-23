import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.integrations.shell import render_shell


def test_invalid_variable_names_are_not_executable():
    for name in ("A;touch /tmp/bad", "A=B", "1BAD", "用户"):
        with pytest.raises(ToolError):
            render_shell({"variables": {name: "value"}})


def test_unset_and_empty_are_distinct():
    rendered = render_shell({"variables": {"EMPTY": ""}, "unset": ["ABSENT"]})
    assert "unset ABSENT" in rendered
    assert "export EMPTY=''" in rendered
