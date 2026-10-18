"""Documented LH2 source-term chain: tank -> pipe -> nozzle -> droplets -> ground.

The implementation is deliberately independent from SLABx, DEGADISx, pool,
or ledger adapters.  It follows PRESLHY D6.5 §3.3 for the tank/line/nozzle
interfaces, Alexandros Venetsanos (2018) for the HEM/HNEM critical-flow
selection, Henk Witlox et al. (2007) Eqs. (1)--(12) for selectable SMD
correlations, and Rescigno/TNO for evaporation and ground interception.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import CoolProp.CoolProp as CP

from .horizontal_crosswind_extension import HorizontalCrosswindInput, integrate_horizontal_crosswind
from .lh2_critical_flow import CriticalFlowInput, CriticalFlowResult, hem_critical_flow, hnem_critical_flow
from .lh2_jet_source import wind_from_bearing_to_vector
from .rescigno_baseline import ExitState, evaluate_rescigno_2025


G = 9.80665


@dataclass(frozen=True)
class TankState:
    pressure_pa: float
    temperature_k: float
    volume_m3: float
    vapour_quality: float = 0.0
    wall_heat_input_w: float = 0.0
    fluid: str = "Hydrogen"


@dataclass(frozen=True)
class PipeSection:
    length_m: float
    diameter_m: float
    roughness_m: float = 1.5e-6
    resistance_k: float = 0.0
    wall_temperature_k: float | None = None
    wall_thickness_m: float = 0.002
    wall_density_kg_m3: float = 7850.0
    wall_heat_capacity_j_kg_k: float = 500.0
    external_heat_transfer_w_m2_k: float = 5.0
    internal_heat_transfer_w_m2_k: float = 100.0


@dataclass(frozen=True)
class NozzleGeometry:
    diameter_m: float
    length_m: float
    height_m: float
    direction_enu: tuple[float, float, float] = (1.0, 0.0, 0.0)
    discharge_coefficient: float = 1.0
    resistance_k: float = 0.0


@dataclass(frozen=True)
class AmbientState:
    pressure_pa: float = 101325.0
    temperature_k: float = 288.15
    wind_speed_m_s: float = 0.0
    wind_from_bearing_deg: float | None = None


@dataclass(frozen=True)
class ModelChoices:
    phase_model: Literal["HEM", "HNEM"] = "HEM"
    hnem_eta: float | None = None
    fictitious_nozzle: Literal["none", "mach1_adiabatic", "momentum_adiabatic"] = "momentum_adiabatic"
    droplet_correlation: Literal["rescigno_yellow_book", "henk2007_phaseII", "henk2007_weber_ccps"] = "rescigno_yellow_book"
    rescigno_quality_path: Literal["printed_equation", "table3_inferred_omits_hv_delta"] = "printed_equation"
    distribution: Literal["single_smd", "henk2007_three_class_sensitivity"] = "single_smd"


@dataclass(frozen=True)
class IntegratedSourceInput:
    tank: TankState
    pipe_sections: tuple[PipeSection, ...]
    nozzle: NozzleGeometry
    ambient: AmbientState
    choices: ModelChoices = ModelChoices()
    duration_s: float = 1.0
    time_step_s: float = 0.1


@dataclass(frozen=True)
class PipeState:
    pressure_pa: float
    temperature_k: float
    enthalpy_j_kg: float
    density_kg_m3: float
    velocity_m_s: float
    darcy_friction_factor: float
    wall_heat_w: float
    wall_temperature_k: float


@dataclass(frozen=True)
class FictitiousNozzleState:
    pressure_pa: float
    temperature_k: float
    density_kg_m3: float
    velocity_m_s: float
    area_m2: float
    diameter_m: float
    vapour_quality: float
    model: str


@dataclass(frozen=True)
class DropletState:
    smd_m: float
    correlation: str
    regime: str
    distribution_identifier: str
    class_diameters_m: tuple[float, ...]
    class_mass_weights: tuple[float, ...]
    superheat_k: float

@dataclass(frozen=True)
class DropletClassOutcome:
    diameter_m: float; mass_weight: float; postflash_liquid_mass_flow_kg_s: float
    airborne_evaporated_mass_flow_kg_s: float; ground_liquid_mass_flow_kg_s: float
    impact_position_m: tuple[float,float,float] | None; flight_time_s: float | None; complete_evaporation: bool
    impact_velocity_m_s: tuple[float,float,float] | None = None


@dataclass(frozen=True)
class IntegratedSourceStep:
    time_s: float
    tank: TankState
    critical: CriticalFlowResult
    pipe: tuple[PipeState, ...]
    real_nozzle: PipeState
    fictitious_nozzle: FictitiousNozzleState | None
    total_mass_flow_kg_s: float
    gas_mass_flow_kg_s: float
    airborne_liquid_mass_flow_kg_s: float
    ground_liquid_mass_flow_kg_s: float
    vapour_quality: float
    velocity_vector_m_s: tuple[float, float, float]
    droplet: DropletState
    evaporation_fraction_of_postflash_liquid: float
    impact_position_m: tuple[float, float, float] | None
    mass_residual_kg_s: float
    energy_residual_w: float
    regime: tuple[str, ...]
    assumptions: tuple[str, ...]
    status: tuple[str, ...]
    droplet_class_outcomes: tuple[DropletClassOutcome, ...] = ()


@dataclass(frozen=True)
class IntegratedSourceHistory:
    steps: tuple[IntegratedSourceStep, ...]
    model_name: str = "lh2_integrated_source_term_v1"
    references: tuple[str, ...] = (
        "PRESLHY D6.5 (2021), §3.3, Eqs. (3.15)-(3.25).",
        "Venetsanos (2018), HEM/HNEM choked-flow algorithm A.",
        "Witlox et al. (2007), Eqs. (1)-(12), SMD correlations.",
        "Rescigno et al. (2025), Eqs. (1)-(13); TNO Yellow Book §2.5.3.7.",
    )


def _positive(name: str, value: float, zero: bool = False) -> None:
    if not math.isfinite(value) or value < 0 or (not zero and value == 0):
        raise ValueError(f"{name} must be finite and {'>= 0' if zero else '> 0'}")


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    if len(v) != 3 or not all(math.isfinite(x) for x in v):
        raise ValueError("nozzle direction must be three finite ENU components")
    n = math.sqrt(sum(x*x for x in v))
    if n == 0: raise ValueError("nozzle direction must not be zero")
    return tuple(x/n for x in v)  # type: ignore[return-value]


def _mixture_props(p: float, t: float, q: float, fluid: str) -> tuple[float, float, float]:
    """HEM mixture rho/h/s; input q is only used when P,T is saturated."""
    if not 0 <= q <= 1: raise ValueError("tank vapour quality must be in [0,1]")
    try:
        ts = CP.PropsSI("T", "P", p, "Q", 0, fluid)
        if abs(t-ts) < 0.03:
            rl, rv = CP.PropsSI("D", "P", p, "Q", 0, fluid), CP.PropsSI("D", "P", p, "Q", 1, fluid)
            hl, hv = CP.PropsSI("H", "P", p, "Q", 0, fluid), CP.PropsSI("H", "P", p, "Q", 1, fluid)
            sl, sv = CP.PropsSI("S", "P", p, "Q", 0, fluid), CP.PropsSI("S", "P", p, "Q", 1, fluid)
            return 1/((1-q)/rl+q/rv), (1-q)*hl+q*hv, (1-q)*sl+q*sv
        return CP.PropsSI("D", "P", p, "T", t, fluid), CP.PropsSI("H", "P", p, "T", t, fluid), CP.PropsSI("S", "P", p, "T", t, fluid)
    except Exception as exc:
        raise ValueError("thermodynamic state is unsupported by selected fluid/EOS") from exc


def _colebrook(reynolds: float, roughness_m: float, diameter_m: float) -> float:
    if reynolds <= 0: return 0.0
    if reynolds < 2300: return 64/reynolds
    value = 0.02
    for _ in range(30):
        new = 1/(-2*math.log10(roughness_m/(3.7*diameter_m)+2.51/(reynolds*math.sqrt(value))))**2
        if abs(new-value) < 1e-10: return new
        value = new
    return value


def _pipe_pass(inp: IntegratedSourceInput, mass_flow: float, tank: TankState,
               direction: tuple[float, float, float]) -> tuple[tuple[PipeState, ...], float]:
    """D6.5 (3.17)-(3.21) lumped finite-volume pass; returns outlet pressure."""
    rho, h, _s = _mixture_props(tank.pressure_pa, tank.temperature_k, tank.vapour_quality, tank.fluid)
    p, t = tank.pressure_pa, tank.temperature_k
    states: list[PipeState] = []
    # A nozzle loss belongs to the line momentum balance, not to Cd.  It is
    # optional so existing ideal-nozzle use remains unchanged.  When supplied,
    # the short final restriction is evaluated at its actual bore.
    sections = inp.pipe_sections
    if inp.nozzle.resistance_k > 0:
        sections = (*sections, PipeSection(inp.nozzle.length_m, inp.nozzle.diameter_m,
                                           resistance_k=inp.nozzle.resistance_k))
    for section in sections:
        area = math.pi*section.diameter_m**2/4
        try:
            mu = CP.PropsSI("V", "P", p, "T", t, tank.fluid)
        except Exception:
            mu = 1.5e-5
        u = mass_flow/(rho*area)
        re = rho*abs(u)*section.diameter_m/max(mu, 1e-12)
        f = _colebrook(re, section.roughness_m, section.diameter_m)
        dp = (f*section.length_m/section.diameter_m + section.resistance_k)*rho*u*u/2
        p2 = p-dp
        if p2 <= inp.ambient.pressure_pa:
            return tuple(states), p2
        tw = section.wall_temperature_k if section.wall_temperature_k is not None else inp.ambient.temperature_k
        wall_area = math.pi*section.diameter_m*section.length_m
        qin = section.internal_heat_transfer_w_m2_k*wall_area*(tw-t)
        h2 = h + qin/max(mass_flow, 1e-12)
        try:
            t2 = CP.PropsSI("T", "P", p2, "H", h2, tank.fluid)
            q2 = CP.PropsSI("Q", "P", p2, "H", h2, tank.fluid)
            if 0 <= q2 <= 1: t2 = CP.PropsSI("T", "P", p2, "Q", 0, tank.fluid)
            rho2 = CP.PropsSI("D", "P", p2, "H", h2, tank.fluid)
        except Exception:
            t2, rho2 = t, rho
        wall_mass = math.pi/4*((section.diameter_m+2*section.wall_thickness_m)**2-section.diameter_m**2)*section.length_m*section.wall_density_kg_m3
        qout = section.external_heat_transfer_w_m2_k*math.pi*(section.diameter_m+2*section.wall_thickness_m)*section.length_m*(inp.ambient.temperature_k-tw)
        tw2 = tw + inp.time_step_s*(qout-qin)/max(wall_mass*section.wall_heat_capacity_j_kg_k, 1e-12)
        states.append(PipeState(p2, t2, h2, rho2, mass_flow/(rho2*area), f, qin, tw2))
        p, t, rho, h = p2, t2, rho2, h2
    return tuple(states), p


def _critical(inp: IntegratedSourceInput, tank: TankState) -> CriticalFlowResult:
    ci = CriticalFlowInput(tank.pressure_pa, tank.temperature_k, inp.nozzle.diameter_m,
                           inp.nozzle.discharge_coefficient, inp.ambient.pressure_pa, tank.fluid)
    if inp.choices.phase_model == "HEM":
        if inp.choices.hnem_eta is not None: raise ValueError("HEM requires hnem_eta=None")
        return hem_critical_flow(ci)
    if inp.choices.hnem_eta is None: raise ValueError("HNEM requires an explicit hnem_eta")
    return hnem_critical_flow(ci, eta=inp.choices.hnem_eta)


def _pif_mass_flow(inp: IntegratedSourceInput, tank: TankState, critical: CriticalFlowResult,
                   direction: tuple[float, float, float]) -> tuple[float, tuple[PipeState, ...]]:
    """Possible/impossible line search to the nozzle critical pressure.

    The pipe outlet is the upstream state of the real nozzle.  Comparing it
    with ambient pressure incorrectly lets a resistive nozzle collapse the
    line to ambient before the critical restriction is applied.  The target is
    therefore the critical pressure associated with the selected HEM/HNEM
    branch; an optional, documented nozzle K is included by ``_pipe_pass``.
    """
    if not inp.pipe_sections:
        return critical.mass_flow_kg_s, ()
    cap = critical.mass_flow_kg_s
    states, pexit = _pipe_pass(inp, cap, tank, direction)
    target = max(inp.ambient.pressure_pa, critical.critical_pressure_pa)
    if pexit >= target: return cap, states
    lo, hi = 0.0, cap
    best: tuple[PipeState, ...] = ()
    for _ in range(60):
        mid = (lo+hi)/2
        states, pexit = _pipe_pass(inp, mid, tank, direction)
        if pexit >= target:
            lo, best = mid, states
        else:
            hi = mid
    if lo <= 1e-12: raise ValueError("PIF pipe search found no possible flow to back pressure")
    return lo, best


def _fictitious(inp: IntegratedSourceInput, real: PipeState, mdot: float, q: float) -> FictitiousNozzleState | None:
    if inp.choices.fictitious_nozzle == "none": return None
    fluid, pa = inp.tank.fluid, inp.ambient.pressure_pa
    hf, hg = CP.PropsSI("H", "P", pa, "Q", 0, fluid), CP.PropsSI("H", "P", pa, "Q", 1, fluid)
    htotal = real.enthalpy_j_kg + .5*real.velocity_m_s**2
    x = min(1., max(0., (htotal-hf)/(hg-hf)))
    hstatic = (1-x)*hf+x*hg
    rho_l, rho_v = CP.PropsSI("D", "P", pa, "Q", 0, fluid), CP.PropsSI("D", "P", pa, "Q", 1, fluid)
    rho = 1/((1-x)/rho_l+x/rho_v)
    # An HEM throat state may carry a static enthalpy which is below the
    # ambient-flash mixture enthalpy.  The D6.5 momentum-balance fictitious
    # route must then retain the real-nozzle momentum rather than invent a
    # zero-velocity, infinite-area pseudo nozzle.
    vel = max(real.velocity_m_s, math.sqrt(max(0., 2*(htotal-hstatic))))
    if inp.choices.fictitious_nozzle == "mach1_adiabatic":
        try: vel = CP.PropsSI("A", "P", pa, "Q", x, fluid)
        except Exception: pass
    area = mdot/max(rho*vel, 1e-15)
    return FictitiousNozzleState(pa, CP.PropsSI("T", "P", pa, "Q", 0, fluid), rho, vel, area,
                                  math.sqrt(4*area/math.pi), x, inp.choices.fictitious_nozzle)


def _henk_smd(inp: IntegratedSourceInput, real: PipeState, mdot: float) -> DropletState:
    """Witlox 2007 Eqs. (1)-(12); no empirical parameter is re-fitted."""
    fluid, pa, n = inp.tank.fluid, inp.ambient.pressure_pa, inp.nozzle
    rho_l = CP.PropsSI("D", "P", real.pressure_pa, "Q", 0, fluid)
    rho_v = CP.PropsSI("D", "P", real.pressure_pa, "Q", 1, fluid)
    mu_l = CP.PropsSI("V", "P", real.pressure_pa, "Q", 0, fluid)
    sigma = CP.PropsSI("I", "P", real.pressure_pa, "Q", 0, fluid)
    rho_a = CP.PropsSI("D", "P", pa, "T", inp.ambient.temperature_k, "Air")
    cp_l = CP.PropsSI("C", "P", real.pressure_pa, "Q", 0, fluid)
    hfg = CP.PropsSI("H", "P", real.pressure_pa, "Q", 1, fluid)-CP.PropsSI("H", "P", real.pressure_pa, "Q", 0, fluid)
    tsat = CP.PropsSI("T", "P", pa, "Q", 0, fluid)
    l_over_d = min(50., max(2., n.length_m/n.diameter_m))
    re = rho_l*real.velocity_m_s*n.diameter_m/mu_l
    we = rho_l*real.velocity_m_s**2*n.diameter_m/sigma
    dda = n.diameter_m*64.73*we**-.533*re**-.014*l_over_d**.114
    d_weber = sigma*12.5/(max(real.velocity_m_s**2*rho_a, 1e-18))
    h0 = _mixture_props(inp.tank.pressure_pa, inp.tank.temperature_k, inp.tank.vapour_quality, fluid)[1]
    vst = 1/_mixture_props(inp.tank.pressure_pa, inp.tank.temperature_k, inp.tank.vapour_quality, fluid)[0]
    psv = CP.PropsSI("P", "T", inp.tank.temperature_k, "Q", 1, fluid)
    ep = (- (h0-CP.PropsSI("H", "P", pa, "Q", 0, fluid)) - (psv-pa)*vst + (inp.tank.pressure_pa-psv)*vst
          if pa < psv else (inp.tank.pressure_pa-pa)*vst)
    ddf = .833e-3-.0734e-3*math.log(max(ep, 1.))
    superheat = real.temperature_k-tsat
    we_v = rho_v*real.velocity_m_s**2*n.diameter_m/sigma
    ja = cp_l*max(superheat, 0)/hfg*rho_l/rho_v
    phi = 1-math.exp(-2300*rho_v/rho_l)
    a, c = 55*we_v**(-1/7), 150*we_v**(-1/7)
    if inp.choices.droplet_correlation == "henk2007_weber_ccps":
        smd, regime = min(d_weber, ddf), "weber_ccps_eq1_to_4"
    elif ja*phi <= a:
        smd, regime = dda, "henk_mechanical_eq7"
    elif ja*phi < c:
        smd, regime = dda*(1-(1-1/2.4)*(ja*phi-a)/(c-a)), "henk_transition_eq9_to_12"
    else:
        smd, regime = min(dda/2.4, ddf), "henk_fully_flashing_eq1_to_3"
    return _distribution(max(smd, 1e-8), inp.choices.distribution, regime, inp.choices.droplet_correlation, superheat)


def _distribution(smd: float, mode: str, regime: str, correlation: str, superheat: float) -> DropletState:
    if mode == "single_smd":
        return DropletState(smd, correlation, regime, "single_representative_SMD", (smd,), (1.,), superheat)
    # Henk 2007 explicitly warns that an SMD-only approach hides distribution
    # rainout sensitivity.  This is a disclosed three-class quadrature around
    # SMD, not a fit or a claimed universal measured distribution.
    return DropletState(smd, correlation, regime, "Henk2007_SMD_three_class_sensitivity_unfitted", (0.5*smd, smd, 2*smd), (.2, .6, .2), superheat)


def _droplets(inp: IntegratedSourceInput, real: PipeState, mdot: float, q: float) -> tuple[DropletState, float, float, float]:
    if inp.choices.droplet_correlation.startswith("henk2007"):
        d = _henk_smd(inp, real, mdot)
        # Henk size selection is independent of the Rescigno flash-energy path;
        # use the literal thermodynamic flash fraction for mass partition.
        res = evaluate_rescigno_2025(ExitState(real.pressure_pa, real.temperature_k,
                                      math.pi*inp.nozzle.diameter_m**2/4, mdot, q,
                                      real.velocity_m_s, inp.nozzle.height_m, inp.tank.fluid),
                                      exit_velocity_mode="provided", flash_quality_mode=inp.choices.rescigno_quality_path)
        return d, res.flashed_quality, res.evaporation_kb_m2_s, res.liquid_density_kg_m3
    res = evaluate_rescigno_2025(ExitState(real.pressure_pa, real.temperature_k,
                                  math.pi*inp.nozzle.diameter_m**2/4, mdot, q,
                                  real.velocity_m_s, inp.nozzle.height_m, inp.tank.fluid),
                                  exit_velocity_mode="provided", flash_quality_mode=inp.choices.rescigno_quality_path)
    return _distribution(res.droplet_diameter_m, inp.choices.distribution, "rescigno_yellow_book_eq5", "rescigno_yellow_book", real.temperature_k-CP.PropsSI("T", "P", inp.ambient.pressure_pa, "Q", 0, inp.tank.fluid)), res.flashed_quality, res.evaporation_kb_m2_s, res.liquid_density_kg_m3


def _trajectory(inp: IntegratedSourceInput, drop: DropletState, liquid_mdot: float, rho_l: float,
                kb: float, velocity: tuple[float, float, float]) -> tuple[float, float, tuple[float, float, float] | None, float, float, tuple[DropletClassOutcome,...]]:
    if liquid_mdot <= 0: return 0., 0., None, 0., 0., ()
    rho_a = CP.PropsSI("D", "P", inp.ambient.pressure_pa, "T", inp.ambient.temperature_k, "Air")
    nu_a = CP.PropsSI("V", "P", inp.ambient.pressure_pa, "T", inp.ambient.temperature_k, "Air")/rho_a
    diffusivity = 7.5e-5
    sc = nu_a/diffusivity
    lv = CP.PropsSI("H", "P", inp.ambient.pressure_pa, "Q", 1, inp.tank.fluid)-CP.PropsSI("H", "P", inp.ambient.pressure_pa, "Q", 0, inp.tank.fluid)
    gas, ground, impact, evap_heat, eres, outcomes = 0., 0., None, 0., 0., []
    for d, w in zip(drop.class_diameters_m, drop.class_mass_weights):
        mass = liquid_mdot*w
        r = integrate_horizontal_crosswind(HorizontalCrosswindInput(mass, d, rho_l, velocity, inp.nozzle.height_m,
                                             rho_a, nu_a, kb, sc, inp.ambient.wind_speed_m_s,
                                             inp.ambient.wind_from_bearing_deg), max_time_s=120.)
        gas += r.airborne_gas_mass_flow_kg_s; ground += r.ground_liquid_mass_flow_kg_s
        if r.impact_position_m is not None: impact = r.impact_position_m
        outcomes.append(DropletClassOutcome(d,w,mass,r.airborne_gas_mass_flow_kg_s,r.ground_liquid_mass_flow_kg_s,r.impact_position_m,r.flight_time_s,r.impact_position_m is None and r.final_droplet_diameter_m <= 0.0,r.final_velocity_m_s if r.impact_position_m is not None else None))
    evap_heat = gas*lv
    return gas, ground, impact, evap_heat, liquid_mdot-gas-ground, tuple(outcomes)


def _advance_tank(tank: TankState, mdot: float, dt: float) -> TankState:
    rho, _h, s = _mixture_props(tank.pressure_pa, tank.temperature_k, tank.vapour_quality, tank.fluid)
    rho2 = rho-mdot*dt/tank.volume_m3
    if rho2 <= 0: raise ValueError("transient tank inventory depleted")
    s2 = s+tank.wall_heat_input_w*dt/max(rho*tank.volume_m3*tank.temperature_k, 1e-12)
    try:
        p2, t2 = CP.PropsSI("P", "D", rho2, "S", s2, tank.fluid), CP.PropsSI("T", "D", rho2, "S", s2, tank.fluid)
        q = CP.PropsSI("Q", "D", rho2, "S", s2, tank.fluid)
        if 0 <= q <= 1:
            # CriticalFlowInput is a P,T nozzle interface.  Move a saturated
            # tank endpoint infinitesimally onto its declared liquid/vapour
            # side so CoolProp does not reject an ambiguous P,T saturation
            # pair; the actual quality remains recorded in TankState.
            side = -0.05 if q <= .5 else .05
            t2 += side
        return TankState(p2, t2, tank.volume_m3, q if 0 <= q <= 1 else 0., tank.wall_heat_input_w, tank.fluid)
    except Exception:
        return tank


def evaluate_integrated_lh2_source(inp: IntegratedSourceInput) -> IntegratedSourceHistory:
    """Run steady (one step) or transient tank-to-ground source history.

    Every returned step closes total mass as total = gas + airborne liquid +
    ground liquid.  The evaporation heat is reported as an explicit ambient
    energy demand; no downstream pool or dispersion adapter is invoked.
    """
    for n, v in (("duration_s", inp.duration_s), ("time_step_s", inp.time_step_s), ("tank volume_m3", inp.tank.volume_m3), ("nozzle diameter_m", inp.nozzle.diameter_m), ("nozzle length_m", inp.nozzle.length_m), ("nozzle height_m", inp.nozzle.height_m)):
        _positive(n, v, zero=n == "nozzle height_m")
    if inp.tank.pressure_pa < inp.ambient.pressure_pa: raise ValueError("tank pressure must not be below ambient pressure")
    if not 0 < inp.nozzle.discharge_coefficient <= 1: raise ValueError("nozzle discharge coefficient must be in (0,1]")
    for s in inp.pipe_sections:
        for n, v in (("pipe length",s.length_m),("pipe diameter",s.diameter_m),("roughness",s.roughness_m),("resistance K",s.resistance_k)):_positive(n,v,zero=n in {"resistance K"})
    _positive("nozzle resistance K", inp.nozzle.resistance_k, zero=True)
    direction = _unit(inp.nozzle.direction_enu)
    wind = wind_from_bearing_to_vector(inp.ambient.wind_speed_m_s, inp.ambient.wind_from_bearing_deg)
    if inp.tank.pressure_pa == inp.ambient.pressure_pa:
        rho, h, _ = _mixture_props(inp.tank.pressure_pa, inp.tank.temperature_k, inp.tank.vapour_quality, inp.tank.fluid)
        real = PipeState(inp.tank.pressure_pa, inp.tank.temperature_k, h, rho, 0., 0., 0., inp.ambient.temperature_k)
        critical = CriticalFlowResult("NO_FLOW", 0., 0., inp.tank.pressure_pa, h, rho, 0., 0., None, "zero_driving_pressure")
        drop = DropletState(0., "not_applicable", "zero_release", "none", (), (), 0.)
        step = IntegratedSourceStep(0., inp.tank, critical, (), real, None, 0., 0., 0., 0., 0., (0.,0.,0.), drop, 0., None, 0., 0.,
                                    ("NO_FLOW",), ("no downstream adapter invoked",), ("zero_release", "mass_closed"))
        return IntegratedSourceHistory((step,))
    t, tank, steps = 0., inp.tank, []
    while t < inp.duration_s-1e-12:
        # Once the transient tank has reached the back-pressure neighbourhood,
        # there is no choked release to propagate.  Stop instead of forcing a
        # near-ambient state through an out-of-domain flash correlation.
        if tank.pressure_pa <= inp.ambient.pressure_pa*1.001:
            break
        critical = _critical(inp, tank)
        mdot, pipe = _pif_mass_flow(inp, tank, critical, direction)
        if pipe: real = pipe[-1]
        else:
            rho,h,_ = _mixture_props(tank.pressure_pa, tank.temperature_k,tank.vapour_quality,tank.fluid)
            area=math.pi*inp.nozzle.diameter_m**2/4
            real=PipeState(critical.critical_pressure_pa,tank.temperature_k,critical.mixture_enthalpy_j_kg,critical.mixture_density_kg_m3,mdot/(critical.mixture_density_kg_m3*area),0.,0.,inp.ambient.temperature_k)
        if real.pressure_pa <= inp.ambient.pressure_pa*1.01:
            break
        try: q = CP.PropsSI("Q","P",real.pressure_pa,"H",real.enthalpy_j_kg,tank.fluid)
        except Exception: q=tank.vapour_quality
        q=min(1.,max(0.,q))
        fict=_fictitious(inp,real,mdot,q)
        drop, phi, kb, rho_l = _droplets(inp,real,mdot,q)
        base_v=(fict.velocity_m_s if fict else real.velocity_m_s)
        velocity=tuple(base_v*x for x in direction)
        liquid_post=mdot*(1-phi)
        # Use the existing drag/gravity/evaporation integrator for each class.
        # It needs non-calm bearing; calm calls are represented by a zero-speed
        # bearing of 0 degrees after its zero-wind validation update.
        gas_ev, ground, impact, evap_heat, traj_res, outcomes = _trajectory(inp,drop,liquid_post,rho_l,kb,velocity)
        gas=mdot*phi+gas_ev
        airborne=max(0.,liquid_post-ground-gas_ev)
        mass_res=mdot-gas-ground-airborne
        lv = CP.PropsSI("H", "P", inp.ambient.pressure_pa, "Q", 1, tank.fluid)-CP.PropsSI("H", "P", inp.ambient.pressure_pa, "Q", 0, tank.fluid)
        # The trajectory supplies an explicit latent-heat demand, not a fitted
        # ambient heat-transfer rate.  This residual verifies that accounting.
        energy_res=evap_heat-gas_ev*lv
        status=("integrated_tank_pipe_nozzle_flash_droplet_ground", "pif_mass_flow_search", "mass_closed", "latent_evaporation_energy_closed", "steady_mean_wind")
        steps.append(IntegratedSourceStep(t,tank,critical,pipe,real,fict,mdot,gas,airborne,ground,phi,velocity,drop,
                                         gas_ev/max(liquid_post,1e-30),impact,mass_res,energy_res,
                                         (inp.choices.phase_model, inp.choices.droplet_correlation, inp.choices.fictitious_nozzle),
                                         ("no fitting to sensors/LFL/wind/source data", "ground liquid is source-term output only", "wall heat uses D6.5 lumped finite-volume closure"),status,outcomes))
        dt=min(inp.time_step_s,inp.duration_s-t)
        tank=_advance_tank(tank,mdot,dt) if inp.duration_s>inp.time_step_s else tank
        t+=dt
    return IntegratedSourceHistory(tuple(steps))
