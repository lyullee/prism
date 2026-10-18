"""Rescigno et al. (ESREL 2025) LH2 rainout baseline, without wind transport.

This is a direct, equation-labelled implementation of the published preliminary
integral model.  It accepts *nozzle exit* conditions, as the paper does; it
does not replace a discharge/nozzle-flow solver.  Crosswind/footprint movement
is deliberately absent rather than blended into the published baseline.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Literal
import CoolProp.CoolProp as CP

G, R = 9.80665, 8.314462618

@dataclass(frozen=True)
class ExitState:
    pressure_pa: float; temperature_k: float; area_m2: float; mass_flow_kg_s: float
    vapour_quality: float; velocity_m_s: float; release_height_m: float
    fluid: str = "Hydrogen"

@dataclass(frozen=True)
class BaselineResult:
    exit_velocity_m_s: float
    exit_density_kg_m3: float
    flashed_velocity_m_s: float; flashed_quality: float; flashed_area_m2: float
    flashed_radius_m: float; droplet_diameter_m: float; final_droplet_diameter_m: float
    gas_mass_flow_kg_s: float; rainout_mass_flow_kg_s: float; mass_residual_kg_s: float
    evaporation_kb_m2_s: float; trajectory_initial_droplet_diameter_m: float
    liquid_density_kg_m3: float
    maximum_rainout_diameter_m: float
    maximum_rainout_reynolds: float
    flashed_reynolds: float
    flashed_weber: float
    droplet_temperature_k: float
    droplet_temperature_converged: bool
    flash_quality_mode: str
    status: tuple[str, ...]


def _select_droplet_diameter(*, bf: float, uf: float, rho_lf: float,
                              liquid_kinematic_viscosity_m2_s: float,
                              surface_tension_n_m: float,
                              air_density_kg_m3: float,
                              exit_temperature_k: float,
                              normal_boiling_temperature_k: float,
                              droplet_diameter_coefficient: float) -> tuple[float, str, float, float]:
    """Apply Rescigno Eq. (5a)/(5b), returning diameter, branch, Re and We."""
    re_f = 2 * bf * uf / liquid_kinematic_viscosity_m2_s
    we_f = 2 * bf * uf**2 * rho_lf / surface_tension_n_m
    if we_f < re_f**(-0.45) * 1e6 and exit_temperature_k < 1.11 * normal_boiling_temperature_k:
        return (3.78 * bf * math.sqrt(1 + 3 * math.sqrt(we_f) / re_f),
                "eq5a_selected", re_f, we_f)
    return (droplet_diameter_coefficient * surface_tension_n_m / (uf**2 * air_density_kg_m3),
            "eq5b_selected", re_f, we_f)


def _maximum_rainout_diameter(*, rho_lf: float, air_density_kg_m3: float,
                              air_kinematic_viscosity_m2_s: float,
                              evaporation_kb_m2_s: float, release_height_m: float,
                              schmidt_number: float) -> float | None:
    """Rescigno Eq. (9), equivalent to Yellow Book Eq. (2.148)."""
    correction = 1 - 0.204 * schmidt_number**(1 / 3) * (
        rho_lf * G / (18 * air_density_kg_m3 * air_kinematic_viscosity_m2_s**2)
    )**0.5 * (
        72 * air_density_kg_m3 * air_kinematic_viscosity_m2_s * evaporation_kb_m2_s
        * release_height_m / (rho_lf * G)
    )**(3 / 8)
    if correction <= 0:
        # Eq. (9) is an approximation/screen, not a prerequisite of the
        # numerical Eq. (10)--(11) route.  A non-real expression therefore
        # means "screen unavailable", and must not reject an otherwise valid
        # physical release state.
        return None
    return 2 * (
        9 * air_density_kg_m3 * air_kinematic_viscosity_m2_s * evaporation_kb_m2_s
        * release_height_m / (2 * rho_lf * G) / correction
    )**0.25

def evaluate_rescigno_2025(exit: ExitState, *, ambient_pressure_pa: float = 101325.,
                           ambient_temperature_k: float = 288.15,
                           air_density_kg_m3: float = 1.225,
                           air_kinematic_viscosity_m2_s: float = 1.5e-5,
                           hydrogen_air_diffusivity_m2_s: float = 7.5e-5,
                           surface_tension_n_m: float = 0.002,
                            liquid_kinematic_viscosity_m2_s: float = 1.5e-7,
                            droplet_diameter_coefficient: float = 15.,
                            exit_velocity_mode: Literal["mass_closure", "provided"] = "mass_closure",
                            flash_quality_mode: Literal["printed_equation", "table3_inferred_omits_hv_delta"] = "printed_equation",
                            integrate_rainout: bool = True) -> BaselineResult:
    """Rescigno Eqs. (1)--(13), including both Eq. (5) branches and Eq. (9).

    The calculation starts at the *reported nozzle exit*, rather than solving a
    tank/nozzle discharge.  ``exit_velocity_mode='provided'`` consumes a documented
    DISCHA/nozzle velocity; ``mass_closure`` derives it as q/(rho_e A) when that
    output is not published. ``printed_equation`` follows the Eq. (2) typeset in
    the paper. ``table3_inferred_omits_hv_delta`` is an explicitly labelled
    reproduction route: omitting its Hv,f-Hv,e term brings all eight numerical
    Table 3 PRESHLY rows within 0.001 in phi (seven within half a displayed
    digit; 2.1 is 0.000585 away). It is not a replacement for the printed
    equation.
    """
    for n, v in vars(exit).items():
        if n != "fluid" and (not math.isfinite(v) or v < 0): raise ValueError(f"{n} must be finite and >= 0")
    if exit.area_m2 <= 0 or exit.mass_flow_kg_s <= 0 or exit.release_height_m <= 0: raise ValueError("area, mass flow and height must be > 0")
    if not 0 <= exit.vapour_quality <= 1: raise ValueError("vapour_quality must be in [0,1]")
    if not 10 <= droplet_diameter_coefficient <= 20: raise ValueError("Eq. 5b coefficient must be in published range [10,20]")
    if exit_velocity_mode not in {"mass_closure", "provided"}: raise ValueError("exit_velocity_mode must be 'mass_closure' or 'provided'")
    if flash_quality_mode not in {"printed_equation", "table3_inferred_omits_hv_delta"}:
        raise ValueError("unknown flash_quality_mode")
    if exit_velocity_mode == "provided" and exit.velocity_m_s <= 0:
        raise ValueError("provided exit velocity must be > 0")
    physical_inputs = {
        "ambient_pressure_pa": ambient_pressure_pa,
        "ambient_temperature_k": ambient_temperature_k,
        "air_density_kg_m3": air_density_kg_m3,
        "air_kinematic_viscosity_m2_s": air_kinematic_viscosity_m2_s,
        "hydrogen_air_diffusivity_m2_s": hydrogen_air_diffusivity_m2_s,
        "surface_tension_n_m": surface_tension_n_m,
        "liquid_kinematic_viscosity_m2_s": liquid_kinematic_viscosity_m2_s,
    }
    if any(not math.isfinite(v) or v <= 0 for v in physical_inputs.values()):
        raise ValueError("ambient and transport inputs must be finite and > 0")
    try:
        # Yellow Book (2.138) treats the stated quality as an equilibrium
        # liquid/vapour mixture at Te.  Do not query a fictitious single phase
        # with both P and T when the input explicitly says it is two phase.
        rho_le = CP.PropsSI("D", "T", exit.temperature_k, "Q", 0, exit.fluid)
        rho_ve = CP.PropsSI("D", "T", exit.temperature_k, "Q", 1, exit.fluid)
        rho_lf = CP.PropsSI("D", "P", ambient_pressure_pa, "Q", 0, exit.fluid)
        rho_vf = CP.PropsSI("D", "P", ambient_pressure_pa, "Q", 1, exit.fluid)
        hv_e = CP.PropsSI("H", "T", exit.temperature_k, "Q", 1, exit.fluid)
        lv_e = CP.PropsSI("H", "T", exit.temperature_k, "Q", 1, exit.fluid)-CP.PropsSI("H", "T", exit.temperature_k, "Q", 0, exit.fluid)
        hv_f = CP.PropsSI("H", "P", ambient_pressure_pa, "Q", 1, exit.fluid)
        lv_f = CP.PropsSI("H", "P", ambient_pressure_pa, "Q", 1, exit.fluid)-CP.PropsSI("H", "P", ambient_pressure_pa, "Q", 0, exit.fluid)
    except Exception as exc: raise ValueError("exit/ambient state unsupported by CoolProp") from exc
    # Yellow Book (2.138)--(2.141), reproduced as Rescigno Eqs. (1)--(4).
    rho_e = 1.0 / ((1-exit.vapour_quality)/rho_le + exit.vapour_quality/rho_ve)
    ue = (exit.mass_flow_kg_s/(rho_e*exit.area_m2)
          if exit_velocity_mode == "mass_closure" else exit.velocity_m_s)
    uf = ue + (exit.pressure_pa-ambient_pressure_pa)*exit.area_m2/exit.mass_flow_kg_s
    hv_delta = hv_f-hv_e if flash_quality_mode == "printed_equation" else 0.0
    phi = 1-(hv_delta+(1-exit.vapour_quality)*lv_e+0.5*(uf**2-ue**2))/lv_f
    if not -1e-8 <= phi <= 1+1e-8:
        raise ValueError(f"flash quality outside [0,1] ({phi:.6g}); inconsistent nozzle-exit state")
    phi = min(1., max(0., phi))
    rho_f = 1.0 / ((1-phi)/rho_lf + phi/rho_vf)
    af = rho_e*ue*exit.area_m2/(rho_f*max(uf, 1e-30)); bf = math.sqrt(max(0., af)/math.pi)
    tb = CP.PropsSI("T", "P", 101325.0, "Q", 0, exit.fluid)
    dd, atomisation, re_f, we_f = _select_droplet_diameter(
        bf=bf, uf=uf, rho_lf=rho_lf,
        liquid_kinematic_viscosity_m2_s=liquid_kinematic_viscosity_m2_s,
        surface_tension_n_m=surface_tension_n_m, air_density_kg_m3=air_density_kg_m3,
        exit_temperature_k=exit.temperature_k, normal_boiling_temperature_k=tb,
        droplet_diameter_coefficient=droplet_diameter_coefficient,
    )
    # Yellow Book (2.145)--(2.147); Rescigno uses the documented plus-sign
    # alteration in Eq. (7), and the critical-pressure cap when Td crosses Tc.
    try:
        lam = CP.PropsSI("L", "T", ambient_temperature_k, "P", ambient_pressure_pa, "Air")
        cp_air = CP.PropsSI("C", "T", ambient_temperature_k, "P", ambient_pressure_pa, "Air")
    except Exception as exc: raise ValueError("ambient-air transport properties unavailable") from exc
    pr = air_kinematic_viscosity_m2_s*air_density_kg_m3*cp_air/lam
    tcrit = CP.PropsSI("Tcrit", exit.fluid)
    td = min(exit.temperature_k, tcrit)
    converged = False
    for _ in range(200):
        tref = min(max(td, CP.PropsSI("Ttriple", exit.fluid)), tcrit)
        ps = CP.PropsSI("Pcrit", exit.fluid) if td >= tcrit else CP.PropsSI("P", "T", tref, "Q", 0, exit.fluid)
        kb = 4*0.002016*hydrogen_air_diffusivity_m2_s*ambient_pressure_pa/(rho_lf*R*ambient_temperature_k)*math.log(1+ps/ambient_pressure_pa)
        ud = rho_lf*G*dd**2/(18*air_kinematic_viscosity_m2_s*air_density_kg_m3); re = dd*ud/air_kinematic_viscosity_m2_s
        sc = air_kinematic_viscosity_m2_s/hydrogen_air_diffusivity_m2_s
        lv_d = CP.PropsSI("H", "T", tref, "Q", 1, exit.fluid)-CP.PropsSI("H", "T", tref, "Q", 0, exit.fluid)
        new_td = ambient_temperature_k-lv_d*kb*rho_lf*(1+.28*math.sqrt(re)*sc**(1/3))/(4*lam*(1+.28*math.sqrt(re)*pr**(1/3)))
        if abs(new_td-td)/max(abs(td),1) < .01:
            td = new_td
            converged = True
            break
        td = .5*(td+new_td)
    # Eq. (7) must use the accepted Eq. (8) temperature, not the previous
    # iteration's trial value.  The paper caps Ps at its critical value when Td
    # reaches the critical temperature.
    tref = min(max(td, CP.PropsSI("Ttriple", exit.fluid)), tcrit)
    ps = CP.PropsSI("Pcrit", exit.fluid) if td >= tcrit else CP.PropsSI("P", "T", tref, "Q", 0, exit.fluid)
    kb = 4*0.002016*hydrogen_air_diffusivity_m2_s*ambient_pressure_pa/(rho_lf*R*ambient_temperature_k)*math.log(1+ps/ambient_pressure_pa)
    dm = _maximum_rainout_diameter(
        rho_lf=rho_lf, air_density_kg_m3=air_density_kg_m3,
        air_kinematic_viscosity_m2_s=air_kinematic_viscosity_m2_s,
        evaporation_kb_m2_s=kb, release_height_m=exit.release_height_m,
        schmidt_number=sc,
    )
    if dm is None:
        re_m = math.nan
    else:
        ud_m = rho_lf*G*dm**2/(18*air_kinematic_viscosity_m2_s*air_density_kg_m3)
        re_m = dm*ud_m/air_kinematic_viscosity_m2_s
    # Text below (2.143): falling large drops are first limited by (2.143b),
    # solved with their free-fall speed.  Then integrate (2.149)--(2.150).
    # Eq. (9) is an explicit no-rainout screen only within Red(dM)<4.  The
    # paper/Yellow Book require Eq. (10)--(11) otherwise.
    screened_no_rainout = dm is not None and re_m < 4 and dd < dm
    d_initial, z = dd, exit.release_height_m
    if screened_no_rainout:
        final = 0.0
        trajectory = "eq9_screened_no_rainout"
    elif integrate_rainout:
        d = dd
        for _ in range(100):
            ud = rho_lf*G*d*d/(18*air_kinematic_viscosity_m2_s*air_density_kg_m3)
            d_new = min(dd, droplet_diameter_coefficient*surface_tension_n_m/(max(ud, 1e-30)**2*air_density_kg_m3))
            if abs(d_new-d)/max(d, 1e-30) < 1e-8:
                d = d_new
                break
            d = .5*(d+d_new)
        d_initial = d
        for _ in range(2_000_000):
            if d <= 0 or z <= 0: break
            ud = rho_lf*G*d*d/(18*air_kinematic_viscosity_m2_s*air_density_kg_m3); re = d*ud/air_kinematic_viscosity_m2_s
            rate = kb/max(d,1e-30)*(1+.28*math.sqrt(re)*sc**(1/3))
            dt = min(1e-3, .005*d/max(rate,1e-30))
            d = max(0., d-dt*rate); z -= ud*dt
            # Eq. (10) approaches zero asymptotically under a fractional step.
            # At this diameter the remaining drop mass is <1e-27 of its initial
            # mass, so continuing cannot alter any reported qL digit.
            if d <= d_initial * 1e-9:
                d = 0.0
                break
        final = d if z <= 0 else 0.0
        trajectory = "eq10_eq11_integrated" if dm is not None else "eq9_unavailable_eq10_eq11_integrated"
    else:
        # A crosswind caller owns the trajectory; do not spend a long Stokes
        # fall calculating a baseline branch which it will not consume.
        final = 0.0
        trajectory = "rainout_trajectory_not_integrated"
    qv = exit.mass_flow_kg_s*(phi+(1-phi)*(1-(final/d_initial)**3)); ql = exit.mass_flow_kg_s-qv
    return BaselineResult(
        exit_velocity_m_s=ue, exit_density_kg_m3=rho_e,
        flashed_velocity_m_s=uf, flashed_quality=phi, flashed_area_m2=af,
        flashed_radius_m=bf, droplet_diameter_m=dd, final_droplet_diameter_m=final,
        gas_mass_flow_kg_s=qv, rainout_mass_flow_kg_s=ql,
        mass_residual_kg_s=exit.mass_flow_kg_s-qv-ql, evaporation_kb_m2_s=kb,
        trajectory_initial_droplet_diameter_m=d_initial, liquid_density_kg_m3=rho_lf,
        maximum_rainout_diameter_m=dm if dm is not None else math.nan,
        maximum_rainout_reynolds=re_m,
        flashed_reynolds=re_f, flashed_weber=we_f,
        droplet_temperature_k=td, droplet_temperature_converged=converged,
        flash_quality_mode=flash_quality_mode,
        status=(("rescigno_2025_eq1_to_13", atomisation, trajectory,
                 "no_wind_in_baseline", "rescigno_eq7_plus_sign") +
                (("ue_mass_closure_derived",) if exit_velocity_mode == "mass_closure" else ("ue_from_exit_state",)) +
                (() if flash_quality_mode == "printed_equation" else ("table3_inferred_eq2_omits_hv_delta",)) +
                (() if converged else ("droplet_temperature_iteration_not_converged",)) +
                (() if integrate_rainout else ("baseline_rainout_not_integrated_crosswind_owns_trajectory",))),
    )
