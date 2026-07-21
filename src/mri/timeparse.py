"""ISO-8601 parsing that behaves the same on every supported Python.

`datetime.fromisoformat` only accepts a trailing ``Z`` from Python 3.11 on;
on 3.10 it raises ``ValueError: Invalid isoformat string``. Git and agent
session logs both emit ``Z``-suffixed UTC timestamps, so every parse site in
the codebase goes through this helper instead of calling ``fromisoformat``
directly.
"""

from __future__ import annotations

from datetime import datetime

__all__ = ["parse_iso8601"]


def parse_iso8601(raw: str) -> datetime:
    """Parse an ISO-8601 timestamp, accepting a ``Z`` suffix on Python 3.10."""
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
