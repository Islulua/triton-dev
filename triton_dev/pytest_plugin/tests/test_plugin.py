from triton_dev.cases.service import collect


def test_plugin_does_not_execute_test_body(tmp_path):
    source = tmp_path / "test_never_run.py"
    marker = tmp_path / "executed"
    source.write_text(f"def test_no_run():\n open({str(marker)!r}, 'w').write('bad')\n")
    assert len(collect(source)["cases"]) == 1
    assert not marker.exists()
