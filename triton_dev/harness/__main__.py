"""JSON stdin/stdout worker. Never accepts an executable or shell command."""
import argparse
import json
import sys
from pathlib import Path

from triton_dev.common.contracts import ToolError, envelope
from .catalog import catalog, execute_cli


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--sdk-root", type=Path, default=Path("/workspace/triton-harness/sdks"))
    parser.add_argument("--cache-root", type=Path, default=Path("/workspace/triton-harness/cache"))
    args = parser.parse_args()
    try:
        if args.catalog:
            value = catalog()
        else:
            request = json.loads(sys.stdin.read(1024 * 1024 + 1))
            value = execute_cli(request["command"], request.get("arguments", {}),
                                sdk_root=args.sdk_root, cache_root=args.cache_root)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (ToolError, ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps(envelope(error=exc if isinstance(exc, ToolError) else
                                 ToolError("HARNESS_INPUT_ERROR", str(exc)))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
