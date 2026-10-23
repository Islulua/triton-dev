import sys
from pathlib import Path

from triton_dev.diagnosis.service import compare
from triton_dev.reporting.service import summarize


def test_sdk_selection_execution_diagnosis_report_flow(make_sdk, tmp_path):
    good = make_sdk()
    bad = make_sdk("TX82_SDK_Daily_2026-10-23-01-00")
    script = tmp_path / "reproduce.py"
    script.write_text("import os\nbad='2026-10-23' in os.environ['RAISA_CMODEL_PATH']\nprint('NUMERIC_MISMATCH' if bad else 'OK')\nraise SystemExit(1 if bad else 0)\n")
    result = compare(good.parent, tmp_path / "cache", good.name, bad.name,
                     [sys.executable, str(script)], match="NUMERIC_MISMATCH", repeat=1, native_only=True)
    report = summarize(result)
    assert report["conclusion"] == "sdk_change_associated"
    assert report["scope"] == "sdk"
    assert report["counts"] == {"passed": 1, "target_failure": 1}


def test_each_module_has_progress_and_tests():
    root = Path(__file__).resolve().parents[1]
    modules = ("env", "build", "cases", "execution", "diagnosis", "reporting", "doctor",
               "agent", "pytest_plugin", "serve", "common", "cli", "integrations/ai", "integrations/shell")
    for name in modules:
        directory = root / "triton_dev" / name
        assert (directory / "TODO.md").is_file(), name
        assert list((directory / "tests").glob("test_*.py")), name
        assert "## 当前进度" in (directory / "TODO.md").read_text(), name
