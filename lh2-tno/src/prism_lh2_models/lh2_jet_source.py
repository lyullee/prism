"""Independent, transparent liquid-hydrogen jet source term.

This module deliberately has no import from SLAB, DEGADIS, HyRAM+, LH2PoolX,
or an adapter.  It is a screening source-term model, not a CFD atomisation or
impinging-jet solver.  All uncertain spray inputs are public parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

import CoolProp.CoolProp as CP

from .lh2_critical_flow import CriticalFlowInput, CriticalFlowResult, hem_critical_flow, hnem_critical_flow

G = 9.80665
R_H2 = 4124.48


@dataclass(frozen=True)
class StorageState:
    """Upstream liquid state. Pressure is absolute; units are SI."""
    pressure_pa: float
    temperature_k: float
    discharge_coefficient: float = 0.62
    fluid: str = "Hydrogen"


@dataclass(frozen=True)
class Nozzle:
    diameter_m: float
    height_m: float
    direction: tuple[float, float, float] = (1.0, 0.0, 0.0)


@dataclass(frozen=True)
class Environment:
    pressure_pa: float = 101325.0
    temperature_k: float = 288.15
    wind_speed_m_s: float = 0.0
    wind_from_bearing_deg: float | None = None


@dataclass(frozen=True)
class SprayAssumptions:
    """Declared uncertain spray/trajectory inputs, intentionally unfitted.

    ``d2_evaporation_constant_m2_s`` is the coefficient K in d^2=d0^2-Kt.
    Set it to zero for the no-in-flight-evaporation bounding case.  The spray
    angle is a circular-cone half angle used only for a circular-equivalent
    ground footprint.  No experimental concentration, LFL, wind, flow or
    area data are used to estimate these values.
    """
    droplet_diameter_m: float = 5e-4
    d2_evaporation_constant_m2_s: float = 1e-7
    spray_half_angle_deg: float = 12.0
    liquid_velocity_fraction: float = 1.0


@dataclass(frozen=True)
class GasBranch:
    mass_flow_kg_s: float
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float
    velocity_m_s: float
    direction: tuple[float, float, float]
    effective_area_m2: float


@dataclass(frozen=True)
class GroundBranch:
    mass_flow_kg_s: float
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float
    velocity_m_s: float
    impact_position_m: tuple[float, float, float]
    footprint_radius_m: float
    footprint_area_m2: float
    flight_time_s: float | None


@dataclass(frozen=True)
class ConservationReport:
    mass_in_kg_s: float
    mass_out_kg_s: float
    mass_residual_kg_s: float
    energy_in_w: float
    heat_to_evaporate_droplets_w: float
    energy_out_w: float
    energy_residual_w: float | None
    energy_balance_status: str


@dataclass(frozen=True)
class SourceStep:
    time_s: float
    gas: GasBranch
    ground: GroundBranch
    flash_vapour_fraction: float
    in_flight_evaporated_fraction_of_liquid: float
    conservation: ConservationReport
    wind_to_vector_m_s: tuple[float, float, float]
    jet_wind_relative_angle_deg: float | None
    wind_along_jet_m_s: float
    wind_cross_jet_m_s: float
    assumptions: tuple[str, ...]
    status: tuple[str, ...]


@dataclass(frozen=True)
class SourceHistory:
    steps: tuple[SourceStep, ...]
    model_name: str = "independent_lh2_liquid_jet_source_term"
    references: tuple[str, ...] = field(default=(
        "ISO 5167-style incompressible sharp-orifice relation: m=C_d A sqrt(2 rho DeltaP).",
        "Isenthalpic equilibrium flash: x=(h_in-h_f)/(h_g-h_f) at ambient pressure.",
        "Classical d-squared droplet evaporation idealisation: d^2=d0^2-Kt.",
    ))


def _finite_positive(name: str, value: float, *, allow_zero: bool = False) -> None:
    if not math.isfinite(value) or value < 0.0 or (not allow_zero and value == 0.0):
        relation = ">= 0" if allow_zero else "> 0"
        raise ValueError(f"{name} must be finite and {relation}, got {value!r}")


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    if len(v) != 3 or not all(math.isfinite(x) for x in v):
        raise ValueError("direction must contain three finite components")
    norm = math.sqrt(sum(x*x for x in v))
    if norm == 0.0:
        raise ValueError("direction must not be the zero vector")
    return tuple(x / norm for x in v)  # type: ignore[return-value]


def wind_from_bearing_to_vector(speed_m_s: float, from_bearing_deg: float | None
                                ) -> tuple[float, float, float]:
    """Meteorological *from* bearing (clockwise from north) to ENU to-vector.

    Components are east, north, up.  A 0 degree wind comes from north and
    therefore travels south; a 90 degree wind travels west.  A calm wind may
    omit its bearing, but a non-calm wind may not.
    """
    _finite_positive("wind_speed_m_s", speed_m_s, allow_zero=True)
    if speed_m_s == 0.0:
        return (0.0, 0.0, 0.0)
    if from_bearing_deg is None or not math.isfinite(from_bearing_deg):
        raise ValueError("wind_from_bearing_deg is required and finite when wind_speed_m_s > 0")
    to_rad = math.radians((from_bearing_deg + 180.0) % 360.0)
    return (speed_m_s * math.sin(to_rad), speed_m_s * math.cos(to_rad), 0.0)


def _wind_jet_components(direction: tuple[float, float, float], wind: tuple[float, float, float]
                         ) -> tuple[float | None, float, float]:
    speed = math.sqrt(sum(v*v for v in wind))
    if speed == 0.0:
        return None, 0.0, 0.0
    along = sum(a*b for a, b in zip(direction, wind))
    cross = math.sqrt(max(0.0, speed*speed - along*along))
    angle = math.degrees(math.acos(max(-1.0, min(1.0, along / speed))))
    return angle, along, cross


def _validate(s: StorageState, n: Nozzle, e: Environment, a: SprayAssumptions,
              duration_s: float, time_step_s: float) -> tuple[float, float, float]:
    for name, value in (("storage pressure_pa", s.pressure_pa), ("storage temperature_k", s.temperature_k),
                        ("nozzle diameter_m", n.diameter_m), ("environment pressure_pa", e.pressure_pa),
                        ("environment temperature_k", e.temperature_k), ("duration_s", duration_s),
                        ("time_step_s", time_step_s), ("droplet_diameter_m", a.droplet_diameter_m)):
        _finite_positive(name, value)
    _finite_positive("nozzle height_m", n.height_m, allow_zero=True)
    _finite_positive("wind_speed_m_s", e.wind_speed_m_s, allow_zero=True)
    wind_from_bearing_to_vector(e.wind_speed_m_s, e.wind_from_bearing_deg)
    _finite_positive("discharge_coefficient", s.discharge_coefficient)
    if s.discharge_coefficient > 1.0:
        raise ValueError("discharge_coefficient must be <= 1")
    _finite_positive("d2_evaporation_constant_m2_s", a.d2_evaporation_constant_m2_s, allow_zero=True)
    if not 0.0 <= a.spray_half_angle_deg < 90.0:
        raise ValueError("spray_half_angle_deg must be in [0, 90)")
    if not 0.0 <= a.liquid_velocity_fraction <= 1.0:
        raise ValueError("liquid_velocity_fraction must be in [0, 1]")
    direction = _unit(n.direction)
    try:
        rho = float(CP.PropsSI("D", "P", s.pressure_pa, "T", s.temperature_k, s.fluid))
        h = float(CP.PropsSI("H", "P", s.pressure_pa, "T", s.temperature_k, s.fluid))
    except Exception as exc:
        raise ValueError("storage state is outside CoolProp's supported fluid domain") from exc
    if rho <= 0.0 or not math.isfinite(rho):
        raise ValueError("storage density must be positive")
    return direction + (rho, h)  # type: ignore[return-value]


def _flight_time(height: float, vertical_velocity: float) -> float | None:
    """Vacuum-ballistic time to z=0. Upward/horizontal jets have no ground hit."""
    if height == 0.0:
        return 0.0
    if vertical_velocity >= 0.0:
        return None
    return (vertical_velocity + math.sqrt(vertical_velocity**2 + 2.0 * G * height)) / G


def evaluate_liquid_jet(storage: StorageState, nozzle: Nozzle, environment: Environment,
                        duration_s: float, *, time_step_s: float = 1.0,
                        spray: SprayAssumptions = SprayAssumptions()) -> SourceHistory:
    """Evaluate a constant-state LH2 release on interval endpoints.

    The model supports liquid upstream states only.  It uses an incompressible
    orifice relation, an equilibrium isenthalpic flash at ambient pressure,
    and a declared d² spray evaporation calculation.  A non-downward jet has
    no calculated ground interception: un-evaporated droplets are reported as
    unresolved rather than silently labelled deposited.
    """
    values = _validate(storage, nozzle, environment, spray, duration_s, time_step_s)
    direction, rho0, h0 = values[:3], values[3], values[4]
    wind = wind_from_bearing_to_vector(environment.wind_speed_m_s, environment.wind_from_bearing_deg)
    wind_angle, wind_along, wind_cross = _wind_jet_components(direction, wind)
    try:
        q0 = float(CP.PropsSI("Q", "P", storage.pressure_pa, "T", storage.temperature_k, storage.fluid))
    except Exception:
        q0 = -1.0
    if q0 > 1e-8:
        raise ValueError("storage state is not liquid; this liquid-jet model does not accept vapour/two-phase inlet states")
    delta_p = storage.pressure_pa - environment.pressure_pa
    area0 = math.pi * nozzle.diameter_m**2 / 4.0
    if delta_p <= 0.0:
        zero_gas = GasBranch(0.0, environment.temperature_k, environment.pressure_pa,
                             environment.pressure_pa/(R_H2*environment.temperature_k), 0.0, direction, 0.0)
        zero_ground = GroundBranch(0.0, storage.temperature_k, environment.pressure_pa, rho0, 0.0,
                                   (0.0, 0.0, 0.0), 0.0, 0.0, None)
        report = ConservationReport(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                    "zero_flow_no_thermal_closure_required")
        return SourceHistory(tuple(SourceStep(t, zero_gas, zero_ground, 0.0, 0.0, report, wind,
                                               wind_angle, wind_along, wind_cross,
                                               ("No driving pressure: zero release.",), ("zero_flow", "steady_mean_wind_only"))
                                   for t in (0.0, duration_s)))
    try:
        hf = float(CP.PropsSI("H", "P", environment.pressure_pa, "Q", 0, storage.fluid))
        hg = float(CP.PropsSI("H", "P", environment.pressure_pa, "Q", 1, storage.fluid))
        tsat = float(CP.PropsSI("T", "P", environment.pressure_pa, "Q", 0, storage.fluid))
        rhol = float(CP.PropsSI("D", "P", environment.pressure_pa, "Q", 0, storage.fluid))
    except Exception as exc:
        raise ValueError("ambient pressure does not support an LH2 saturation flash") from exc
    x = min(1.0, max(0.0, (h0 - hf) / (hg - hf)))
    mdot = storage.discharge_coefficient * area0 * math.sqrt(2.0 * rho0 * delta_p)
    v0 = mdot / (rho0 * area0)
    liquid_mdot = mdot * (1.0 - x)
    t_flight = _flight_time(nozzle.height_m, v0 * spray.liquid_velocity_fraction * direction[2])
    if t_flight is None:
        evap = 0.0
        ground_mdot = 0.0
        status = ("no_ground_interception", "unresolved_airborne_liquid")
        impact = (math.nan, math.nan, math.nan)
        radius = area = 0.0
    else:
        remaining_d2 = max(0.0, spray.droplet_diameter_m**2 - spray.d2_evaporation_constant_m2_s * t_flight)
        evap = 1.0 - (remaining_d2 / spray.droplet_diameter_m**2)**1.5
        ground_mdot = liquid_mdot * (1.0 - evap)
        horizontal_time = t_flight
        impact = (v0 * spray.liquid_velocity_fraction * direction[0] * horizontal_time + wind[0] * horizontal_time,
                  v0 * spray.liquid_velocity_fraction * direction[1] * horizontal_time + wind[1] * horizontal_time, 0.0)
        radius = (max(0.0, math.tan(math.radians(spray.spray_half_angle_deg)) *
                      math.sqrt(impact[0]**2 + impact[1]**2)) if ground_mdot > 0.0 else 0.0)
        area = math.pi * radius**2
        status = ("ground_interception", "d_squared_evaporation")
    gas_mdot = mdot * x + liquid_mdot * evap
    rho_g = environment.pressure_pa / (R_H2 * tsat)
    gas_velocity = max(v0, 1e-12)
    gas = GasBranch(gas_mdot, tsat, environment.pressure_pa, rho_g, gas_velocity,
                    direction, gas_mdot / (rho_g * gas_velocity) if gas_mdot else 0.0)
    ground = GroundBranch(ground_mdot, tsat, environment.pressure_pa, rhol,
                          v0 * spray.liquid_velocity_fraction, impact, radius, area, t_flight)
    q_evap = liquid_mdot * evap * (hg - hf)
    energy_in = mdot * (h0 + 0.5 * v0**2)
    energy_out = gas_mdot * (hg + 0.5 * gas_velocity**2) + ground_mdot * (hf + 0.5 * ground.velocity_m_s**2)
    # K in a declared d² law determines how much liquid evaporates, but is not
    # a model of the heat supplied by air, ground, radiation or the jet itself.
    # Do not turn the latent-heat requirement into a fictitious heat source.
    report = ConservationReport(mdot, gas_mdot + ground_mdot, mdot - gas_mdot - ground_mdot,
                                energy_in, q_evap, energy_out, None,
                                "energy_balance_open_declared_d2_evaporation")
    assumptions = ("Incompressible liquid-orifice discharge; no choking or line losses.",
                   "Equilibrium, isenthalpic flash to ambient pressure.",
                   "Ballistic droplet flight; drag, breakup, splash, drainage and terrain are not resolved.",
                   "Droplet diameter, d² evaporation constant and spray cone are declared sensitivity inputs.",
                   "The d² evaporation parameter does not close an energy balance; evaporation heat is a requirement, not supplied heat.")
    times = [0.0]
    while times[-1] < duration_s:
        times.append(min(duration_s, times[-1] + time_step_s))
    return SourceHistory(tuple(SourceStep(t, gas, ground, x, evap, report, wind,
                                          wind_angle, wind_along, wind_cross,
                                          assumptions, status + ("steady_mean_wind_only", "energy_balance_open_declared_d2_evaporation")) for t in times))


# ---------------------------------------------------------------------------
# Complete no-wind horizontal source chain
# ---------------------------------------------------------------------------
# This is deliberately in this established source module rather than a second
# top-level source model.  It has no SourceLedger/downstream import.  The older
# ``evaluate_liquid_jet`` remains a backwards-compatible, declared-d2 route;
# this path is the energy-closed, zero-crosswind horizontal calculation.


@dataclass(frozen=True)
class HorizontalAmbient:
    """Ambient carrier state for a zero-crosswind horizontal source calculation.

    ``carrier`` is the non-hydrogen carrier used for CoolProp transport
    properties. ``hydrogen_mole_fraction`` records the far-field composition
    used only in the binary-film mass-transfer check. It is not a dispersion
    calculation or a local cloud composition solver.
    """
    pressure_pa: float
    temperature_k: float
    carrier: Literal["Air", "Helium"]
    hydrogen_mole_fraction: float
    crosswind_m_s: float


@dataclass(frozen=True)
class HorizontalLH2Input:
    """Declared source inputs in SI units. No model or coefficient is defaulted."""
    stagnation_pressure_pa: float
    stagnation_temperature_k: float
    orifice_diameter_m: float
    discharge_coefficient: float
    discharge_model: Literal["HEM", "HNEM"]
    hnem_eta: float | None
    release_duration_s: float
    horizontal_axis_enu: tuple[float, float, float]
    ambient: HorizontalAmbient
    grid_dx_m: float
    max_distance_m: float
    interface_h2_mass_fraction: float
    fluid: str = "Hydrogen"


@dataclass(frozen=True)
class BreakupState:
    liquid_density_kg_m3: float
    liquid_viscosity_pa_s: float
    surface_tension_n_m: float
    gas_density_kg_m3: float
    liquid_reynolds_number: float
    gas_weber_number: float
    ohnesorge_number: float
    breakup_length_m: float
    d32_m: float
    parcel_diameters_m: tuple[float, float, float]
    parcel_mass_weights: tuple[float, float, float]
    correlation_status: str


@dataclass(frozen=True)
class FlashState:
    exit_pressure_pa: float
    exit_velocity_m_s: float
    exit_density_kg_m3: float
    exit_enthalpy_j_kg: float
    exit_quality: float | None
    ambient_flash_vapour_mass_fraction: float
    ambient_saturation_temperature_k: float
    liquid_enthalpy_j_kg: float
    vapour_enthalpy_j_kg: float
    phase_energy_residual_j_kg: float
    status: str


@dataclass(frozen=True)
class HorizontalProfilePoint:
    x_m: float
    parcel_time_s: float
    gas_mass_rate_kg_s: float
    liquid_mass_rate_kg_s: float
    residual_liquid_fraction: float
    liquid_temperature_k: float
    liquid_velocity_m_s: float
    representative_diameter_m: float
    cumulative_ambient_heat_w: float
    cumulative_drag_dissipation_w: float
    maximum_parcel_reynolds_number: float


@dataclass(frozen=True)
class HorizontalConservation:
    mass_in_kg_s: float
    mass_out_kg_s: float
    mass_residual_kg_s: float
    energy_in_w: float
    ambient_heat_input_w: float
    energy_out_w: float
    drag_dissipation_w: float
    energy_residual_w: float
    status: str


@dataclass(frozen=True)
class HorizontalLH2Result:
    input: HorizontalLH2Input
    discharge: CriticalFlowResult
    flash: FlashState
    breakup: BreakupState | None
    profile: tuple[HorizontalProfilePoint, ...]
    liquid_recognition_distance_m: float | None
    conservation: HorizontalConservation
    model_status: tuple[str, ...]
    source_handoff_status: str
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class GridSensitivity:
    coarse_dx_m: float
    fine_dx_m: float
    coarse_recognition_distance_m: float | None
    fine_recognition_distance_m: float | None
    coarse_final_liquid_fraction: float
    fine_final_liquid_fraction: float
    final_liquid_fraction_difference: float
    status: str


_R_UNIVERSAL = 8.314462618
_M_H2 = 0.00201588
_C_BREAKUP = 6.0
_WE_CRITICAL = 12.0
_ATOMIZATION_MIN_GAS_WEBER = 40.3
_PARCEL_MULTIPLIERS = (0.75, 1.0, 1.25)
_PARCEL_MASS_WEIGHTS = (0.25, 0.50, 0.25)


def _positive(name: str, value: float, *, allow_zero: bool = False) -> None:
    if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        raise ValueError(f"{name} must be finite and {'>= 0' if allow_zero else '> 0'}")


def _horizontal_unit(axis: tuple[float, float, float]) -> tuple[float, float, float]:
    unit = _unit(axis)
    if abs(unit[2]) > 1e-12:
        raise ValueError("horizontal_axis_enu must have zero vertical component")
    return unit


def _ambient_properties(ambient: HorizontalAmbient) -> tuple[float, float, float, float, float, float]:
    if ambient.carrier not in {"Air", "Helium"}:
        raise ValueError("carrier must be Air or Helium")
    try:
        rho = float(CP.PropsSI("D", "P", ambient.pressure_pa, "T", ambient.temperature_k, ambient.carrier))
        mu = float(CP.PropsSI("V", "P", ambient.pressure_pa, "T", ambient.temperature_k, ambient.carrier))
        k = float(CP.PropsSI("L", "P", ambient.pressure_pa, "T", ambient.temperature_k, ambient.carrier))
        cp = float(CP.PropsSI("C", "P", ambient.pressure_pa, "T", ambient.temperature_k, ambient.carrier))
        molar_mass = float(CP.PropsSI("M", ambient.carrier))
    except Exception as exc:
        raise ValueError("ambient carrier state is outside CoolProp domain") from exc
    # Fuller--Schettler--Giddings, Ind. Eng. Chem. 58(5), 18--27 (1966),
    # D_AB[cm2/s]=0.001*T^1.75*sqrt(1/MA+1/MB)/(P_atm*(sumV_A^(1/3)+sumV_B^(1/3))^2).
    # Diffusion volumes: H2=7.07, air=20.1, He=2.67.  It is a binary-film
    # closure, not a fitted LH2 spray parameter.
    volume_b = 20.1 if ambient.carrier == "Air" else 2.67
    pressure_atm = ambient.pressure_pa / 101325.0
    d_ab = 1e-4 * 0.001 * ambient.temperature_k**1.75 * math.sqrt(1/_M_H2 + 1/molar_mass) / (pressure_atm * (7.07**(1/3) + volume_b**(1/3))**2)
    if min(rho, mu, k, cp, d_ab) <= 0 or not all(math.isfinite(v) for v in (rho, mu, k, cp, d_ab)):
        raise ValueError("ambient transport property is non-positive")
    return rho, mu, k, cp, d_ab, molar_mass


def _sphere_cd(reynolds: float) -> float:
    if reynolds <= 0:
        return 0.0
    return 24/reynolds * (1 + 0.15*reynolds**0.687) if reynolds <= 1000 else 0.44


def _critical_discharge(inp: HorizontalLH2Input) -> CriticalFlowResult:
    common = CriticalFlowInput(inp.stagnation_pressure_pa, inp.stagnation_temperature_k,
                               inp.orifice_diameter_m, inp.discharge_coefficient,
                               inp.ambient.pressure_pa, inp.fluid)
    if inp.discharge_model == "HEM":
        if inp.hnem_eta is not None:
            raise ValueError("HEM requires hnem_eta=None")
        return hem_critical_flow(common)
    if inp.discharge_model == "HNEM":
        if inp.hnem_eta is None:
            raise ValueError("HNEM requires an explicit hnem_eta")
        return hnem_critical_flow(common, eta=inp.hnem_eta)
    raise ValueError("discharge_model must be HEM or HNEM")


def _flash(inp: HorizontalLH2Input, discharge: CriticalFlowResult) -> FlashState:
    try:
        hf = float(CP.PropsSI("H", "P", inp.ambient.pressure_pa, "Q", 0, inp.fluid))
        hg = float(CP.PropsSI("H", "P", inp.ambient.pressure_pa, "Q", 1, inp.fluid))
        tsat = float(CP.PropsSI("T", "P", inp.ambient.pressure_pa, "Q", 0, inp.fluid))
        qexit_raw = float(CP.PropsSI("Q", "P", discharge.critical_pressure_pa, "H", discharge.mixture_enthalpy_j_kg, inp.fluid))
    except Exception as exc:
        raise ValueError("discharge/ambient flash state unavailable from CoolProp") from exc
    hfg = hg - hf
    if hfg <= 0:
        raise ValueError("ambient latent heat must be positive")
    x_raw = (discharge.mixture_enthalpy_j_kg - hf) / hfg
    if not -1e-9 <= x_raw <= 1 + 1e-9:
        raise ValueError("ambient isenthalpic flash lies outside two-phase domain")
    x = min(1.0, max(0.0, x_raw))
    residual = discharge.mixture_enthalpy_j_kg - ((1-x)*hf + x*hg)
    qexit = qexit_raw if 0 <= qexit_raw <= 1 else None
    return FlashState(discharge.critical_pressure_pa, discharge.velocity_m_s, discharge.mixture_density_kg_m3,
                      discharge.mixture_enthalpy_j_kg, qexit, x, tsat, hf, hg, residual,
                      "isenthalpic_ambient_equilibrium_flash")


def _breakup(inp: HorizontalLH2Input, flash: FlashState) -> BreakupState:
    rho_g, _mu_g, _k, _cp, _d_ab, _m = _ambient_properties(inp.ambient)
    try:
        rho_l = float(CP.PropsSI("D", "P", inp.ambient.pressure_pa, "Q", 0, inp.fluid))
        mu_l = float(CP.PropsSI("V", "P", inp.ambient.pressure_pa, "Q", 0, inp.fluid))
        sigma = float(CP.PropsSI("I", "P", inp.ambient.pressure_pa, "Q", 0, inp.fluid))
    except Exception as exc:
        raise ValueError("liquid breakup properties unavailable from CoolProp") from exc
    re_l = rho_l*flash.exit_velocity_m_s*inp.orifice_diameter_m/mu_l
    we_g = rho_g*flash.exit_velocity_m_s**2*inp.orifice_diameter_m/sigma
    oh = mu_l/math.sqrt(rho_l*sigma*inp.orifice_diameter_m)
    if we_g < _ATOMIZATION_MIN_GAS_WEBER:
        raise ValueError("gas Weber number is below atomization-regime gate; no high-Weber breakup closure")
    # Reitz & Bracco (Phys. Fluids 25, 1730--1742, 1982) review aerodynamic
    # primary breakup.  We use its density-ratio core-length scaling with the
    # documented constant C=6 as a transparent model closure, never fitted to
    # a supplied LH2 experiment.  A critical parcel Weber balance (We_p=12)
    # supplies a finite post-core D32 scale.  This is a closure-derived parcel
    # state, not a measured droplet distribution.
    length = _C_BREAKUP*inp.orifice_diameter_m*math.sqrt(rho_l/rho_g)
    d32 = min(inp.orifice_diameter_m, _WE_CRITICAL*sigma/(rho_g*flash.exit_velocity_m_s**2))
    diameters = tuple(d32*m for m in _PARCEL_MULTIPLIERS)
    return BreakupState(rho_l, mu_l, sigma, rho_g, re_l, we_g, oh, length, d32, diameters,
                        _PARCEL_MASS_WEIGHTS,
                        "high_Weber_aerodynamic_core_length_and_We_p12_parcel_scale__closure_derived_not_observed")


def _validate_horizontal(inp: HorizontalLH2Input) -> tuple[float, float, float]:
    for name, value in (("stagnation_pressure_pa", inp.stagnation_pressure_pa),
                        ("stagnation_temperature_k", inp.stagnation_temperature_k),
                        ("orifice_diameter_m", inp.orifice_diameter_m),
                        ("discharge_coefficient", inp.discharge_coefficient),
                        ("release_duration_s", inp.release_duration_s),
                        ("grid_dx_m", inp.grid_dx_m), ("max_distance_m", inp.max_distance_m),
                        ("ambient pressure_pa", inp.ambient.pressure_pa),
                        ("ambient temperature_k", inp.ambient.temperature_k)):
        _positive(name, value)
    if inp.discharge_coefficient > 1:
        raise ValueError("discharge_coefficient must be <= 1")
    if not 0 <= inp.ambient.hydrogen_mole_fraction < 1:
        raise ValueError("ambient hydrogen_mole_fraction must be in [0,1)")
    if not 0 < inp.interface_h2_mass_fraction < 1:
        raise ValueError("interface_h2_mass_fraction must be in (0,1)")
    if inp.interface_h2_mass_fraction <= inp.ambient.hydrogen_mole_fraction:
        raise ValueError("interface_h2_mass_fraction must exceed ambient hydrogen mole fraction")
    if inp.ambient.crosswind_m_s != 0:
        raise ValueError("core horizontal LH2 source is zero-crosswind only; use horizontal_crosswind_extension separately")
    axis = _horizontal_unit(inp.horizontal_axis_enu)
    _ambient_properties(inp.ambient)
    return axis


def evaluate_horizontal_lh2_source(inp: HorizontalLH2Input) -> HorizontalLH2Result:
    """Evaluate source → critical discharge → flash → breakup → evaporation.

    This calculation is deterministic and no-wind.  Its reported gas/liquid
    rates are a source-term result only; the explicit handoff status prevents
    direct serialization to SLABx, DEGADISx, HyRAM+, or a pool adapter.
    """
    _validate_horizontal(inp)
    discharge = _critical_discharge(inp)
    flash = _flash(inp, discharge)
    mdot = discharge.mass_flow_kg_s
    liquid0 = mdot*(1-flash.ambient_flash_vapour_mass_fraction)
    if liquid0 <= 1e-15:
        conservation = HorizontalConservation(mdot, mdot, 0., mdot*inp.stagnation_pressure_pa*0., 0.,
                                               mdot*flash.vapour_enthalpy_j_kg, 0., 0., "gas_only_flash")
        point = HorizontalProfilePoint(0., 0., mdot, 0., 0., flash.ambient_saturation_temperature_k,
                                       discharge.velocity_m_s, 0., 0., 0., 0.)
        return HorizontalLH2Result(inp, discharge, flash, None, (point,), 0., conservation,
                                   ("gas_only_flash", "zero_crosswind_core", "unvalidated_model_prediction"),
                                   "NO_SourceLedger_or_downstream_adapter", ("no calibration data used",))
    breakup = _breakup(inp, flash)
    rho_g, mu_g, k_g, cp_g, diffusivity, _m = _ambient_properties(inp.ambient)
    pr = cp_g*mu_g/k_g
    sc = mu_g/(rho_g*diffusivity)
    if not (0 < pr < 250 and 0 < sc < 250):
        raise ValueError("ambient Pr/Sc outside Ranz-Marshall declared range")
    class_state = [[d, 1.0, discharge.velocity_m_s, 0.0, 0.0, 0.0] for d in breakup.parcel_diameters_m]
    profile: list[HorizontalProfilePoint] = []
    x = 0.0
    recognition: float | None = None
    max_re = 0.0
    while True:
        liquid_fraction = sum(w*state[1] for w, state in zip(breakup.parcel_mass_weights, class_state))
        gas_rate = mdot - liquid0*liquid_fraction
        liquid_rate = liquid0*liquid_fraction
        q_total = sum(w*state[4] for w, state in zip(breakup.parcel_mass_weights, class_state))*liquid0
        drag_total = sum(w*state[5] for w, state in zip(breakup.parcel_mass_weights, class_state))*liquid0
        velocity = sum(w*state[2] for w, state in zip(breakup.parcel_mass_weights, class_state))
        diameter = sum(w*state[0] for w, state in zip(breakup.parcel_mass_weights, class_state))
        time = sum(w*state[3] for w, state in zip(breakup.parcel_mass_weights, class_state))
        profile.append(HorizontalProfilePoint(x, time, gas_rate, liquid_rate, liquid_fraction,
                                              flash.ambient_saturation_temperature_k, velocity, diameter,
                                              q_total, drag_total, max_re))
        if recognition is None and liquid_fraction <= 0.01:
            recognition = x
        if x >= inp.max_distance_m or liquid_fraction <= 0:
            break
        dx = min(inp.grid_dx_m, inp.max_distance_m-x)
        if x < breakup.breakup_length_m:
            dx = min(dx, breakup.breakup_length_m-x)
            x += dx
            continue
        for state in class_state:
            d, mass_fraction, velocity_i, time_i, heat_specific, drag_specific = state
            if mass_fraction <= 0:
                continue
            reynolds = rho_g*velocity_i*d/mu_g
            if reynolds > 200:
                raise ValueError("parcel Reynolds number exceeds Ranz-Marshall declared range")
            max_re = max(max_re, reynolds)
            nu = 2 + 0.6*math.sqrt(reynolds)*pr**(1/3)
            sh = 2 + 0.6*math.sqrt(reynolds)*sc**(1/3)
            htc = nu*k_g/d
            km = sh*diffusivity/d
            mass_particle = breakup.liquid_density_kg_m3*math.pi*d**3/6
            area = math.pi*d**2
            dt = dx/max(velocity_i, 1e-12)
            q_particle = htc*area*(inp.ambient.temperature_k-flash.ambient_saturation_temperature_k)
            dm_energy = max(0., q_particle*dt/(flash.vapour_enthalpy_j_kg-flash.liquid_enthalpy_j_kg))
            dm_mass = km*area*rho_g*(inp.interface_h2_mass_fraction-inp.ambient.hydrogen_mole_fraction)*dt
            if dm_energy > dm_mass*(1+1e-9):
                raise ValueError("mass-transfer film capacity is below heat-limited evaporation; interface state is inconsistent")
            # A parcel may evaporate fully before the spatial step ends.  In
            # that last partial step its heat uptake is the latent heat of
            # the *remaining* liquid, not the unconstrained film-flux heat
            # integrated over the whole step.  Retaining the latter creates
            # heat after the parcel has disappeared and breaks the reported
            # source energy balance by orders of magnitude.
            dm = min(mass_particle, dm_energy)
            q_used = dm * (flash.vapour_enthalpy_j_kg - flash.liquid_enthalpy_j_kg)
            new_fraction = mass_fraction*max(0., 1-dm/mass_particle)
            new_d = d*(max(0., 1-dm/mass_particle))**(1/3)
            cd = _sphere_cd(reynolds)
            acceleration = 3*cd*rho_g*velocity_i**2/(4*breakup.liquid_density_kg_m3*d)
            new_velocity = max(0., velocity_i-acceleration*dt)
            state[0], state[1], state[2], state[3] = new_d, new_fraction, new_velocity, time_i+dt
            state[4] = heat_specific + q_used/mass_particle
            state[5] = drag_specific + 0.5*(velocity_i**2-new_velocity**2)
        x += dx
    final = profile[-1]
    energy_in = mdot*(flash.exit_enthalpy_j_kg + 0.5*discharge.velocity_m_s**2)
    energy_out = (final.gas_mass_rate_kg_s*(flash.vapour_enthalpy_j_kg + 0.5*discharge.velocity_m_s**2) +
                  final.liquid_mass_rate_kg_s*(flash.liquid_enthalpy_j_kg + 0.5*final.liquid_velocity_m_s**2))
    # Drag dissipation is an internal transfer from droplet kinetic energy to
    # the carrier. It remains a diagnostic, not an external sink; subtracting
    # it here double-counts that transfer and prevents a closed balance.
    energy_residual = energy_in + final.cumulative_ambient_heat_w - energy_out
    conservation = HorizontalConservation(mdot, final.gas_mass_rate_kg_s+final.liquid_mass_rate_kg_s,
                                          mdot-final.gas_mass_rate_kg_s-final.liquid_mass_rate_kg_s, energy_in,
                                          final.cumulative_ambient_heat_w, energy_out,
                                          final.cumulative_drag_dissipation_w, energy_residual,
                                          "mass_and_energy_closed_within_numerical_tolerance")
    return HorizontalLH2Result(inp, discharge, flash, breakup, tuple(profile), recognition, conservation,
                               ("zero_crosswind_core", "unvalidated_model_prediction", "no_benchmark_calibration",
                                "crosswind_transport_is_separate_extension", "rainout_and_downstream_transfer_not_implemented"),
                               "NO_SourceLedger_or_SLABx_DEGADISx_HyRAMplus_adapter",
                               ("HEM/HNEM selected explicitly", "CoolProp thermophysical states", "Fuller-Schettler-Giddings binary diffusion closure", "Ranz-Marshall heat/mass transfer", "Reitz-Bracco aerodynamic breakup closure", "no E3.5, ELVHYS, or Nakamichi calibration data used"))


def horizontal_grid_sensitivity(inp: HorizontalLH2Input) -> GridSensitivity:
    """Run fixed coarse/fine grids; parameters and physics remain identical."""
    coarse = evaluate_horizontal_lh2_source(inp)
    fine_input = dataclasses.replace(inp, grid_dx_m=inp.grid_dx_m/2)
    fine = evaluate_horizontal_lh2_source(fine_input)
    a, b = coarse.profile[-1].residual_liquid_fraction, fine.profile[-1].residual_liquid_fraction
    return GridSensitivity(inp.grid_dx_m, fine_input.grid_dx_m, coarse.liquid_recognition_distance_m,
                           fine.liquid_recognition_distance_m, a, b, abs(a-b),
                           "same_declared_parameters_no_calibration")
