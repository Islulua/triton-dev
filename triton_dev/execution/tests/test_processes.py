import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from triton_dev.common.contracts import ToolError, run_process
from triton_dev.env.service import resolve
from triton_dev.execution.service import execute


def test_two_processes_do_not_share_environment(make_sdk, tmp_path):
    a = make_sdk()
    b = make_sdk("TX82_SDK_Daily_2026-10-23-02-52")
    before = dict(os.environ)
    environments = [resolve(a.parent, tmp_path, p.name, native_only=True) for p in (a, b)]
    argv = [sys.executable, "-c", "import os,json; print(json.dumps([os.environ['RAISA_CMODEL_PATH'],os.environ['TRITON_CACHE_DIR']]))"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda env: execute(env, argv), environments))
    observations = [json.loads(r["stdout"]) for r in results]
    assert observations[0][0] == str(a) + "/"
    assert observations[1][0] == str(b) + "/"
    assert observations[0][1] != observations[1][1]
    assert dict(os.environ) == before


def test_timeout_and_raw_failure():
    assert run_process([sys.executable, "-c", "raise SystemExit(7)"])["returncode"] == 7
    with pytest.raises(ToolError) as error:
        run_process([sys.executable, "-c", "import time;time.sleep(10)"], timeout=0.05)
    assert error.value.code == "TIMEOUT"
