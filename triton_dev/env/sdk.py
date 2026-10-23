from __future__ import annotations

import re
import tarfile
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from triton_dev.common.contracts import ToolError, digest, file_lock
from .settings import PACKAGES, SDK_PATTERN


def sdk_time(name):
    match = re.fullmatch(SDK_PATTERN, name)
    if not match:
        return None
    try:
        return datetime.strptime(match['stamp'], "%Y-%m-%d-%H-%M")
    except ValueError:
        return None


def discover(root: Path):
    if not root.is_dir():
        return []
    return sorted([
        {"name": p.name, "path": str(p.resolve()), "time": sdk_time(p.name).isoformat(),
         "complete": all((p / part).is_dir() for part in ("wheel", "lib", "bin"))}
        for p in root.iterdir() if p.is_dir() and sdk_time(p.name)
    ], key=lambda item: item["time"], reverse=True)


def select(root: Path, selector="latest") -> Path:
    candidates = discover(root)
    if selector != "latest":
        if re.fullmatch(r"\d{8}", selector):
            try:
                day = datetime.strptime(selector, "%Y%m%d").date().isoformat()
            except ValueError as exc:
                raise ToolError("INVALID_DATE", selector) from exc
            candidates = [x for x in candidates if x["time"].startswith(day)]
        else:
            candidates = [x for x in candidates if x["name"] == selector]
    if not candidates:
        raise ToolError("SDK_NOT_FOUND", f"No matching SDK: {selector}")
    chosen = candidates[0]
    if not chosen["complete"]:
        raise ToolError("SDK_INCOMPLETE", chosen["name"])
    return Path(chosen["path"])


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def wheels(sdk: Path, *, context=None):
    found = {normalize(name): [] for name in PACKAGES}
    for path in sorted((sdk / "wheel").glob("*.whl")):
        if context is not None:
            from .preflight import compatible
            if not compatible(path, context):
                continue
        try:
            with ZipFile(path) as archive:
                names = [x for x in archive.namelist() if x.endswith(".dist-info/METADATA")]
                if len(names) != 1:
                    raise ValueError("Expected one METADATA")
                metadata = BytesParser().parsebytes(archive.read(names[0]))
                name, version = metadata.get("Name"), metadata.get("Version")
                if not name or not version:
                    raise ValueError("Missing Name/Version")
                if normalize(name) in found:
                    found[normalize(name)].append({
                        "name": name, "version": version, "path": str(path.resolve()),
                        "sha256": digest(path), "requires_python": metadata.get("Requires-Python"),
                        "requires_dist": metadata.get_all("Requires-Dist", []),
                    })
        except (BadZipFile, ValueError, KeyError) as exc:
            raise ToolError("INVALID_WHEEL", f"{path.name}: {exc}") from exc
    result = []
    for name, matches in found.items():
        if len(matches) != 1:
            raise ToolError("WHEEL_SELECTION_FAILED", f"{name}: expected one wheel, got {len(matches)}")
        result.append(matches[0])
    return result


