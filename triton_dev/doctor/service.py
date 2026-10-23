import os
import shutil
import sys

from triton_dev.env.sdk import discover


def check(root, cache):
    parent = cache
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return {"python": sys.version, "platform": sys.platform, "sdk_root": str(root),
            "sdk_count": len(discover(root)), "cache_parent_writable": os.access(parent, os.W_OK),
            "shells": {x: shutil.which(x) for x in ("bash", "zsh")},
            "native_runtime": "not_checked", "changes_made": False}
