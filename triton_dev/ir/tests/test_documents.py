import gzip
import json

import pytest

from triton_dev.common.contracts import ToolError
from triton_dev.ir.documents import import_trace, make_document


SOURCE = {"code": "def kernel(x):\n    y = x + 1\n    return y\n", "file_path": "/work/kernel.py", "start_line": 10}
TTIR = '%0 = arith.addi %a, %b : i32 loc(#loc1)\n#loc1 = loc("/work/kernel.py":11:9)'


def test_major_stages_map_real_locations_without_fabricating_unknowns():
    doc = make_document(SOURCE, {"kernel.ttir": TTIR, "kernel.coreir": TTIR, "kernel.txir": "module {}"})
    assert [s["id"] for s in doc["stages"]] == ["ttir", "coreir", "txir"]
    assert doc["stages"][0]["mapping"]["1"]["line"] == 11
    assert doc["stages"][2]["mapping"] == {}
    assert doc["stages"][2]["mapping_status"] == "unavailable"
    assert len(doc["source_hash"]) == 64


def test_trace_import_keeps_specializations_and_never_reads_referenced_paths(tmp_path):
    secret = tmp_path / "secret.ttir"
    secret.write_text("secret")
    entries = [
        {"event_type": "compilation", "metadata": {"name": "kernel", "hash": key}, "payload": {
            "python_source": SOURCE, "file_content": {"kernel.ttir": TTIR},
            "file_path": {"secret.ttir": str(secret)}}}
        for key in ["specialization-one", "specialization-two"]
    ]
    docs = import_trace(gzip.compress("\n".join(json.dumps(e) for e in entries).encode()))
    assert len(docs) == 2
    assert [d["metadata"]["hash"] for d in docs] == ["specialization-one", "specialization-two"]
    assert all(len(d["stages"]) == 1 and "secret" not in d["stages"][0]["content"] for d in docs)


def test_inline_callsite_and_exact_file_identity():
    ir = '%0 = arith.addi %a, %b : i32 loc(#loc3)\n#loc1 = loc("/lib/math.py":30:2)\n#loc2 = loc("/work/kernel.py":11:9)\n#loc3 = loc(callsite(#loc1 at #loc2))'
    doc = make_document(SOURCE, {"k.ttir": ir, "k.coreir": TTIR.replace("/work/kernel.py", "/other/kernel.py")})
    assert doc["stages"][0]["mapping"]["1"]["line"] == 11
    assert doc["stages"][0]["mapping"]["1"]["file"] == "/work/kernel.py"
    assert doc["stages"][1]["mapping"] == {}


def test_import_uses_only_valid_bounded_mapping_locations():
    entry = {"payload": {"python_source": SOURCE, "file_content": {"k.custom": "a\nb"},
        "source_mappings": {"custom": {"1": {"file": "/work/kernel.py", "line": 11},
            "99": {"file": "/work/kernel.py", "line": 11},
            "2": {"file": "/work/kernel.py", "line": 99}}}}}
    doc = import_trace(json.dumps(entry).encode())[0]
    assert doc["stages"][0]["mapping"] == {"1": {"file": "/work/kernel.py", "line": 11, "column": 0}}


@pytest.mark.parametrize("data", [b"not json", b"[]", b'{"payload": {}}', gzip.compress(b"x" * (8 * 1024 * 1024 + 1))])
def test_bad_or_expanding_trace_rejected(data):
    with pytest.raises(ToolError):
        import_trace(data)


def test_normalized_export_can_be_reimported():
    doc = make_document(SOURCE, {"kernel.ttir": TTIR})
    imported = import_trace(json.dumps(doc).encode())[0]
    assert imported["stages"][0]["mapping"] == doc["stages"][0]["mapping"]
    assert imported["source_hash"] == doc["source_hash"]


def test_nonfinite_metadata_and_duplicate_stages_are_rejected():
    entry = {'payload': {'python_source': SOURCE, 'file_content': {'k.ttir': TTIR}}, 'metadata': {'time': float('nan')}}
    with pytest.raises(ToolError):
        import_trace(json.dumps(entry).encode())
    doc = make_document(SOURCE, {'k.ttir': TTIR})
    doc['stages'].append(doc['stages'][0])
    with pytest.raises(ToolError):
        import_trace(json.dumps(doc).encode())


def test_deep_location_graph_is_rejected_before_quadratic_parser_work():
    ir = TTIR + '\n' + '\n'.join(f'#loc{i} = loc(callsite(#loc1 at #loc{i-1}))' for i in range(2, 1100))
    with pytest.raises(ToolError, match='complexity'):
        make_document(SOURCE, {'k.ttir': ir})
