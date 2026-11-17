"""Require a second documentation build to reproduce every public output byte."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "target" / "site"


def snapshot():
    return {path.relative_to(SITE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(SITE.rglob("*")) if path.is_file()}


def main():
    before = snapshot()
    if not before:
        raise SystemExit("No generated documentation to compare")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_docs.py")], cwd=ROOT, check=True,
                   env={**os.environ, "PYTHONHASHSEED": "1"})
    after = snapshot()
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    if changed:
        raise SystemExit("Documentation is not reproducible: " + ", ".join(changed))
    print(f"Identical output in two documentation builds: {len(before)} files")


if __name__ == "__main__":
    main()