def inspect_sdk(sdk):
    return {"name": sdk.name, "path": str(sdk), "wheels": wheels(sdk),
            "native_component_mapping": "unknown", "native_loading": "not_checked"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            name = urllib.parse.unquote(urllib.parse.urlsplit(href).path).rsplit("/", 1)[-1]
            if name.endswith(".tar.gz") and sdk_time(name[:-7]):
                self.names.add(name[:-7])


def open_url(url, headers=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30)


def remote_names(base_url, *, headers=None):
    try:
        with open_url(base_url, headers) as response:
            parser = Links()
            parser.feed(response.read(8 * 1024 * 1024).decode("utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ToolError("REMOTE_LIST_FAILED", "Cannot read SDK directory listing") from exc
    if not parser.names:
        raise ToolError("REMOTE_LIST_UNSUPPORTED", "No SDK links found; authenticated listing adapter may be required")
    return sorted(parser.names, key=sdk_time, reverse=True)


def choose_remote(names, when=None):
    names = sorted([n for n in names if sdk_time(n)], key=sdk_time, reverse=True)
    if when:
        fmt = {8: "%Y%m%d", 12: "%Y%m%d%H%M"}.get(len(when))
        if not fmt:
            raise ToolError("INVALID_DATE", "Use YYYYMMDD or YYYYMMDDHHMM")
        try:
            stamp = datetime.strptime(when, fmt)
        except ValueError as exc:
            raise ToolError("INVALID_DATE", when) from exc
        names = [n for n in names if (sdk_time(n).date() == stamp.date() if len(when) == 8
                                      else sdk_time(n) == stamp)]
    if not names:
        raise ToolError("SDK_NOT_FOUND", "No remote SDK matches the requested date")
    return names[0]


def download(root, base_url, when=None, *, headers=None, expected_sha256=None, name=None):
    name = name or choose_remote(remote_names(base_url, headers=headers), when)
    if not sdk_time(name):
        raise ToolError("INVALID_ARGUMENT", "Invalid SDK name")
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    with file_lock(root / ".triton-dev-locks" / f"{name}.lock"):
        if target.exists():
            return {"sdk": str(select(root, name)), "reused": True}
        with tempfile.TemporaryDirectory(prefix=".download-", dir=root) as temp:
            temp = Path(temp)
            archive = temp / "sdk.tar.gz"
            try:
                with open_url(base_url.rstrip("/") + "/" + name + ".tar.gz", headers) as src:
                    with archive.open("wb") as dst:
                        total = 0
                        for chunk in iter(lambda: src.read(1024 * 1024), b""):
                            total += len(chunk)
                            if total > 50 * 1024**3:
                                raise ToolError("ARCHIVE_TOO_LARGE", "Download exceeds 50 GiB")
                            dst.write(chunk)
                actual = digest(archive)
                if expected_sha256 and actual != expected_sha256:
                    raise ToolError("CHECKSUM_MISMATCH", "Archive checksum mismatch")
                unpack = temp / "unpack"
                unpack.mkdir()
                with tarfile.open(archive) as tar:
                    members = tar.getmembers()
                    total = 0
                    for member in members:
                        dest = (unpack / member.name).resolve()
                        if not dest.is_relative_to(unpack.resolve()) or not (member.isfile() or member.isdir()):
                            raise ToolError("UNSAFE_ARCHIVE", "Links, special files or escaping paths are not accepted")
                        total += member.size
                        if total > 100 * 1024**3:
                            raise ToolError("ARCHIVE_TOO_LARGE", "Unpacked size exceeds 100 GiB")
                    # Members are explicitly restricted to regular files/directories.
                    for member in members:
                        dest = unpack / member.name
                        if member.isdir():
                            dest.mkdir(parents=True, exist_ok=True)
                        else:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with tar.extractfile(member) as src, dest.open("wb") as dst:
                                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                                    dst.write(chunk)
                            dest.chmod(member.mode & 0o777 & ~0o022)
                source = unpack / name if (unpack / name).is_dir() else unpack
                if not all((source / part).is_dir() for part in ("bin", "lib", "wheel")):
                    raise ToolError("SDK_INCOMPLETE", "Archive lacks bin/lib/wheel")
                source.rename(target)
            except (OSError, tarfile.TarError) as exc:
                raise ToolError("DOWNLOAD_FAILED", "Download or unpack failed") from exc
    return {"sdk": str(target.resolve()), "reused": False, "sha256": actual,
            "checksum_verified": bool(expected_sha256)}


def sdk_diff(left, right):
    def files(root):
        return {str(p.relative_to(root)): digest(p) for p in root.rglob("*") if p.is_file()}
    a, b = files(left), files(right)
    return {"left": str(left), "right": str(right),
            "changed": [p for p in sorted(a.keys() | b.keys()) if a.get(p) != b.get(p)],
            "component_attribution": "unknown"}
