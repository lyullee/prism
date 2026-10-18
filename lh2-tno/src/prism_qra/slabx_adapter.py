"""
slabx-lh2 adapter.

Maps the dispersion package onto the gated contract the pipeline expects.
Two things the interface note did not say, found by running it:

1.  critical_wind() and applicability() disagree, and applicability wins.
    At q = 6.08 kg/s, u = 1.5 m/s the pre-screen refuses (u_crit = 3.41)
    while the post-run diagnostic returns VALID with a premise ratio of
    0.006. The pre-screen is a cheap conservative filter, not the premise
    test. Using it as the gate refuses runs the model can answer.

    It is still useful: it needs no integration, so a monitoring loop can
    ask "is this worth running" in microseconds. It is kept in that role
    and labelled as over-refusing, and the verdict comes from
    applicability().

2.  critical_wind() extrapolates silently outside its fit range. The fit
    covers 0.1 to 30 kg/s; at 0.05 kg/s it returns a number rather than
    raising. The range check is applied here.

A third gate is added that neither function provides. rise_scaling() can
return a degenerate decomposition -- exponent_predicted NaN, s of order
-100, width_ratio four times its usual value -- while applicability()
still reports VALID, because the premise ratio only tests rise against
advection and says nothing about whether the rise closure itself behaved.
The height quantity is refused on that basis independently of the status.

Declared deviation
------------------
Purple Book 4.7.2 B places ignition at maximum cloud extent, defined as
the maximum AREA of the LFL footprint over time. The plume mode is steady
state, so no time history of area exists and the steady-state area is used
instead. This is an assumption, not the rule, and it is recorded on every
result rather than mentioned once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from slabx.core.plume import run_dispersion
from slabx.core.source import HorizontalJet
from slabx.post.concentration import concentration_field
from slabx.submodels.atmosphere import Atmosphere
from slabx.thermo.base import Substance
from slabx.thermo.coolprop import CoolPropThermo, coolprop_water
from slabx_lh2.diagnostics import (CRITICAL_WIND_RANGE_KGS, applicability,
                                   critical_wind, rise_scaling)
from slabx_lh2.lfl import flammable_distance
from slabx_lh2.plume_width import plume_width_coupling
from slabx_lh2.water_ice import with_sublimation

from gating import Gated
from taxonomy import Grade, Provenance, TranscriptionSource

H2 = Substance(name="H2", mw=0.002016, cp_vapour=14300., cp_liquid=9800.,
               dh_vap=445000., T_boil=20.3, rho_liquid=70.8)

SLABX = Provenance(
    source="slabx-lh2 (MIT); SLAB with LH2 extensions",
    grade=Grade.PUBLISHED_VALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="Water sublimation below the triple point, plume width coupling, "
         "x1.25 safety factor derived from and evaluated on the same six "
         "FFI trials, so not an independently validated factor.",
    not_claimable_as=["an independently validated safety factor"],
)

FOOTPRINT_DEVIATION = (
    "Purple Book 4.7.2 B asks for ignition at the maximum LFL footprint "
    "AREA over time. The plume mode is steady state, so the steady-state "
    "area is substituted. Declared assumption, not the rule."
)

PREMISE_EDGE_CAVEAT = (
    "A value taken at u = u_crit is where the MODEL's own premise breaks, "
    "not a physical boundary. u_crit must not be used as an experimental "
    "correlation."
)

# Flammability is governed by the maximum momentary footprint, not by a
# toxic-dose average over the entire release. A longer release may establish
# a steady plume, but it must not numerically dilute the LFL concentration.
# Purple Book 4.7.2 B asks for the maximum flammable footprint. The SLAB
# post-processor defines zero averaging as the instantaneous, meander-free
# concentration; a 30 s mean can otherwise make a longer release appear to
# have a smaller maximum footprint.
FLAMMABLE_AVERAGING_S = 0.0


@dataclass(frozen=True)
class DispersionResult:
    lfl_distance_m: Gated[float]
    flammable_mass_kg: Gated[float]
    footprint_area_m2: Gated[float]
    cloud_top_height_m: Gated[float]
    u_crit_m_s: Optional[float]
    wind_m_s: float
    status: str
    premise_ratio: float
    provenance: Provenance
    prescreen_disagrees: bool = False

    @property
    def any_refused(self) -> bool:
        return any(g.refused for g in (self.lfl_distance_m,
                                       self.flammable_mass_kg,
                                       self.footprint_area_m2,
                                       self.cloud_top_height_m))


# --------------------------------------------------------------------------

def prescreen(rate_kg_s: float, wind_m_s: float,
              stability: str = "D") -> tuple[bool, Optional[float], str]:
    """Cheap filter, no integration. Returns (worth_running, u_crit, note).

    Over-refuses relative to applicability(), so a False here means
    'probably not worth the 400 ms', never 'the model cannot answer'."""
    lo, hi = CRITICAL_WIND_RANGE_KGS
    if not (lo <= rate_kg_s <= hi):
        return True, None, (
            f"rate {rate_kg_s:.4g} kg/s is outside the critical-wind fit "
            f"range {lo}-{hi} kg/s; the pre-screen is not applicable and no "
            f"filtering is applied")
    uc = critical_wind(rate_kg_s, stability)
    if wind_m_s < uc:
        return False, uc, (f"u={wind_m_s:.2f} < u_crit={uc:.2f}; conservative "
                           f"pre-screen, applicability() is authoritative")
    return True, uc, ""


def _rise_is_degenerate(rs: dict) -> tuple[bool, str]:
    """rise_scaling() can decompose into nonsense while applicability()
    still says VALID, because the premise ratio does not test the rise
    closure. Catch that separately."""
    if not math.isfinite(rs.get("exponent_predicted", float("nan"))):
        return True, "rise_scaling exponent_predicted is not finite"
    s = rs.get("s", 0.0)
    if abs(s) > 20.0:
        return True, f"rise_scaling residual s = {s:.1f} is degenerate"
    return False, ""


def dispersion(rate_kg_s: float, wind_m_s: float,
               temperature_c: float = 15.0, relative_humidity: float = 50.0,
               duration_s: float = 300.0, *, z0: float = 0.01,
               stability: str = "D", nozzle_mm: float = 25.4,
               liquid_fraction: float = 0.559, height_m: float = 0.5,
               x_max: float = 300.0, n_puff_steps: int = 40
               ) -> DispersionResult:
    worth, u_crit, _note = prescreen(rate_kg_s, wind_m_s, stability)

    atm = Atmosphere(u_ref=wind_m_s, z_ref=10., T=temperature_c + 273.15,
                     rh=relative_humidity, z0=z0, stability=stability)
    src = HorizontalJet(substance=H2, rate=rate_kg_s,
                        area=math.pi * (nozzle_mm / 1000.) ** 2 / 4,
                        duration=duration_s, liquid_fraction=liquid_fraction,
                        height=height_m, T_source=20.37)

    with plume_width_coupling():
        traj, _ = run_dispersion(src, atm, CoolPropThermo(H2, fluid="Hydrogen"),
                                 with_sublimation(coolprop_water()),
                                 x_max=x_max, n_puff_steps=n_puff_steps)

    app = applicability(traj)
    status = app["status"]
    ratio = app["premise_ratio"]
    reason = app["reason"]
    averaging_s = min(duration_s * 0.85, FLAMMABLE_AVERAGING_S)
    lfl = flammable_distance(traj, atm, t_avg=averaging_s,
                             t_release=duration_s)

    # Retain the computed values for the controlled FORCE comparison. They
    # never become ordinary answers when applicability says OUT_OF_SCOPE.
    forced_distance = (float(lfl["factored"]) if lfl["reached"] else 0.0)
    area, mass = _footprint(traj, atm, duration_s, lfl["level"])
    z_c = np.asarray(traj.z_c, dtype=float)
    depth = np.asarray(traj.h, dtype=float)
    finite_top = z_c + 0.5 * depth
    finite_top = finite_top[np.isfinite(finite_top)]
    predicted_height = (float(np.max(finite_top))
                        if finite_top.size else None)
    try:
        rs = rise_scaling(traj)
        bad_rise, bad_rise_reason = _rise_is_degenerate(rs)
    except (TypeError, ValueError, np.linalg.LinAlgError) as exc:
        rs = None
        bad_rise = True
        bad_rise_reason = f"rise_scaling unavailable: {exc}"
    forced_height = predicted_height

    disagrees = (not worth) and status == "VALID"

    if status == "OUT_OF_SCOPE":
        edge = _edge_distance(rate_kg_s, u_crit, stability, temperature_c,
                              relative_humidity, duration_s, z0, nozzle_mm,
                              liquid_fraction, height_m, x_max, n_puff_steps)
        return DispersionResult(
            lfl_distance_m=Gated.refuse(
                "lfl_distance_m", reason, bound=edge,
                bound_basis=PREMISE_EDGE_CAVEAT,
                forced_value=forced_distance),
            flammable_mass_kg=Gated.refuse(
                "flammable_mass_kg", reason, forced_value=mass),
            footprint_area_m2=Gated.refuse(
                "footprint_area_m2", reason, forced_value=area),
            cloud_top_height_m=Gated.refuse(
                "cloud_top_height_m",
                reason + " Rise is the unresolved quantity; no bound.",
                forced_value=forced_height),
            u_crit_m_s=u_crit, wind_m_s=wind_m_s, status=status,
            premise_ratio=ratio, provenance=SLABX,
            prescreen_disagrees=disagrees)

    flags: tuple[str, ...] = ("x1.25 factor, not independently validated",)
    if status == "MARGINAL":
        flags = flags + (f"MARGINAL: {reason}",)
    if disagrees:
        flags = flags + ("pre-screen refused, applicability accepted",)

    # "not reached" is an ANSWER of zero, not a refusal. Conflating no
    # effect with no answer corrupts the coverage metric: the small leak
    # bins carry most of the frequency and reach no flammable extent at
    # all, so treating them as refused made a fully evaluated case report
    # 2.4% coverage. The metric exists to catch silent underestimation and
    # must not manufacture a false alarm instead.
    if not lfl["reached"]:
        dist = Gated.answer(
            "lfl_distance_m", 0.0,
            flags + (f"LFL {lfl['level']} vol% not reached within "
                     f"x_max={x_max:g} m at heights {lfl['heights']}",))
    else:
        dist = Gated.answer("lfl_distance_m", float(lfl["factored"]), flags)

    area_flags = flags + ("steady state area; see FOOTPRINT_DEVIATION",)

    if bad_rise or predicted_height is None:
        height = Gated.refuse(
            "cloud_top_height_m",
            f"{bad_rise_reason}; applicability reported {status} but the premise ratio "
            f"does not test the rise closure. No bound.",
            forced_value=predicted_height)
    else:
        height = Gated.answer(
            "cloud_top_height_m", predicted_height,
            flags + ("top = max(z_c + h/2) over the computed trajectory; "
                     f"fitted rise exponent={rs['exponent']:.3g}",))

    return DispersionResult(
        lfl_distance_m=dist,
        flammable_mass_kg=Gated.answer("flammable_mass_kg", mass, flags),
        footprint_area_m2=Gated.answer("footprint_area_m2", area, area_flags),
        cloud_top_height_m=height,
        u_crit_m_s=u_crit, wind_m_s=wind_m_s, status=status,
        premise_ratio=ratio, provenance=SLABX, prescreen_disagrees=disagrees)


def _footprint(traj, atm, duration_s, level_vol_pct) -> tuple[float, float]:
    averaging_s = min(duration_s * 0.85, FLAMMABLE_AVERAGING_S)
    f = concentration_field(traj, atm, z=1.0, t_avg=averaging_s,
                            t_release=duration_s)
    c = np.asarray(f.peak) * 100.0
    x = np.asarray(f.x)
    B = np.asarray(f.B_c)
    inside = c >= level_vol_pct
    if not inside.any():
        return 0.0, 0.0
    area = float(np.trapezoid(2.0 * B[inside], x[inside]))
    # crude mass proxy from the flammable footprint; replace when the
    # package exposes an integrated flammable mass
    rho_lfl = 0.04 * 101325.0 / (8.314462 / 2.016e-3 * 288.15)
    return area, float(area * 2.0 * rho_lfl)


def _edge_distance(rate, u_crit, stability, tc, rh, dur, z0, nozzle,
                   lf, h, x_max, nps) -> Optional[float]:
    """Re-run at u = u_crit to get a value at the premise edge."""
    if u_crit is None:
        return None
    try:
        r = dispersion(rate, u_crit, tc, rh, dur, z0=z0, stability=stability,
                       nozzle_mm=nozzle, liquid_fraction=lf, height_m=h,
                       x_max=x_max, n_puff_steps=nps)
        g = r.lfl_distance_m
        return g._value if not g.refused else None
    except Exception:
        return None
