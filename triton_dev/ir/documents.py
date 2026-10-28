"""Bounded, filesystem-independent TritonParse import and source-qualified IR maps."""

import gzip
import hashlib
import io
import json
import posixpath
import re

from triton_dev.common.contracts import ToolError
from .vendor.ir_parser import (
    _parse_generic_loc, _parse_llvm_dbg, _parse_ptx_loc, _parse_amdgcn_loc, _parse_sass_loc,
)

MAX_INPUT = 2 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
ORDER = {name: i for i, name in enumerate(["ttir", "ttgir", "coreir", "mkir", "txir", "llvm_mlir", "llir", "ptx", "amdgcn", "sass"])}
LABELS = {"coreir": "CoreIR", "txir": "TxIR", "llvm_mlir": "LLVM MLIR", "llir": "LLVM IR"}


def fail(message):
    raise ToolError("INVALID_TRACE", message)


def path_key(value):
    # Never read locations from disk, including paths embedded by the compiler.
    return posixpath.normpath(value.replace("\\", "/")) if isinstance(value, str) else ""


def sanitize_mapping(mapping, source, line_count):
    result = {}
    if not isinstance(mapping, dict):
        return result
    end = source["start_line"] + len(source["code"].split("\n")) - 1
    for key, loc in mapping.items():
        if not re.fullmatch(r"[1-9]\d*", str(key)) or int(key) > line_count or not isinstance(loc, dict):
            continue
        file = loc.get("inlined_at_file") or loc.get("file")
        line = loc.get("inlined_at_line", loc.get("line"))
        if (path_key(file) != path_key(source["file_path"]) or type(line) is not int
                or not source["start_line"] <= line <= end):
            continue
        col = loc.get("column", 0)
        result[str(key)] = {"file": source["file_path"], "line": line,
                            "column": col if type(col) is int and col >= 0 else 0}
    return result


def make_document(source, files, *, mappings=None, metadata=None, source_kind="imported", budget=None):
    budget = budget if budget is not None else {"locations": 12000, "edges": 2048}
    if not isinstance(source, dict) or not isinstance(source.get("code"), str):
        fail("Embedded Python source code is required")
    source = {"code": source["code"], "file_path": path_key(source.get("file_path", "kernel.py")),
              "start_line": source.get("start_line", 1)}
    if not source["file_path"] or type(source["start_line"]) is not int or source["start_line"] < 1:
        fail("Invalid source file or start line")
    if not isinstance(files, dict) or not files or len(files) > 64:
        fail("Expected 1..64 embedded artifacts")
    mappings = mappings if isinstance(mappings, dict) else {}
    stages, seen = [], set()
    for name, content in files.items():
        if not isinstance(name, str) or not isinstance(content, str):
            continue  # Binary artifacts are not text IR.
        stage = name.rsplit(".", 1)[-1].lower()
        if stage in {"json", "so", "cubin", "hsaco", "py"}:
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", stage) or stage in seen:
            fail("Ambiguous or invalid IR stage; select a single compilation instance")
        seen.add(stage)
        if len(content.encode()) > MAX_EXPANDED:
            fail("IR artifact exceeds size limit")
        raw = mappings.get(stage)
        if not isinstance(raw, dict):
            definitions = len(re.findall(r'#loc\d*\s*=\s*loc\s*\(', content))
            edges = len(re.findall(r'callsite\s*\(|#loc\d*\s*=\s*loc\s*\(\s*(?:#loc|"[^"\n]*"\s*\(\s*#loc)', content))
            budget["locations"] -= definitions
            budget["edges"] -= edges
            if definitions > 4096 or edges > 512 or min(budget.values()) < 0:
                fail("Source location complexity limit exceeded; split the trace or import precomputed mappings")
            parser = {"llir": _parse_llvm_dbg, "ptx": _parse_ptx_loc,
                      "amdgcn": _parse_amdgcn_loc, "sass": _parse_sass_loc}.get(stage, _parse_generic_loc)
            try:
                raw = parser(content, ir_type=stage)
            except (ValueError, TypeError, KeyError, RecursionError):
                raw = {}
        mapping = sanitize_mapping(raw, source, len(content.split("\n")))
        stages.append({"id": stage, "label": LABELS.get(stage, stage.upper()), "content": content,
                       "mapping": mapping, "mapping_status": "available" if mapping else "unavailable"})
    if not stages:
        fail("No embedded text IR found; referenced filesystem paths are not read")
    stages.sort(key=lambda s: (ORDER.get(s["id"], 99), s["id"]))
    metadata = metadata if isinstance(metadata, dict) else {}
    return {"schema_version": 1, "source_kind": source_kind, "kernel": str(metadata.get("name", "kernel")),
            "source": source, "source_hash": hashlib.sha256(source["code"].encode()).hexdigest(),
            "metadata": metadata, "stages": stages, "hardware_verified": False}


def import_trace(data):
    if not isinstance(data, bytes) or len(data) > MAX_INPUT:
        fail("Trace input limit is 2 MiB")
    try:
        if data.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                data = stream.read(MAX_EXPANDED + 1)
        if len(data) > MAX_EXPANDED:
            fail("Expanded trace limit is 8 MiB")
        text = data.decode("utf-8")
        try:
            entries = json.loads(text, parse_constant=lambda value: fail('Nonfinite JSON values are not accepted'))
            entries = entries if isinstance(entries, list) else [entries]
        except json.JSONDecodeError:
            entries = [json.loads(line, parse_constant=lambda value: fail('Nonfinite JSON values are not accepted')) for line in text.splitlines() if line.strip()]
        if len(entries) > 10000:
            fail("Too many trace events")
        documents = []
        budget = {"locations": 12000, "edges": 2048}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if "source" in entry and isinstance(entry.get("stages"), list):
                stages = entry["stages"]
                if any(not isinstance(s, dict) or not isinstance(s.get("id"), str) for s in stages):
                    fail("Invalid stage objects")
                if len({s['id'] for s in stages}) != len(stages):
                    fail("Duplicate IR stage IDs")
                doc = make_document(entry["source"], {s["id"]: s.get("content") for s in stages},
                                    mappings={s["id"]: s.get("mapping", {}) for s in stages},
                                    metadata={**entry.get("metadata", {}), "name": entry.get("kernel", "kernel")},
                                    source_kind="illustrative" if entry.get("source_kind") == "illustrative" else "imported", budget=budget)
                documents.append(doc)
            else:
                payload = entry.get("payload", {})
                if not isinstance(payload, dict) or not payload.get("python_source") or not payload.get("file_content"):
                    continue
                documents.append(make_document(payload["python_source"], payload["file_content"],
                                               mappings=payload.get("source_mappings"), metadata=entry.get("metadata"), budget=budget))
            if len(documents) > 50:
                fail("Import at most 50 compilation instances at once")
    except (ValueError, TypeError, OSError, EOFError, RecursionError) as exc:
        raise ToolError("INVALID_TRACE", "Malformed JSON/NDJSON or gzip trace") from exc
    if not documents:
        fail("No compilation instances with embedded source and IR")
    return documents
