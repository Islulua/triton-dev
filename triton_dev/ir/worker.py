"""Copy into the sandbox workdir and execute there. Never import this in the API."""

import importlib.util
import inspect
import json
import os
from pathlib import Path
import resource


def main():
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    root = Path.cwd()
    os.environ["TRITON_CACHE_DIR"] = str(root / "cache")
    os.environ["TRITON_DEBUG"] = "1"
    spec = json.loads((root / "spec.json").read_text())
    from triton.compiler import ASTSource, compile
    from triton.backends.compiler import GPUTarget

    module_spec = importlib.util.spec_from_file_location("edited_kernel", root / "kernel.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    fn = getattr(module, spec["entry"])
    constant_arg = "constexprs" if "constexprs" in inspect.signature(ASTSource).parameters else "constants"
    ast_source = ASTSource(fn, signature=spec["signature"], **{constant_arg: spec["constexprs"]})
    compiled = compile(ast_source, target=GPUTarget(**spec["target"]), options=spec["options"])
    files = {f'{spec["entry"]}.{stage}': content for stage, content in compiled.asm.items() if isinstance(content, str)}
    (root / "artifacts.json").write_text(json.dumps({"source_path": str(root / "kernel.py"), "files": files,
        "metadata": {"name": spec["entry"], "compiler_hash": compiled.hash}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
