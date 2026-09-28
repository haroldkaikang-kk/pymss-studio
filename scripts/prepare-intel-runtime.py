"""Prepare a relocatable Intel macOS engine without touching system Python."""
import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT / "intel-build" / "python-runtime")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise SystemExit("Run on an Intel Mac, using native x86_64 tools.")
    destination = args.destination.resolve()
    if destination.exists():
        raise SystemExit(f"Destination already exists; preserve or move it before rebuilding: {destination}")
    downloads = ROOT / "intel-build" / "managed-python"
    subprocess.run(["uv", "python", "install", "--no-bin", "--install-dir", str(downloads), "3.10.21"], check=True)
    candidates = list(downloads.glob("cpython-3.10.21-macos-x86_64-*/bin/python3"))
    if len(candidates) != 1:
        raise SystemExit(f"Expected exactly one Intel Python runtime under {downloads}")
    shutil.copytree(candidates[0].parent.parent, destination, symlinks=True)
    # This private copy belongs to the app, not uv's managed installation.
    # Keep uv's original protected while allowing dependencies in the bundle.
    (destination / "lib" / "python3.10" / "EXTERNALLY-MANAGED").unlink(missing_ok=True)
    python = destination / "bin" / "python3"
    env = {**os.environ, "PYTHONHOME": str(destination), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], env=env, check=True)
    wheels = sorted((ROOT / "python" / "intel-wheels").glob("*.whl"))
    if len(wheels) != 2:
        raise SystemExit("Both patched Intel pymss wheels must be included.")
    subprocess.run([str(python), "-m", "pip", "install", "--only-binary=:all:",
                    "--find-links", str(ROOT / "python" / "intel-wheels"),
                    "-r", str(ROOT / "python" / "requirements-intel-lock.txt"),
                    *map(str, wheels)], env=env, check=True)
    subprocess.run([str(python), "-m", "pip", "check"], env=env, check=True)
    subprocess.run([str(python), str(ROOT / "scripts" / "write-intel-runtime-state.py"), str(destination)], env=env, check=True)


if __name__ == "__main__":
    main()
