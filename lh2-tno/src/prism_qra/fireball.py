"""
Hydrogen fireball: high-pressure tank rupture and LH2 spill.

Makarov, Shentsov, Kuznetsov & Molkov (2021), Hydrogen 2(1), 134-146,
open access, read from the paper. It replaces a Yellow Book
implementation that stood here first and that this paper explicitly rules
out: "the correlations obtained for hydrocarbon fireballs are not
applicable to hydrogen safety engineering", and "fireballs from rupture
of high-pressure hydrogen tanks and liquified hydrogen spills are
generally larger than those from hydrocarbon fuels."

The size of the error, taking the Yellow Book fireball radius against the
conservative hydrogen correlations:

        mass        Yellow Book      GH2 rupture       LH2 spill
        1 kg            6.5 m           19.5 m           10.0 m
      100 kg           28.9 m           90.5 m           79.4 m
     5000 kg          103.2 m          333.4 m          461.9 m

At storage-tank scale the hydrocarbon correlation is out by three to four
times, in the unsafe direction.

Two different correlations, and they are not interchangeable
------------------------------------------------------------
Tank rupture drives an explosive, supersonic expansion and the fireball
is close to hemispherical, so its volume and hence its diameter scale
with mass to the one third. An LH2 spill burns subsonically, is shaped by
buoyancy and entrainment, and takes a mushroom form; its size scales
closer to mass to the one half. The paper attributes the difference to
the time available for buoyancy to act, and notes that small LH2 spills
flash-evaporate fast enough to behave like the first case.

For a cryogenic storage site the LH2 spill correlation is the relevant
one for the pool, and the tank rupture correlation for the high-pressure
gas side.

Hazard distance is set by the fireball, not by the radiation
------------------------------------------------------------
The paper's CFD of the Weyandt stand-alone test found that "the hazard
distance defined by fireball size exceeds the hazard distance defined by
thermal dose during the whole fireball development period", and that the
second-degree burn dose threshold was never reached outside it. So for a
tank rupture the governing question is whether a person is inside the
fireball, and the radiation field outside it is secondary. That inverts
the usual QRA treatment, where a fireball is a radiating sphere and the
hazard is a distance to a flux.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from fire import Coefficient, Confidence
from taxonomy import Grade, Provenance, TranscriptionSource


# --------------------------------------------------------------------------
# high-pressure gaseous hydrogen tank rupture in a fire
# --------------------------------------------------------------------------

# V_b = E_i (V_H2 + V_air) = 257.26 m, with the expansion coefficient for
# adiabatic stoichiometric combustion of hydrogen in air E_i = 6.85.
COMBUSTION_PRODUCT_VOLUME = Coefficient(
    257.26, "V_b/m", "Makarov et al. (2021) sec.3, m3 of combustion "
                     "products per kg of hydrogen", Confidence.STRUCTURE_SOUND)
EXPANSION_COEFFICIENT = Coefficient(
    6.85, "E_i", "adiabatic stoichiometric H2-air expansion ratio",
    Confidence.STRUCTURE_SOUND)

C_GH2_HEMISPHERICAL = Coefficient(
    9.8, "9.8", "Makarov et al. (2021) eq.7, theoretical hemispherical "
                "fireball diameter", Confidence.STRUCTURE_SOUND)
C_GH2_CONSERVATIVE = Coefficient(
    19.5, "19.5", "Makarov et al. (2021) eq.8, calibrated to the 24 m "
                  "fireball of the under-vehicle rupture test",
    Confidence.STRUCTURE_SOUND)
C_GH2_SPHERICAL = Coefficient(
    7.78, "7.78", "Makarov et al. (2021) sec.3, the equivalent spherical "
                  "diameter, 2^(1/3) smaller than hemispherical",
    Confidence.STRUCTURE_SOUND)

# --------------------------------------------------------------------------
# liquid hydrogen spill fireball
# --------------------------------------------------------------------------

C_LH2_BEST_FIT = Coefficient(
    8.16, "8.16", "Makarov et al. (2021) eq.11, unconstrained best fit to "
                  "Zabetakis (1964), R2 = 0.9356", Confidence.STRUCTURE_SOUND)
C_LH2_CONSERVATIVE = Coefficient(
    10.0, "10", "Makarov et al. (2021) eq.12, adjusted to under-predict no "
                "Zabetakis point", Confidence.STRUCTURE_SOUND)
LH2_EXPONENT = Coefficient(
    0.45, "0.45", "Makarov et al. (2021) eq.11 and 12",
    Confidence.STRUCTURE_SOUND)
C_ZABETAKIS = Coefficient(
    8.056, "8.056", "Zabetakis (1964), the original m^0.5 form",
    Confidence.STRUCTURE_SOUND)

# Zabetakis spilled 2.8 to 89 litres of LH2, which at 70.8 kg/m3 is
# 0.20 to 6.3 kg. Anything beyond that is extrapolation and it is
# reported rather than clipped.
LH2_FIT_RANGE_KG = (0.20, 6.30)

FIREBALL_PROV = Provenance(
    source="Makarov, Shentsov, Kuznetsov & Molkov (2021), Hydrogen 2(1) "
           "134-146, open access",
    grade=Grade.PUBLISHED_VALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="Hydrogen-specific. Replaces a Yellow Book implementation that "
         "this paper rules out for hydrogen and that under-predicts by "
         "three to four times at storage-tank scale.",
    not_claimable_as=["a validated result outside the fitted mass range"],
)


@dataclass(frozen=True)
class Fireball:
    mass_kg: float
    size_m: float                 # maximum horizontal size
    height_m: float
    kind: str                     # GH2_RUPTURE or LH2_SPILL
    conservative: bool
    extrapolated: bool            # outside the fitted mass range
    products_volume_m3: float
    duration_s: Optional[float]
    provenance: Provenance = None

    @property
    def radius_m(self) -> float:
        return self.size_m / 2.0

    def contains(self, ground_distance_m: float) -> bool:
        """Whether a receptor at ground level is inside the fireball. For a
        tank rupture this is the governing question: the paper finds the
        fireball larger than the thermal dose hazard distance throughout."""
        return ground_distance_m <= self.radius_m


def gh2_tank_rupture_fireball(mass_kg: float, conservative: bool = True,
                              width_to_height: Optional[float] = None
                              ) -> Fireball:
    """Fireball after a high-pressure hydrogen tank ruptures in a fire.

        D_hms = 9.8 m^(1/3)                 theoretical, hemispherical
        D_c   = 19.5 m^(1/3)                conservative                (8)

    The conservative coefficient is calibrated to the largest reliably
    measured fireball, 24 m from an under-vehicle rupture with 1.87 kg,
    where the vehicle body forced the fireball to spread sideways. A
    stand-alone tank at ground level gives the hemispherical value.

    width_to_height overrides both with the flattened form, equation 9:

        D_p = (257.26 m . 4 (D_p/H_p) / pi)^(1/3)

    A hemisphere corresponds to a ratio of 2. The measured 24 m fireball
    corresponds to 22.6, and the Tamura tests to 12, so real ruptures
    depart from hemispherical by a lot and always toward a larger
    horizontal size.
    """
    m = max(mass_kg, 1e-12)
    vb = float(COMBUSTION_PRODUCT_VOLUME) * m

    if width_to_height is not None:
        d = (vb * 4.0 * width_to_height / math.pi) ** (1.0 / 3.0)
        h = d / width_to_height
        kind_note = f"pancake, D/H = {width_to_height:g}"
    else:
        c = (float(C_GH2_CONSERVATIVE) if conservative
             else float(C_GH2_HEMISPHERICAL))
        d = c * m ** (1.0 / 3.0)
        h = d / 2.0                     # hemisphere
        kind_note = "conservative" if conservative else "hemispherical"

    return Fireball(mass_kg=m, size_m=d, height_m=h, kind="GH2_RUPTURE",
                    conservative=conservative, extrapolated=False,
                    products_volume_m3=vb, duration_s=None,
                    provenance=Provenance(
                        source=FIREBALL_PROV.source,
                        grade=FIREBALL_PROV.grade,
                        transcription=FIREBALL_PROV.transcription,
                        note=f"tank rupture fireball, {kind_note}. "
                             + FIREBALL_PROV.note,
                        not_claimable_as=FIREBALL_PROV.not_claimable_as))


def lh2_spill_fireball(mass_kg: float, conservative: bool = True) -> Fireball:
    """Fireball from an ignited liquid hydrogen spill.

        D_bf = 8.16 m^0.45                                            (11)
        D_c  = 10 m^0.45                                              (12)

    The exponent is near one half rather than one third because an LH2
    spill burns subsonically: buoyancy and entrainment have time to act
    and the fireball takes a mushroom shape, so the even three-dimensional
    expansion behind the one-third scaling does not hold.

    Fitted to Zabetakis (1964) over 2.8 to 89 litres, which is 0.2 to
    6.3 kg. A storage tank is three orders of magnitude beyond that and
    the result is flagged rather than refused: the correlation is the best
    available and the extrapolation is the thing to declare.
    """
    m = max(mass_kg, 1e-12)
    c = (float(C_LH2_CONSERVATIVE) if conservative
         else float(C_LH2_BEST_FIT))
    d = c * m ** float(LH2_EXPONENT)
    lo, hi = LH2_FIT_RANGE_KG
    out = not (lo <= m <= hi)
    return Fireball(
        mass_kg=m, size_m=d, height_m=d, kind="LH2_SPILL",
        conservative=conservative, extrapolated=out,
        products_volume_m3=float(COMBUSTION_PRODUCT_VOLUME) * m,
        duration_s=None,
        provenance=Provenance(
            source=FIREBALL_PROV.source,
            grade=(Grade.PUBLISHED_UNVALIDATED if out
                   else Grade.PUBLISHED_VALIDATED),
            transcription=FIREBALL_PROV.transcription,
            note=(f"LH2 spill fireball. Zabetakis fitted {lo} to {hi} kg; "
                  f"this is {m:.3g} kg" + (", EXTRAPOLATED" if out else "")
                  + ". Height equals width in the original correlation."),
            not_claimable_as=(["a validated size at this mass"] if out
                              else [])))


def zabetakis_original(mass_kg: float) -> float:
    """H_max = W_max = 8.056 sqrt(m), equation 1.

    Kept because the paper shows it is not the best fit to its own data
    (R2 0.9182 against 0.9356 for the free exponent) and calls it a
    practical approximation. Having both makes that visible."""
    return float(C_ZABETAKIS) * math.sqrt(max(mass_kg, 0.0))


# --------------------------------------------------------------------------
# harm criteria
# --------------------------------------------------------------------------

# LaChance, Tchouvelev & Engebo (2011), as tabulated by Makarov et al.
# Incident flux thresholds, kW/m2.
HARM_FLUX_KW = {
    "no_harm_long_exposure": 1.6,
    "pain_20s": 4.5,
    "second_degree_20s": 9.5,
    "first_degree_10s_or_1pct_1min": 13.75,
    "significant_injury_10s_or_100pct_1min": 25.0,
    "1pct_lethality_10s": 36.25,
}

# Thermal dose I^(4/3) t, (kW/m2)^(4/3) s
HARM_DOSE = {
    "first_degree": (80.0, 130.0),
    "second_degree": (240.0, 730.0),
    "third_degree": (870.0, 2640.0),
}

# Temperature thresholds inside or at the edge of a fireball, degC
HARM_TEMPERATURE_C = {
    "no_harm": 70.0,
    "pain_5min": 115.0,
    "third_degree_20s": 309.0,
}


def thermal_dose(flux_kw_m2: float, duration_s: float) -> float:
    """I^(4/3) t. The same quantity the Green Book probit takes, in the
    units this literature reports thresholds in."""
    return max(flux_kw_m2, 0.0) ** (4.0 / 3.0) * max(duration_s, 0.0)


# --------------------------------------------------------------------------
# Planck mean absorption, a third independent route
# --------------------------------------------------------------------------

def planck_absorption_yan(t_k: float = 2390.0,
                          water_mole_fraction: float = 1.0 / (1.0 + 1.88),
                          p_atm: float = 1.0) -> float:
    """a_p = k X_w p, with k = 1.2234e7 T^-2.1564 in (m atm)^-1.

    Yan, Yue & He (2015), as used by Makarov et al. in the CFD behind the
    fireball paper. At 2390 K this gives 0.220 1/m.

    Three independent routes now agree to within a factor of two, and two
    of them to within 5%:

        Molina Table 2, RADCAL          0.23
        this correlation                0.220
        Chmielewski & Gieras, HITEMP    0.126

    A calibrated 177 once stood in fire.py in place of this. It was
    absorbing a factor of about thirty that belongs somewhere else in the
    radiant fraction chain, and putting it in a physical constant hid
    that. The constant is settled; the factor is not.
    """
    k = 1.2234e7 * t_k ** -2.1564
    return k * water_mole_fraction * p_atm


HAZARD_NOTE = (
    "For a tank rupture the paper finds the hazard distance set by the "
    "fireball SIZE rather than by thermal dose: the second-degree burn "
    "dose threshold was never reached outside the fireball, and the "
    "fireball exceeded the dose hazard distance throughout its life. "
    "Modelling a fireball as a radiating sphere and taking a distance to "
    "a flux therefore understates it."
)

YELLOW_BOOK_NOT_APPLICABLE = (
    "Yellow Book 6.5.7 gives r_fb = 3.24 m^0.325 and t = 0.852 m^0.26, "
    "fitted to LPG. Makarov et al. state that hydrocarbon fireball "
    "correlations are not applicable to hydrogen and that hydrogen "
    "fireballs are larger. At 5000 kg the Yellow Book radius is 103 m "
    "against 333 m from the conservative tank-rupture correlation and "
    "462 m from the conservative LH2 spill correlation."
)

NEEDS_SOURCE_LIST = []
