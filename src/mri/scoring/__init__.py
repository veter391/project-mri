"""Score composition.

How a set of analyzer scores becomes one number, and why that number is what it
is. This lives apart from the scanner because the scanner's job is orchestration
— and because the layer that decomposes a score into AI-authored, human-authored
and unattributed shares is a subsystem, not a static method on the conductor.

The rule this module exists to protect: every number explains itself. A composed
score always carries the ledger that produced it, and a share that cannot be
attributed is reported as unattributed rather than guessed.
"""
from __future__ import annotations

from dataclasses import dataclass

from mri.models.scan import AnalyzerRun

__all__ = ["Composition", "compose_overall"]


@dataclass(frozen=True)
class Composition:
    """A composed score together with the ledger that explains it."""

    value: float
    ledger: list[str]
    #: Analyzers that produced no score and so contributed nothing.
    unscored: list[str]

    @property
    def is_measured(self) -> bool:
        """False when nothing scored — the value is a placeholder, not a finding."""
        return bool(self.ledger)


#: Used when no analyzer produced a score. Deliberately mid-range and always
#: reported as unmeasured, so it can never read as a real assessment.
UNMEASURED_VALUE = 50.0


def compose_overall(
    runs: list[AnalyzerRun],
    weights: dict[str, float],
) -> Composition:
    """Combine analyzer scores into one weighted health value.

    Analyzers that failed or produced no score are excluded from the average
    rather than counted as zero: a crashed analyzer means "not measured", and
    scoring it as zero would silently turn a tooling failure into a bad verdict
    about the user's code.
    """
    scored = [r for r in runs if r.score is not None]
    unscored = [r.name for r in runs if r.score is None]

    if not scored:
        return Composition(value=UNMEASURED_VALUE, ledger=[], unscored=unscored)

    pairs = [(r, weights.get(r.name, 1.0)) for r in scored]
    total_weight = sum(w for _, w in pairs) or 1.0
    value = sum(r.score.value * w for r, w in pairs) / total_weight

    ledger = [
        f"{r.score.label} = {r.score.value} (weight {round(w / total_weight, 2)})"
        for r, w in pairs
    ]
    for name in unscored:
        ledger.append(f"{name} = not measured (excluded from the average)")

    return Composition(value=value, ledger=ledger, unscored=unscored)
