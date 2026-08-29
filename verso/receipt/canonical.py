"""The one and only way a receipt is serialized to bytes.

Byte-stable serialization is the foundation every other receipt property depends
on: sorted keys, no insignificant whitespace, UTF-8, floats rounded to one
decimal, RFC 3339 timestamps with a Z suffix and no fractional seconds.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 1)
    if isinstance(value, list):
        return [_round_floats(v) for v in value]
    if isinstance(value, tuple):
        return [_round_floats(v) for v in value]
    if isinstance(value, dict):
        return {k: _round_floats(v) for k, v in value.items()}
    return value


def canonical_bytes(obj: Any) -> bytes:
    """Canonical JSON encoding used for hashing and signing."""
    normalized = _round_floats(obj)
    return json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def rfc3339_now() -> str:
    """Current UTC time, RFC 3339, 'Z' suffix, no fractional seconds."""
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")
