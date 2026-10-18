"""
Delayed ignition from actual ignition sources.

Purple Book 4.7.2 method A and Appendix 4.A, read from the book.

What this corrects
------------------
The PURPLE branch in ignition.py took delayed ignition as one minus
direct, so a release always ignited eventually and there was no
no-ignition outcome at all. That is not what the book says. It gives two
methods and both allow the cloud to escape ignition:

    A  actual ignition sources. "If only a few (weak) ignition sources
       are present, there is a probability that ignition of the cloud
       will not occur."
    B  free field. Ignition at maximum cloud area, and "if an LFL-contour
       is not present outside the establishment ... ignition is assumed
       not to take place."

and it assigns them: Societal Risk must use A; Individual Risk may use
either, decided by the competent authority. The version implemented
before was method B with the escape clause dropped, which is the most
conservative reading of the most conservative branch.

That mattered. The gap between the PURPLE and HYRAM schemes was a factor
of about fifty at the level of individual risk, and it was the single
largest divergence anywhere in the system. Some of it was this.

The model
---------
    P(t) = P_present (1 - exp(-omega t))                        (4.A.1)

with omega recovered from the tabulated one-minute probability:

    omega = -ln(1 - p_1min) / 60

Sources are independent, so the cloud escapes only if every one of them
fails to ignite it.

The book's own warning, carried
-------------------------------
"It should be noted, however, that the numbers are not well established
and should be used as a guideline." They are graded accordingly, and a
site with no sources entered gets a refusal rather than a probability of
zero: an empty source list means nobody has looked, not that there is
nothing there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from gating import Gated
from taxonomy import Grade, Provenance, TranscriptionSource


class SourceKind(str, Enum):
    POINT = "POINT"
    LINE = "LINE"
    AREA = "AREA"
    POPULATION = "POPULATION"


# Table 4.A.1, probability of ignition in one minute.
POINT_SOURCES = {
    "flare": 1.0,
    "outdoor furnace": 0.9,
    "electric train": 0.8,
    "ship": 0.5,
    "indoor furnace": 0.45,
    "outdoor boiler": 0.45,
    "motor vehicle": 0.4,
    "diesel train": 0.4,
    "ship transporting flammable materials": 0.3,
    "indoor boiler": 0.23,
    "fishing vessel": 0.2,
    "pleasure craft": 0.1,
}

LINE_SOURCES = {
    "transmission line": 0.2,          # per 100 m
}

AREA_SOURCES = {
    "chemical plant": 0.9,             # per site
    "oil refinery": 0.9,
    "heavy industry": 0.7,
}

POPULATION_SOURCES = {
    "residential": 0.01,               # per person
}

IGNITION_PROV = Provenance(
    source="Purple Book (CPR 18E) Appendix 4.A, Table 4.A.1",
    grade=Grade.PUBLISHED_UNVALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="The book states these numbers are not well established and are "
         "to be used as a guideline.",
    not_claimable_as=["a measured ignition probability"],
)


@dataclass(frozen=True)
class IgnitionSource:
    """One source, with what it is and where.

    p_one_minute overrides the table, for a source not in it. length_m
    applies to line sources at 0.2 per 100 m; population applies to
    population sources at 0.01 per person."""
    name: str
    kind: SourceKind
    x: float = 0.0
    y: float = 0.0
    p_present: float = 1.0
    p_one_minute: Optional[float] = None
    length_m: float = 0.0
    population: float = 0.0

    def one_minute_probability(self) -> float:
        if self.p_one_minute is not None:
            return min(max(self.p_one_minute, 0.0), 1.0)
        key = self.name.strip().lower()
        if self.kind is SourceKind.POINT:
            return POINT_SOURCES.get(key, 0.0)
        if self.kind is SourceKind.LINE:
            per_100 = LINE_SOURCES.get(key, 0.0)
            n = max(self.length_m, 0.0) / 100.0
            return 1.0 - (1.0 - per_100) ** n
        if self.kind is SourceKind.AREA:
            return AREA_SOURCES.get(key, 0.0)
        per_person = POPULATION_SOURCES.get(key, 0.01)
        return 1.0 - (1.0 - per_person) ** max(self.population, 0.0)

    def effectiveness(self) -> float:
        """omega, from the one-minute figure. A source that ignites with
        certainty in a minute has infinite effectiveness and is handled
        as such rather than by clamping the probability."""
        p = self.one_minute_probability()
        if p >= 1.0:
            return math.inf
        if p <= 0.0:
            return 0.0
        return -math.log(1.0 - p) / 60.0

    def probability(self, exposure_s: float) -> float:
        """P(t) = P_present (1 - exp(-omega t)), equation 4.A.1."""
        w = self.effectiveness()
        if w == math.inf:
            return self.p_present
        if w == 0.0 or exposure_s <= 0.0:
            return 0.0
        return self.p_present * (1.0 - math.exp(-w * exposure_s))

    def reached_by(self, cloud_radius_m: float,
                   source_x: float = 0.0, source_y: float = 0.0) -> bool:
        """Whether the flammable cloud reaches this source at all."""
        return math.hypot(self.x - source_x,
                          self.y - source_y) <= cloud_radius_m


@dataclass
class IgnitionSourceSet:
    sources: list[IgnitionSource] = field(default_factory=list)

    def delayed_probability(self, exposure_s: float,
                            cloud_radius_m: Optional[float] = None,
                            release_x: float = 0.0,
                            release_y: float = 0.0) -> Gated[float]:
        """Probability that at least one source ignites the cloud.

        Refused on an empty set. A site with no sources listed has not
        been surveyed; returning zero would turn that into a finding of
        no ignition hazard, which is the opposite of what it means."""
        if not self.sources:
            return Gated.refuse(
                "delayed_ignition_probability",
                "no ignition sources have been entered. Purple Book 4.7.2 "
                "method A needs the distribution of sources at and around "
                "the establishment; an empty list means the survey has not "
                "been done, not that there is nothing to ignite the cloud")
        in_reach = [s for s in self.sources
                    if cloud_radius_m is None
                    or s.reached_by(cloud_radius_m, release_x, release_y)]
        if not in_reach:
            return Gated.answer(
                "delayed_ignition_probability", 0.0,
                (f"the cloud reaches none of the {len(self.sources)} "
                 f"sources within {cloud_radius_m:.0f} m",))
        escape = 1.0
        for s in in_reach:
            escape *= (1.0 - s.probability(exposure_s))
        return Gated.answer(
            "delayed_ignition_probability", 1.0 - escape,
            (f"{len(in_reach)} of {len(self.sources)} sources reached; "
             f"Table 4.A.1 values are a guideline, not established",))

    def dominant(self, exposure_s: float) -> Optional[str]:
        if not self.sources:
            return None
        return max(self.sources,
                   key=lambda s: s.probability(exposure_s)).name


# --------------------------------------------------------------------------
# method B
# --------------------------------------------------------------------------

def free_field_delayed_probability(lfl_reaches_beyond_site: bool,
                                   ignited_at_site: bool = False
                                   ) -> Gated[float]:
    """Method B.

    Ignition at maximum cloud area if the cloud leaves the site. If the
    LFL contour does not reach beyond the establishment and nothing at the
    establishment ignites it, the book says ignition is assumed NOT to
    take place -- so even the free field method has a no-ignition
    outcome, which the earlier implementation dropped."""
    if ignited_at_site:
        return Gated.answer("delayed_ignition_probability", 1.0,
                            ("ignited at the establishment",))
    if lfl_reaches_beyond_site:
        return Gated.answer(
            "delayed_ignition_probability", 1.0,
            ("free field: ignition assumed at maximum LFL footprint AREA",))
    return Gated.answer(
        "delayed_ignition_probability", 0.0,
        ("no LFL contour beyond the establishment and no ignition at it, "
         "so 4.7.2 B assumes ignition does not take place",))


METHOD_ASSIGNMENT = (
    "Purple Book 4.7.2: Societal Risk is to be calculated with method A, "
    "actual ignition sources. Individual Risk may use either A or B, to "
    "be decided by the competent authorities. Using B for both, which is "
    "the simpler path, is not what the book says."
)

WHAT_WAS_WRONG = (
    "The PURPLE branch took delayed ignition as one minus direct, giving "
    "no no-ignition outcome at all. Neither method in the book says that. "
    "Method A allows the cloud to escape when sources are few or weak, "
    "and method B allows it when the LFL contour does not leave the site. "
    "Part of the factor of fifty between the two ignition schemes was "
    "this, not a disagreement about hydrogen."
)
