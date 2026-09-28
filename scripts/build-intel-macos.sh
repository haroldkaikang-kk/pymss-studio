#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin && "$(uname -m)" == x86_64 ]] || { echo "请在 Intel Mac 上构建。"; exit 1; }
for executable in python3 uv node pnpm cargo xcrun; do
  command -v "$executable" >/dev/null || { echo "缺少构建工具：$executable"; exit 1; }
done
export MACOSX_DEPLOYMENT_TARGET=12.0
export PYMSS_BUILD_TARGET=macos-x86_64
export PYMSS_BUILD_VARIANT=intel-monterey-cpu
export PYMSS_BUILD_OFFICIAL=false
export PYMSS_BUILD_UPDATE_SUPPORTED=false
python3 scripts/prepare-intel-runtime.py
PYMSS_MACOS_TOOLS_ARCH=x86_64 bash scripts/prepare-macos-bundled-tools.sh intel-build/bin
pnpm install --frozen-lockfile
pnpm tauri build --target x86_64-apple-darwin --bundles app --config src-tauri/tauri.intel.conf.json
app_path="$PWD/src-tauri/target/x86_64-apple-darwin/release/bundle/macos/Pymss Studio Intel.app"
python3 scripts/audit-intel-macos.py "$app_path" > intel-build/macos-binary-audit.json
SIGN_IDENTITY=- bash scripts/resign-macos-app.sh "$app_path"
codesign --verify --deep --strict "$app_path"
resources="$app_path/Contents/Resources"
PYTHONHOME="$resources/python-runtime" "$resources/python-runtime/bin/python3" "$resources/python/worker.py" env_info
PYTHONHOME="$resources/python-runtime" "$resources/python-runtime/bin/python3" "$resources/python/worker.py" list_models > intel-build/bundled-models.jsonl
ditto -c -k --sequesterRsrc --keepParent "$app_path" intel-build/Pymss-Studio-Intel-Monterey-candidate.zip
echo "构建检查通过；仍需在 macOS 12.7.6 上启动、试听并验收。"
echo "$PWD/intel-build/Pymss-Studio-Intel-Monterey-candidate.zip"
