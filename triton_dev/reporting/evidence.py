"""Export bounded, redacted evidence without executing or extracting archive contents."""
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

from triton_dev.common.contracts import ToolError


def redact(text, secrets=()):
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)(bearer\s+)[^\s"\\]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:token|password|api_key|secret)["\s]*[:=]["\s]*)[^\s",}]+',
                  r'\1[REDACTED]', text)
    return text


def redact_value(value, secrets=()):
    if isinstance(value, dict):
        return {key: ('[REDACTED]' if re.search(r'(?i)token|password|api_key|secret', key)
                      else redact_value(item, secrets)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]
    return redact(value, secrets) if isinstance(value, str) else value


def export_run(store, run_id, output, *, secrets=(), max_bytes=32 * 1024 * 1024):
    record = store.read(run_id)
    if record['state'] in {'queued', 'running'}:
        raise ToolError('RUN_ACTIVE', 'Export a terminal run to obtain a consistent evidence package')
    root = store.directory(run_id)
    files = [root / 'record.json', *root.glob('*.log'), *root.glob('*events*.jsonl')]
    contents, total = {}, 0
    for path in sorted(set(files)):
        if path.is_symlink() or not path.is_file():
            raise ToolError('UNSAFE_EVIDENCE', str(path))
        size = path.stat().st_size
        if total + size > max_bytes:
            raise ToolError('EVIDENCE_TOO_LARGE', 'Export budget exceeded')
        text = path.read_text(errors='replace')
        if path.suffix == '.json':
            data = json.dumps(redact_value(json.loads(text), secrets), indent=2).encode()
        elif path.suffix == '.jsonl':
            lines = []
            for line in text.splitlines():
                try:
                    lines.append(json.dumps(redact_value(json.loads(line), secrets)))
                except ValueError:
                    lines.append(json.dumps({'incomplete_event': redact(line, secrets)}))
            data = ('\n'.join(lines) + '\n').encode()
        else:
            data = redact(text, secrets).encode()
        total += len(data)
        contents[path.name] = data
    manifest = {'schema_version': 1, 'run_id': run_id,
                'scope': 'record_logs_and_events', 'redacted': True,
                'limitations': ['Automatic redaction is heuristic; supply explicit secret literals',
                                'SDK binaries, tensor inputs and credentials are not bundled'],
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    # Exclusive creation prevents clobbering an existing report or source evidence.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        with ZipFile(stream, 'w', compression=ZIP_DEFLATED) as archive:
            for name, data in contents.items():
                archive.writestr(name, data)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2))
    return {'output': str(Path(output).resolve()), 'manifest': manifest}


def verify_archive(path, *, max_bytes=32 * 1024 * 1024):
    with ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if (len(set(names)) != len(names) or 'manifest.json' not in names
                or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names)
                or sum(i.file_size for i in infos) > max_bytes):
            raise ToolError('INVALID_EVIDENCE', 'Unsafe, duplicate or oversized archive entries')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema_version') != 1 or set(manifest.get('files', {})) != set(names) - {'manifest.json'}:
            raise ToolError('INVALID_EVIDENCE', 'Manifest does not match archive entries')
        for name, expected in manifest['files'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ToolError('CHECKSUM_MISMATCH', name)
    return {'valid': True, 'run_id': manifest['run_id'], 'scope': manifest['scope'],
            'limitation': 'Integrity within this archive, not producer authenticity or root-cause proof'}
