from dataclasses import asdict

from triton_dev.common.contracts import ToolError
from .predicates import FailurePredicate
from triton_dev.env.sdk import sdk_diff, select
from triton_dev.env.service import resolve
from triton_dev.execution.service import execute


def classify(result, match):
    if result["returncode"] == 0:
        return "passed"
    return "target_failure" if match in (result["stdout"] + result["stderr"]) else "different_failure"


def compare(root, cache, good, bad, command, *, match=None, predicate=None, repeat=3, native_only=False, timeout=300):
    predicate = predicate or FailurePredicate("text", match=match or "")
    if not 1 <= repeat <= 20:
        raise ToolError("INVALID_ARGUMENT", "A non-empty failure match and repeat=1..20 are required")
    left, right = select(root, good), select(root, bad)
    if left == right:
        raise ToolError("INVALID_ARGUMENT", "Good and bad must be different SDKs")
    # Capture paths once; never re-resolve 'latest' during experiments.
    environments = [resolve(root, cache, p.name, native_only=native_only) for p in (left, right)]
    evidence = []
    for label, environment in zip(("good", "bad"), environments):
        for index in range(repeat):
            try:
                result = execute(environment, command, timeout=timeout)
            except ToolError as exc:
                result = {"state": "error", "error": {"code": exc.code, "message": str(exc)},
                          "result": exc.details}
            evidence.append({"id": f"{label}-{index + 1}", "role": label,
                             "classification": predicate.classify(result), "result": result})
        if label == "good" and any(x["classification"] != "passed" for x in evidence):
            return {"conclusion": "baseline_invalid", "scope": "unknown", "evidence": evidence}
    failures = [x["classification"] for x in evidence if x["role"] == "bad"]
    stable = all(x == "target_failure" for x in failures)
    return {
        "conclusion": "sdk_change_associated" if stable else "not_stably_reproduced",
        "scope": "sdk" if stable else "unknown", "evidence": evidence,
        "diff": sdk_diff(left, right), "predicate": asdict(predicate),
        "limitations": ["Text matching is a basic predicate, not semantic root-cause proof",
                        "Repository/commit and native component attribution require confirmed mappings",
                        "native-only does not verify SDK Python packages or native loading" if native_only
                        else "Native loading probe is not yet implemented"],
    }
