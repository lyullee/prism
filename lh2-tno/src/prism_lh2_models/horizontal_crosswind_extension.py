"""Opt-in horizontal-droplet trajectory extension; not part of the TNO baseline.

Uses a single spherical drop, Schiller--Naumann drag and the Yellow Book /
Rescigno Eq. (10) evaporation form. It accepts declared initial drop size and
evaporation coefficient; neither is fitted to concentration, LFL, or footprint.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from .lh2_jet_source import wind_from_bearing_to_vector

G = 9.80665

@dataclass(frozen=True)
class HorizontalCrosswindInput:
    liquid_mass_flow_kg_s: float
    droplet_diameter_m: float
    liquid_density_kg_m3: float
    initial_velocity_m_s: tuple[float, float, float]
    release_height_m: float
    air_density_kg_m3: float
    air_kinematic_viscosity_m2_s: float
    evaporation_kb_m2_s: float
    schmidt_number: float
    wind_speed_m_s: float
    wind_from_bearing_deg: float
    # Optional declared thermal accounting.  The d2 law is a mass-transfer
    # closure, not a complete heat-transfer balance.  Supplying both values
    # permits an auditable energy residual; omitting either deliberately
    # reports that energy was not closed rather than inventing a heat flux.
    latent_heat_j_kg: float | None = None
    environmental_heat_input_w: float | None = None

@dataclass(frozen=True)
class HorizontalCrosswindResult:
    airborne_gas_mass_flow_kg_s: float
    ground_liquid_mass_flow_kg_s: float
    impact_position_m: tuple[float, float, float] | None
    flight_time_s: float | None
    initial_droplet_diameter_m: float
    final_droplet_diameter_m: float
    maximum_reynolds_number: float
    mass_residual_kg_s: float
    evaporation_heat_requirement_w: float | None
    energy_residual_w: float | None
    final_velocity_m_s: tuple[float, float, float]
    status: tuple[str, ...]
    # The endpoint is needed by an explicit source-to-dispersion handoff.  It
    # is reported for both complete evaporation and ground impact; callers
    # must still decide whether the endpoint has a sufficiently resolved
    # thermodynamic/entrainment state for their downstream model.
    terminal_position_m: tuple[float, float, float] | None = None
    terminal_time_s: float | None = None

def _cd(re: float) -> float:
    """Schiller--Naumann sphere Cd through Re=1000; constant Cd above it."""
    if re <= 0: return 0.0
    return 24/re*(1+0.15*re**.687) if re <= 1000 else .44

def integrate_horizontal_crosswind(inp: HorizontalCrosswindInput, *, max_time_s: float = 120.) -> HorizontalCrosswindResult:
    """Time-integrate drag, gravity, mean-wind and Yellow Book Eq. (2.149).

    The wind is a meteorological *from* bearing and appears in the relative-
    velocity drag force, not in post-processing. This is one declared droplet
    diameter only; breakup, distributions and turbulent dispersion are excluded.
    """
    vals = (inp.liquid_mass_flow_kg_s, inp.droplet_diameter_m, inp.liquid_density_kg_m3,
            inp.release_height_m, inp.air_density_kg_m3, inp.air_kinematic_viscosity_m2_s,
            inp.evaporation_kb_m2_s, inp.schmidt_number, max_time_s)
    if any(not math.isfinite(q) or q <= 0 for q in vals): raise ValueError("all scalar inputs must be finite and > 0")
    if not math.isfinite(inp.wind_speed_m_s) or inp.wind_speed_m_s < 0:
        raise ValueError("wind_speed_m_s must be finite and >= 0")
    if len(inp.initial_velocity_m_s) != 3 or not all(math.isfinite(q) for q in inp.initial_velocity_m_s): raise ValueError("initial_velocity_m_s must be three finite values")
    if (inp.latent_heat_j_kg is None) != (inp.environmental_heat_input_w is None):
        raise ValueError("provide both latent_heat_j_kg and environmental_heat_input_w, or neither")
    if inp.latent_heat_j_kg is not None and (not math.isfinite(inp.latent_heat_j_kg) or inp.latent_heat_j_kg <= 0):
        raise ValueError("latent_heat_j_kg must be finite and > 0")
    if inp.environmental_heat_input_w is not None and not math.isfinite(inp.environmental_heat_input_w):
        raise ValueError("environmental_heat_input_w must be finite")
    wind = wind_from_bearing_to_vector(inp.wind_speed_m_s, inp.wind_from_bearing_deg)
    pos, vel, d, t, maximum_re = [0.,0.,inp.release_height_m], list(inp.initial_velocity_m_s), inp.droplet_diameter_m, 0., 0.
    # The continuum d²-law has no meaningful point-particle trajectory once
    # the remaining diameter is many orders below the injected class.  Stop at
    # that explicitly declared numerical extinction limit rather than letting
    # the 1/d drag term manufacture an infinite "impact" speed.
    extinction_diameter = max(1.0e-12, inp.droplet_diameter_m * 1.0e-8)
    while t < max_time_s and pos[2] > 0 and d > extinction_diameter:
        slip = [wind[i]-vel[i] for i in range(3)]; speed = math.sqrt(sum(q*q for q in slip))
        re = speed*d/inp.air_kinematic_viscosity_m2_s; maximum_re=max(maximum_re,re)
        cd = _cd(re); a_drag = 3*cd*inp.air_density_kg_m3*speed/(4*inp.liquid_density_kg_m3*d)
        evap = inp.evaporation_kb_m2_s/max(d,1e-30)*(1+.28*math.sqrt(re)*inp.schmidt_number**(1/3))
        dt = min(1e-3, .002*d/max(evap,1e-30), .005*max(1.,d/max(speed,1e-30)))
        for i in range(3): vel[i] += a_drag*slip[i]*dt
        vel[2] -= G*(1-inp.air_density_kg_m3/inp.liquid_density_kg_m3)*dt
        for i in range(3): pos[i] += vel[i]*dt
        d=max(0.,d-evap*dt); t+=dt
        if d <= extinction_diameter:
            d=0.
            break
    hit = pos[2] <= 0 and d > 0; final = d if hit else 0.
    liquid = inp.liquid_mass_flow_kg_s*(final/inp.droplet_diameter_m)**3; gas = inp.liquid_mass_flow_kg_s-liquid
    evaporation_heat = gas*inp.latent_heat_j_kg if inp.latent_heat_j_kg is not None else None
    energy_residual = (inp.environmental_heat_input_w-evaporation_heat
                       if evaporation_heat is not None else None)
    drag_status = ("schiller_naumann_validated_to_re800" if maximum_re <= 800 else
                   "schiller_naumann_extrapolated_re800_to_1000" if maximum_re <= 1000 else
                   "constant_cd_above_re1000")
    energy_status = ("energy_residual_reported" if energy_residual is not None else
                     "energy_balance_not_closed_without_declared_heat_input")
    terminal_position = (float(pos[0]), float(pos[1]), float(max(pos[2], 0.0)))
    return HorizontalCrosswindResult(gas, liquid, (pos[0],pos[1],0.) if hit else None,
                                     t if hit else None, inp.droplet_diameter_m, final, maximum_re,
                                     inp.liquid_mass_flow_kg_s-gas-liquid, evaporation_heat, energy_residual,
                                     (vel[0], vel[1], vel[2]),
                                     ("horizontal_crosswind_extension", "steady_mean_wind_only", "single_droplet",
                                      drag_status, "yellow_book_eq10_evaporation", energy_status,
                                      "complete_evaporation_before_ground" if not hit and d == 0.0 else "ground_impact" if hit else "trajectory_time_limit"),
                                     terminal_position, t)
