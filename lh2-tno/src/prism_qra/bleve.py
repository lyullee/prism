"""
BLEVE fireball and pool fire.

Yellow Book (CPR 14E) chapter 6, sections 6.5.4 and 6.5.7, read from the
book. These complete the outcome set: the ignition tree already branches
to BLEVE and pool fire, and until now had nothing to hand them to.

Why this matters for an LH2 site
--------------------------------
The storage vessel is the largest inventory on the site and the only
component whose instantaneous release is credible, so the BLEVE branch
carries the tail of the risk. Evaluating that branch as a dispersing
cloud, which is what happened while this module did not exist, replaces
a short intense radiation event with a long dilute one.

Hydrogen specifics, and where the book does not reach
-----------------------------------------------------
The fireball correlations are dimensional fits to hydrocarbon BLEVEs,
mostly LPG. Radius goes as m^0.325 and duration as m^0.26, and neither
carries a fuel property, so applying them to hydrogen is an extrapolation
in substance rather than in scale. Two things push in opposite directions
and neither is quantified here: hydrogen's heat of combustion per kilogram
is about 2.7 times that of propane, which argues for a larger fireball at
equal mass, while its density is far lower, so an equal-volume vessel
holds far less mass.

The surface emissive power route in step 7 needs the vapour pressure in
the vessel, which for a cryogenic tank at 6 bar is not the same quantity
as for a pressurised LPG tank at ambient temperature. It is computed the
same way and flagged.

Pool fire on land uses the book's burning rate and Thomas flame height.
For LH2 the burning rate is not the book's hydrocarbon value; it is taken
from the same cryogenic regression rate the pool radius already uses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import fire as F
from fire import Coefficient, Confidence
from taxonomy import Grade, Provenance, TranscriptionSource

P_AMB = F.P_AMB
G = F.G

# --------------------------------------------------------------------------
# Yellow Book 6.5.7, read from the book
# --------------------------------------------------------------------------

C9_RADIUS = Coefficient(3.24, "c9", "Yellow Book eq.6.90, m/kg^0.325",
                        Confidence.STRUCTURE_SOUND)
C9_EXP = Coefficient(0.325, "-", "Yellow Book eq.6.90",
                     Confidence.STRUCTURE_SOUND)
C10_DURATION = Coefficient(0.852, "c10", "Yellow Book eq.6.91, s/kg^0.26",
                           Confidence.STRUCTURE_SOUND)
C10_EXP = Coefficient(0.26, "-", "Yellow Book eq.6.91",
                      Confidence.STRUCTURE_SOUND)
C6_RADIATED = Coefficient(0.00325, "c6", "Yellow Book eq.6.21, (N/m2)^-0.32",
                          Confidence.STRUCTURE_SOUND)
C6_EXP = Coefficient(0.32, "-", "Yellow Book eq.6.21",
                     Confidence.STRUCTURE_SOUND)

BLEVE_PROV = Provenance(
    source="Yellow Book (CPR 14E) 6.5.7, equations 6.90 to 6.96",
    grade=Grade.PUBLISHED_UNVALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="Correlations fitted to hydrocarbon BLEVEs, principally LPG. "
         "Radius and duration carry no fuel property, so hydrogen is an "
         "extrapolation in substance and not merely in scale.",
    not_claimable_as=["a validated hydrogen fireball model"],
)


@dataclass(frozen=True)
class Fireball:
    mass_kg: float
    radius_m: float
    duration_s: float
    liftoff_height_m: float
    radiated_fraction: float
    net_heat_j_kg: float
    sep_w_m2: float
    provenance: Provenance = None

    @property
    def total_radiated_j(self) -> float:
        return self.radiated_fraction * self.mass_kg * self.net_heat_j_kg


def fireball(mass_kg: float,
             vessel_vapour_pressure_pa: float,
             heat_of_combustion_j_kg: float = F.H2_HEAT_OF_COMBUSTION,
             heat_of_vaporisation_j_kg: float = 445_000.0,
             cp_j_kg_k: float = 14_300.0,
             delta_t_k: float = 0.0) -> Fireball:
    """Steps 1 to 9 of 6.5.7.

        r_fb  = 3.24 m^0.325                                    (6.90)
        t     = 0.852 m^0.26                                    (6.91)
        H     = 2 r_fb                                          (6.22)
        F_s   = 0.00325 P_sv^0.32                               (6.21)
        dH    = dHc - dHv - Cp dT                               (6.94)

    delta_t_k is the superheat above the boiling point. For a cryogenic
    tank vented to its relief setting it is small; the book's LPG case
    has it substantial. Left to the caller rather than assumed.
    """
    m = max(mass_kg, 1e-9)
    r = float(C9_RADIUS) * m ** float(C9_EXP)
    t = float(C10_DURATION) * m ** float(C10_EXP)
    h = 2.0 * r
    fs = float(C6_RADIATED) * max(vessel_vapour_pressure_pa, 1.0) ** float(C6_EXP)
    fs = min(fs, 1.0)
    dh = heat_of_combustion_j_kg - heat_of_vaporisation_j_kg - cp_j_kg_k * delta_t_k
    dh = max(dh, 0.0)
    area = 4.0 * math.pi * r * r
    sep = fs * m * dh / (area * max(t, 1e-9))
    return Fireball(mass_kg=m, radius_m=r, duration_s=t, liftoff_height_m=h,
                    radiated_fraction=fs, net_heat_j_kg=dh, sep_w_m2=sep,
                    provenance=BLEVE_PROV)


def fireball_heat_flux(fb: Fireball, ground_distance_m: float,
                       relative_humidity: float = 0.5,
                       temperature_k: float = F.T_AMB) -> float:
    """Steps 5, 6, 13 and 14.

        X      = sqrt(x^2 + H^2)                                (6.92)
        F_view = (r_fb / X)^2                                   (6.93)
        q"     = SEP F_view tau                                 (6.4)

    The view factor uses the distance to the CENTRE and the transmissivity
    the distance to the SURFACE; the book is explicit about the difference
    and it matters close in, where X and X - r differ by most.
    """
    x_centre = math.hypot(max(ground_distance_m, 0.0), fb.liftoff_height_m)
    if x_centre <= fb.radius_m:
        return F.ENGULFED
    view = (fb.radius_m / x_centre) ** 2
    x_surface = x_centre - fb.radius_m
    tau = F.transmissivity(x_surface, relative_humidity, temperature_k)
    return fb.sep_w_m2 * view * tau


def fireball_distance_to_flux(fb: Fireball, target_w_m2: float,
                              relative_humidity: float = 0.5,
                              x_max: float = 2000.0) -> Optional[float]:
    lo = 0.0
    if fireball_heat_flux(fb, lo, relative_humidity) < target_w_m2:
        return None
    if fireball_heat_flux(fb, x_max, relative_humidity) > target_w_m2:
        return None
    hi = x_max
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        if fireball_heat_flux(fb, mid, relative_humidity) > target_w_m2:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------
# Pool fire, Yellow Book 6.5.4
# --------------------------------------------------------------------------

# Thomas (1963) flame height for a pool fire in still air, which the book
# carries in 6.5.4.
THOMAS_C = Coefficient(42.0, "42", "Yellow Book 6.5.4, Thomas correlation",
                       Confidence.STRUCTURE_SOUND)
THOMAS_EXP = Coefficient(0.61, "0.61", "Yellow Book 6.5.4",
                         Confidence.STRUCTURE_SOUND)

# Cryogenic regression rate. Not the book's hydrocarbon burning rate: this
# is the ~1 mm/s late-phase value that PRESLHY E3.4, Takeno et al. and
# ISO TR 15916 Annex B.1 report for LH2, and which the pool radius model
# already uses, converted to a mass flux.
LH2_REGRESSION_M_S = Coefficient(
    1.0e-3, "y_dot", "PRESLHY E3.4 / Takeno / ISO TR 15916 Annex B.1, late "
                     "phase regression rate for LH2",
    Confidence.STRUCTURE_SOUND)
LH2_LIQUID_DENSITY = 70.8

# Surface emissive power. Hydrogen pool fires are not sooty, so the book's
# hydrocarbon SEP values do not carry over. There is no LH2 pool fire SEP
# in the project; the value below is the optically thin limit reached from
# the same radiant fraction used for jet fires, and is flagged as such.
POOL_PROV = Provenance(
    source="Yellow Book (CPR 14E) 6.5.4 geometry; LH2 burning rate from "
           "cryogenic regression data",
    grade=Grade.ENGINEERING_JUDGEMENT,
    transcription=TranscriptionSource.UNVERIFIED,
    note="Flame height from Thomas as carried by the book. The burning "
         "rate is the cryogenic regression rate rather than the book's "
         "hydrocarbon value. Surface emissive power for an LH2 pool fire "
         "is not established anywhere in this project and is derived from "
         "the jet fire radiant fraction, which is a different flame.",
    not_claimable_as=["a validated pool fire model",
                      "a measured surface emissive power"],
)


@dataclass(frozen=True)
class PoolFire:
    diameter_m: float
    burning_rate_kg_m2_s: float
    flame_height_m: float
    sep_w_m2: float
    duration_s: float
    provenance: Provenance = None

    @property
    def total_power_w(self) -> float:
        area = math.pi * self.diameter_m ** 2 / 4.0
        return (self.burning_rate_kg_m2_s * area
                * F.H2_HEAT_OF_COMBUSTION)


def pool_diameter_from_area(area_m2: float) -> float:
    """Equation 6.64. An irregular pool is transformed to a circle of
    equal area before any view factor is taken."""
    return math.sqrt(4.0 * max(area_m2, 0.0) / math.pi)


def pool_fire(diameter_m: float, pool_mass_kg: Optional[float] = None,
              radiant_fraction: float = 0.15) -> PoolFire:
    """Thomas flame height with the cryogenic burning rate.

        H / D = 42 (m" / (rho_a sqrt(g D)))^0.61

    Duration is the pool mass divided by the burning rate when a mass is
    given, and infinite otherwise: a pool fed continuously burns until the
    feed stops, which is the isolation time, not a property of the pool.
    """
    d = max(diameter_m, 1e-6)
    m_dot = float(LH2_REGRESSION_M_S) * LH2_LIQUID_DENSITY
    rho_a = P_AMB * F.M_AIR / (F.R_U * F.T_AMB)
    h = d * float(THOMAS_C) * (m_dot / (rho_a * math.sqrt(G * d))) ** float(THOMAS_EXP)
    area = math.pi * d * d / 4.0
    power = m_dot * area * F.H2_HEAT_OF_COMBUSTION
    surface = math.pi * d * h + area          # cylinder side plus top
    sep = radiant_fraction * power / max(surface, 1e-9)
    duration = (pool_mass_kg / (m_dot * area)
                if pool_mass_kg is not None and m_dot * area > 0
                else float("inf"))
    return PoolFire(diameter_m=d, burning_rate_kg_m2_s=m_dot,
                    flame_height_m=h, sep_w_m2=sep, duration_s=duration,
                    provenance=POOL_PROV)


def pool_fire_heat_flux(pf: PoolFire, distance_m: float,
                        receptor_height_m: float = 1.0,
                        relative_humidity: float = 0.5,
                        n_points: int = 15) -> float:
    """Multi-point source along the flame axis, as for a jet fire, rather
    than the book's solid flame view factor.

    The book's cylinder view factor and this are not interchangeable:
    Hankinson & Lowesmith measured solid flame shapes running about 1.2
    times the weighted multi-point result in the far field, so a radiant
    fraction derived for one is not valid in the other without adjustment.
    The multi-point route is used throughout this project so that jet and
    pool fires stay on one basis.
    """
    r_pool = pf.diameter_m / 2.0
    if distance_m <= r_pool:
        return F.ENGULFED
    w = F.weights_hankinson(n_points)
    area = math.pi * pf.diameter_m * pf.flame_height_m + math.pi * r_pool ** 2
    power = pf.sep_w_m2 * area
    total = 0.0
    for i, wi in enumerate(w):
        z = pf.flame_height_m * (i + 0.5) / n_points
        r = math.hypot(distance_m, receptor_height_m - z)
        r = max(r, r_pool)
        tau = F.transmissivity(r, relative_humidity)
        total += wi * power * tau / (4.0 * math.pi * r * r)
    return total


def pool_fire_distance_to_flux(pf: PoolFire, target_w_m2: float,
                               relative_humidity: float = 0.5,
                               x_max: float = 1000.0) -> Optional[float]:
    lo = pf.diameter_m / 2.0 + 0.05
    if pool_fire_heat_flux(pf, lo, relative_humidity=relative_humidity) < target_w_m2:
        return None
    hi = x_max
    if pool_fire_heat_flux(pf, hi, relative_humidity=relative_humidity) > target_w_m2:
        return None
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        if pool_fire_heat_flux(pf, mid,
                               relative_humidity=relative_humidity) > target_w_m2:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


NEEDS_SOURCE_LIST = []
