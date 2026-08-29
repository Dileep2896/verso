"""Architectural lint: the structural detector may not call a model.

Verso decides whether an agent may read a document. A detector that feeds
untrusted document text to a model to make that decision has reproduced the
vulnerability it exists to prevent. This check fails the build if anything under
verso/detect/ imports an LLM SDK, an HTTP client, or the advisory package.

Run by ``make lint``. Exits nonzero on any violation.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DETECT = ROOT / "verso" / "detect"

FORBIDDEN_ROOTS = {
    "anthropic", "openai", "cohere", "google", "mistralai", "llama_cpp",
    "requests", "httpx", "urllib", "http", "socket", "aiohttp", "websocket",
}
FORBIDDEN_INTERNAL = {"verso.advisory"}


def _module_roots(node: ast.AST):
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for alias in n.names:
                yield alias.name
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                yield n.module


def main() -> int:
    violations = []
    for path in sorted(DETECT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for mod in _module_roots(tree):
            root = mod.split(".")[0]
            if root in FORBIDDEN_ROOTS:
                violations.append((path, mod, "network/LLM import"))
            if any(mod == f or mod.startswith(f + ".") for f in FORBIDDEN_INTERNAL):
                violations.append((path, mod, "advisory import in detector"))

    if violations:
        print("LINT FAIL -- detector purity violated:")
        for path, mod, why in violations:
            rel = path.relative_to(ROOT)
            print(f"  {rel}: imports {mod!r} ({why})")
        return 1
    n = len(list(DETECT.rglob("*.py")))
    print(f"lint: PASS ({n} detector modules, no LLM/HTTP/advisory imports)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
