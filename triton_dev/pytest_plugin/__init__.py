"""Explicitly loaded collection adapter; it is not auto-enabled for user's pytest."""
import json
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption("--triton-dev-collection-output", default=None)


def pytest_collection_finish(session):
    output = session.config.getoption("--triton-dev-collection-output")
    if output:
        data = [{"nodeid": item.nodeid, "path": str(item.path),
                 "markers": sorted({m.name for m in item.iter_markers()})}
                for item in session.items]
        Path(output).write_text(json.dumps(data), encoding="utf-8")
