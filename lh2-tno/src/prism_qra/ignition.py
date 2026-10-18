"""
Ignition event trees for flammable releases.

Purple Book 6.2.4 and 4.7-4.8. The tree turns one loss of containment into
a set of mutually exclusive outcomes, each with a conditional probability
Pi, so that the risk layer can weight them:

    f(S, M, phi, i) = fS * PM * Pphi * Pi                        (6.5)

The conditional probabilities must sum to one over the outcomes of a
release. Red Book 10.4 states this closure explicitly as the check on an
event tree, and it is enforced here rather than assumed.

Two ignition probability schemes
--------------------------------
They disagree by more than an order of magnitude for hydrogen, so neither
is applied silently.

  PURPLE   Table 4.5 for stationary installations. Hydrogen is absent from
           the Table 4.7 reactivity list; the book's own rule is that a
           substance with little information is classified as HIGH
           reactive, which selects the 0.2 / 0.5 / 0.7 column. Delayed
           ignition for stationary units is (1 - direct), so a release
           always ignites eventually: there is no no-ignition branch.
           Section 3.5.3 additionally notes that a HIGHER direct ignition
           probability may be considered for hydrogen because its minimum
           ignition energy is low.

  HYRAM    Hydrogen-specific values from the Sandia toolkit, roughly an
           order of magnitude lower, and with a genuine no-ignition
           branch. Read from the software rather than its report; treated
           as a cross-check, not as a source.

Choosing between them changes the result by more than any model in the
chain, so IgnitionResult records which was used.

Post-ignition split (4.8)
-------------------------
Ignition of an unconfined vapour cloud is modelled as either a pure flash
fire with no pressure effects (0.6) or a pure explosion with no flash fire
effects (0.4). The explosion uses multi-energy at blast strength 10 with
a default obstructed mass fraction of 0.08.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

P_ATM = 101325.0


class Outcome(str, Enum):
    JET_FIRE = "JET_FIRE"
    POOL_FIRE = "POOL_FIRE"
    BLEVE = "BLEVE"
    FLASH_FIRE = "FLASH_FIRE"
    EXPLOSION = "EXPLOSION"
    NO_IGNITION = "NO_IGNITION"


class ReleaseType(str, Enum):
    CONTINUOUS = "CONTINUOUS"
    INSTANTANEOUS = "INSTANTANEOUS"


class Reactivity(str, Enum):
    LOW = "LOW"
    AVERAGE_HIGH = "AVERAGE_HIGH"
    K1_LIQUID = "K1_LIQUID"


class IgnitionScheme(str, Enum):
    PURPLE = "PURPLE"          # 4.7.2 B with the escape clause dropped
    PURPLE_SOURCES = "PURPLE_SOURCES"   # 4.7.2 A, actual ignition sources
    HYRAM = "HYRAM"


# --------------------------------------------------------------------------
# direct ignition probability
# --------------------------------------------------------------------------

# Purple Book Table 4.5, stationary installations.
# rows: < 10 kg/s (< 1000 kg) | 10-100 kg/s (1e3-1e4 kg) | > 100 kg/s (> 1e4 kg)
_PURPLE_DIRECT = {
    Reactivity.K1_LIQUID:    [0.065, 0.065, 0.065],
    Reactivity.LOW:          [0.02, 0.04, 0.09],
    Reactivity.AVERAGE_HIGH: [0.2, 0.5, 0.7],
}

# HyRAM+ hydrogen defaults, thresholds in kg/s.
_HYRAM_THRESHOLDS = [0.125, 6.25]
_HYRAM_IMMEDIATE = [0.008, 0.053, 0.23]
_HYRAM_DELAYED = [0.004, 0.027, 0.12]


def _purple_band(release: ReleaseType, magnitude: float) -> int:
    if release is ReleaseType.CONTINUOUS:
        return 0 if magnitude < 10.0 else (1 if magnitude <= 100.0 else 2)
    return 0 if magnitude < 1000.0 else (1 if magnitude <= 10000.0 else 2)


def _hyram_band(rate_kg_s: float) -> int:
    if rate_kg_s < _HYRAM_THRESHOLDS[0]:
        return 0
    return 1 if rate_kg_s < _HYRAM_THRESHOLDS[1] else 2


@dataclass(frozen=True)
class IgnitionProbabilities:
    direct: float
    delayed_given_no_direct: float
    scheme: IgnitionScheme
    band: int
    note: str


def ignition_probabilities(
        scheme: IgnitionScheme,
        release: ReleaseType,
        magnitude: float,
        reactivity: Reactivity = Reactivity.AVERAGE_HIGH,
        delayed_conditional: Optional[float] = None,
) -> IgnitionProbabilities:
    """magnitude is kg/s for a continuous release, kg for an instantaneous one.

    delayed_conditional supplies P(delayed | no direct) from an external
    calculation, which is how method A enters: the probability then
    depends on what ignition sources the cloud actually reaches, not on
    an assumption that it always finds one."""
    if not math.isfinite(magnitude) or magnitude < 0.0:
        raise ValueError("release magnitude must be finite and non-negative")
    if (delayed_conditional is not None
            and (not math.isfinite(delayed_conditional)
                 or not 0.0 <= delayed_conditional <= 1.0)):
        raise ValueError("delayed ignition probability must be between 0 and 1")
    if scheme is IgnitionScheme.PURPLE_SOURCES:
        b = _purple_band(release, magnitude)
        p_d = _PURPLE_DIRECT[reactivity][b]
        if delayed_conditional is None:
            raise ValueError(
                "PURPLE_SOURCES is Purple Book 4.7.2 method A and needs the "
                "delayed ignition probability computed from the actual "
                "ignition sources. Pass delayed_conditional, or choose "
                "PURPLE for the free field reading.")
        return IgnitionProbabilities(
            direct=p_d,
            delayed_given_no_direct=delayed_conditional,
            scheme=scheme, band=b,
            note=("Table 4.5 for direct ignition; delayed ignition from "
                  "Appendix 4.A with the site's own sources. The book "
                  "requires this method for Societal Risk and leaves the "
                  "choice to the authority for Individual Risk."))
    if scheme is IgnitionScheme.PURPLE:
        b = _purple_band(release, magnitude)
        p_d = _PURPLE_DIRECT[reactivity][b]
        return IgnitionProbabilities(
            direct=p_d, delayed_given_no_direct=1.0,
            scheme=scheme, band=b,
            note=("Table 4.5 for direct ignition. Delayed ignition taken "
                  "as (1 - direct), which is method B read WITHOUT its "
                  "escape clause: 4.7.2 B says that if the LFL contour "
                  "does not leave the establishment and nothing there "
                  "ignites it, ignition is assumed not to take place. "
                  "This branch is therefore the most conservative reading "
                  "available and is kept as a sensitivity bound, not as "
                  "the recommended calculation. Hydrogen is absent from "
                  "the Table 4.7 reactivity list and defaults to HIGH; "
                  "3.5.3 invites a value above the table for hydrogen."))
    b = _hyram_band(magnitude)
    p_d = _HYRAM_IMMEDIATE[b]
    p_del = _HYRAM_DELAYED[b]
    return IgnitionProbabilities(
        direct=p_d, delayed_given_no_direct=p_del / max(1.0 - p_d, 1e-12),
        scheme=scheme, band=b,
        note=("HyRAM+ hydrogen defaults; delayed probability is absolute in "
              "the source and is converted to a conditional here. Read from "
              "software, not from its report."))


# --------------------------------------------------------------------------
# post-ignition split (4.8) and BLEVE (4.7.1)
# --------------------------------------------------------------------------

P_FLASH_FIRE = 0.6      # pure flash fire, no pressure effects
P_EXPLOSION = 0.4       # pure explosion, no flash fire effects
P_BLEVE_STATIONARY = 0.7
P_BLEVE_TRANSPORT_IN_ESTABLISHMENT = 1.0
F_OBSTRUCTED_DEFAULT = 0.08


def multi_energy_radii(combustion_energy_j: float,
                       f_obstructed: float = F_OBSTRUCTED_DEFAULT
                       ) -> tuple[float, float]:
    """Equations 4.5 and 4.6: distances to 0.3 barg and 0.1 barg, from the
    multi-energy method at blast strength 10.

    Purple Book 5.2.4 restricts the lethality attached to these contours to
    vapour cloud explosion and excludes detonation, on the grounds that the
    blast duration differs. Hydrogen DDT sits outside that restriction, so
    the radii may be computed while the lethality attached to them may not
    be claimed."""
    scaled = (f_obstructed * combustion_energy_j / P_ATM) ** (1.0 / 3.0)
    return 1.5 * scaled, 3.0 * scaled


def vapour_cloud_mass_fraction(flash_fraction: float) -> float:
    """Table 4.8: fraction of tank inventory in the vapour cloud after an
    instantaneous release with direct ignition."""
    x = flash_fraction
    if x < 0.1:
        return min(2.0 * x, 1.0)
    if x < 0.36:
        return (0.8 * x - 0.028) / 0.26
    return 1.0


# --------------------------------------------------------------------------
# the tree
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class IgnitionEvent:
    outcome: Outcome
    probability: float
    path: str


@dataclass(frozen=True)
class IgnitionResult:
    events: tuple[IgnitionEvent, ...]
    probabilities: IgnitionProbabilities
    release: ReleaseType
    closure_error: float

    def by_outcome(self, outcome: Outcome) -> float:
        return sum(e.probability for e in self.events if e.outcome is outcome)

    @property
    def p_ignited(self) -> float:
        return 1.0 - self.by_outcome(Outcome.NO_IGNITION)


def build_ignition_tree(
        release: ReleaseType,
        magnitude: float,
        scheme: IgnitionScheme = IgnitionScheme.PURPLE,
        reactivity: Reactivity = Reactivity.AVERAGE_HIGH,
        p_bleve: float = P_BLEVE_STATIONARY,
        forms_pool: bool = False,
        tolerance: float = 1e-9,
        delayed_conditional: Optional[float] = None,
) -> IgnitionResult:
    """Conditional probabilities of each outcome, given the release.

    Continuous release
        direct ignition            -> jet fire (and pool fire if a pool forms)
        delayed ignition           -> flash fire 0.6 / explosion 0.4
        neither                    -> no ignition

    Instantaneous release
        direct ignition            -> BLEVE with p_bleve, otherwise the cloud
                                      burns as flash fire / explosion
        delayed ignition           -> flash fire 0.6 / explosion 0.4
    """
    if not math.isfinite(magnitude) or magnitude < 0.0:
        raise ValueError("release magnitude must be finite and non-negative")
    if not math.isfinite(p_bleve) or not 0.0 <= p_bleve <= 1.0:
        raise ValueError("p_bleve must be between 0 and 1")
    p = ignition_probabilities(scheme, release, magnitude, reactivity,
                               delayed_conditional)
    pd, pdel = p.direct, p.delayed_given_no_direct
    ev: list[IgnitionEvent] = []

    if release is ReleaseType.CONTINUOUS:
        if forms_pool:
            # A liquid-source jet and its burn-back are simultaneous, not
            # mutually exclusive events with an evidenceless 50:50 split.
            # The implemented LH2 burn-back field is the conservative union
            # surrogate and carries the whole direct-ignition probability.
            ev.append(IgnitionEvent(Outcome.POOL_FIRE, pd,
                                    "direct/liquid fire"))
        else:
            ev.append(IgnitionEvent(Outcome.JET_FIRE, pd, "direct"))
    else:
        ev.append(IgnitionEvent(Outcome.BLEVE, pd * p_bleve, "direct/BLEVE"))
        rest = pd * (1.0 - p_bleve)
        ev.append(IgnitionEvent(Outcome.FLASH_FIRE, rest * P_FLASH_FIRE,
                                "direct/no BLEVE/flash"))
        ev.append(IgnitionEvent(Outcome.EXPLOSION, rest * P_EXPLOSION,
                                "direct/no BLEVE/explosion"))

    p_delayed = (1.0 - pd) * pdel
    ev.append(IgnitionEvent(Outcome.FLASH_FIRE, p_delayed * P_FLASH_FIRE,
                            "delayed/flash"))
    ev.append(IgnitionEvent(Outcome.EXPLOSION, p_delayed * P_EXPLOSION,
                            "delayed/explosion"))

    p_none = (1.0 - pd) * (1.0 - pdel)
    if p_none > tolerance:
        ev.append(IgnitionEvent(Outcome.NO_IGNITION, p_none, "no ignition"))

    total = sum(e.probability for e in ev)
    err = abs(total - 1.0)
    if err > 1e-6:
        raise ValueError(f"event tree does not close: sum(Pi) = {total:.9f}")

    return IgnitionResult(tuple(e for e in ev if e.probability > 0.0),
                          p, release, err)


# --------------------------------------------------------------------------
# free field rule for Individual Risk  (4.7.2 B, 6.2.4.2)
# --------------------------------------------------------------------------

FREE_FIELD_RULE = (
    "Individual Risk is calculated free field (method B): if the cloud is "
    "not ignited at the establishment, ignition is placed at maximum cloud "
    "extent, defined as the maximum AREA of the LFL footprint. The maximum "
    "mass within LFL is deliberately not used, because that definition "
    "would make an instantaneous release ignite at the source."
)
