from triton_dev.common.contracts import ToolError


def summarize(report):
    if not isinstance(report, dict) or not isinstance(report.get("evidence"), list):
        raise ToolError("INVALID_REPORT", "Expected a comparison report with evidence")
    counts = {}
    for item in report["evidence"]:
        key = item["classification"]
        counts[key] = counts.get(key, 0) + 1
    return {"conclusion": report.get("conclusion", "unknown"), "scope": report.get("scope", "unknown"),
            "counts": counts, "evidence_ids": [x["id"] for x in report["evidence"]],
            "limitations": report.get("limitations", [])}
