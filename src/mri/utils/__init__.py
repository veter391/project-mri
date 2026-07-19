"""Small shared helpers with no dependency on the rest of the package."""
from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["utc_iso"]

_UTC = timezone.utc


def utc_iso(moment: datetime) -> str:
    """A datetime as canonical UTC ISO-8601.

    Timestamps in the database are compared as strings by SQLite, which is only
    correct when they share one offset. A commit authored at +09:00 and a scan
    stored at +00:00 would otherwise sort by their written offset, not their
    instant — an audit showed that picking a post-decision scan as the baseline
    and fabricating a delta. A naive datetime is taken to already be UTC rather
    than guessed at. Shared by the storage layer and the consequence loop so both
    write and compare on the identical footing.
    """
    if moment.tzinfo is not None:
        moment = moment.astimezone(_UTC)
    else:
        moment = moment.replace(tzinfo=_UTC)
    return moment.isoformat()
