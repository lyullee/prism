"""
Source terms: discharge rate, optional upstream-line loss, and released mass.

One direct-hole numerical method covers both phases. Expansion from stagnation to the
throat is taken as isentropic; the mass flux

    G(P_t) = rho(P_t, s0) * sqrt(2 * (h0 - h(P_t, s0)))

is evaluated along the isentrope and maximised. If the maximum falls above
ambient pressure the flow is choked and that maximum is the flux; otherwise
the flow is subsonic and the ambient value is used. For a compressed gas
this reproduces choked nozzle flow with a real equation of state; for a
saturated or subcooled liquid it is the homogeneous equilibrium model.
Nothing switches on phase, so a cold two-phase release is handled by the
same path as a gas one.

Real properties come from CoolProp (MIT licence), so no GPL obligation
attaches. The ideal-gas form is retained only to quantify its own error.

Primary sources
---------------
maximum-flux criterion   : standard compressible-flow result
homogeneous equilibrium  : e.g. Yellow Book (CPR 14E) ch.2
discharge coefficient    : left to the caller; see note below
finite gas line friction : Haaland (1983), J. Fluids Eng. 105(1), 89-90
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, Optional

import numpy as np
import CoolProp.CoolProp as CP

P_AMB = 101325.0
R_U = 8.314462
M_H2 = 2.01588e-3


@dataclass(frozen=True)
class Discharge:
    mass_flux_kg_m2s: float      # G at the throat
    rate_kg_s: float             # q = Cd * A * G
    throat_pressure_pa: float
    choked: bool
    throat_quality: float        # vapour mass fraction at the throat, nan if gas
    velocity_m_s: float
    z_stagnation: float          # compressibility at the source, 1.0 => ideal
    fluid: str
    note: str = ""
    # Audit fields for a source reached through a finite upstream line.
    # They are None for the original sharp-hole calculation, preserving
    # both its API and its numerical result.
    flow_model: str = "sharp-hole"
    line_outlet_pressure_pa: Optional[float] = None
    line_pressure_drop_pa: Optional[float] = None
    line_friction_factor: Optional[float] = None
    line_reynolds: Optional[float] = None
    line_outlet_mach: Optional[float] = None


def _state(fluid: str, P: float, s: float) -> tuple[float, float]:
    """(density, enthalpy) on the isentrope at pressure P."""
    return (CP.PropsSI("D", "P", P, "S", s, fluid),
            CP.PropsSI("H", "P", P, "S", s, fluid))


def discharge(P0: float, T0: Optional[float], fluid: str,
              hole_diameter_m: float, Cd: float = 1.0,
              saturated_liquid: bool = False,
              stagnation_quality: Optional[float] = None,
              n_scan: int = 240) -> Discharge:
    """Discharge through a sharp hole.

    saturated_liquid=True starts from the bubble line at P0 (T0 ignored),
    which is the usual state of a cryogenic transfer line.
    """
    if not math.isfinite(P0) or P0 <= 0.0:
        raise ValueError("stagnation pressure must be finite and positive")
    if (not math.isfinite(hole_diameter_m)
            or hole_diameter_m <= 0.0):
        raise ValueError("hole diameter must be finite and positive")
    if isinstance(n_scan, bool) or not isinstance(n_scan, int) or n_scan < 2:
        raise ValueError("n_scan must be an integer of at least 2")
    if not math.isfinite(Cd) or not 0.0 < Cd <= 1.0:
        raise ValueError("discharge coefficient must be in (0, 1]")
    if saturated_liquid and stagnation_quality is not None:
        raise ValueError(
            "choose saturated_liquid or stagnation_quality, not both")
    if stagnation_quality is not None and (
            not math.isfinite(stagnation_quality)
            or not 0.0 <= stagnation_quality <= 1.0):
        raise ValueError("stagnation quality must be between 0 and 1")
    if (not saturated_liquid and stagnation_quality is None
            and (T0 is None or not math.isfinite(T0) or T0 <= 0.0)):
        raise ValueError(
            "gas stagnation temperature must be finite and positive")
    # A vessel below ambient pressure does not discharge; air flows in.
    # The isentrope is scanned from P_AMB up to P0, so with P0 below
    # P_AMB the range inverts and the scan silently returns a flow in the
    # wrong direction. At 0.5 bar absolute it gave 5.8e-5 kg/s outward.
    if P0 <= P_AMB:
        return Discharge(
            mass_flux_kg_m2s=0.0, rate_kg_s=0.0, throat_pressure_pa=P0,
            choked=False, throat_quality=float("nan"), velocity_m_s=0.0,
            z_stagnation=1.0, fluid=fluid,
            note=f"stagnation pressure {P0:.0f} Pa is at or below ambient; "
                 f"there is no outward flow. Ingress is not modelled.")

    if saturated_liquid:
        s0 = CP.PropsSI("S", "P", P0, "Q", 0, fluid)
        h0 = CP.PropsSI("H", "P", P0, "Q", 0, fluid)
        rho0 = CP.PropsSI("D", "P", P0, "Q", 0, fluid)
        T0 = CP.PropsSI("T", "P", P0, "Q", 0, fluid)
    elif stagnation_quality is not None:
        s0 = CP.PropsSI("S", "P", P0, "Q", stagnation_quality, fluid)
        h0 = CP.PropsSI("H", "P", P0, "Q", stagnation_quality, fluid)
        rho0 = CP.PropsSI("D", "P", P0, "Q", stagnation_quality, fluid)
        T0 = CP.PropsSI("T", "P", P0, "Q", stagnation_quality, fluid)
    else:
        s0 = CP.PropsSI("S", "P", P0, "T", T0, fluid)
        h0 = CP.PropsSI("H", "P", P0, "T", T0, fluid)
        rho0 = CP.PropsSI("D", "P", P0, "T", T0, fluid)

    z0 = P0 / (rho0 * (R_U / M_H2) * T0)

    # scan the isentrope from ambient up to the stagnation pressure
    # At pressures just above ambient, 0.999*P0 can be below the
    # downstream boundary. Never scan an impossible sub-ambient throat.
    ps = np.linspace(P_AMB, max(P_AMB, P0 * 0.999), n_scan)
    best = (-1.0, P_AMB, 0.0, 0.0)
    for P in ps:
        try:
            rho, h = _state(fluid, float(P), s0)
        except Exception:
            continue
        dh = h0 - h
        if dh <= 0:
            continue
        u = math.sqrt(2.0 * dh)
        G = rho * u
        if G > best[0]:
            best = (G, float(P), u, rho)

    G, Pt, u, rho_t = best
    if not math.isfinite(G) or G < 0.0:
        raise ValueError(
            "no valid isentropic throat state was found for the source")
    choked = Pt > P_AMB * 1.001

    try:
        q_t = CP.PropsSI("Q", "P", Pt, "S", s0, fluid)
        if not (0.0 <= q_t <= 1.0):
            q_t = float("nan")
    except Exception:
        q_t = float("nan")

    area = math.pi * hole_diameter_m ** 2 / 4.0
    state_note = (
        f" Stagnation quality={stagnation_quality:g}."
        if stagnation_quality is not None else "")
    return Discharge(
        mass_flux_kg_m2s=G, rate_kg_s=Cd * area * G,
        throat_pressure_pa=Pt, choked=choked, throat_quality=q_t,
        velocity_m_s=u, z_stagnation=z0, fluid=fluid,
        note=(f"Caller-supplied Cd={Cd:g}; Cd=1 is the conservative default."
              f"{state_note} "
              "Any lower value requires equipment-specific evidence or an "
              "explicitly labelled sensitivity assumption."))


def ideal_gas_choked(P0: float, T0: float, hole_diameter_m: float,
                     gamma: float = 1.41, Cd: float = 1.0) -> float:
    """Textbook choked flow with ideal gas. Kept to measure its own error."""
    rho0 = P0 / ((R_U / M_H2) * T0)
    area = math.pi * hole_diameter_m ** 2 / 4.0
    f = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
    return Cd * area * math.sqrt(gamma * rho0 * P0 * f)


# --------------------------------------------------------------------------
# finite upstream line for gaseous hydrogen
# --------------------------------------------------------------------------

def haaland_friction_factor(reynolds: float,
                            relative_roughness: float = 0.0) -> float:
    """Darcy friction factor, including an explicit transition blend.

    Turbulent flow uses Haaland's primary 1983 explicit correlation.  The
    2,300--4,000 transition has no unique steady correlation, so the two
    endpoint values are linearly blended and the caller can audit Re.
    """
    if not math.isfinite(reynolds) or reynolds <= 0.0:
        raise ValueError("Reynolds number must be finite and positive")
    if (not math.isfinite(relative_roughness)
            or not 0.0 <= relative_roughness < 0.1):
        raise ValueError(
            "relative roughness must be finite, non-negative and below 0.1")

    def _turbulent(re: float) -> float:
        inverse_root = -1.8 * math.log10(
            (relative_roughness / 3.7) ** 1.11 + 6.9 / re)
        return 1.0 / inverse_root ** 2

    if reynolds < 2300.0:
        return 64.0 / reynolds
    if reynolds >= 4000.0:
        return _turbulent(reynolds)
    weight = (reynolds - 2300.0) / (4000.0 - 2300.0)
    return ((1.0 - weight) * (64.0 / reynolds)
            + weight * _turbulent(reynolds))


def line_discharge(P0: float, T0: float, fluid: str,
                   hole_diameter_m: float, line_length_m: float,
                   line_diameter_m: float, Cd: float = 1.0,
                   roughness_m: float = 0.0, minor_loss_k: float = 0.0,
                   n_scan: int = 240, n_integral: int = 320,
                   max_outlet_mach: float = 0.30) -> Discharge:
    """Steady GH2 flow through a finite line and terminal sharp hole.

    The terminal opening retains :func:`discharge`.  Its local stagnation
    pressure is coupled to an isothermal, constant-area real-gas line:

        mdot = A sqrt(2 integral(rho dP) / (f_D L/D + sum(K)))

    Density and viscosity are evaluated with CoolProp and the Darcy factor
    with Haaland (1983).  This is a diagnostic/equipment-path model, not a
    blowdown or a two-phase relief model.  The low-Mach limit is enforced
    because heat transfer and Fanno choking are outside this closure.
    """
    values = {
        "stagnation pressure": P0, "temperature": T0,
        "hole diameter": hole_diameter_m, "line length": line_length_m,
        "line diameter": line_diameter_m, "roughness": roughness_m,
        "minor loss coefficient": minor_loss_k,
    }
    for name, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if T0 <= 0.0:
        raise ValueError("temperature must be positive")
    if hole_diameter_m <= 0.0 or line_length_m <= 0.0 \
            or line_diameter_m <= 0.0:
        raise ValueError("line length and diameters must be positive")
    if roughness_m < 0.0 or minor_loss_k < 0.0:
        raise ValueError("roughness and minor loss coefficient cannot be negative")
    if roughness_m / line_diameter_m >= 0.1:
        raise ValueError("line relative roughness must be below 0.1")
    if hole_diameter_m > line_diameter_m:
        raise ValueError(
            "terminal hole cannot exceed the upstream line diameter")
    if max_outlet_mach <= 0.0 or max_outlet_mach > 0.30:
        raise ValueError("max_outlet_mach must be in (0, 0.30]")
    if fluid not in {"Hydrogen", "H2"}:
        raise ValueError(
            "finite-line source currently covers gaseous hydrogen only")
    phase = str(CP.PhaseSI("P", P0, "T", T0, fluid)).lower()
    if phase in {"liquid", "twophase", "supercritical_liquid"}:
        raise ValueError(
            f"finite-line source requires a gas or supercritical gas state; "
            f"CoolProp classified the inlet as {phase}")

    direct = discharge(P0, T0, fluid, hole_diameter_m, Cd=Cd,
                       n_scan=n_scan)
    if direct.rate_kg_s <= 0.0:
        return replace(
            direct, flow_model="isothermal-real-gas-line+terminal-orifice",
            note=direct.note + " Finite line was supplied but no outward "
                 "flow exists.")

    # One property grid makes the repeated coupling root inexpensive and
    # deterministic.  cum(P) = integral from ambient to P of rho dP.
    pressures = np.linspace(P_AMB, P0, n_integral)
    densities = np.asarray([
        CP.PropsSI("D", "P", float(p), "T", T0, fluid)
        for p in pressures], dtype=float)
    viscosities = np.asarray([
        CP.PropsSI("V", "P", float(p), "T", T0, fluid)
        for p in pressures], dtype=float)
    increments = ((densities[1:] + densities[:-1]) * 0.5
                  * np.diff(pressures))
    cumulative = np.concatenate(([0.0], np.cumsum(increments)))
    total_integral = float(cumulative[-1])
    area = math.pi * line_diameter_m ** 2 / 4.0
    relative_roughness = roughness_m / line_diameter_m

    def _capacity(outlet_pressure: float) -> tuple[float, float, float]:
        below = float(np.interp(outlet_pressure, pressures, cumulative))
        density_integral = max(total_integral - below, 0.0)
        representative_pressure = math.sqrt(P0 * outlet_pressure)
        viscosity = float(np.interp(
            representative_pressure, pressures, viscosities))
        friction = 0.02
        rate = 0.0
        reynolds = 1.0
        for _ in range(30):
            loss = friction * line_length_m / line_diameter_m + minor_loss_k
            if loss <= 0.0:
                return float("inf"), friction, float("inf")
            rate = area * math.sqrt(2.0 * density_integral / loss)
            reynolds = max(
                4.0 * rate / (math.pi * line_diameter_m * viscosity), 1.0)
            updated = haaland_friction_factor(reynolds,
                                               relative_roughness)
            if math.isclose(updated, friction, rel_tol=1e-8, abs_tol=0.0):
                friction = updated
                break
            friction = 0.5 * (friction + updated)
        return rate, friction, reynolds

    def _root(terminal_rate_per_pa: float) -> tuple[float, float, float, float]:
        low, high = P_AMB, P0
        friction = reynolds = float("nan")
        for _ in range(70):
            mid = 0.5 * (low + high)
            capacity, friction, reynolds = _capacity(mid)
            if capacity > terminal_rate_per_pa * mid:
                low = mid
            else:
                high = mid
        outlet = 0.5 * (low + high)
        capacity, friction, reynolds = _capacity(outlet)
        return outlet, capacity, friction, reynolds

    # Choked GH2 rate is nearly proportional to local stagnation pressure.
    # Re-evaluate the real-gas terminal after each root so the approximation
    # does not become a hidden calibration when the pressure loss is large.
    rate_per_pa = direct.rate_kg_s / P0
    terminal = direct
    outlet = P0
    capacity = direct.rate_kg_s
    friction = reynolds = float("nan")
    for _ in range(5):
        outlet, capacity, friction, reynolds = _root(rate_per_pa)
        terminal = discharge(outlet, T0, fluid, hole_diameter_m, Cd=Cd,
                             n_scan=n_scan)
        updated = terminal.rate_kg_s / outlet
        if math.isclose(updated, rate_per_pa, rel_tol=2e-5, abs_tol=0.0):
            rate_per_pa = updated
            break
        rate_per_pa = updated
    outlet, capacity, friction, reynolds = _root(rate_per_pa)
    terminal = discharge(outlet, T0, fluid, hole_diameter_m, Cd=Cd,
                         n_scan=n_scan)
    mismatch = abs(capacity - terminal.rate_kg_s) / terminal.rate_kg_s
    if mismatch > 2e-3:
        raise RuntimeError(
            f"line/orifice coupling did not converge ({mismatch:.3%})")

    rho_out = CP.PropsSI("D", "P", outlet, "T", T0, fluid)
    speed_of_sound = CP.PropsSI("A", "P", outlet, "T", T0, fluid)
    line_velocity = terminal.rate_kg_s / (rho_out * area)
    mach = line_velocity / speed_of_sound
    if mach > max_outlet_mach:
        raise ValueError(
            f"line outlet Mach {mach:.3f} exceeds the enforced "
            f"low-Mach limit {max_outlet_mach:.3f}; use a compressible "
            "Fanno/transient line model")

    return replace(
        terminal,
        flow_model="isothermal-real-gas-line+terminal-orifice",
        line_outlet_pressure_pa=outlet,
        line_pressure_drop_pa=P0 - outlet,
        line_friction_factor=friction,
        line_reynolds=reynolds,
        line_outlet_mach=mach,
        note=(terminal.note + " Upstream line: steady isothermal real-gas "
              "Darcy integration; Haaland (1983) friction; constant bore; "
              f"K={minor_loss_k:g}; outlet Mach={mach:.3f}. Heat transfer, "
              "line inventory/blowdown and two-phase flow are not modelled."))


# --------------------------------------------------------------------------
# released mass
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Release:
    rate_kg_s: float
    duration_s: float
    released_kg: float
    limited_by: Literal["ISOLATION", "INVENTORY"]
    inventory_kg: float
    isolation_time_s: float

    @property
    def fraction_of_inventory(self) -> float:
        return self.released_kg / self.inventory_kg


def released_mass(rate_kg_s: float, inventory_kg: float,
                  isolation_time_s: float) -> Release:
    """min(q * t_iso, inventory), with the binding constraint recorded.

    Holding the rate constant is optimistic for a blowdown, whose rate
    falls as the section depressurises, and pessimistic in that no
    detection delay is added ahead of isolation. Neither is modelled here.
    """
    if not math.isfinite(rate_kg_s) or rate_kg_s < 0.0:
        raise ValueError("release rate must be finite and non-negative")
    if not math.isfinite(inventory_kg) or inventory_kg <= 0.0:
        raise ValueError("inventory must be finite and positive")
    if (math.isnan(isolation_time_s) or isolation_time_s <= 0.0):
        raise ValueError("isolation time must be positive")
    if rate_kg_s == 0.0:
        return Release(0.0, 0.0, 0.0, "ISOLATION",
                       inventory_kg, isolation_time_s)
    m_iso = rate_kg_s * isolation_time_s
    if m_iso <= inventory_kg:
        return Release(rate_kg_s, isolation_time_s, m_iso, "ISOLATION",
                       inventory_kg, isolation_time_s)
    return Release(rate_kg_s, inventory_kg / rate_kg_s, inventory_kg,
                   "INVENTORY", inventory_kg, isolation_time_s)
