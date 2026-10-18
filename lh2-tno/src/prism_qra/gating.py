"""
Applicability gating.

A consequence model has a domain. Outside it the model still returns a
number, and that number is not wrong so much as meaningless -- the SLAB
plume mode marches along x on the premise that the cloud is carried
downwind faster than it rises, and once w_c/u exceeds one, x has stopped
tracking the cloud. Commercial consequence codes do not report this. They
return the number.

The design rule here is that a refused quantity carries no number at all.
Verdict is not a flag beside a float; on REFUSE the float is absent, and
reading it raises. A caller cannot forget to check, because there is
nothing to read.

Three states
------------
    ANSWER          inside the premise; use the value
    ANSWER_FLAGGED  inside the premise but near its edge, or carrying a
                    safety factor; usable, and the flag travels with it
    REFUSE          outside the premise; no value exists

Gating is per quantity, not per run
-----------------------------------
The premise fails for different quantities at different places. In the
buoyancy-dominated regime an LH2 cloud lifts, so the ground-level LFL
distance becomes small and comparatively easy to bound, while the cloud
height -- which is what actually matters there, because a lofted cloud can
reach elevated ignition sources -- is exactly what the bent-over
formulation cannot give. One DispersionResult can therefore hold an
answered distance and a refused height at the same time.

Accounting
----------
Dropping refused scenarios silently is worse than crashing: the risk
number still looks like a risk number, and it is too low. Coverage
therefore travels with the result as the LOC frequency that could not be
evaluated, so that a partial answer says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class Verdict(str, Enum):
    ANSWER = "ANSWER"
    ANSWER_FLAGGED = "ANSWER_FLAGGED"
    REFUSE = "REFUSE"


class RefusedError(RuntimeError):
    """Raised when a refused quantity is read."""


class RefusePolicy(str, Enum):
    EXCLUDE = "EXCLUDE"      # drop the scenario, record its frequency
    BOUND = "BOUND"          # substitute a declared conservative bound
    ESCALATE = "ESCALATE"    # stop; the caller must decide
    # Experiment only: expose the number produced outside the model premise.
    # Production callers should use EXCLUDE, BOUND or ESCALATE.
    FORCE = "FORCE"


@dataclass(frozen=True)
class Gated(Generic[T]):
    """A quantity that may not exist."""
    verdict: Verdict
    quantity: str
    _value: Optional[T] = None
    reason: str = ""
    bound: Optional[T] = None          # conservative substitute, if defined
    bound_basis: str = ""
    forced_value: Optional[T] = None   # experiment-only out-of-premise value
    flags: tuple[str, ...] = ()

    @classmethod
    def answer(cls, quantity: str, value: T,
               flags: tuple[str, ...] = ()) -> "Gated[T]":
        return cls(Verdict.ANSWER_FLAGGED if flags else Verdict.ANSWER,
                   quantity, value, flags=flags)

    @classmethod
    def refuse(cls, quantity: str, reason: str,
               bound: Optional[T] = None,
               bound_basis: str = "",
               forced_value: Optional[T] = None) -> "Gated[T]":
        return cls(Verdict.REFUSE, quantity, None, reason=reason,
                   bound=bound, bound_basis=bound_basis,
                   forced_value=forced_value)

    @property
    def value(self) -> T:
        if self.verdict is Verdict.REFUSE:
            raise RefusedError(
                f"{self.quantity}: outside the model premise. {self.reason} "
                f"No value exists. Use resolve(policy=...) to choose what "
                f"happens instead.")
        return self._value  # type: ignore[return-value]

    @property
    def refused(self) -> bool:
        return self.verdict is Verdict.REFUSE

    @property
    def has_bound(self) -> bool:
        return self.bound is not None

    def resolve(self, policy: RefusePolicy) -> Optional[T]:
        """Apply a policy. EXCLUDE returns None so the caller must branch;
        BOUND returns the declared bound, or raises if none was defined,
        because an undefined bound is not a conservative one."""
        if not self.refused:
            return self._value
        if policy is RefusePolicy.ESCALATE:
            raise RefusedError(f"{self.quantity}: {self.reason}")
        if policy is RefusePolicy.EXCLUDE:
            return None
        if policy is RefusePolicy.FORCE:
            if self.forced_value is None:
                raise RefusedError(
                    f"{self.quantity}: FORCE policy requested but the "
                    "out-of-premise value was not retained. FORCE is for "
                    "controlled comparison experiments only.")
            return self.forced_value
        if self.bound is None:
            raise RefusedError(
                f"{self.quantity}: BOUND policy requested but no conservative "
                f"bound is defined for this quantity. Define one or use "
                f"EXCLUDE. Substituting an arbitrary number here would be "
                f"the failure this gate exists to prevent.")
        return self.bound

    def describe(self) -> str:
        if self.verdict is Verdict.REFUSE:
            b = f" bound={self.bound}" if self.has_bound else " no bound"
            return f"{self.quantity}: REFUSE ({self.reason}){b}"
        f = f" [{', '.join(self.flags)}]" if self.flags else ""
        return f"{self.quantity}: {self._value}{f}"


# --------------------------------------------------------------------------
# coverage accounting
# --------------------------------------------------------------------------

@dataclass
class Coverage:
    """How much of the enumerated risk the answer actually covers.

    evaluated + refused + no_data should equal the total LOC frequency
    enumerated. The fractions are of frequency, not of scenario count,
    because one rare large release matters more than many small ones."""
    evaluated_frequency: float = 0.0
    refused_frequency: float = 0.0
    no_data_frequency: float = 0.0
    refused_quantities: dict[str, int] = field(default_factory=dict)
    refused_scenarios: list[str] = field(default_factory=list)
    # A frequency cannot be assigned to these scenarios at all. They must
    # remain visible without pretending that an unknown value is zero.
    unquantified: list[tuple[str, str]] = field(default_factory=list)

    def record_evaluated(self, f: float) -> None:
        self.evaluated_frequency += f

    def record_refused(self, f: float, quantity: str, scenario: str) -> None:
        self.refused_frequency += f
        self.refused_quantities[quantity] = (
            self.refused_quantities.get(quantity, 0) + 1)
        if scenario not in self.refused_scenarios:
            self.refused_scenarios.append(scenario)

    def record_no_data(self, f: float) -> None:
        self.no_data_frequency += f

    def record_unquantified(self, scenario: str, component: str) -> None:
        item = (scenario, component)
        if item not in self.unquantified:
            self.unquantified.append(item)

    @property
    def total_frequency(self) -> float:
        return (self.evaluated_frequency + self.refused_frequency
                + self.no_data_frequency)

    @property
    def evaluated_fraction(self) -> float:
        t = self.total_frequency
        return self.evaluated_frequency / t if t > 0 else 0.0

    @property
    def complete(self) -> bool:
        return (self.refused_frequency == 0.0
                and self.no_data_frequency == 0.0
                and not self.unquantified)

    def statement(self) -> str:
        if self.complete:
            return "Complete: every enumerated scenario was evaluated."
        unknown = ""
        if self.unquantified:
            labels = ", ".join(f"{tag} ({sid})" for sid, tag
                               in self.unquantified[:6])
            if len(self.unquantified) > 6:
                labels += ", and others"
            unknown = (f" NO frequency at all is available for {labels}; "
                       "those scenarios cannot enter a frequency-weighted "
                       "coverage percentage.")
        return (
            f"PARTIAL: {self.evaluated_fraction*100:.1f}% of enumerated LOC "
            f"frequency evaluated. {self.refused_frequency:.3e}/yr refused as "
            f"outside model premise, {self.no_data_frequency:.3e}/yr lacking "
            f"data.{unknown} The risk reported is therefore a LOWER BOUND, "
            f"not an estimate.")


# --------------------------------------------------------------------------
# the LH2 bent-over premise
# --------------------------------------------------------------------------

def critical_wind_speed(rate_kg_s: float) -> float:
    """u_crit ~ 2.5 * q^0.15, below which the cloud rises faster than it is
    carried downwind and the bent-over plume formulation loses its meaning.

    It is a screening criterion evaluated BEFORE the run, which is what
    makes gating usable in a monitoring loop: the model can be asked
    whether it is entitled to answer, rather than checked afterwards."""
    return 2.5 * max(rate_kg_s, 1e-12) ** 0.15


GROUND_DISTANCE_NOTE = (
    "In the buoyancy-dominated regime the cloud lifts, so the ground-level "
    "flammable extent is smaller than in the bent-over regime rather than "
    "larger. The design maximum for ground-level distance lies on the "
    "convective side, inside the premise. The refused region matters for "
    "cloud height and elevated ignition, not for ground-level reach."
)
