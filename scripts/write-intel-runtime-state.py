"""Called with the newly bundled interpreter, not the builder's Python."""
import json
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata, util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from worker_bootstrap import _manifest, _manifest_versions_are_satisfied, _probe_python_runtime


def main():
    destination = Path(sys.argv[1]).resolve()
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise SystemExit("Intel macOS only")
    manifest = _manifest()
    probed = _probe_python_runtime(Path(sys.executable))
    ok, failures = _manifest_versions_are_satisfied(probed, manifest, "cpu")
    if not ok or not all(probed["packages"].values()):
        raise SystemExit(f"Incomplete Intel runtime: {failures}")
    state = {
        **probed, "backend": "cpu", "manifestVersion": manifest["manifestVersion"],
        "stateVersion": 2, "source": "bundled", "pythonPath": "../bin/python3",
        "installedAt": datetime.now(timezone.utc).isoformat(),
    }
    envs = destination / "runtime-envs"
    envs.mkdir()
    (envs / "active-runtime.json").write_text(json.dumps(state, indent=2) + "\n")
    print("Verified Intel engine and wrote its relocatable runtime pointer.")


if __name__ == "__main__":
    main()
