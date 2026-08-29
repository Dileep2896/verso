"""The refusal ledger: append-only, chained, tamper evident.

Receipts are written as ``NNNNNN_<id>.json`` so issue order is recoverable from
the filesystem. Verification walks them in order and checks that each ``prev``
resolves to the previous receipt, each ``chain_hash`` recomputes, and each
signature validates -- reporting the FIRST break by receipt id, because a ledger
with a hole is worse than no ledger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .build import recompute_chain_hash, signed_payload
from .canonical import canonical_bytes
from .sign import public_from_b64, verify_bytes


def _entries(ledger_dir: Path) -> list[Path]:
    return sorted(ledger_dir.glob("[0-9]*_rcp_*.json"))


def latest(ledger_dir: str | Path) -> Optional[str]:
    """Return the id of the last receipt in the ledger, or None if empty."""
    ledger_dir = Path(ledger_dir)
    files = _entries(ledger_dir)
    if not files:
        return None
    return json.loads(files[-1].read_text())["id"]


def append(receipt: dict, ledger_dir: str | Path) -> Path:
    ledger_dir = Path(ledger_dir)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    seq = len(_entries(ledger_dir)) + 1
    path = ledger_dir / f"{seq:06d}_{receipt['id']}.json"
    path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True))
    return path


@dataclass
class VerifyResult:
    ok: bool
    count: int
    first_break: Optional[str] = None
    reason: Optional[str] = None

    def __bool__(self) -> bool:
        return self.ok


def verify(ledger_dir: str | Path) -> VerifyResult:
    ledger_dir = Path(ledger_dir)
    files = _entries(ledger_dir)
    prev_id: Optional[str] = None
    for path in files:
        try:
            receipt = json.loads(path.read_text())
        except Exception as e:
            return VerifyResult(False, len(files), path.name, f"unreadable: {e}")

        rid = receipt.get("id", path.name)

        # 1. prev linkage
        if receipt.get("prev") != prev_id:
            return VerifyResult(False, len(files), rid,
                                f"prev mismatch: expected {prev_id!r}, "
                                f"got {receipt.get('prev')!r}")

        # 2. chain hash recomputes
        expect = recompute_chain_hash(receipt)
        if receipt.get("chain_hash") != expect:
            return VerifyResult(False, len(files), rid,
                                "chain_hash does not recompute (content altered)")

        # 3. signature validates over core + chain_hash
        signer = receipt.get("signer", {})
        try:
            public = public_from_b64(signer["public_key"])
        except Exception:
            return VerifyResult(False, len(files), rid, "missing/invalid signer key")
        if not verify_bytes(public, receipt.get("signature", ""), signed_payload(receipt)):
            return VerifyResult(False, len(files), rid, "signature invalid")

        prev_id = rid

    return VerifyResult(True, len(files))
