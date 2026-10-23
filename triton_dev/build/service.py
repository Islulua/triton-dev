from pathlib import Path

from triton_dev.common.contracts import ToolError

TARGETS = {
    "llvm": "compiler/riscv-gnu-toolchain/llvm",
    "spike": "basetools/tx82-spike-sim",
    "triton": "programming/triton/tx82triton",
    "flaggems": "programming/triton/flaggems5.4",
    "txops": "programming/txops/tx82",
    "torch-txda": "programming/torch_txda",
}


def workspace(start):
    start = Path(start).resolve()
    for path in (start, *start.parents):
        if (path / ".repo").is_dir():
            return path
    raise ToolError("WORKSPACE_NOT_FOUND", "No .repo directory; pass --workspace")


def targets(root):
    root = Path(root).resolve()
    return [{"name": name, "path": str(root / path), "exists": (root / path).is_dir(),
             "recipe": "not_implemented"} for name, path in TARGETS.items()]


def plan_build(root, target):
    if target not in TARGETS:
        raise ToolError("TARGET_NOT_FOUND", target)
    item = next(x for x in targets(root) if x["name"] == target)
    if not item["exists"]:
        raise ToolError("SOURCE_NOT_FOUND", item["path"])
    return {**item, "will_modify_source": False, "can_build": False,
            "todo": "Define recipe, build inputs, output mapping and isolation with project owners"}
