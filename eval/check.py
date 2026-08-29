"""Determinism gate: scan every corpus file twice, assert identical output hash.

Binary pass or fail. Exits 0 on PASS, 1 on FAIL, naming the first file that
differs. This is what ``make check`` runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from verso.scan import scan

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "corpus" / "build"
LABELS = BUILD / "labels.json"


def main() -> int:
    labels = json.loads(LABELS.read_text())
    files = [c["file"] for c in labels["attacks"]] + \
            [c["file"] for c in labels["clean"]]
    failures = []
    for rel in files:
        p = BUILD / rel
        h1 = scan(p).output_hash
        h2 = scan(p).output_hash
        if h1 != h2:
            failures.append(rel)
            print(f"NONDETERMINISTIC: {rel}\n  {h1}\n  {h2}")

    if failures:
        print(f"\ndeterminism: FAIL ({len(failures)} file(s))")
        return 1
    print(f"determinism: PASS ({len(files)} files, scanned twice each)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
