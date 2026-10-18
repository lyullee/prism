"""
Ignited liquid hydrogen spill.

Deliberately NOT called a pool fire. The Yellow Book route -- a burning
rate, a Thomas flame height and a solid flame -- describes a hydrocarbon
pool that establishes and burns at a steady rate. An LH2 spill does not
do that, and the experiments say so.

What HSL measured
-----------------
Royle & Willoughby (2011, 2014) and Hall et al. (2014) spilled liquid
hydrogen at 60 litres a minute onto concrete and ignited it. They report
the outcome as THREE phenomena, not one:

    jet fires          at the release point, in high and low wind
    burn-back          the ignited cloud burning back to the source
    secondary explosions   after burn-back, in one prolonged windy release

There is no steady pool burning at a fixed rate to build a solid flame
around. The fire is a cloud that burns back, leaving a jet at the source.

So this module gives what can be defended: the radiative output of the
burn-back, and the residual jet, which is the existing jet fire model
with the source term of a flashing release. A "pool diameter" is computed
only because the mass balance gives one, and it is not used to build a
cylinder.

Measured values, and how far they are from the hydrocarbon ones
----------------------------------------------------------------
    radiative fraction   0.06 to 0.12        HSL, ignited LH2 spills
    jet flame SEP        7 to 15 kW/m2       BAM, large-scale hydrogen
    hydrocarbon pool SEP 100 to 286 kW/m2    LNG Montoir, Phoenix series

An order of magnitude. Using a hydrocarbon surface emissive power for
hydrogen would overstate the radiation by ten to twenty times, and the
Yellow Book has no hydrogen entry, so the mistake is easy to make.

The secondary explosion
-----------------------
HSL observed one after burn-back in a prolonged windy release, and
attribute it to hydrogen reacting suddenly with air "possibly enriched
with oxygen, that was condensed on the ground". They estimate 400 g to
1200 g of hydrogen, about 100 MJ, and say it is not clear whether the
reaction was in the gas or the condensed phase.

This does NOT contradict the air condensation result already in the
project. That one asks whether nitrogen and oxygen leave the gas phase
INSIDE the dispersing cloud, and finds onset at 88 to 94 mol% hydrogen
against a 75 mol% upper flammability limit -- so within the flammable
range, no. HSL is about air condensing ON THE COLD GROUND beneath the
pool, which is a different place and a different mechanism. Both can be
true, and the module records that rather than letting the earlier result
appear to rule the observation out.

The secondary explosion is enumerated as a possible outcome with its
observed energy, and is NOT given a probability: one occurrence in one
test series is not a frequency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import fire as F
from fire import Coefficient, Confidence
from taxonomy import Grade, Provenance, TranscriptionSource

# Radiative fraction of an ignited LH2 spill, measured. Note this is
# LOWER than the 0.09 to 0.19 the jet fire module computes from the
# Molina correlation for a momentum jet, which is consistent: a
# burn-back through a dispersed cloud is cooler and shorter lived than a
# sustained jet flame.
XRAD_SPILL_LOW = Coefficient(
    0.06, "X_rad low", "Royle & Willoughby / Hall et al., HSL ignited LH2 "
                       "spill experiments", Confidence.STRUCTURE_SOUND)
XRAD_SPILL_HIGH = Coefficient(
    0.12, "X_rad high", "same series", Confidence.STRUCTURE_SOUND)

# Surface emissive power of a large hydrogen flame, measured.
SEP_H2_LOW = Coefficient(
    7.0e3, "SEP low", "BAM large-scale hydrogen jet flame measurements",
    Confidence.STRUCTURE_SOUND)
SEP_H2_HIGH = Coefficient(
    15.0e3, "SEP high", "same", Confidence.STRUCTURE_SOUND)

# For comparison only, never used in a calculation.
SEP_HYDROCARBON_POOL = 100.0e3

# Observed secondary explosion, one occurrence.
SECONDARY_EXPLOSION_MASS_KG = (0.4, 1.2)
SECONDARY_EXPLOSION_ENERGY_J = 100.0e6

SPILL_FIRE_PROV = Provenance(
    source="Royle & Willoughby (2011, 2014) and Hall et al. (2014), HSL "
           "ignited liquid hydrogen spill experiments; BAM large-scale "
           "hydrogen jet flame radiation measurements",
    grade=Grade.PUBLISHED_UNVALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="Measured at 60 litres per minute on concrete. The radiative "
         "fraction range is measured; the geometry is not, because an "
         "ignited LH2 spill does not form a steady pool to build a solid "
         "flame around.",
    not_claimable_as=["a pool fire model",
                      "a validated geometry at another scale"],
)


class SpillFirePhase(str, Enum):
    JET = "JET"                    # at the release point
    BURN_BACK = "BURN_BACK"        # the cloud burning back to the source
    SECONDARY = "SECONDARY"        # observed once, after burn-back


@dataclass(frozen=True)
class SpillFire:
    rate_kg_s: float
    flammable_mass_kg: float
    pool_diameter_m: float
    radiative_fraction_low: float
    radiative_fraction_high: float
    burn_back_energy_j: float
    provenance: Provenance = None

    def radiated_power_range_w(self, duration_s: float) -> tuple[float, float]:
        """Burn-back radiates the flammable inventory over its own
        duration, which is set by the flame speed through the cloud and
        not by a burning rate."""
        e = self.burn_back_energy_j / max(duration_s, 1e-6)
        return (self.radiative_fraction_low * e,
                self.radiative_fraction_high * e)


def equilibrium_pool_diameter(rate_kg_s: float,
                              regression_m_s: float = 1.0e-3,
                              liquid_density: float = 70.8) -> float:
    """From the mass balance alone: spill rate equals evaporation rate.

    Reported because the mass balance gives it and because the dispersion
    model needs a source area, NOT because a fire of this diameter burns
    steadily. The regression rate is the late-phase cryogenic value that
    the dispersion source term already uses."""
    area = rate_kg_s / (regression_m_s * liquid_density)
    return math.sqrt(4.0 * max(area, 0.0) / math.pi)


def spill_fire(rate_kg_s: float, flammable_mass_kg: float) -> SpillFire:
    """Ignited LH2 spill.

    flammable_mass_kg comes from the dispersion model: the mass inside
    the LFL contour at the moment of ignition. That is what burns back,
    and it is not the same as the mass spilled."""
    return SpillFire(
        rate_kg_s=rate_kg_s,
        flammable_mass_kg=max(flammable_mass_kg, 0.0),
        pool_diameter_m=equilibrium_pool_diameter(rate_kg_s),
        radiative_fraction_low=float(XRAD_SPILL_LOW),
        radiative_fraction_high=float(XRAD_SPILL_HIGH),
        burn_back_energy_j=max(flammable_mass_kg, 0.0)
        * F.H2_HEAT_OF_COMBUSTION,
        provenance=SPILL_FIRE_PROV)


def burn_back_heat_flux(sf: SpillFire, distance_m: float,
                        duration_s: float = 10.0,
                        relative_humidity: float = 0.5,
                        conservative: bool = True) -> float:
    """Point source at the cloud centre, which is the honest geometry for
    a flame front sweeping a dispersed cloud.

    A solid flame would need a shape the experiments do not support. The
    conservative branch uses the upper measured radiative fraction."""
    if distance_m <= 0.0:
        return F.ENGULFED
    lo, hi = sf.radiated_power_range_w(duration_s)
    power = hi if conservative else lo
    r = max(distance_m, sf.pool_diameter_m / 2.0)
    if distance_m <= sf.pool_diameter_m / 2.0:
        return F.ENGULFED
    tau = F.transmissivity(r, relative_humidity)
    return power * tau / (4.0 * math.pi * r * r)


def burn_back_distance_to_flux(sf: SpillFire, target_w_m2: float,
                               duration_s: float = 10.0,
                               relative_humidity: float = 0.5,
    conservative: bool = True,
                               x_max: float = 500.0) -> Optional[float]:
    lo = sf.pool_diameter_m / 2.0 + 0.05
    def q(x):
        return burn_back_heat_flux(sf, x, duration_s, relative_humidity,
                                   conservative)
    if q(lo) < target_w_m2 or q(x_max) > target_w_m2:
        return None
    hi = x_max
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if q(mid) > target_w_m2 else (lo, mid)
    return 0.5 * (lo + hi)


WHY_NOT_A_POOL_FIRE = (
    "The Yellow Book pool fire route assumes a liquid pool that "
    "establishes and burns at a steady rate, and builds a solid flame "
    "around it. HSL's ignited LH2 spills produced a jet at the source, a "
    "burn-back of the dispersed cloud, and in one case a secondary "
    "explosion. There is no steady pool to build a flame around, so the "
    "geometry is not modelled and the radiative output is."
)

SEP_WARNING = (
    "Hydrogen flame surface emissive power is 7 to 15 kW/m2 measured at "
    "large scale. A hydrocarbon pool fire is 100 to 286. Using a "
    "hydrocarbon value for hydrogen overstates the radiation by ten to "
    "twenty times, and the Yellow Book has no hydrogen entry to prevent "
    "the substitution."
)

SECONDARY_EXPLOSION_NOTE = (
    "HSL observed one secondary explosion after burn-back in a prolonged "
    "windy release, 400 g to 1200 g of hydrogen and about 100 MJ, and "
    "attribute it to reaction with air condensed on the ground and "
    "possibly enriched in oxygen. They could not tell whether the "
    "reaction was in the gas or the condensed phase.\n\n"
    "This does not contradict slabx_lh2.air_condensation, which finds "
    "condensation onset at 88 to 94 mol% hydrogen against a 75 mol% "
    "upper flammability limit. That result is about air leaving the gas "
    "phase INSIDE the dispersing cloud; HSL is about air condensing on "
    "the cold ground beneath the pool. Different place, different "
    "mechanism, both can hold.\n\n"
    "One occurrence in one test series is not a frequency, so no "
    "probability is attached and the outcome is not enumerated in the "
    "ignition tree. It is recorded here so that it is not forgotten."
)

NEEDS_SOURCE_LIST = []
