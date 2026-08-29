"""Ed25519 signing for receipts.

Keys live under ``keys/`` (gitignored). The public key is also embedded in every
receipt so the ledger is self-verifying without out-of-band key distribution --
a verifier can still pin an expected key, but does not have to.
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

DEFAULT_KEY_DIR = Path("keys")
PRIV_NAME = "signing_key.pem"
PUB_NAME = "signing_key.pub.pem"


def load_or_create_keypair(key_dir: str | Path = DEFAULT_KEY_DIR):
    key_dir = Path(key_dir)
    key_dir.mkdir(parents=True, exist_ok=True)
    priv_path = key_dir / PRIV_NAME
    pub_path = key_dir / PUB_NAME

    if priv_path.is_file():
        private = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    else:
        private = Ed25519PrivateKey.generate()
        priv_path.write_bytes(private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        try:
            priv_path.chmod(0o600)
        except OSError:
            pass
    public = private.public_key()
    if not pub_path.is_file():
        pub_path.write_bytes(public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
    return private, public


def sign_bytes(private: Ed25519PrivateKey, data: bytes) -> str:
    return base64.b64encode(private.sign(data)).decode("ascii")


def public_key_b64(public: Ed25519PublicKey) -> str:
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def public_from_b64(b64: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(b64))


def verify_bytes(public: Ed25519PublicKey, signature_b64: str, data: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    try:
        public.verify(base64.b64decode(signature_b64), data)
        return True
    except (InvalidSignature, Exception):
        return False
