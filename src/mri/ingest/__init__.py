"""Reading agent session logs into the fusion tables.

One parser per agent tool, and a parser ships only for a format that has been
inspected on real data. A parser written against documentation, for a tool we
cannot test against, would produce attribution numbers nobody has verified —
and those numbers are the product.

Today that means Claude Code. Cursor and aider are deliberately absent.
"""
from __future__ import annotations

from mri.ingest.service import IngestResult, ingest_log, ingest_workspace

__all__ = ["IngestResult", "ingest_log", "ingest_workspace"]
