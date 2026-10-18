"""
Conditional ignition rates from recorded incidents.

HIAD 2.2, the European Hydrogen Incidents and Accidents Database, export
of 2026-01-01: 1,142 events collected by the EC Joint Research Centre.

Why this exists
---------------
The two ignition schemes in use disagree by a factor of seventy-nine at
the level of individual risk, and neither is founded on measurement. The
Purple Book values come from a 1990s Dutch hydrocarbon project and
hydrogen is absent from its reactivity table; the HyRAM values come from
a 2008 IEA white paper whose title is "Knowledge gaps in hydrogen
safety". Until now there was nothing empirical to set against either.

What the database gives, and what it does not
----------------------------------------------
It gives the CONDITIONAL rate: given that a release was recorded, was it
ignited. It cannot give a frequency, because there is no denominator --
no count of facility-years exposed. JRC says this directly: the goal of
serving quantitative risk assessment "could not be reached because of a
lack of required statistics", and the database "cannot be used to compare
hydrogen technologies with other technologies".

So these numbers bound and inform an ignition probability. They do not
replace one.

Reporting bias, and the direction it runs
------------------------------------------
An ignited release is more likely to be noticed, investigated and
recorded than one that dispersed quietly, so the raw rate is an upper
bound. The database's own quality grading shows this: the LH2 ignition
rate rises monotonically with quality grade, from 28.8% at Q=2 to 63.6%
at Q=5. Better documented events are more often ignited ones.

That is why these are reported as ranges over quality grade rather than
as point values, and why the LH2 to GH2 RATIO is the more robust
quantity: whatever bias applies, it applies to both.

The finding
-----------
Liquid hydrogen releases ignite about half as often as gaseous ones.
That holds at every quality grade, and it is the first hydrogen-specific,
phase-specific empirical figure available to this project.
"""

from __future__ import annotations

from dataclasses import dataclass

from taxonomy import Grade, Provenance, TranscriptionSource

HIAD_PROV = Provenance(
    source="HIAD 2.2, European Hydrogen Incidents and Accidents Database, "
           "European Commission Joint Research Centre, export 2026-01-01",
    grade=Grade.MEASURED,
    transcription=TranscriptionSource.REPORT,
    note="Conditional on a release having been recorded. There is no "
         "denominator of facility-years, so this is not a frequency. JRC "
         "states the database could not meet its goal of serving "
         "quantitative risk assessment for lack of statistics.",
    not_claimable_as=["an ignition frequency",
                      "an unbiased conditional probability"],
)


@dataclass(frozen=True)
class IgnitionRecord:
    label: str
    ignited: int
    unignited: int

    @property
    def n(self) -> int:
        return self.ignited + self.unignited

    @property
    def rate(self) -> float:
        return self.ignited / self.n if self.n else float("nan")


# Whole database, 1,142 events: 753 ignited, 277 unignited, 110 with no
# release and 2 unspecified.
ALL = IgnitionRecord("all media", 753, 277)

# By storage medium. Two spellings of the gaseous category are combined.
LH2 = IgnitionRecord("liquid hydrogen", 61, 111)
GH2 = IgnitionRecord("gaseous hydrogen", 544, 145)

# By quality grade, liquid hydrogen only. The trend is the evidence of
# reporting bias and is kept rather than averaged away.
LH2_BY_QUALITY = {
    5: IgnitionRecord("LH2 Q=5", 7, 4),
    4: IgnitionRecord("LH2 Q=4", 8, 10),
    3: IgnitionRecord("LH2 Q=3", 27, 50),
    2: IgnitionRecord("LH2 Q=2", 19, 47),
}
GH2_HIGH_QUALITY = IgnitionRecord("GH2 Q>=4", 155, 47)
LH2_HIGH_QUALITY = IgnitionRecord("LH2 Q>=4", 15, 14)

# Events whose title, description or component list mentions a vent
# stack, vent line, relief valve, rupture disc, burst disc, safety valve
# or pressure relief.
VENT_RELATED = IgnitionRecord("vent and relief paths", 86, 56)
VENT_RELATED_LH2 = IgnitionRecord("vent and relief paths, LH2", 26, 33)

# Events mentioning vacuum, insulation, Dewar or jacket.
VACUUM_RELATED = IgnitionRecord("vacuum and insulation", 46, 24)


def lh2_range() -> tuple[float, float]:
    """Lowest and highest LH2 rate across quality grades.

    28.8% to 63.6%. A point estimate would hide that the spread is
    systematic rather than random."""
    rs = [r.rate for r in LH2_BY_QUALITY.values()]
    return min(rs), max(rs)


def lh2_over_gh2(high_quality: bool = False) -> float:
    """The robust quantity. Whatever reporting bias applies, it applies
    to both phases, so the ratio survives it better than either rate."""
    if high_quality:
        return LH2_HIGH_QUALITY.rate / GH2_HIGH_QUALITY.rate
    return LH2.rate / GH2.rate


