"""Conditional probability arithmetic with explicit initiating-event semantics."""
from __future__ import annotations
import math
from typing import Literal
from .contracts import Contract, Fraction, Name, Nonnegative, Positive


class HazardInterval(Contract):
    duration_s: Positive
    initiation_intensity_per_s: Nonnegative
    harm_probability_given_initiation: Fraction


def first_event_harm_probability(intervals: tuple[HazardInterval, ...]) -> dict:
    """Piecewise Poisson first-event law, not repeated leaks or annual IR.

    Each harm probability must already include the remaining-horizon consequence,
    ignition and barrier branches conditional on initiation in that interval.
    """
    if not intervals: raise ValueError("nonempty horizon required")
    survival, harm, total_depth = 1.0, 0.0, 0.0
    for x in intervals:
        optical_depth = x.duration_s*x.initiation_intensity_per_s
        total_depth += optical_depth
        p_event = -math.expm1(-optical_depth)
        harm += survival*p_event*x.harm_probability_given_initiation
        survival *= math.exp(-optical_depth)
    return {"metric":"first_initiation_harm_probability", "value":harm, "units":"1",
            "horizon_s":sum(x.duration_s for x in intervals), "initiation_probability":-math.expm1(-total_depth),
            "conditioning":"no event has yet initiated; supplied conditional harm branches",
            "physical_validation_claim":False}


class AnnualScenario(Contract):
    id: Name
    initiating_event_id: Name
    weather_class: Name
    frequency_per_year: Nonnegative | None
    harm_probability_given_event: Fraction
    annual_weather_probability: Fraction
    occupancy_probability: Fraction


def annual_risk(scenarios: tuple[AnnualScenario, ...]) -> dict:
    if not scenarios or len({x.id for x in scenarios}) != len(scenarios):
        raise ValueError("nonempty unique scenario ids required")
    groups={}
    for x in scenarios: groups.setdefault(x.initiating_event_id,[]).append(x)
    for rows in groups.values():
        if len({x.weather_class for x in rows})!=len(rows):
            raise ValueError("duplicate weather branch within initiating event")
        if len({x.frequency_per_year for x in rows})!=1:
            raise ValueError("weather branches must share initiating frequency")
        if not math.isclose(sum(x.annual_weather_probability for x in rows),1,abs_tol=1e-9):
            raise ValueError("annual weather partition must close to one")
    missing = sorted({x.initiating_event_id for x in scenarios if x.frequency_per_year is None})
    known = sum(x.frequency_per_year*x.harm_probability_given_event*x.annual_weather_probability*x.occupancy_probability
                for x in scenarios if x.frequency_per_year is not None)
    return {"metric":"annual_individual_risk_rate", "units":"year^-1", "value":None if missing else known,
            "known_contribution":known, "uncomputed_scenarios":missing,
            "conditioning":"user-supplied mutually exclusive annual scenarios and weather partitions",
            "physical_validation_claim":False}


def harm_given_observed_release(probability: float, *, horizon_s: float) -> dict:
    if not math.isfinite(probability) or not 0 <= probability <= 1 or not math.isfinite(horizon_s) or horizon_s <= 0:
        raise ValueError("valid harm probability and positive horizon required")
    return {"metric":"harm_given_observed_release", "value":probability, "units":"1", "horizon_s":horizon_s,
            "conditioning":"release already observed; no initiating frequency multiplier",
            "physical_validation_claim":False}


class FluxStep(Contract):
    time_s: Nonnegative
    heat_flux_w_m2: Nonnegative


def thermal_dose(steps: tuple[FluxStep, ...]) -> dict:
    """Integrate q^(4/3), assuming linear heat flux between supplied samples."""
    if len(steps) < 2 or any(b.time_s <= a.time_s for a,b in zip(steps,steps[1:])):
        raise ValueError("at least two strictly increasing flux samples required")
    dose = 0.0
    for a,b in zip(steps,steps[1:]):
        q0,q1 = a.heat_flux_w_m2,b.heat_flux_w_m2
        # Stable quadrature close to constant flux; exact power primitive elsewhere.
        if math.isclose(q0,q1,rel_tol=1e-7):
            average = ((q0**(4/3))+4*((q0+q1)/2)**(4/3)+q1**(4/3))/6
        else:
            average = (q1**(7/3)-q0**(7/3))/((7/3)*(q1-q0))
        dose += (b.time_s-a.time_s)*average
    duration=steps[-1].time_s-steps[0].time_s
    return {"dose":dose,"units":"(W/m2)^(4/3)*s", "exposure_s":duration,
            "equivalent_heat_flux_w_m2":(dose/duration)**.75,
            "integration":"linear heat flux; analytic segment integral"}
