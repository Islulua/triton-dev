#!/usr/bin/env bash
set -euo pipefail
repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_root="${TRITON_HARNESS_ROOT:-/workspace/triton-harness}"
cd "$repository"
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
(cd frontend && npm ci --cache "$runtime_root/npm-cache" && TRITON_DEV_UI_BASE=/triton/ npm run build)
(cd harness && npm ci --cache "$runtime_root/npm-cache" && npm run build)
npm install --prefix "$runtime_root/runtime" @deepseek-ai/dsh@0.2.2-rc.1 --cache "$runtime_root/npm-cache"
npm install --prefix "$runtime_root/tooling" pnpm@11.28.5 --cache "$runtime_root/npm-cache"
DSH_HOME="${DSH_HOME:-$runtime_root/home}" \
PNPM_HOME="$runtime_root/pnpm" XDG_DATA_HOME="$runtime_root/data" XDG_CACHE_HOME="$runtime_root/cache" \
PATH="$runtime_root/tooling/node_modules/.bin:$PATH" \
  "$runtime_root/runtime/node_modules/.bin/dsh" plugin --profile web add "$repository/harness"
