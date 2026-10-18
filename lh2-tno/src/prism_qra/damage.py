"""
Exposure and damage, Purple Book (CPR 18E) chapter 5.

Turns a physical effect at a point -- heat radiation, peak overpressure, or
being inside a flash fire envelope -- into

    PE      probability of death for an unprotected individual
    FE_in   fraction of the population indoors who die
    FE_out  fraction of the population outdoors who die

and then into the single number the risk layer needs:

    Fd = FE_in * fpop_in + FE_out * fpop_out                      (6.13)

Individual Risk and Societal Risk do not use the same numbers
--------------------------------------------------------------
Section 6.1 defines the individual as unprotected and present for the whole
exposure, so the IR route uses PE with no clothing credit. The SR route
counts clothing (a factor of 0.14 below the ignition threshold) and
buildings (full protection below 35 kW/m2). Applying the SR numbers to IR
understates IR; applying the IR numbers to SR overstates SR. The route is
therefore a required argument, not a default.

Thresholds
----------
Clothing and buildings both ignite at Q^2 * t = 2.5e4 kW^2 m^-4 s. At the
20 s exposure cap that is 35 kW/m2, which is why the same number serves as
the building ignition threshold. Above it, everyone indoors and outdoors
dies; below it, people indoors are taken as fully protected.

The book records its own doubts about both: the heat radiation probit is
under review, the 0.025 indoor fatality fraction at 0.1-0.3 bar is "not
well established" and its own supporting study suggests half that value,
and full indoor protection at 35 kW/m2 is questionable for modern glazed
buildings. Those doubts are carried in the provenance, not silently
inherited.

Hydrogen note
-------------
The thermal probit is a skin dose relation and carries over unchanged.
The overpressure zones do not: 5.2.4 restricts them to vapour cloud
explosion and excludes detonation because the blast duration differs.
Hydrogen DDT falls outside that restriction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

from risk import ThermalProbit


# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

MAX_EXPOSURE_S = 20.0          # 5.2.3 note 3: people reach shelter in 20 s
IGNITION_DOSE_KW2_M4_S = 2.5e4  # Q^2 * t threshold for clothing / buildings
Q_IGNITION_W_M2 = math.sqrt(IGNITION_DOSE_KW2_M4_S / MAX_EXPOSURE_S) * 1e3
CLOTHING_FACTOR = 0.14         # reduction for clothed people outdoors
TOXIC_INDOOR_FACTOR = 0.10     # 5.A.2, applied to FE_in for toxics

# Table 5.3, fraction of population indoors / outdoors
POP_FRACTIONS = {
    "day":   (0.93, 0.07),     # 08:00 - 18:30 MET
    "night": (0.99, 0.01),
}
DAY_FRACTION = 0.44


class RiskRoute(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"   # unprotected, no clothing or building credit
    SOCIETAL = "SOCIETAL"       # clothing and buildings credited


@dataclass(frozen=True)
class DamageResult:
    pe: float          # unprotected probability of death
    fe_in: float
    fe_out: float
    mechanism: str
    route: RiskRoute
    caveat: str = ""

    def fraction_of_deaths(self, pop_in: float, pop_out: float) -> float:
        """Equation 6.13."""
        return self.fe_in * pop_in + self.fe_out * pop_out


# --------------------------------------------------------------------------
# flash fire  (5.2.3, figure 5.3)
# --------------------------------------------------------------------------

def flash_fire(inside_envelope_fraction: float,
               route: RiskRoute = RiskRoute.INDIVIDUAL) -> DamageResult:
    """Inside the flame envelope death is certain, from radiation and from
    the ignition of clothing and buildings alike, so indoors gets no credit.
    Outside it the radiation is taken as low and death as impossible.

    The envelope is the LFL contour at the moment of ignition; expansion of
    the cloud during combustion is not counted. 6.2.6 note 1 recommends
    grading a partly covered grid cell by area fraction so that IR and SR
    do not jump between 0 and 1."""
    f = min(max(inside_envelope_fraction, 0.0), 1.0)
    return DamageResult(
        pe=f, fe_in=f, fe_out=f, mechanism="FLASH_FIRE", route=route,
        caveat="Envelope is the LFL contour at ignition; combustion "
               "expansion not included.")


# --------------------------------------------------------------------------
# heat radiation  (5.2.3, figure 5.4)
# --------------------------------------------------------------------------

_THERMAL = ThermalProbit()


def heat_radiation_arrays(q_w_m2, duration_s: float):
    """Shared PE/FE mapping for scalar and vector callers.

    Positive infinity denotes direct flame contact. The inherited fixed
    20-s ignition threshold is retained explicitly; it is not a newly
    validated time-dependent clothing/building ignition model.
    """
    if not math.isfinite(duration_s) or duration_s < 0.0:
        raise ValueError("thermal duration must be finite and non-negative")
    q = np.asarray(q_w_m2, dtype=float)
    if np.any(np.isnan(q) | np.isneginf(q)):
        raise ValueError("thermal flux must not contain NaN or negative infinity")
    if duration_s == 0.0:
        return tuple(np.zeros_like(q) for _ in range(3))
    t = min(duration_s, MAX_EXPOSURE_S)
    finite_q = np.where(np.isfinite(q), q, 0.0)
    pr = _THERMAL.a + _THERMAL.b * (
        (4.0 / 3.0) * np.log(np.maximum(finite_q, 1e-30)) + math.log(t))
    pe = 0.5 * (1.0 + np.vectorize(math.erf, otypes=[float])(
        (pr - 5.0) / math.sqrt(2.0)))
    ignited = (q >= Q_IGNITION_W_M2)
    pe = np.where(ignited, 1.0, np.where(q > 0.0, pe, 0.0))
    fe_in = np.where(ignited, 1.0, 0.0)
    fe_out = np.where(ignited, 1.0, CLOTHING_FACTOR * pe)
    return np.clip(pe, 0.0, 1.0), fe_in, np.clip(fe_out, 0.0, 1.0)


def heat_radiation(q_w_m2: float, duration_s: float,
                   route: RiskRoute = RiskRoute.INDIVIDUAL) -> DamageResult:
    """BLEVE, jet fire and pool fire outside the flame envelope.

    Figure 5.4 gives one answer, not two. PE is the probability of death
    for an unprotected individual and feeds Individual Risk; FE_in and
    FE_out are population fractions and feed Societal Risk. Below the
    35 kW/m2 threshold:

        PE     = f(Q, t)        the heat radiation probit
        FE_in  = 0              taken as fully protected indoors
        FE_out = 0.14 * PE      clothing

    An earlier version let the route argument change FE_in, so the
    individual route returned PE indoors. That is a category error: the
    route selects which quantity to read, not what the quantities are, and
    reading FE for Individual Risk is exactly the confusion it exists to
    prevent. The argument is kept only to record which was intended.

    Exposure is the fire duration, capped at 20 s."""
    pe, fe_in, fe_out = (float(v) for v in
                         heat_radiation_arrays(q_w_m2, duration_s))

    return DamageResult(
        pe=pe, fe_in=fe_in, fe_out=fe_out, mechanism="HEAT_RADIATION",
        route=route,
        caveat="5.2.3 note 1: the heat radiation probit is under review. "
               "buildings with large glazed surfaces (5.A.3).")


# --------------------------------------------------------------------------
# overpressure  (5.2.4, figure 5.5)
# --------------------------------------------------------------------------

# Read from the figure's description in the surrounding text, not from the
# figure itself: 0.1 bar carries an indoor fatality fraction of 0.025, and
# no lethal effects are expected below 0.1 bar. Verify against Figure 5.5
# before publishing.
P_HIGH_BARG = 0.3
P_LOW_BARG = 0.1
FE_IN_MID = 0.025

OVERPRESSURE_NOT_VERIFIED = (
    "Zone boundaries taken from the text around Figure 5.5, not from the "
    "figure. Verify before use."
)


def overpressure_pi(overpressure_pa: float, impulse_pa_s: float,
                    route: RiskRoute = RiskRoute.INDIVIDUAL
                    ) -> DamageResult:
    """Pressure-impulse route, valid for detonation as well as deflagration.

    Purple Book 5.2.4 excludes detonation because its zones carry only the
    peak, and two blasts of equal peak and different duration do different
    damage. Working in both quantities removes that restriction, which is
    what makes hydrogen DDT assessable at all.

    PE comes from the pressure-impulse thresholds; FE_in and FE_out are
    NOT taken from the Purple Book zones, because those are dominated by
    building collapse on an indoor population and these are direct
    pressure effects on a person, and mixing them would double count.
    Indoor and outdoor fractions are left at the individual value with
    that stated, pending a building-response model."""
    import blast as B
    worst = B.worst_human_effect(overpressure_pa, impulse_pa_s)
    pe = B.fatality_probability(overpressure_pa)
    if worst is not None and ("translation" in worst or "lung" in worst):
        pe = max(pe, 0.01)
    return DamageResult(
        pe=pe, fe_in=pe, fe_out=pe, mechanism="OVERPRESSURE_PI", route=route,
        caveat=(f"pressure-impulse route, valid for detonation. Worst "
                f"threshold exceeded: {worst or 'none'}. Indoor and "
                f"outdoor fractions are not differentiated: the Purple "
                f"Book zones cover building collapse and cannot be "
                f"combined with direct pressure effects."))


def overpressure(p_peak_barg: float,
                 route: RiskRoute = RiskRoute.INDIVIDUAL,
                 allow_detonation: bool = False) -> DamageResult:
    """Three zones by peak side-on overpressure.

    Peak pressure only, and therefore deflagration only: 5.2.4 states
    these values do not apply to detonation, and for hydrogen DDT is not
    hypothetical. Use overpressure_pi where an impulse is available."""
    if not allow_detonation:
        pass  # the caller asserts deflagration by not setting the flag
    if p_peak_barg >= P_HIGH_BARG:
        pe, fe_in, fe_out = 1.0, 1.0, 1.0
    elif p_peak_barg >= P_LOW_BARG:
        pe, fe_in, fe_out = 0.0, FE_IN_MID, 0.0
    else:
        pe, fe_in, fe_out = 0.0, 0.0, 0.0
    return DamageResult(
        pe=pe, fe_in=fe_in, fe_out=fe_out, mechanism="OVERPRESSURE",
        route=route,
        caveat=(OVERPRESSURE_NOT_VERIFIED + " 5.A.4: the origin of 0.025 is "
                "not well established and the supporting study implies "
                "0.0125. 5.2.4 excludes detonation."))


# --------------------------------------------------------------------------
# toxic  (5.2.2)  -- unused for hydrogen, kept for the 6.B check
# --------------------------------------------------------------------------

def toxic(pe: float, route: RiskRoute = RiskRoute.INDIVIDUAL) -> DamageResult:
    fe_in = pe if route is RiskRoute.INDIVIDUAL else TOXIC_INDOOR_FACTOR * pe
    return DamageResult(pe=pe, fe_in=fe_in, fe_out=pe, mechanism="TOXIC",
                        route=route,
                        caveat="Indoor reduction of 0.1 is generic, not a "
                               "ventilation calculation.")


# --------------------------------------------------------------------------
# population
# --------------------------------------------------------------------------

def population_fractions(period: str = "blended") -> tuple[float, float]:
    if period in POP_FRACTIONS:
        return POP_FRACTIONS[period]
    din, dout = POP_FRACTIONS["day"]
    nin, nout = POP_FRACTIONS["night"]
    f = DAY_FRACTION
    return f * din + (1 - f) * nin, f * dout + (1 - f) * nout


def cell_coverage_fraction(cell_x: float, cell_y: float, cell_size: float,
                           envelope_radius: float,
                           source_x: float = 0.0, source_y: float = 0.0,
                           n_sub: int = 7) -> float:
    """Fraction of a square grid cell inside a circular envelope, by
    subsampling. 6.2.6 note 1 asks for this grading so that flash fire and
    overpressure contours do not make IR and SR jump discontinuously."""
    half = cell_size / 2.0
    hits = 0
    for i in range(n_sub):
        px = cell_x - half + cell_size * (i + 0.5) / n_sub
        for j in range(n_sub):
            py = cell_y - half + cell_size * (j + 0.5) / n_sub
            if math.hypot(px - source_x, py - source_y) <= envelope_radius:
                hits += 1
    return hits / (n_sub * n_sub)
