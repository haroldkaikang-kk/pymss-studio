#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_root="$PWD"
mkdir -p intel-build/engine-sources python/intel-wheels
prepare_engine() {
  local name="$1" commit="$2" patch="$3"
  local destination="$project_root/intel-build/engine-sources/$name"
  git init "$destination"
  git -C "$destination" fetch --depth 1 "https://github.com/pymss-project/$name.git" "$commit"
  git -C "$destination" checkout --detach FETCH_HEAD
  git -C "$destination" apply "$project_root/scripts/intel-patches/$patch"
  uv build --wheel --no-sources --out-dir "$project_root/python/intel-wheels" "$destination"
}
prepare_engine pymss-core 4b7312d8c291fce401ffc07e0855ff25ebc2f46f pymss-core.patch
prepare_engine pymss 6ff2735f8d6362b4db905d7851e15da22ca2fc09 pymss.patch
