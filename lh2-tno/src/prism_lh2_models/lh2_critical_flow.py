"""Independent, adiabatic LH2 critical-flow branches.

This module is intentionally upstream of E3.5.  It has no concentration,
wind, rainout, or E3.5 trial inputs.  HEM follows the homogeneous direct
evaluation mass-flux relation G=rho*sqrt(2*(h0-h)); its critical state is the
maximum along the isentrope.  HNEM follows Travis et al.'s liquid-temperature
interpolation T_l=(1-eta)T_v+eta*T_s.  Both branches are only applicable to a
short, adiabatic, frictionless nozzle; pipe-line losses require a separate
validated line model.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

import CoolProp.CoolProp as CP


@dataclass(frozen=True)
class CriticalFlowInput:
    stagnation_pressure_pa: float
    stagnation_temperature_k: float
    throat_diameter_m: float
    discharge_coefficient: float
    back_pressure_pa: float = 101325.0
    fluid: str = "Hydrogen"


@dataclass(frozen=True)
class CriticalFlowResult:
    model: str
    critical_mass_flux_kg_m2_s: float
    mass_flow_kg_s: float
    critical_pressure_pa: float
    mixture_enthalpy_j_kg: float
    mixture_density_kg_m3: float
    velocity_m_s: float
    energy_residual_j_kg: float
    eta: float | None
    status: str


def _validate(inp: CriticalFlowInput) -> None:
    if inp.stagnation_pressure_pa <= inp.back_pressure_pa or inp.stagnation_temperature_k <= 0 or inp.back_pressure_pa <= 0:
        raise ValueError("stagnation pressure must exceed declared back pressure and temperature must be positive")
    if inp.throat_diameter_m <= 0 or not 0 < inp.discharge_coefficient <= 1:
        raise ValueError("positive throat diameter and 0<Cd<=1 are required")


def _state_at_ps(fluid: str, pressure_pa: float, entropy_j_kg_k: float):
    h = CP.PropsSI("H", "P", pressure_pa, "S", entropy_j_kg_k, fluid)
    rho = CP.PropsSI("D", "P", pressure_pa, "S", entropy_j_kg_k, fluid)
    return h, rho


def _search(inp: CriticalFlowInput, state_at_pressure, model: str, eta: float | None) -> CriticalFlowResult:
    _validate(inp)
    h0 = CP.PropsSI("H", "P", inp.stagnation_pressure_pa, "T", inp.stagnation_temperature_k, inp.fluid)
    s0 = CP.PropsSI("S", "P", inp.stagnation_pressure_pa, "T", inp.stagnation_temperature_k, inp.fluid)
    # Direct evaluation by an evenly spaced pressure grid.  The reported critical
    # point is refined locally; this is transparent and avoids a hidden correlation.
    low = inp.back_pressure_pa
    best = None
    for iteration in range(3):
        n = 801
        step = (inp.stagnation_pressure_pa - low) / (n - 1)
        candidates = []
        for i in range(1, n - 1):
            pressure = low + i * step
            try:
                h, rho = state_at_pressure(pressure, h0, s0)
                delta_h = h0 - h
                if rho <= 0 or delta_h <= 0:
                    continue
                velocity = sqrt(2 * delta_h)
                candidates.append((rho * velocity, pressure, h, rho, velocity))
            except ValueError:
                continue
        if not candidates:
            raise ValueError("no admissible critical-flow states in requested domain")
        best = max(candidates)
        half = max(step * 3, 1.0)
        low, high = max(inp.back_pressure_pa, best[1] - half), min(inp.stagnation_pressure_pa, best[1] + half)
        if iteration < 2:
            # Subsequent local scans use the selected bracket instead of ambient-to-P0.
            original_p0 = inp.stagnation_pressure_pa
            class _Local: pass
            # Avoid mutating the immutable input: execute a local scan inline below.
            step = (high - low) / (n - 1)
            candidates = []
            for i in range(1, n - 1):
                pressure = low + i * step
                try:
                    h, rho = state_at_pressure(pressure, h0, s0); delta_h = h0 - h
                    if rho > 0 and delta_h > 0:
                        velocity = sqrt(2 * delta_h); candidates.append((rho * velocity, pressure, h, rho, velocity))
                except ValueError:
                    continue
            if candidates:
                best = max(candidates)
            break
    assert best is not None
    flux, pressure, h, rho, velocity = best
    area = pi * inp.throat_diameter_m**2 / 4
    return CriticalFlowResult(model, flux, inp.discharge_coefficient * area * flux, pressure, h, rho,
                              velocity, h0 - h - velocity**2 / 2, eta,
                              "conditional_short_adiabatic_nozzle_only_not_an_E35_source_state")


def hem_critical_flow(inp: CriticalFlowInput) -> CriticalFlowResult:
    """HEM critical-flow branch; equal phase velocity and thermal equilibrium."""
    return _search(inp, lambda p, _h0, s0: _state_at_ps(inp.fluid, p, s0), "HEM", None)


def _saturation_locus_temperature(fluid: str, s0: float, pressure_max: float) -> float:
    lo, hi = 101325.0, pressure_max
    slo = CP.PropsSI("S", "P", lo, "Q", 0, fluid)
    shi = CP.PropsSI("S", "P", hi, "Q", 0, fluid)
    if not min(slo, shi) <= s0 <= max(slo, shi):
        raise ValueError("HNEM applicability fails: isentrope does not cross liquid saturation locus")
    for _ in range(80):
        mid = (lo + hi) / 2
        smid = CP.PropsSI("S", "P", mid, "Q", 0, fluid)
        if (smid - s0) * (slo - s0) <= 0:
            hi = mid
        else:
            lo, slo = mid, smid
    return CP.PropsSI("T", "P", (lo + hi) / 2, "Q", 0, fluid)


def hnem_critical_flow(inp: CriticalFlowInput, *, eta: float) -> CriticalFlowResult:
    """Homogeneous non-equilibrium branch using Travis et al. Eq. (34).

    ``eta=0`` is HEM.  ``eta>0`` permits liquid superheat between saturated
    vapor temperature and the isentropic liquid-saturation locus.  It is a
    sensitivity parameter, not calibrated from E3.5; an eta-specific measured
    benchmark is required before use as a validated source state.
    """
    if not 0 <= eta <= 1:
        raise ValueError("HNEM eta must lie in [0, 1]")
    _validate(inp)
    s0 = CP.PropsSI("S", "P", inp.stagnation_pressure_pa, "T", inp.stagnation_temperature_k, inp.fluid)
    ts = _saturation_locus_temperature(inp.fluid, s0, inp.stagnation_pressure_pa)

    def state(p: float, _h0: float, s0_local: float):
        tv = CP.PropsSI("T", "P", p, "Q", 1, inp.fluid)
        tl = (1 - eta) * tv + eta * ts
        # CoolProp's imposed liquid phase accesses the metastable liquid branch.
        hl = CP.PropsSI("H", "T|liquid", tl, "P", p, inp.fluid)
        sl = CP.PropsSI("S", "T|liquid", tl, "P", p, inp.fluid)
        rhol = CP.PropsSI("D", "T|liquid", tl, "P", p, inp.fluid)
        hv = CP.PropsSI("H", "P", p, "Q", 1, inp.fluid)
        sv = CP.PropsSI("S", "P", p, "Q", 1, inp.fluid)
        rhov = CP.PropsSI("D", "P", p, "Q", 1, inp.fluid)
        quality = (s0_local - sl) / (sv - sl)
        if not 0 <= quality <= 1:
            raise ValueError("outside two-phase HNEM quality domain")
        h = quality * hv + (1 - quality) * hl
        rho = 1 / (quality / rhov + (1 - quality) / rhol)
        return h, rho

    return _search(inp, state, "HNEM", eta)