# --------------------------------------------------------------------------
# what this says about the two schemes
# --------------------------------------------------------------------------

SCHEME_COMPARISON = {
    "HYRAM smallest band (<0.125 kg/s)": 0.012,
    "HYRAM middle band (0.125-6.25 kg/s)": 0.080,
    "HYRAM largest band (>6.25 kg/s)": 0.350,
    "PURPLE method A, quiet site": 0.280,
    "PURPLE free field bound": 1.000,
    "HIAD, liquid hydrogen, all grades": LH2.rate,
    "HIAD, liquid hydrogen, Q>=4": LH2_HIGH_QUALITY.rate,
    "HIAD, gaseous hydrogen": GH2.rate,
}

VERDICT = """
The recorded LH2 rate of 0.355 lands almost exactly on HyRAM's largest
band, 0.350, and close to the Purple Book method A value for a quiet site,
0.280. It is nowhere near the free field bound of 1.000, which the Purple
Book branch reaches only because that branch drops the escape clause the
book actually gives.

But the same database puts GASEOUS hydrogen at 0.790, more than twice as
high, and HyRAM applies the same rate-dependent table to both. So the
agreement at the largest band is not evidence that HyRAM's rate
dependence is right; it is evidence that a rate-independent LH2 figure
happens to sit where HyRAM's largest band does.

What survives is the phase difference: liquid hydrogen releases ignite
about half as often as gaseous ones, at every quality grade. Neither
scheme in use represents that, because both are indexed on release rate
alone.
"""

# --------------------------------------------------------------------------
# reporting alongside, not substituting
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SchemeCheck:
    """What a chosen ignition scheme gives, set beside what was recorded.

    Deliberately NOT a correction. Multiplying a scheme's absolute
    probability by the recorded LH2-to-GH2 ratio would assume the rate
    dependence is the same in both phases, and nothing here tests that.
    The recorded figures are also conditional on a release having been
    reported, so they are not the same kind of quantity as a scheme's
    probability and cannot replace one.

    What this does is put the two side by side so that a scheme sitting
    outside the recorded range is visible rather than silently used."""
    scheme: str
    scheme_probability: float
    recorded_low: float
    recorded_high: float
    medium: str

    @property
    def within_recorded_range(self) -> bool:
        return self.recorded_low <= self.scheme_probability <= self.recorded_high

    @property
    def ratio_to_midpoint(self) -> float:
        mid = 0.5 * (self.recorded_low + self.recorded_high)
        return self.scheme_probability / mid if mid > 0 else float("inf")

    def statement(self) -> str:
        where = ("inside" if self.within_recorded_range else
                 "ABOVE" if self.scheme_probability > self.recorded_high
                 else "BELOW")
        return (f"{self.scheme} gives {self.scheme_probability:.3f}; "
                f"HIAD records {self.recorded_low:.3f} to "
                f"{self.recorded_high:.3f} for {self.medium}, so the "
                f"scheme sits {where} the recorded range "
                f"({self.ratio_to_midpoint:.2f}x its midpoint)")


def check_scheme(scheme_name: str, p_ignited: float,
                 medium: str = "LH2") -> SchemeCheck:
    """Set a computed ignition probability beside the recorded range.

    The range is over quality grade, which is where the reporting bias
    shows itself, rather than a confidence interval."""
    if medium.upper() == "LH2":
        lo, hi = lh2_range()
    else:
        lo = hi = GH2.rate
    return SchemeCheck(scheme_name, p_ignited, lo, hi, medium.upper())


WHY_NOT_A_CORRECTION = (
    "The obvious move is to scale a scheme by the recorded LH2-to-GH2 "
    "ratio of 0.45. It is not done, for two reasons. The ratio is between "
    "quantities conditional on a release being REPORTED, and a scheme's "
    "probability is conditional on a release OCCURRING; those differ by "
    "whatever fraction of releases go unrecorded, which is unknown and "
    "differs by phase. And applying a single ratio assumes the rate "
    "dependence is the same in both phases, which nothing here tests. "
    "Reporting both is honest; combining them would manufacture a number "
    "with no defensible basis."
)

RELEASES_THAT_DID_NOT_IGNITE = [
    (145_000, "hydrogen leak delaying a rocket launch"),
    (55_000, "LH2 tank cracking"),
    (4_425, "release from an LH2 tanker"),
    (4_291, "release from an LH2 tanker"),
    (4_082, "release from an LH2 trailer"),
    (3_888, "pressure increase in an LH2 tanker"),
    (3_880, "over-pressurisation of an LH2 tanker"),
]

LARGE_UNIGNITED_NOTE = (
    "The largest recorded unignited LH2 release is 145 tonnes. A model "
    "that takes ignition as certain above some release rate has to "
    "account for that, and the free field branch of the Purple Book, "
    "read without its escape clause, does not."
)
