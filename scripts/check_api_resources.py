"""Check a built API service JAR: only the two active SHACL policies may ship."""

import argparse
import hashlib
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jar", type=Path)
    parser.add_argument("--model", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Model checkout whose active policy bytes must match the JAR")
    args = parser.parse_args()
    with zipfile.ZipFile(args.jar) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        prefix = "BOOT-INF/classes/" if any(name.startswith("BOOT-INF/classes/") for name in names) else ""
        shipped = {name.removeprefix(prefix) for name in names if name.startswith(prefix + "shacl/")}
        expected = {"shacl/items.ttl", "shacl/records.ttl"}
        if shipped != expected:
            raise SystemExit(f"Unexpected model resources: {sorted(shipped)}; expected {sorted(expected)}")
        for name in sorted(expected):
            expected_bytes = (args.model / Path(name).name).read_bytes()
            actual = archive.read(prefix + name)
            if actual != expected_bytes:
                raise SystemExit(f"Policy differs from selected model checkout: {name}")
            print(f"{name}: SHA256 {hashlib.sha256(actual).hexdigest()}")
    print("API JAR contains exactly the selected active policies.")


if __name__ == "__main__":
    main()
