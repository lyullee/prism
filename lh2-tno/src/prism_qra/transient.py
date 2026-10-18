"""
Time-dependent release.

The rest of this system takes the discharge rate as constant and
multiplies it by an isolation time. That is the Purple Book treatment and
it is right for a short isolated release from a large inventory. It is
wrong for the two cases that matter most here.

Where the constant rate fails
-----------------------------
**Blowdown.** A vessel emptying through a hole loses pressure as it
empties, so the rate falls. Taking the initial rate for the whole release
over-states the mass and, worse, over-states the rate at every moment
after the first.

**Self-pressurisation.** A cryogenic vessel that loses its vacuum does
the opposite: heat leaks in, liquid boils, and the pressure RISES until
the relief lifts. HIAD event 58 is exactly this -- an LH2 rail tanker
whose interspace vacuum failed, reaching the 13 bar relief setting
against a 1 bar design pressure and venting for seven hours. A constant
rate describes neither the rise nor the seven hours.

What this returns
-----------------
A profile, and a set of representative values taken from it:

    time, pressure, rate, released mass, phase, isolation state

and then the peak rate, the mass-equivalent time-mean rate, and the duration.
The consequence models downstream take a single rate, so **the profile
is used to choose that number and to show what choosing it hides**,
rather than to drive time-resolved consequences. Making every
consequence model time-resolved is a much larger change and is not
attempted.

What is NOT modelled
--------------------
Heat transfer to the vessel wall during gas blowdown. The expansion is
taken as isentropic, which cools the remaining gas so its pressure falls
faster and it releases less; the isothermal alternative holds the
pressure up and releases more, over a longer time. Both are computed so
the band is visible.

Two-phase level swell and vapour pull-through during a liquid blowdown.
The liquid is taken as draining from the bottom until it is gone, which
is right for a bottom connection and wrong for a top one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import CoolProp.CoolProp as CP

from source_term import discharge
from taxonomy import Grade, Provenance, TranscriptionSource

# Discharge is the expensive call: each one scans the isentrope and a
# blowdown makes one per step. The result depends only on the state and
# the hole, so identical states share a slot. Rounding is coarse enough
# to hit and fine enough that the profile does not visibly change.
_DISCHARGE_CACHE: dict = {}
BLOWDOWN_SCAN_POINTS = 120


def _cached_discharge(p_pa: float, t_k, fluid: str, d_m: float,
                      saturated_liquid: bool = False):
    key = (round(p_pa, -2), None if t_k is None else round(t_k, 2),
           fluid, round(d_m, 6), saturated_liquid)
    hit = _DISCHARGE_CACHE.get(key)
    if hit is None:
        # A coarser isentrope scan than the default 240. Each scan costs
        # 64 ms and a blowdown makes one per step, so a profile took 12 s
        # for a result that does not visibly move: the scan is looking
        # for a maximum in a smooth function, and 120 points find it to
        # five significant figures.
        hit = discharge(p_pa, t_k, fluid, d_m,
                        saturated_liquid=saturated_liquid,
                        n_scan=BLOWDOWN_SCAN_POINTS)
        _DISCHARGE_CACHE[key] = hit
    return hit

P_AMB = 101325.0
LH2_LATENT_J_KG = 445.6e3          # at normal boiling point
LH2_DENSITY_KG_M3 = 70.8
H2_GAS_CP_J_KGK = 14_300.0


class Phase(str, Enum):
    GAS = "GAS"
    LIQUID = "LIQUID"
    TWO_PHASE = "TWO_PHASE"
    EMPTY = "EMPTY"


class IsolationState(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class RateBasis(str, Enum):
    """Single-rate reduction used by downstream consequence models."""
    PEAK = "PEAK"
    MASS_EQUIVALENT_MEAN = "MASS_EQUIVALENT_MEAN"


@dataclass(frozen=True)
class Step:
    t_s: float
    pressure_pa: float
    temperature_k: float
    rate_kg_s: float
    released_kg: float
    remaining_kg: float
    phase: Phase
    isolation: IsolationState


@dataclass
class Profile:
    steps: list = field(default_factory=list)
    limited_by: str = ""
    provenance: Provenance = None
    # External histories default to instantaneous samples. Native solvers
    # record the average over the interval ending at each timestamp.
    rate_sampling: str = "instantaneous"

    @property
    def initial_mass_kg(self) -> float:
        if not self.steps:
            return 0.0
        first = self.steps[0]
        return first.released_kg + first.remaining_kg

    @property
    def duration_s(self) -> float:
        return self.steps[-1].t_s if self.steps else 0.0

    @property
    def released_kg(self) -> float:
        return self.steps[-1].released_kg if self.steps else 0.0

    @property
    def peak_rate_kg_s(self) -> float:
        return max((s.rate_kg_s for s in self.steps), default=0.0)

    @property
    def peak_pressure_pa(self) -> float:
        return max((s.pressure_pa for s in self.steps), default=0.0)

    def mean_rate_kg_s(self) -> float:
        """Mass-equivalent time mean: released mass divided by duration.

        This is not the arithmetic mean of the recorded step rates, which
        would depend on the numerical step spacing rather than the release.
        """
        d = self.duration_s
        return self.released_kg / d if d > 0 else 0.0

    def representative_rate(self, basis: RateBasis) -> float:
        """Reduce the profile to the rate required by a steady model."""
        try:
            basis = RateBasis(basis)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown transient rate basis {basis!r}") from exc
        if basis is RateBasis.PEAK:
            return self.peak_rate_kg_s
        return self.mean_rate_kg_s()

    def validate(self, *, mass_tolerance_kg: float = 1e-6,
                 rate_integral_relative_tolerance: float = 0.05) -> None:
        """Check that a supplied profile is usable and mass conserving.

        The release solvers normally satisfy these invariants themselves.
        This check is mainly the trust boundary for externally supplied
        profiles before they can change a QRA result.
        """
        if not self.steps:
            raise ValueError("transient profile must contain at least one step")
        if self.provenance is None:
            raise ValueError("transient profile must declare provenance")
        if (not math.isfinite(mass_tolerance_kg)
                or mass_tolerance_kg < 0.0):
            raise ValueError("mass tolerance must be finite and non-negative")
        if (not math.isfinite(rate_integral_relative_tolerance)
                or rate_integral_relative_tolerance < 0.0):
            raise ValueError(
                "rate integral tolerance must be finite and non-negative")

        initial = self.initial_mass_kg
        if not math.isfinite(initial) or initial <= 0.0:
            raise ValueError("transient profile initial mass must be positive")
        previous = None
        tolerance = max(mass_tolerance_kg, initial * 1e-9)
        for i, step in enumerate(self.steps):
            values = (step.t_s, step.pressure_pa, step.temperature_k,
                      step.rate_kg_s, step.released_kg,
                      step.remaining_kg)
            if not all(math.isfinite(v) for v in values):
                raise ValueError(
                    f"transient profile step {i} contains a non-finite value")
            if step.t_s < 0.0:
                raise ValueError("transient profile time must be non-negative")
            if step.pressure_pa < 0.0:
                raise ValueError("transient profile pressure cannot be negative")
            if step.temperature_k <= 0.0:
                raise ValueError("transient profile temperature must be positive")
            if (step.rate_kg_s < 0.0 or step.released_kg < 0.0
                    or step.remaining_kg < 0.0):
                raise ValueError(
                    "transient rate, released mass and remaining mass "
                    "must be non-negative")
            if not math.isclose(step.released_kg + step.remaining_kg,
                                initial, rel_tol=0.0,
                                abs_tol=tolerance):
                raise ValueError(
                    f"transient profile violates mass conservation at step {i}")
            if previous is not None:
                if step.t_s < previous.t_s:
                    raise ValueError("transient profile time must not decrease")
                if step.released_kg < previous.released_kg - tolerance:
                    raise ValueError("transient released mass must not decrease")
                if step.remaining_kg > previous.remaining_kg + tolerance:
                    raise ValueError("transient remaining mass must not increase")
            previous = step

        if self.duration_s <= 0.0:
            raise ValueError("transient profile duration must be positive")
        if self.released_kg <= 0.0:
            raise ValueError("transient profile must release positive mass")
        if self.peak_rate_kg_s <= 0.0 or self.mean_rate_kg_s() <= 0.0:
            raise ValueError("transient profile must have a positive rate")
        if self.rate_sampling not in {"instantaneous", "interval_mean_ending"}:
            raise ValueError("unknown transient rate sampling convention")
        integrated_mass = sum(
            (right.rate_kg_s if self.rate_sampling == "interval_mean_ending"
             else 0.5 * (left.rate_kg_s + right.rate_kg_s))
            * (right.t_s - left.t_s)
            for left, right in zip(self.steps, self.steps[1:]))
        integral_tolerance = max(
            mass_tolerance_kg,
            rate_integral_relative_tolerance
            * max(self.released_kg, integrated_mass),
        )
        if not math.isclose(
                integrated_mass, self.released_kg, rel_tol=0.0,
                abs_tol=integral_tolerance):
            raise ValueError(
                "transient profile rate integral does not match released mass")

    def rate_at(self, t_s: float) -> float:
        for s in self.steps:
            if s.t_s >= t_s:
                return s.rate_kg_s
        return 0.0

    def constant_rate_error(self) -> float:
        """How much a constant-rate treatment over-states the release.

        Peak over mean. One means the rate really was constant; larger
        means the first instant is not representative of the rest."""
        m = self.mean_rate_kg_s()
        return self.peak_rate_kg_s / m if m > 0 else 1.0

    def statement(self) -> str:
        return (f"{self.released_kg:.1f} kg over {self.duration_s:.0f} s, "
                f"peak {self.peak_rate_kg_s:.3f} kg/s falling to a "
                f"mass-equivalent mean of {self.mean_rate_kg_s():.3f}, "
                f"a factor of {self.constant_rate_error():.2f}. "
                f"Limited by {self.limited_by}.")


BLOWDOWN_PROV = Provenance(
    source="mass and energy balance on the vessel with CoolProp "
           "properties; isentropic and isothermal bounds both computed",
    grade=Grade.ENGINEERING_JUDGEMENT,
    transcription=TranscriptionSource.UNVERIFIED,
    note="Wall heat transfer during gas blowdown is not modelled, so the "
         "two branches bound it: the isentropic gas cools as it expands "
         "and its pressure falls faster, releasing LESS over a shorter "
         "time; the isothermal wall holds the pressure up and releases "
         "more over a longer one. The true profile lies between.",
    not_claimable_as=["a validated blowdown profile"],
)


# --------------------------------------------------------------------------
# gas blowdown
# --------------------------------------------------------------------------

def gas_blowdown(volume_m3: float, pressure_pa: float, temperature_k: float,
                 hole_diameter_m: float, *,
                 isolation_time_s: Optional[float] = None,
                 isothermal: bool = False,
                 fluid: str = "Hydrogen",
                 max_time_s: float = 3600.0,
                 dt_s: Optional[float] = None) -> Profile:
    """Vessel emptying through a hole.

    Isentropic by default: the gas left behind does the work of expelling
    what leaves, so it cools and the rate falls faster than pressure
    alone would suggest. Isothermal is the other bound, where the wall
    supplies heat as fast as the gas takes it.
    """
    positive_inputs = {
        "volume_m3": volume_m3,
        "pressure_pa": pressure_pa,
        "temperature_k": temperature_k,
        "hole_diameter_m": hole_diameter_m,
        "max_time_s": max_time_s,
    }
    for name, value in positive_inputs.items():
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value)) or value <= 0.0):
            raise ValueError(f"{name} must be finite and positive")
    if (isolation_time_s is not None
            and (isinstance(isolation_time_s, bool)
                 or not isinstance(isolation_time_s, (int, float))
                 or not math.isfinite(float(isolation_time_s))
                 or isolation_time_s < 0.0)):
        raise ValueError("isolation_time_s must be finite and non-negative")
    if (dt_s is not None
            and (isinstance(dt_s, bool)
                 or not isinstance(dt_s, (int, float))
                 or not math.isfinite(float(dt_s)) or dt_s <= 0.0)):
        raise ValueError("dt_s must be finite and positive")

    # Step size from the vessel's own emptying time rather than fixed.
    # A fixed 0.5 s emptied a 25 mm hole in one step and reported a rate
    # of zero, because the first step is recorded before any flow.
    if dt_s is None:
        try:
            _d0 = _cached_discharge(pressure_pa, temperature_k, fluid,
                                    hole_diameter_m)
            _rho0 = CP.PropsSI("D", "P", pressure_pa, "T", temperature_k,
                               fluid)
            _tau = (_rho0 * volume_m3) / max(_d0.rate_kg_s, 1e-12)
            # Roughly 200 steps over the emptying time, floored so that a
            # very fast release does not produce millions of steps.
            # Forty steps over the emptying time. Each step runs a full
            # isentropic discharge scan and three CoolProp calls, so a
            # finer grid costs seconds per profile for no visible change
            # in the mass-equivalent mean; 1,400 steps took 87 s and 40
            # takes under three.
            dt_s = max(_tau / 40.0, 1e-3)
        except Exception:
            dt_s = 0.5

    rho0 = CP.PropsSI("D", "P", pressure_pa, "T", temperature_k, fluid)
    s0 = CP.PropsSI("S", "P", pressure_pa, "T", temperature_k, fluid)
    m = rho0 * volume_m3
    p, t_k = pressure_pa, temperature_k
    released, t = 0.0, 0.0
    try:
        _r0 = _cached_discharge(p, t_k, fluid,
                                hole_diameter_m).rate_kg_s
    except Exception:
        _r0 = 0.0
    steps = [Step(0.0, p, t_k, _r0, 0.0, m, Phase.GAS,
                  IsolationState.OPEN)]
    limited = "ambient pressure"

    max_steps = 400
    while t < max_time_s and m > 1e-9 and len(steps) < max_steps:
        iso = (IsolationState.CLOSED
               if isolation_time_s is not None and t >= isolation_time_s
               else IsolationState.OPEN)
        if iso is IsolationState.CLOSED:
            limited = f"isolation at {isolation_time_s:g} s"
            steps.append(Step(t, p, t_k, 0.0, released, m, Phase.GAS, iso))
            break
        if p <= P_AMB * 1.001:
            limited = "ambient pressure"
            break
        try:
            d = _cached_discharge(p, t_k, fluid, hole_diameter_m)
        except Exception:
            limited = "discharge model failed"
            break
        rate = d.rate_kg_s
        if rate <= 0.0:
            limited = "no outward flow"
            break

        remaining_time = max_time_s - t
        if isolation_time_s is not None:
            remaining_time = min(remaining_time, isolation_time_s - t)
        step_dt = min(dt_s, remaining_time)
        dm = min(rate * step_dt, m)
        m -= dm
        released += dm
        t += step_dt
        actual_rate = dm / step_dt
        rho = m / volume_m3
        if rho <= 1e-9:
            limited = "vessel empty"
            m = 0.0
            steps.append(Step(t, p, t_k, actual_rate, released, m,
                              Phase.EMPTY, IsolationState.OPEN))
            break
        try:
            if isothermal:
                p = CP.PropsSI("P", "D", rho, "T", temperature_k, fluid)
                t_k = temperature_k
            else:
                p = CP.PropsSI("P", "D", rho, "S", s0, fluid)
                t_k = CP.PropsSI("T", "D", rho, "S", s0, fluid)
        except Exception:
            limited = "property evaluation failed"
            steps.append(Step(t, p, t_k, actual_rate, released, m,
                              Phase.GAS, IsolationState.OPEN))
            break
        steps.append(Step(t, p, t_k, actual_rate, released, m,
                          Phase.GAS if m > 0 else Phase.EMPTY,
                          IsolationState.OPEN))
        if isolation_time_s is not None and t >= isolation_time_s:
            limited = f"isolation at {isolation_time_s:g} s"
            steps.append(Step(t, p, t_k, 0.0, released, m,
                              Phase.GAS if m > 0 else Phase.EMPTY,
                              IsolationState.CLOSED))
            break
        if t >= max_time_s:
            limited = f"time limit {max_time_s:g} s"
    if len(steps) >= max_steps:
        limited = f"step limit {max_steps}"

    return Profile(steps=steps, limited_by=limited,
                   provenance=BLOWDOWN_PROV,
                   rate_sampling="interval_mean_ending")


# --------------------------------------------------------------------------
# cryogenic self-pressurisation
# --------------------------------------------------------------------------

SELF_PRESSURISATION_PROV = Provenance(
    source="energy balance on a cryogenic vessel with a heat leak; "
           "compared against HIAD event 58",
    grade=Grade.ENGINEERING_JUDGEMENT,
    transcription=TranscriptionSource.UNVERIFIED,
    note="The heat leak after a loss of vacuum is the governing input "
         "and it is not published for any real vessel. What can be "
         "checked is that the model reproduces the ONE recorded case "
         "when given a heat leak that matches it, which is a calibration "
         "and not a validation.",
    not_claimable_as=["a validated self-pressurisation model",
                      "a heat leak for any particular vessel"],
)


def loss_of_vacuum(inventory_kg: float, volume_m3: float,
                   heat_leak_w: float, relief_pressure_pa: float,
                   relief_diameter_m: float, *,
                   start_pressure_pa: float = 1.5e5,
                   max_time_s: float = 40000.0,
                   dt_s: float = 10.0) -> Profile:
    """A cryogenic vessel that has lost its insulation.

    Heat leaks in, liquid boils, pressure rises until the relief lifts,
    and the vessel then vents at whatever rate the relief passes until
    the inventory is gone. That is the HIAD 58 sequence and it takes
    hours, not the seconds a hole in a pipe takes.

    The heat leak is the input that decides everything and it is not
    published for any real vessel. Giving it is the user's problem; what
    this does is turn it into a profile.
    """
    positive_inputs = {
        "inventory_kg": inventory_kg,
        "volume_m3": volume_m3,
        "heat_leak_w": heat_leak_w,
        "relief_pressure_pa": relief_pressure_pa,
        "relief_diameter_m": relief_diameter_m,
        "start_pressure_pa": start_pressure_pa,
        "max_time_s": max_time_s,
        "dt_s": dt_s,
    }
    for name, value in positive_inputs.items():
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value)) or value <= 0.0):
            raise ValueError(f"{name} must be finite and positive")
    if volume_m3 <= inventory_kg / LH2_DENSITY_KG_M3:
        raise ValueError("volume_m3 must exceed the initial liquid volume")

    p = start_pressure_pa
    released, t = 0.0, 0.0
    t_sat = _sat_temperature(p)
    ullage = max(volume_m3 - inventory_kg / LH2_DENSITY_KG_M3, 1e-6)
    # The initial ullage vapour is part of the stated inventory. Tracking it
    # explicitly prevents boiled liquid from disappearing before the relief
    # opens.
    vapour_kg = min(
        p * ullage * 2.016e-3 / (8.314 * t_sat), inventory_kg)
    liquid_kg = max(inventory_kg - vapour_kg, 0.0)
    remaining = liquid_kg + vapour_kg
    steps = [Step(0.0, p, t_sat, 0.0, 0.0, remaining, Phase.TWO_PHASE,
                   IsolationState.OPEN)]
    limited = "inventory exhausted"
    venting = False

    while t < max_time_s and remaining > 1e-6:
        step_dt = min(dt_s, max_time_s - t)
        boil_kg_s = heat_leak_w / LH2_LATENT_J_KG

        # Heat converts liquid to vapour; it does not remove mass from the
        # vessel. The pressure follows the accumulated ullage vapour.
        dm_boil = min(boil_kg_s * step_dt, liquid_kg)
        liquid_kg -= dm_boil
        vapour_kg += dm_boil
        t_sat = _sat_temperature(max(p, start_pressure_pa))
        ullage = max(volume_m3 - liquid_kg / LH2_DENSITY_KG_M3, 1e-6)
        p_unvented = (vapour_kg * (8.314 / 2.016e-3) * t_sat / ullage)
        rate = 0.0

        if (p_unvented >= relief_pressure_pa
                or (venting and liquid_kg <= 1e-9)):
            venting = True
            try:
                discharge_pressure = max(
                    p_unvented, relief_pressure_pa)
                if liquid_kg > 1e-9:
                    d = _cached_discharge(
                        discharge_pressure, None, "ParaHydrogen",
                        relief_diameter_m, saturated_liquid=True)
                else:
                    d = _cached_discharge(
                        discharge_pressure, max(t_sat, 20.4), "Hydrogen",
                        relief_diameter_m, saturated_liquid=False)
                cap = d.rate_kg_s
            except Exception:
                cap = 0.0

            target_vapour = (relief_pressure_pa * ullage * 2.016e-3
                             / (8.314 * t_sat))
            required_kg = max(vapour_kg - target_vapour, 0.0)
            # After the liquid is gone, heat still expands the gas and the
            # relief continues to vent it. At constant relief pressure the
            # first-order energy balance gives m_dot = Q / (cp T).
            if liquid_kg <= 1e-9:
                required_kg += (heat_leak_w /
                                 (H2_GAS_CP_J_KGK * max(t_sat, 1.0))) * step_dt
            dm_vent = min(required_kg, cap * step_dt, vapour_kg)
            vapour_kg -= dm_vent
            released += dm_vent
            rate = dm_vent / step_dt
            if dm_vent + 1e-12 >= required_kg:
                p = relief_pressure_pa
            else:
                p = (vapour_kg * (8.314 / 2.016e-3) * t_sat / ullage)
            if p > relief_pressure_pa * 1.001:
                limited = ("relief capacity below the boil-off rate; the "
                           "vessel over-pressures")
        else:
            venting = False
            p = p_unvented

        t += step_dt
        remaining = liquid_kg + vapour_kg
        phase = (Phase.TWO_PHASE if liquid_kg > 1e-9 and vapour_kg > 1e-9
                 else Phase.GAS if vapour_kg > 1e-9 else Phase.EMPTY)
        steps.append(Step(t, p, _sat_temperature(p), rate, released,
                          max(remaining, 0.0), phase,
                          IsolationState.OPEN))
        if t >= max_time_s and limited == "inventory exhausted":
            limited = f"time limit {max_time_s:g} s"

    return Profile(steps=steps, limited_by=limited,
                   provenance=SELF_PRESSURISATION_PROV,
                   rate_sampling="interval_mean_ending")


def _sat_temperature(p_pa: float) -> float:
    try:
        return float(CP.PropsSI("T", "P", min(p_pa, 1.28e6), "Q", 0,
                                "ParaHydrogen"))
    except Exception:
        return 20.4


# Heat leak that reproduces the one recorded case, back-solved from the
# boil-off rate rather than fitted to the profile:
#
#     Q = rate x latent heat = 0.10 kg/s x 445.6 kJ/kg = 45 kW
#
# and the mass-conserving model returns 2,600 kg over 29,540 s at
# 0.0880 kg/s against a recorded 2,500 kg over 25,000 s at 0.10. This is
# only a calibration-scale check: one case cannot validate a model, and
# the loss-of-vacuum heat leak is not published for a real vessel.
HIAD58_HEAT_LEAK_W = 45.0e3

HIAD58 = {
    "inventory_kg": 2600.0,
    "volume_m3": 42.0,
    "relief_pressure_pa": 12.0e5,   # 13 bar recorded, above the 12.86 bar
                                    # critical pressure, so 12 is used
    "recorded_rate_kg_s": 0.10,
    "recorded_released_kg": 2500.0,
    "recorded_duration_s": 25000.0,
}


WHY_A_PROFILE_AND_NOT_TIME_RESOLVED_CONSEQUENCES = (
    "Every consequence model downstream takes a single rate. Making them "
    "time-resolved is a much larger change than computing the profile, "
    "and it would need a decision about what a time-varying flammable "
    "cloud even means for an ignition probability. The profile is "
    "therefore used to CHOOSE the single rate and to show what choosing "
    "it hides, which is the peak-to-mean ratio."
)
