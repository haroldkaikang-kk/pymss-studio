"""Reject bundles containing non-Intel binaries or deployment targets above Monterey."""
import json
import re
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(sys.argv[1]).resolve()
    records, failures = [], []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        description = subprocess.check_output(["file", "-b", str(path)], text=True)
        if "Mach-O" not in description:
            continue
        if "x86_64" not in description:
            failures.append(f"Wrong architecture: {path.relative_to(root)}")
            continue
        loads = subprocess.check_output(["otool", "-arch", "x86_64", "-l", str(path)], text=True)
        targets = re.findall(r"\bminos\s+(\d+\.\d+(?:\.\d+)?)", loads)
        targets += re.findall(r"LC_VERSION_MIN_MACOSX\s+cmdsize\s+\d+\s+version\s+(\d+\.\d+(?:\.\d+)?)", loads)
        for value in targets:
            if tuple(map(int, value.split("."))) > (12, 7, 6):
                failures.append(f"Requires macOS {value}: {path.relative_to(root)}")
        links = subprocess.check_output(["otool", "-arch", "x86_64", "-L", str(path)], text=True)
        if re.search(r"^\s+/(?:opt/homebrew|usr/local|Library/Frameworks)/", links, re.M):
            failures.append(f"Unbundled dependency: {path.relative_to(root)}")
        records.append({"file": str(path.relative_to(root)), "minimum_macos": targets})
    print(json.dumps({"binaries": records, "failures": failures}, indent=2))
    if not records or failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
