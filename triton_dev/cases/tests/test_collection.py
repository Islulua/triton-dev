import pytest

from triton_dev.cases.service import collect
from triton_dev.common.contracts import ToolError


def test_real_parameterized_collection(tmp_path):
    source = tmp_path / "test_sample.py"
    source.write_text("import pytest\n@pytest.mark.parametrize('x',[1,2])\ndef test_value(x): assert x > 0\n")
    result = collect(source)
    assert [x["nodeid"] for x in result["cases"]] == ["test_sample.py::test_value[1]", "test_sample.py::test_value[2]"]
    assert all("parametrize" in x["markers"] for x in result["cases"])


def test_collection_error_not_empty_success(tmp_path):
    source = tmp_path / "test_broken.py"
    source.write_text("this is invalid python !\n")
    with pytest.raises(ToolError) as error:
        collect(source)
    assert error.value.code == "COLLECTION_FAILED"
