import json
import sys

from triton_dev.cli import describe, main, parser_factory


def test_saved_cli_freeze_restore_preflight(make_sdk, tmp_path, capsys):
    sdk = make_sdk()
    common = ['--sdk-root', str(sdk.parent), '--cache-root', str(tmp_path / 'cache'), '--non-interactive']
    assert main(['env', 'save', 'baseline', '--sdk', sdk.name, *common]) == 0
    result = json.loads(capsys.readouterr().out)['data']
    assert result['qualification'] == 'untested'
    assert main(['env', 'plan', '--saved', 'baseline', *common]) == 0
    assert json.loads(capsys.readouterr().out)['data']['key'] == result['spec']['key']
    assert main(['env', 'saved', 'list', *common]) == 0
    assert json.loads(capsys.readouterr().out)['data'] == [{'name': 'baseline'}]
    assert main(['env', 'plan', '--saved', 'baseline', '--sdk', 'latest', *common]) == 2
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'INVALID_ARGUMENT'


def test_recorded_cli_failure_classification_and_export(tmp_path, capsys):
    common = ['--cache-root', str(tmp_path / 'cache')]
    assert main(['runs', 'start', '--cwd', str(tmp_path), *common, '--', sys.executable, '-c',
                 'print("TARGET");raise SystemExit(7)']) == 7
    record = json.loads(capsys.readouterr().out)['data']
    assert record['state'] == 'failed'
    predicate = tmp_path / 'predicate.json'
    predicate.write_text(json.dumps({'kind': 'text', 'match': 'TARGET'}))
    assert main(['diagnose', 'classify', record['id'], '--predicate', str(predicate), *common]) == 0
    assert json.loads(capsys.readouterr().out)['data']['classification'] == 'target_failure'
    output = tmp_path / 'evidence.zip'
    assert main(['runs', 'export', record['id'], '--output', str(output), *common]) == 0
    capsys.readouterr()
    assert main(['runs', 'verify-export', str(output), *common]) == 0
    assert json.loads(capsys.readouterr().out)['data']['valid']


def test_cli_history_executes_real_sdk_environments(make_sdk, tmp_path, capsys):
    a = make_sdk()
    b = make_sdk('TX82_SDK_Daily_2026-10-24-02-52')
    predicate = tmp_path / 'predicate.json'
    predicate.write_text(json.dumps({'kind': 'text', 'match': 'TARGET'}))
    code = 'import os; print("TARGET");raise SystemExit(int("10-24" in os.environ["TRITON_DEV_SDK"]))'
    assert main(['diagnose', 'history', '--sdk-root', str(a.parent), '--cache-root', str(tmp_path / 'cache'),
                 '--versions', a.name, b.name, '--predicate', str(predicate), '--repeat', '2', '--native-only',
                 '--', sys.executable, '-c', code]) == 0
    result = json.loads(capsys.readouterr().out)['data']
    assert result['first_failure'] == b.name
    assert result['source'] == 'execution'


def test_describe_machine_contracts_cover_new_commands():
    parser_factory()
    result = describe('runs.start')
    assert result['input_schema']['properties']['command']['type'] == 'array'
    assert result['input_schema']['properties']['pytest']['type'] == 'boolean'
    assert describe('runs.export')['input_schema']['properties']['redact_env']['type'] == 'array'
    assert result['input_schema']['additionalProperties'] is False
    assert result['output_schema']['properties']['schema_version']['const'] == 1
    assert describe('env.save')['side_effects'] == 'write_cache'


def test_recorded_timeout_has_nonzero_exit_and_error_request_is_terminal(tmp_path, capsys):
    common = ['--cache-root', str(tmp_path / 'cache')]
    assert main(['runs', 'start', '--timeout', '0.1', *common, '--', sys.executable, '-c',
                 'import time;time.sleep(20)']) == 124
    assert json.loads(capsys.readouterr().out)['data']['state'] == 'timeout'
    assert main(['runs', 'start', *common, '--']) == 2
    assert json.loads(capsys.readouterr().out)['data']['state'] == 'error'
