"""Small shared helpers with no dependency on the rest of the package."""
from __future__ import annotations

import re
from datetime import datetime, timezone

__all__ = ["clean_text", "utc_iso"]

_UTC = timezone.utc

#: Text from a scanned repo (commit subjects, ADR titles, file paths) is data,
#: not markup or control codes. Control characters, ANSI escapes and Unicode
#: bidi overrides are stripped before the text reaches any consumer — a
#: terminal, a report, JSON — so a hostile repo cannot inject an escape sequence
#: or a right-to-left override into an operator's view. Tab and newline survive.
#: HTML-escaping remains the web surface's job at its render boundary.
_CONTROL = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"          # ANSI CSI escape sequences
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC sequences (terminated by BEL or ST)
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"   # C0 controls except tab/newline, and DEL
    r"|[‪-‮⁦-⁩]"       # bidi embedding/override/isolate controls  # nosec B613 - the bidi chars ARE the sanitizer's strip-range; this is the defense, not a trojan
)


def clean_text(text: str) -> str:
    """Strip terminal-control and bidi-override sequences from untrusted text."""
    return _CONTROL.sub("", text)


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
