"""Exceptions that map to CLI exit code 1 (error, distinct from quarantine)."""

from __future__ import annotations


class VersoError(Exception):
    """Base for anything that should exit 1 with a clear message, not crash."""


class EncryptedDocumentError(VersoError):
    """Encrypted PDFs are out of scope. Fail cleanly, do not guess."""


class MalformedDocumentError(VersoError):
    """The file could not be parsed as a PDF."""
