"""
Evaluation and management -- what the numbers mean and what to do.

Steps 0 to 4 answer "how much". This answers "so what", and it is a
different kind of question with a different kind of answer. The boundary
matters: importance measures are calculation, acceptance is judgement, and
a system that walks across that line without saying so has started making
decisions on someone's behalf.

    calculation   ranking scenarios by risk contribution
                  Fussell-Vesely, Birnbaum, RAW, RRW
                  the risk reduction a given change would produce
    judgement     whether a risk level is acceptable
                  which measure to take, and whether to take any

So the acceptance test reports a verdict against a stated criterion and
names the criterion; it does not conclude that a plant is safe.

Two carried-over cautions
-------------------------
A risk computed from a partially evaluated set is a lower bound, so an
ACCEPTABLE verdict on incomplete coverage means "not shown to exceed",
never "shown not to exceed". The verdict carries that distinction.

Importance measures divide by the total risk, so they inherit whatever the
total was missing. Ranking is more robust than the individual values, and
that is how it is presented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Optional, Sequence

import numpy as np

from gating import Coverage
from risk import RiskContribution, dutch_sr_limit
from uncertainty import Interval, NOT_PROPAGATED


# --------------------------------------------------------------------------
# acceptance
# --------------------------------------------------------------------------

class Verdict(str, Enum):
    WITHIN = "WITHIN"
    EXCEEDS = "EXCEEDS"
    NOT_SHOWN_TO_EXCEED = "NOT_SHOWN_TO_EXCEED"   # partial coverage
    STRADDLES = "STRADDLES"                       # interval spans the limit
    NO_CRITERION = "NO_CRITERION"


@dataclass(frozen=True)
class AcceptanceResult:
    verdict: Verdict
    value: float
    criterion: float
    criterion_name: str
    margin: float
    caveat: str = ""

    def statement(self) -> str:
        return (f"{self.value:.3e} against {self.criterion_name} "
                f"({self.criterion:.0e}): {self.verdict.value}"
                + (f" -- {self.caveat}" if self.caveat else ""))


# Purple Book 6.3. These are the Dutch policy limits, quoted as the
# criterion they are; another jurisdiction sets different ones, and a
# system that hard-codes one country's policy as "the" threshold is making
# a political choice silently.
IR_LIMIT_EXISTING = 1e-5
IR_LIMIT_NEW = 1e-6
CRITERION_SOURCE = "Purple Book 6.3, Dutch establishment limits"


def check_individual_risk(max_ir: float, coverage: Optional[Coverage] = None,
                          criterion: float = IR_LIMIT_NEW,
                          criterion_name: str = "IR limit, new situations",
                          interval: Optional[Interval] = None
                          ) -> AcceptanceResult:
    """A verdict against a stated criterion.

    When an uncertainty interval is supplied and it straddles the limit,
    the verdict is STRADDLES: the point estimate falls on one side, but
    the data does not distinguish the two sides. Reporting WITHIN in that
    case would let a rounding of the input decide a compliance question."""
    partial = coverage is not None and not coverage.complete

    # The interval decides when it exists, and the point estimate only
    # when it does not. Ordering these the other way round produced a
    # WITHIN verdict on a case whose whole interval sat above the limit:
    # the point estimate was 7.2e-6 against a limit of 1e-5, while the
    # 5th percentile was 2.3e-5. Compliance was being read off a number
    # the data did not support.
    if interval is not None and interval.samples > 0:
        if interval.p05 > criterion:
            v = Verdict.EXCEEDS
        elif interval.p95 < criterion:
            v = (Verdict.NOT_SHOWN_TO_EXCEED if partial else Verdict.WITHIN)
        else:
            v = Verdict.STRADDLES
    elif max_ir > criterion:
        v = Verdict.EXCEEDS          # exceeding a lower bound still exceeds
    elif partial:
        v = Verdict.NOT_SHOWN_TO_EXCEED
    else:
        v = Verdict.WITHIN
    caveat = ""
    if partial:
        caveat = (f"only {coverage.evaluated_fraction*100:.1f}% of enumerated "
                  f"frequency was evaluated, so this is a lower bound")
    if interval is not None:
        n = interval.significant_figures()
        extra = (f"frequency uncertainty alone gives "
                 f"[{interval.p05:.2g}, {interval.p95:.2g}], a factor of "
                 f"{interval.span:,.0f}; the point estimate supports "
                 f"{n} significant figure{'s' if n != 1 else ''}")
        caveat = f"{caveat}; {extra}" if caveat else extra
    return AcceptanceResult(v, max_ir, criterion, criterion_name,
                            margin=criterion / max_ir if max_ir > 0 else math.inf,
                            caveat=caveat)


def check_societal_risk(n: np.ndarray, f: np.ndarray) -> AcceptanceResult:
    """FN curve against F < 1e-3 * N^-2 for N >= 10."""
    mask = np.asarray(n) >= 10.0
    if not mask.any():
        return AcceptanceResult(Verdict.NO_CRITERION, 0.0, 0.0,
                                "Dutch SR limit line", math.inf,
                                "no outcome reaches 10 fatalities")
    lim = dutch_sr_limit(np.asarray(n)[mask])
    ratio = np.asarray(f)[mask] / lim
    i = int(np.argmax(ratio))
    worst = float(ratio[i])
    return AcceptanceResult(
        Verdict.EXCEEDS if worst > 1.0 else Verdict.WITHIN,
        float(np.asarray(f)[mask][i]), float(lim[i]),
        "Dutch SR limit line", 1.0 / worst if worst > 0 else math.inf,
        caveat=f"binding at N = {float(np.asarray(n)[mask][i]):.0f}")


# --------------------------------------------------------------------------
# importance measures
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Importance:
    key: str
    contribution: float
    fussell_vesely: float     # share of total risk this accounts for
    rrw: float                # risk reduction worth: total / (total - this)
    raw: float                # risk achievement worth, needs a failed case
    rank: int = 0


def importance_by(contributions: Sequence[RiskContribution],
                  key: Callable[[RiskContribution], str]
                  ) -> list[Importance]:
    """Fussell-Vesely and RRW by any grouping of contributions.

    FV is the fraction of total risk that disappears if this group is
    removed; RRW is the factor by which total risk would fall. FV ranks;
    RRW says how much a fix is worth. Neither needs a fault tree, because
    the pipeline already produces the contribution list a fault tree would
    be quantified into.
    """
    totals: dict[str, float] = {}
    for c in contributions:
        totals[key(c)] = totals.get(key(c), 0.0) + c.delta_ir
    grand = sum(totals.values())
    if grand <= 0.0:
        return []
    out = []
    for k, v in totals.items():
        rest = grand - v
        out.append(Importance(
            key=k, contribution=v, fussell_vesely=v / grand,
            rrw=grand / rest if rest > 0 else math.inf, raw=math.nan))
    out.sort(key=lambda i: -i.contribution)
    return [Importance(i.key, i.contribution, i.fussell_vesely, i.rrw, i.raw,
                       rank=n + 1) for n, i in enumerate(out)]


def risk_achievement_worth(baseline: float, degraded: float) -> float:
    """RAW = risk with the item failed / baseline risk.

    Needs the pipeline re-run with the item degraded, so it is a function
    of two results rather than of one contribution list. This is the
    measure that answers "how much does keeping this working buy us",
    which is the question a monitoring system is really asking when a
    barrier goes out of service.
    """
    return degraded / baseline if baseline > 0 else math.inf


# --------------------------------------------------------------------------
# ranked measures
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Measure:
    """A change, and what it is calculated to be worth.

    reduction is computed. Whether it is worth doing is not."""
    description: str
    target: str
    risk_before: float
    risk_after: float

    @property
    def reduction_fraction(self) -> float:
        if self.risk_before <= 0:
            return 0.0
        return 1.0 - self.risk_after / self.risk_before

    @property
    def factor(self) -> float:
        return (self.risk_before / self.risk_after
                if self.risk_after > 0 else math.inf)

    def statement(self) -> str:
        return (f"{self.description}: {self.reduction_fraction*100:.1f}% "
                f"reduction (x{self.factor:.2f}) on {self.target}")


def rank_measures(measures: Iterable[Measure]) -> list[Measure]:
    return sorted(measures, key=lambda m: -m.reduction_fraction)


@dataclass
class Report:
    """What the decision layer hands back. Deliberately does not include a
    recommendation: it includes what each option is calculated to be worth
    and leaves the choosing where it belongs."""
    individual: AcceptanceResult
    societal: Optional[AcceptanceResult]
    top_scenarios: list[Importance]
    top_outcomes: list[Importance]
    measures: list[Measure] = field(default_factory=list)
    grade: str = ""
    coverage_statement: str = ""
    interval: Optional[Interval] = None
    ignition_checks: list = field(default_factory=list)

    def lines(self) -> list[str]:
        out = ["Engineering screening only: numerical criterion comparison is "
               "not validated facility acceptance.",
               f"Individual risk: {self.individual.statement()}"]
        if self.societal:
            out.append(f"Societal risk:   {self.societal.statement()}")
        out.append(f"Result grade:    {self.grade}")
        if self.interval:
            out.append(f"IR interval:     {self.interval.statement()}")
            out.append(f"Supported as:    {self.interval.rounded()}/yr")
            out.append("Not propagated:  " + NOT_PROPAGATED[0])
            for s in NOT_PROPAGATED[1:]:
                out.append("                 " + s)
        out.append(f"Coverage:        {self.coverage_statement}")
        if self.ignition_checks:
            out.append("Ignition against recorded incidents:")
            for c in self.ignition_checks:
                out.append("  " + c.statement())
        out.append("Dominant scenarios (Fussell-Vesely):")
        for i in self.top_scenarios[:5]:
            out.append(f"  {i.rank}. {i.key:24s} FV={i.fussell_vesely*100:5.1f}%"
                       f"  RRW={i.rrw:6.2f}")
        out.append("Dominant outcome types:")
        for i in self.top_outcomes[:5]:
            out.append(f"  {i.rank}. {i.key:24s} FV={i.fussell_vesely*100:5.1f}%")
        if self.measures:
            out.append("Measures, by calculated risk reduction:")
            for m in rank_measures(self.measures):
                out.append(f"  - {m.statement()}")
        return out


def build_report(result, measures: Optional[list[Measure]] = None,
                 ir_criterion: float = IR_LIMIT_NEW,
                 interval: Optional[Interval] = None) -> Report:
    n, f = result.fn()
    return Report(
        interval=interval,
        ignition_checks=list(getattr(result, "ignition_checks", [])),
        individual=check_individual_risk(result.max_ir, result.coverage,
                                         ir_criterion, interval=interval),
        societal=check_societal_risk(n, f) if len(n) else None,
        top_scenarios=importance_by(result.contributions, lambda c: c.loc_id),
        top_outcomes=importance_by(result.contributions,
                                   lambda c: c.ignition_event or "none"),
        measures=measures or [],
        grade=result.grade.value,
        coverage_statement=result.coverage.statement())
