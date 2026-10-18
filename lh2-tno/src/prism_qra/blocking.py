"""
Blocking systems.

Purple Book 4.4.1, read from the book. Replaces a bare `isolation_time_s`
whose default of 30 s was shorter than any grade the book defines and had
no source.

Two ways of crediting isolation, and they must not be combined
---------------------------------------------------------------
The Purple Book credits a blocking system by SHORTENING THE RELEASE: the
valves take two, ten or thirty minutes to close depending on how they are
operated, and the released mass is whatever comes out in that time. Its
failure on demand is 0.001 for an automatic system and 0.01 otherwise, so
the system almost always works and the credit is in the duration.

HyRAM credits it by REMOVING THE OUTCOME: a probability of successful
detection and isolation of 0.9 multiplies the whole event away, and the
0.1 that remains proceeds as if nothing had been isolated at all.

These are alternative accountings of the same barrier, not independent
ones. This pipeline computes released mass as rate times isolation time,
which is the Purple route, so applying HyRAM's 0.9 on top would credit
the same valves twice and drop the risk by a further order of magnitude
for no physical reason. The two are therefore offered as a choice, with
the Purple route as the default because it is the one the released-mass
calculation already implements.

What the failure branch means
-----------------------------
Failure on demand does not mean the release stops at the closing time; it
means it does not stop at all and runs to inventory. Both branches are
enumerated rather than the successful one alone, because a 0.001 branch
that empties the vessel is not always negligible against a 0.999 branch
that empties a fraction of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from taxonomy import Grade, Provenance, TranscriptionSource


class BlockingSystem(str, Enum):
    NONE = "NONE"
    AUTOMATIC = "AUTOMATIC"
    REMOTE = "REMOTE"
    HAND = "HAND"


@dataclass(frozen=True)
class BlockingSpec:
    """Closing time and failure on demand, Purple Book 4.4.1.

    The book presents these as guidelines to be used when the system has
    not been analysed, and says the effect should properly be determined
    by an event tree with the failure on demand considered."""
    kind: BlockingSystem
    closing_time_s: float
    failure_on_demand: float
    description: str


# Table values from 4.4.1. An automatic detection system of sufficient
# sensitivity, with monitors covering all wind directions, is assumed in
# every case; only the closure differs.
BLOCKING_DEFAULTS: dict[BlockingSystem, BlockingSpec] = {
    BlockingSystem.AUTOMATIC: BlockingSpec(
        BlockingSystem.AUTOMATIC, 120.0, 0.001,
        "detection and closure fully automatic, no operator action"),
    BlockingSystem.REMOTE: BlockingSpec(
        BlockingSystem.REMOTE, 600.0, 0.01,
        "automatic detection, operator validates and closes from the "
        "control room"),
    BlockingSystem.HAND: BlockingSpec(
        BlockingSystem.HAND, 1800.0, 0.01,
        "automatic detection, operator validates, walks to the valves and "
        "closes them by hand"),
    BlockingSystem.NONE: BlockingSpec(
        BlockingSystem.NONE, float("inf"), 1.0,
        "no blocking system; the release runs to inventory"),
}

BLOCKING_PROV = Provenance(
    source="Purple Book (CPR 18E) 4.4.1",
    grade=Grade.PUBLISHED_VALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="Guideline values, to be used where the blocking system has not "
         "been analysed. The book asks for an event tree with the failure "
         "on demand considered where it has.",
    not_claimable_as=["an analysed blocking system performance"],
)


@dataclass(frozen=True)
class IsolationBranch:
    """One branch of the blocking event tree."""
    succeeded: bool
    probability: float
    isolation_time_s: float


def branches(kind: BlockingSystem = BlockingSystem.AUTOMATIC,
             spec: Optional[BlockingSpec] = None) -> list[IsolationBranch]:
    """Both branches, so the failure case is enumerated rather than
    assumed negligible.

    On failure the release is not shortened at all: it runs until the
    inventory is gone, which the released-mass calculation handles by
    taking the inventory as the binding constraint."""
    s = spec or BLOCKING_DEFAULTS[kind]
    if s.failure_on_demand >= 1.0:
        return [IsolationBranch(False, 1.0, float("inf"))]
    return [
        IsolationBranch(True, 1.0 - s.failure_on_demand, s.closing_time_s),
        IsolationBranch(False, s.failure_on_demand, float("inf")),
    ]


DOUBLE_COUNTING_WARNING = (
    "HyRAM applies a probability of successful detection and isolation of "
    "0.9 that removes the outcome entirely, where the Purple Book credits "
    "the same barrier by shortening the release. This pipeline computes "
    "released mass from an isolation time, which is the Purple route, so "
    "the HyRAM factor must NOT also be applied: it would credit the same "
    "valves twice and drop the risk by a further order of magnitude."
)

WHAT_WAS_WRONG = (
    "An isolation time of 30 s stood as the default. The Purple Book's "
    "fastest grade, a fully automatic system needing no operator, closes "
    "in 120 s. The default was four times more optimistic than the best "
    "case the book recognises, and had no source."
)
