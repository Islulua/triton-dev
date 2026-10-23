import sys

from triton_dev.diagnosis.service import classify, compare


def test_good_bad_comparison_with_real_subprocesses(make_sdk, tmp_path):
    a = make_sdk()
    b = make_sdk("TX82_SDK_Daily_2026-10-23-02-52")
    (b / "lib/bad-marker").write_text("candidate only")
    command = [sys.executable, "-c", "import os,pathlib; bad=(pathlib.Path(os.environ['RAISA_CMODEL_PATH'])/'lib/bad-marker').exists(); print('TARGET' if bad else 'OK'); raise SystemExit(1 if bad else 0)"]
    result = compare(a.parent, tmp_path, a.name, b.name, command, match="TARGET", repeat=2, native_only=True)
    assert result["conclusion"] == "sdk_change_associated"
    assert result["scope"] == "sdk"
    assert [x["classification"] for x in result["evidence"]] == ["passed", "passed", "target_failure", "target_failure"]
    assert "lib/bad-marker" in result["diff"]["changed"]


def test_other_failure_and_invalid_baseline(make_sdk, tmp_path):
    a = make_sdk()
    b = make_sdk("TX82_SDK_Daily_2026-10-23-02-52")
    assert classify({"returncode": 1, "stdout": "ImportError", "stderr": ""}, "numeric error") == "different_failure"
    result = compare(a.parent, tmp_path, a.name, b.name,
                     [sys.executable, "-c", "raise SystemExit(1)"], match="TARGET", native_only=True)
    assert result["conclusion"] == "baseline_invalid"
    assert all(x["role"] == "good" for x in result["evidence"])
