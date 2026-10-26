from triton_dev.cases.service import collect


def test_plugin_does_not_execute_test_body(tmp_path):
    source = tmp_path / "test_never_run.py"
    marker = tmp_path / "executed"
    source.write_text(f"def test_no_run():\n open({str(marker)!r}, 'w').write('bad')\n")
    assert len(collect(source)["cases"]) == 1
    assert not marker.exists()


def test_explicit_operator_metadata_survives_parameterized_collection(tmp_path):
    source = tmp_path / 'test_operators.py'
    source.write_text('''import pytest
@pytest.mark.operator("matmul")
@pytest.mark.parametrize("size", [64, 128])
def test_matrix(size): pass
@pytest.mark.skip(reason="no device")
@pytest.mark.operator("softmax")
def test_normalize(): pass
def test_unlabelled(): pass
''')
    rows = collect(source)['cases']
    assert len(rows) == 4
    assert [r['operator'] for r in rows] == ['matmul', 'matmul', 'softmax', None]
    assert rows[0]['logical_nodeid'] == rows[1]['logical_nodeid']
