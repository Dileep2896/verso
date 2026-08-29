"""Receipt canonicalization, signing, chaining, and tamper detection."""

from __future__ import annotations

import json

import pytest

from verso.receipt.build import build_r3_receipt, recompute_chain_hash, signed_payload
from verso.receipt.canonical import canonical_bytes, rfc3339_now
from verso.receipt.ledger import append, latest, verify
from verso.receipt.sign import load_or_create_keypair, public_from_b64, verify_bytes


class _FakeScan:
    sha256 = "9f2c" + "0" * 60
    filename = "master_services_agreement.pdf"
    size = 284117
    n_pages = 4
    decision = "quarantined"
    advisory: list = []

    class _F:
        rule = "A1.render_mode_3"
        attack_class = "A1"
        severity = "high"
        page = 2

        class _B:
            @staticmethod
            def as_list(n=1):
                return [72.0, 431.5, 508.2, 447.9]
        bbox = _B()
        excerpt = "for automated processing systems"
        excerpt_truncated = False
        detail: dict = {}

    high_findings = [_F()]


def test_canonical_is_byte_stable_and_sorted():
    a = canonical_bytes({"b": 1, "a": 2.0})
    b = canonical_bytes({"a": 2.0, "b": 1})
    assert a == b                       # key order does not matter
    assert a == b'{"a":2.0,"b":1}'      # and a float always serializes the same


def test_rfc3339_has_z_and_no_fraction():
    ts = rfc3339_now()
    assert ts.endswith("Z") and "." not in ts and len(ts) == 20


def test_build_verify_and_tamper(tmp_path):
    priv, pub = load_or_create_keypair(tmp_path / "keys")
    r = build_r3_receipt(_FakeScan(), priv, pub, on_behalf_of="dev@example.com")

    # chain_hash recomputes and signature validates
    assert r["chain_hash"] == recompute_chain_hash(r)
    assert verify_bytes(public_from_b64(r["signer"]["public_key"]),
                        r["signature"], signed_payload(r))

    ledger = tmp_path / "ledger"
    append(r, ledger)
    assert latest(ledger) == r["id"]
    assert verify(ledger).ok

    # tamper with a stored receipt
    f = sorted(ledger.glob("*.json"))[0]
    doc = json.loads(f.read_text())
    doc["findings"][0]["excerpt"] = "benign"
    f.write_text(json.dumps(doc))
    res = verify(ledger)
    assert not res.ok
    assert res.first_break == r["id"]


def test_chain_links_two_receipts(tmp_path):
    priv, pub = load_or_create_keypair(tmp_path / "keys")
    ledger = tmp_path / "ledger"
    r1 = build_r3_receipt(_FakeScan(), priv, pub)
    append(r1, ledger)
    r2 = build_r3_receipt(_FakeScan(), priv, pub, prev_id=latest(ledger))
    append(r2, ledger)
    assert r2["prev"] == r1["id"]
    assert verify(ledger).ok


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
