"""Construct a signed R3 (quarantine-refusal) receipt from a scan result.

R3 is the only class Verso itself emits. R1, R4, R5, R7 exist in the schema and
in docs/REFUSAL-TAXONOMY.md as the shape of the system; the demo narrates them,
the code does not fake them.

chain_hash is over the canonical serialization of the receipt core (which
includes ``prev``). The signature is over the core plus chain_hash, i.e.
everything except the signature itself.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from ..serialize import finding_dict
from .canonical import canonical_bytes, rfc3339_now
from .sign import public_key_b64, sign_bytes

RECEIPT_VERSION = "1"
AGENT_NAME = "verso-cli"
AGENT_VERSION = "0.4.1"


def _new_id() -> str:
    return "rcp_" + secrets.token_hex(13)


def build_r3_receipt(scan_result, private, public, *,
                     on_behalf_of: Optional[str] = None,
                     prev_id: Optional[str] = None) -> dict:
    """Build a signed R3 receipt dict for a quarantined document."""
    core = {
        "version": RECEIPT_VERSION,
        "id": _new_id(),
        "class": "R3",
        "issued_at": rfc3339_now(),
        "subject": {
            "kind": "document",
            "sha256": scan_result.sha256,
            "filename": scan_result.filename,
            "bytes": scan_result.size,
            "pages": scan_result.n_pages,
        },
        "decision": scan_result.decision,
        "actor": {
            "agent": AGENT_NAME,
            "version": AGENT_VERSION,
            "on_behalf_of": on_behalf_of,
        },
        # only high-severity structural findings drive R3
        "findings": [finding_dict(f) for f in scan_result.high_findings],
        "advisory": list(scan_result.advisory),
        "prev": prev_id,
        "signer": {"alg": "ed25519", "public_key": public_key_b64(public)},
    }
    chain_hash = hashlib.sha256(canonical_bytes(core)).hexdigest()
    signed = {**core, "chain_hash": chain_hash}
    signature = sign_bytes(private, canonical_bytes(signed))
    return {**signed, "signature": signature}


def recompute_chain_hash(receipt: dict) -> str:
    core = {k: v for k, v in receipt.items() if k not in ("chain_hash", "signature")}
    return hashlib.sha256(canonical_bytes(core)).hexdigest()


def signed_payload(receipt: dict) -> bytes:
    body = {k: v for k, v in receipt.items() if k != "signature"}
    return canonical_bytes(body)
