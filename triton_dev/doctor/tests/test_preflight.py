from triton_dev.doctor.service import check


def test_preflight_is_read_only(tmp_path):
    root = tmp_path / "missing"
    result = check(root, tmp_path / "cache")
    assert result["sdk_count"] == 0
    assert result["changes_made"] is False
    assert result["native_runtime"] == "not_checked"
    assert not root.exists() and not (tmp_path / "cache").exists()
