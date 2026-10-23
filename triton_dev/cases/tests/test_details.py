from triton_dev.cases.service import collect, lint, show


def test_fixture_details_param_ids_and_lint(tmp_path):
    (tmp_path / 'pytest.ini').write_text('[pytest]\nmarkers =\n    case_id(value): logical id\n')
    test = tmp_path / 'test_details.py'
    test.write_text('import pytest\n'
                    '@pytest.mark.case_id("C-1")\n@pytest.mark.parametrize("value", [1,2])\n'
                    'def test_one(value): pass\n'
                    '@pytest.mark.case_id("C-1")\ndef test_two(): pass\n'
                    'def test_three(): pass\n')
    result = collect(tmp_path)
    first = result['cases'][0]
    assert 'value' in show(tmp_path, first['nodeid'])['fixtures']
    assert first['line'] > 0
    findings = lint(tmp_path, require_id=True)['findings']
    assert {x['code'] for x in findings} == {'DUPLICATE_CASE_ID', 'MISSING_CASE_ID'}
