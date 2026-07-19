"""Models for the fusion layers: sessions, authorship, decisions, consequences.

These mirror the tables in migration 0002 and repeat their guarantees in Python,
so a caller building a record in memory fails at construction rather than at
INSERT. The database is the last line of defence, not the only one.

The guarantees worth naming:

* An authorship split always accounts for the whole file, and `unattributed` is
  a first-class share. Not knowing is an answer this model can express.
* A consequence declares what kind of claim it makes and defaults to
  `correlation`. Nothing produces `causation` by accident.
* Session content is optional everywhere. Metadata-only ingest is a supported
  state, not a degraded one, because reading agent logs is opt-in and redactable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "AuthorshipShare",
    "Consequence",
    "Decision",
    "Session",
    "SessionEvent",
    "SessionFileTouch",
]


class Session(BaseModel):
    """One agent coding session, as recorded by the tool that produced it."""

    id: int | None = None
    #: claude_code, cursor, aider, git_notes, ...
    source: str
    #: The originating tool's own id, so re-ingesting the same log is idempotent.
    external_id: str
    #: The project this session belongs to. None until linked; a session with no
    #: project is evidence for no project's risk — the conservative default.
    project_id: int | None = None
    workspace_path: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    #: Whether turn content was retained, or only metadata.
    content_stored: bool = False
    created_at: datetime | None = None


class SessionEvent(BaseModel):
    """A single turn within a session."""

    id: int | None = None
    session_id: int
    #: Position in the session; ordering must not depend on equal timestamps.
    seq: int
    role: Literal["user", "assistant", "tool", "system"]
    kind: str = "message"
    #: None when running metadata-only. An empty string would assert the turn
    #: had no content, which is a different statement.
    content: str | None = None
    #: Always present, so turns can be correlated and deduplicated without
    #: retaining what was said.
    content_hash: str = ""
    occurred_at: datetime | None = None
    created_at: datetime | None = None


class SessionFileTouch(BaseModel):
    """A file a session read or wrote, and how sure we are of the link."""

    id: int | None = None
    session_id: int
    #: The project the touched file belongs to, denormalised from the session so
    #: file-path lookups scope with one indexed predicate instead of a join.
    project_id: int | None = None
    event_id: int | None = None
    file_path: str
    #: None until the touch is tied to a commit. A session edits files long
    #: before they are committed, and may never commit them.
    commit_sha: str | None = None
    touch_kind: Literal["read", "write", "create", "delete"]
    #: Correlating a log with a working tree is inference, never observation.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    occurred_at: datetime | None = None
    created_at: datetime | None = None


class AuthorshipShare(BaseModel):
    """How a file's content divides between AI, human, and unknown."""

    id: int | None = None
    #: The project this file belongs to, so shares scope per project like touches.
    project_id: int | None = None
    file_path: str
    commit_sha: str | None = None
    share_ai: float = Field(default=0.0, ge=0.0, le=100.0)
    share_human: float = Field(default=0.0, ge=0.0, le=100.0)
    #: The share we cannot attribute. Defaulting to 100 means a record created
    #: with no evidence claims nothing, rather than claiming human authorship.
    share_unattributed: float = Field(default=100.0, ge=0.0, le=100.0)
    #: How the split was derived, so a reader can judge it.
    method: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    computed_at: datetime | None = None
    created_at: datetime | None = None

    @model_validator(mode="after")
    def _shares_account_for_everything(self) -> AuthorshipShare:
        total = self.share_ai + self.share_human + self.share_unattributed
        if abs(total - 100.0) >= 0.01:
            raise ValueError(
                f"authorship shares must sum to 100, got {total:.2f} "
                f"(ai={self.share_ai}, human={self.share_human}, "
                f"unattributed={self.share_unattributed}). A share that is not "
                f"known belongs in `unattributed`, not dropped."
            )
        return self


class Decision(BaseModel):
    """Something that was decided, and — where recoverable — why."""

    id: int | None = None
    summary: str
    #: None when the "why" could not be recovered. A decision mined from a bare
    #: commit has a clear what and no rationale, and inventing one is the exact
    #: failure this record exists to prevent.
    rationale: str | None = None
    source: Literal["adr", "session", "commit", "issue", "manual"]
    source_ref: str = ""
    session_id: int | None = None
    #: The project this decision belongs to. None for a decision not tied to a
    #: scanned project — which is then a confounder for no project's metric.
    project_id: int | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    decided_at: datetime | None = None
    #: Lifecycle of the decision where it has one — an ADR's Accepted/Superseded.
    #: None for a decision (like a commit's) that has no such state; an empty
    #: string would claim it does.
    status: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime | None = None


class Consequence(BaseModel):
    """A measured change that followed a decision or a session.

    Followed. Not caused by — unless someone can justify the stronger word, in
    which case they must say so explicitly.
    """

    id: int | None = None
    decision_id: int | None = None
    session_id: int | None = None
    metric: str
    file_path: str | None = None
    window_start: datetime
    window_end: datetime
    baseline_value: float | None = None
    observed_value: float | None = None
    delta: float | None = None
    causal_claim: Literal["correlation", "causation", "none"] = "correlation"
    #: Alternative explanations considered, as a list. Empty means none were,
    #: which is itself worth reporting.
    confounders: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime | None = None

    @model_validator(mode="after")
    def _must_be_attached_to_something(self) -> Consequence:
        if self.decision_id is None and self.session_id is None:
            raise ValueError(
                "a consequence needs a decision or a session to be about; "
                "an unattached measurement is not a consequence of anything"
            )
        return self
