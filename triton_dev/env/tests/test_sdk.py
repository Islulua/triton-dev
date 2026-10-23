import io
import tarfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.env.sdk import choose_remote, discover, download, remote_names, select, wheels


def test_discovery_date_and_incomplete_latest(make_sdk):
    first = make_sdk()
    newer = make_sdk("TX82_SDK_Daily_2026-10-22-15-30")
    (first.parent / "TX82_SDK_Daily_2026-99-22-15-30").mkdir()
    (first.parent / ".download-incomplete").mkdir()
    assert len(discover(first.parent)) == 2
    assert select(first.parent, "20261022") == newer
    incomplete = make_sdk("TX82_SDK_Daily_2026-10-23-01-00", complete=False)
    with pytest.raises(ToolError, match=incomplete.name):
        select(first.parent)


@pytest.mark.parametrize("date", ["20260230", "20261301", "not-a-date"])
def test_invalid_remote_dates(date):
    with pytest.raises(ToolError):
        choose_remote(["TX82_SDK_Daily_2026-10-22-02-52"], date)


def test_wheel_identity_and_ambiguity(make_sdk):
    sdk = make_sdk()
    assert {w["name"] for w in wheels(sdk)} == {"raops", "torch_raisa", "triton"}
    original = next((sdk / "wheel").glob("raops-*.whl"))
    (original.parent / "raops-copy.whl").write_bytes(original.read_bytes())
    with pytest.raises(ToolError, match="expected one wheel"):
        wheels(sdk)


def test_download_concurrent_and_reuse(make_sdk, tmp_path, http_directory):
    sdk = make_sdk()
    remote = tmp_path / "remote"
    remote.mkdir()
    with tarfile.open(remote / (sdk.name + ".tar.gz"), "w:gz") as tar:
        tar.add(sdk, arcname=sdk.name)
    url = http_directory(remote)
    assert remote_names(url) == [sdk.name]
    destination = tmp_path / "downloaded"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: download(destination, url, "20261022"), range(2)))
    assert sorted(r["reused"] for r in results) == [False, True]
    assert select(destination).name == sdk.name
    assert not list(destination.glob(".download-*"))


@pytest.mark.parametrize("kind", ["escape", "symlink", "checksum"])
def test_download_failure_never_publishes(tmp_path, http_directory, kind):
    remote = tmp_path / "remote"
    remote.mkdir()
    name = "TX82_SDK_Daily_2026-10-22-02-52"
    with tarfile.open(remote / (name + ".tar.gz"), "w:gz") as tar:
        member = tarfile.TarInfo("../escape" if kind == "escape" else "link")
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/escape"
        else:
            member.size = 1
        tar.addfile(member, io.BytesIO(b"x") if member.isfile() else None)
    root = tmp_path / "downloaded"
    with pytest.raises(ToolError):
        download(root, http_directory(remote), expected_sha256="wrong" if kind == "checksum" else None)
    assert not (root / name).exists()
    assert not (tmp_path / "escape").exists()


def test_remote_selects_latest_in_day():
    names = ["TX82_SDK_Daily_2026-10-22-02-52", "TX82_SDK_Daily_2026-10-22-15-30",
             "TX82_SDK_Daily_2026-10-23-01-00"]
    assert choose_remote(names, "20261022") == names[1]
    assert choose_remote(names) == names[2]
    with pytest.raises(ToolError):
        choose_remote(names, "20261021")
