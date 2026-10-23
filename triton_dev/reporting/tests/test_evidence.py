import json
import sys
from zipfile import ZipFile

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.execution.records import RunStore, start
from triton_dev.reporting.evidence import export_run, verify_archive


def test_redacted_export_integrity_and_tampering(tmp_path):
    store = RunStore(tmp_path / 'runs')
    run = start(store, [sys.executable, '-c', 'print("password=abc123 custom-literal")'], cwd=tmp_path)
    archive = tmp_path / 'evidence.zip'
    export_run(store, run['id'], archive, secrets=['custom-literal'])
    assert verify_archive(archive)['valid']
    assert archive.stat().st_mode & 0o777 == 0o600
    with ZipFile(archive) as source:
        files = {name: source.read(name) for name in source.namelist()}
    assert all(b'abc123' not in data and b'custom-literal' not in data for data in files.values())
    assert json.loads(files['record.json'])['id'] == run['id']
    for name, data in files.items():
        if name.endswith('.jsonl'):
            for line in data.decode().splitlines():
                assert isinstance(json.loads(line), dict)
    assert 'cache/' not in files
    files['record.json'] = json.dumps({'tampered': True}).encode()
    bad = tmp_path / 'bad.zip'
    with ZipFile(bad, 'w') as output:
        for name, data in files.items():
            output.writestr(name, data)
    with pytest.raises(ToolError) as error:
        verify_archive(bad)
    assert error.value.code == 'CHECKSUM_MISMATCH'
    assert 'abc123' in store.read(run['id'])['result']['stdout']  # Original evidence retained.


def test_active_run_export_rejected(tmp_path):
    store = RunStore(tmp_path / 'runs')
    run_id = store.create({'argv': ['unused']})
    with pytest.raises(ToolError) as error:
        export_run(store, run_id, tmp_path / 'active.zip')
    assert error.value.code == 'RUN_ACTIVE'
