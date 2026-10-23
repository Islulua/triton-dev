from triton_dev.env.sdk import inspect_sdk
from triton_dev.integrations.mock import create_sdk


def test_mock_sdk_is_explicit_and_inspectable(tmp_path):
    sdk = create_sdk(tmp_path, 'TX82_SDK_Daily_2026-10-23-02-52')
    assert 'mock' in (sdk / 'MOCK_ONLY.json').read_text()
    assert len(inspect_sdk(sdk)['wheels']) == 3
    assert not list((sdk / 'lib').iterdir())
