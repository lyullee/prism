"""
Jet fire: notional nozzle, flame length, radiant heat flux.

Clean room
----------
Implemented from the primary publications. No HyRAM source has been read
for any of it -- only its component leak frequency tables, which are data
rather than code, and are cited to the SAND reports instead. That keeps
the GPL off this file and lets HyRAM serve as an independent check.

Structure vs coefficients
-------------------------
The structure here is sound: mass and momentum conservation through the
notional nozzle, a Froude-number flame length, a weighted multi-point
radiant source with atmospheric attenuation. The numerical coefficients
are the part that needs the papers in hand, and each is marked
NEEDS_SOURCE with the reference to check it against. A coefficient
recalled rather than read is exactly the error already found once in this
project, where a filter leak frequency written from memory was out by a
factor of two.

References to verify against
----------------------------
    notional nozzle     Birch et al. (1984, 1987); Ewan & Moodie (1986)
    flame length        Delichatsios (1993); Molkov & Saffers (2013)
    radiant fraction    Molkov & Saffers (2013); Schefer et al. (2007)
    multi-point source  Hankinson & Lowesmith (2012)
    transmissivity      Wayne (1991)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import CoolProp.CoolProp as CP

from taxonomy import Grade, Provenance, TranscriptionSource

P_AMB = 101325.0
T_AMB = 288.15
G = 9.80665
R_U = 8.314462
M_H2 = 2.01588e-3
M_AIR = 28.9647e-3

H2_HEAT_OF_COMBUSTION = 119.96e6      # J/kg, lower heating value
# H2 + 0.5 (O2 + 3.76 N2). HyRAM+ technical reference eq.40 reports
# 0.02852; the value below follows directly from molecular masses.
H2_STOICH_MASS_FRACTION = 0.028521031947834195


class Confidence(str, Enum):
    STRUCTURE_SOUND = "STRUCTURE_SOUND"       # derivation is first principles
    NEEDS_SOURCE = "NEEDS_SOURCE"             # coefficient must be read


@dataclass(frozen=True)
class Coefficient:
    """A number that came from somewhere. Recording where is the point."""
    value: float
    symbol: str
    reference: str
    confidence: Confidence = Confidence.NEEDS_SOURCE

    def __float__(self) -> float:
        return self.value


# Flame length. Two correlations, and they disagree by 22% at high
# pressure, which is a real disagreement in the field rather than a
# transcription question.
#
# DELICHATSIOS (1993) eq.18 is a Froude-number correlation. It is what
# HyRAM implements, so agreeing with HyRAM on flame length means having
# implemented the same correlation and says nothing about whether it is
# right.
#
# MOLKOV & SAFFERS (2013), IJHE 38, 8141-8158, is hydrogen-specific and
# states plainly that Froude-only correlations are DEFICIENT for
# under-expanded jet fires because they ignore Reynolds and Mach number.
# Their dimensional form
#
#     L_F = 76 (mdot D)^0.347                    best fit
#     L_F = 116 (mdot D)^0.347                   conservative upper bound
#
# is a best fit to 95 published points from several groups at pressures
# to 90 MPa, and needs only the mass flow rate and the actual leak
# diameter -- no notional nozzle at all.
#
# Checked against the paper's own cited experiment: a 4.76 mm nozzle at
# Re = 2870 reconstructs to Fr = 87,800 against the 92,000 quoted, and
# the best fit gives L/D = 101 where the measurements are 134 and 147.
# The conservative line gives 154 and brackets them. A best fit through
# scattered data sitting below the measurements is what a best fit does;
# for a separation distance the conservative line is the defensible one,
# and the paper says so.
#
# Molkov is the default. Delichatsios is kept because it is the basis of
# the cross-check and because dropping a model one disagrees with removes
# the evidence of the disagreement.
C_MOLKOV_FIT = Coefficient(
    76.0, "76", "Molkov & Saffers (2013) eq.8, best fit to 95 points to "
                "90 MPa", Confidence.STRUCTURE_SOUND)
C_MOLKOV_CONSERVATIVE = Coefficient(
    116.0, "116", "Molkov & Saffers (2013), upper limiting curve, 50% "
                  "longer than the best fit", Confidence.STRUCTURE_SOUND)
C_MOLKOV_EXP = Coefficient(
    0.347, "0.347", "Molkov & Saffers (2013) eq.8",
    Confidence.STRUCTURE_SOUND)

C_FLAME_LOW = Coefficient(13.5, "13.5", "Delichatsios (1993) eq.18, read "
                                        "from the paper",
                          Confidence.STRUCTURE_SOUND)
C_FLAME_EXP = Coefficient(0.4, "2/5", "Delichatsios (1993) eq.18",
                          Confidence.STRUCTURE_SOUND)
C_FLAME_DAMP = Coefficient(0.07, "0.07", "Delichatsios (1993) eq.18",
                           Confidence.STRUCTURE_SOUND)
C_FLAME_HIGH = Coefficient(23.0, "23", "Delichatsios (1993) eq.18, the "
                                       "high-Froude asymptote",
                           Confidence.STRUCTURE_SOUND)
FR_TRANSITION = Coefficient(5.0, "Fr_f = 5", "Delichatsios (1993)",
                            Confidence.STRUCTURE_SOUND)

C_XRAD_A = Coefficient(9.45e-9, "9.45e-9",
                       "HyRAM+ eq.109, cited to Molina, Schefer & Houf "
                       "(2007). NOT the form given in that paper, which is "
                       "logarithmic; this is a power law cited to it.",
                       Confidence.NEEDS_SOURCE)
C_XRAD_B = Coefficient(0.47, "0.47", "HyRAM+ eq.109",
                       Confidence.NEEDS_SOURCE)

T_ADIABATIC_H2 = Coefficient(
    2390.0, "T_ad", "stoichiometric adiabatic flame temperature of hydrogen "
                    "in air, K", Confidence.STRUCTURE_SOUND)

# Temperature used in the Delichatsios/HyRAM flame Froude number. This is
# the equilibrium product temperature from the combustion model, not the
# 2390 K RADCAL temperature that travels with the Molina radiant-fraction
# fit. HyRAM+ Figure 3-2 gives 2214 K at a 298 K reactant temperature; at
# the 288.15 K reference condition used here its public result is 2204 K.
T_FROUDE_H2 = Coefficient(
    2204.0, "T_ad,Fr", "HyRAM+ v6 technical reference Figure 3-2 and "
                       "equations 40, 43, and 107",
    Confidence.STRUCTURE_SOUND)

# Planck mean absorption coefficient, computed rather than quoted.
#
# Chmielewski & Gieras (2015), J. Power Technologies 95(2) 97-104, Table 2,
# give PMAC per species as a four-term Gaussian in temperature, in units
# of (m bar)^-1, and their equation 10 mixes them by mole fraction:
#
#     kappa_mix = p_tot * sum_i x_i kappa_i          [1/m]
#
# For stoichiometric H2-air products at 2390 K this gives 0.126 1/m, which
# is what HyRAM's "approximately 0.2 for a hydrogen flame" refers to. The
# units were never the problem.
#
# A calibrated value of 177 stood here, back-solved to make the radiant
# power match an independent implementation. That was wrong about the
# cause: a_p is 0.126 and something else in the chain is out by a factor
# near thirty. Folding the discrepancy into a physical constant hid it
# and would have carried it into any other fuel or flame temperature.
# It is now isolated below, where it can be argued with.
_PMAC_H2O = (
    (63.87, 149.5, 174.3),
    (2.629, 493.6, 111.1),
    (222.9, -2110.0, 1592.0),
    (0.991, 1700.0, 619.2),
)
H2O_MOLE_FRACTION_STOICH = 1.0 / (1.0 + 1.88)   # H2 + 0.5(O2 + 3.76 N2)


# Molina, Schefer & Houf (2007) Table 2 gives a_p directly for the flames
# their correlation was fitted to: 0.23 1/m for hydrogen at an adiabatic
# temperature of 2390 K with an H2O mole fraction of 0.35, computed with
# RADCAL. That is the value to use WITH their correlation, whatever an
# independent route gives, because a correlation and the coefficient it
# was fitted against travel together.
#
# The Chmielewski route below computes 0.126 from HITEMP. The two differ
# by 1.8, and Chmielewski's own paper reports HITEMP and RADCAL diverging
# for several species, so the disagreement is between databases and not
# an error in either transcription.
A_P_MOLINA_H2 = Coefficient(
    0.23, "a_p", "Molina, Schefer & Houf (2007) Table 2, H2 flames, "
                 "RADCAL at T_ad = 2390 K, x_H2O = 0.35",
    Confidence.STRUCTURE_SOUND)


def planck_mean_absorption(t_k: float = None,
                           p_total_bar: float = 1.0) -> float:
    """Mixture Planck mean absorption coefficient [1/m].

    Only water radiates in a hydrogen flame: with no carbon there is no
    soot and no CO2, which is why the emission sits entirely in the water
    bands and why the atmosphere -- also water -- absorbs it so strongly.
    """
    t = float(T_ADIABATIC_H2) if t_k is None else t_k
    kappa = sum(a * math.exp(-((t - b) / g) ** 2) for a, b, g in _PMAC_H2O)
    return p_total_bar * H2O_MOLE_FRACTION_STOICH * kappa


# What is left once a_p is computed properly. The published correlation
# under-predicts the radiant power of an independent implementation by
# about thirty, near enough constant across five decades of release rate,
# which says it is a constant factor somewhere and not a trend. Candidates
# not yet excluded: a different residence time definition in the original,
# a different flame length basis, or a transcription error in the leading
# coefficient of the correlation. Molina, Schefer & Houf (2007) is in the
# project and reading section 3 of it should settle this.
#
# 0.089 against 0.003 is not a tolerance question -- a radiant fraction of
# 0.003 for a hydrogen flame is far below anything reported -- so the
# factor is applied rather than the correlation being taken at face value.
MOLINA_UNEXPLAINED_FACTOR = Coefficient(
    22.7, "-", "UNEXPLAINED. Ratio of an independent implementation's "
               "radiant power to this correlation evaluated with a_p from "
               "Chmielewski & Gieras. Read Molina et al. (2007) sec.3.",
    Confidence.NEEDS_SOURCE)

# What reading the source ruled OUT, which is most of what there was:
#
#   a_p              Table 2 gives 0.23 1/m directly. Not the cause.
#   residence time   equation 2 is the form already implemented, down to
#                    the factor of 3 in the denominator. Not the cause.
#   flame length     cross-checks to 1%, and tau goes as L^3, so a factor
#                    of 23 would need L nearly three times longer.
#   flame width      tau goes as W^2, so it would need W near 0.8 L
#                    against a published 0.17 L.
#
# What reading the source ADDED: the correlation Molina actually presents
# is logarithmic, chi_R proportional to log(tau_G), and Figure 2 plots it
# against tau_G a_p T_ad^4. The power law with an exponent of 0.47 is
# NOT in this paper. It is cited to this paper elsewhere, but it is a
# different function, and that substitution is a candidate for where the
# factor entered.
#
# Molina's own data sits between roughly 5e13 and 1e16 on that abscissa.
# The releases modelled here land near 9e11, below the whole fitted range.
# The correlation is being extrapolated, which is worth stating plainly
# whichever form is used.

ENGULFED = float("inf")

# The flame envelope extends to a DIAMETER of 0.17 L_vis. Hankinson &
# Lowesmith (2012) put it that way explicitly, citing Sivathanu & Gore,
# and HyRAM calls the same number "the flame width".
#
# One constant was doing two jobs here and one of them was wrong. It fed
# the residence time as W_f, correctly, and the engulfment test as a
# radius, which made the exclusion zone twice its true size. The name
# invited it. Two constants now, and the radius is derived rather than
# repeated.
FLAME_WIDTH_RATIO = Coefficient(
    0.17, "W_f / L_vis", "Hankinson & Lowesmith (2012) sec.5, citing "
                         "Sivathanu & Gore; HyRAM+ technical reference",
    Confidence.STRUCTURE_SOUND)
FLAME_RADIUS_RATIO = Coefficient(
    0.085, "R_f / L_vis", "half of FLAME_WIDTH_RATIO",
    Confidence.STRUCTURE_SOUND)


def flame_density(t_adiabatic_k: float = float(T_ADIABATIC_H2)) -> float:
    """Density at the adiabatic flame temperature, using the mean molecular
    weight of the stoichiometric combustion products in air. For hydrogen
    the products are water and the nitrogen carried through."""
    w_mix = 0.0245     # kg/mol, stoichiometric H2-air products
    return P_AMB * w_mix / (R_U * t_adiabatic_k)


def residence_time(rate_kg_s: float, flame_length_m: float,
                   nozzle: "NotionalNozzle" = None) -> float:
    """tau_f = pi rho_f W_f^2 L_vis f_s / (12 mdot).

    The density is that of the burnt gas, not of ambient air; using
    ambient overstates the mass held in the flame by roughly eight."""
    w = float(FLAME_WIDTH_RATIO) * flame_length_m
    return (math.pi * flame_density() * w * w * flame_length_m
            * H2_STOICH_MASS_FRACTION / (12.0 * max(rate_kg_s, 1e-12)))


def radiant_fraction(rate_kg_s: float, flame_length_m: float,
                     nozzle: "NotionalNozzle" = None,
                     form: str = "power") -> float:
    """Molina, Schefer & Houf (2007), which the literature cites in two
    incompatible shapes.

        power   F = 9.45e-9 (tau a_p T_ad^4)^0.47     HyRAM+ eq.109
        log     F = 0.085 log10(tau a_p T_ad^4) - 1.16
                                            Hankinson & Lowesmith eq.5

    Both cite the same paper and they are not the same function. With
    a_p computed properly the group sits near 5e11, where the log form is
    NEGATIVE and the power form gives 0.003. Neither reproduces the 0.089
    an independent implementation reports, and a hydrogen flame does not
    radiate 0.3% of its heat, so both are wrong here by roughly the same
    amount.

    MOLINA_UNEXPLAINED_FACTOR is applied to the power form, which at
    least scales. It cannot rescue the log form: adding a constant offset
    to a logarithm that has already gone negative is not a correction,
    it is a second guess on top of the first. The log form is therefore
    returned unscaled, and it returns zero in this regime, which is the
    honest report of a correlation evaluated outside its range.
    """
    tau = residence_time(rate_kg_s, flame_length_m)
    group = max(tau * float(A_P_MOLINA_H2)
                * float(T_ADIABATIC_H2) ** 4, 1e-30)
    if form == "log":
        x = 0.085 * math.log10(group) - 1.16
    elif form == "power":
        x = (float(C_XRAD_A) * group ** float(C_XRAD_B)
             * float(MOLINA_UNEXPLAINED_FACTOR))
    else:
        raise ValueError(f"unknown radiant fraction form {form!r}")
    return min(max(x, 0.0), 0.4)


FIRE_PROV = Provenance(
    source="primary literature; coefficients pending verification",
    grade=Grade.ENGINEERING_JUDGEMENT,
    transcription=TranscriptionSource.REPORT,
    note="Flame length from Delichatsios (1993) eq.18 and radiant fraction "
         "from Molina, Schefer & Houf (2007), both read from source. Flame "
         "width 0.17 L and the Wayne (1991) transmissivity likewise. The "
          "Power-form radiation includes an unexplained factor 22.7; it is "
          "an engineering sensitivity, not a validated radiation prediction.",
    not_claimable_as=["a validated jet fire model",
                      "validated radiation or thermal-damage prediction"],
)


# --------------------------------------------------------------------------
# notional nozzle
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class NotionalNozzle:
    """The equivalent subsonic source that replaces an underexpanded jet.

    Birch's construction conserves mass and momentum between the real
    orifice and a fictitious larger one at ambient pressure. Momentum flux
    at the orifice is m_dot * u + (P - P_amb) * A, so the pressure term is
    what makes the notional nozzle larger than the hole."""
    diameter_m: float
    velocity_m_s: float
    density_kg_m3: float
    temperature_k: float
    expansion_ratio: float

    @property
    def mass_flow_kg_s(self) -> float:
        area = math.pi * self.diameter_m ** 2 / 4.0
        return self.density_kg_m3 * self.velocity_m_s * area


def notional_nozzle(rate_kg_s: float, throat_pressure_pa: float,
                    throat_velocity_m_s: float, throat_density_kg_m3: float,
                    hole_diameter_m: float,
                    fluid: str = "Hydrogen") -> NotionalNozzle:
    """Expand to ambient conserving mass and momentum.

    m2 = m1                                       (mass)
    m*u2 = m*u1 + (P1 - Pamb)*A1                  (momentum)
    rho2 from the equation of state at Pamb and the expanded temperature.
    """
    a1 = math.pi * hole_diameter_m ** 2 / 4.0
    u2 = throat_velocity_m_s + (throat_pressure_pa - P_AMB) * a1 / max(rate_kg_s, 1e-12)

    # Legacy isentropic-temperature closure, NOT a simultaneous energy
    # balance with the momentum-derived u2. This model-form limitation
    # remains open; do not describe it as conserving total enthalpy.
    try:
        s = CP.PropsSI("S", "P", throat_pressure_pa, "D", throat_density_kg_m3, fluid)
        t2 = CP.PropsSI("T", "P", P_AMB, "S", s, fluid)
        rho2 = CP.PropsSI("D", "P", P_AMB, "S", s, fluid)
    except Exception:
        t2 = T_AMB
        rho2 = P_AMB / ((R_U / M_H2) * T_AMB)

    a2 = rate_kg_s / (rho2 * max(u2, 1e-9))
    d2 = math.sqrt(4.0 * a2 / math.pi)
    return NotionalNozzle(diameter_m=d2, velocity_m_s=u2, density_kg_m3=rho2,
                          temperature_k=t2,
                          expansion_ratio=d2 / max(hole_diameter_m, 1e-12))


# --------------------------------------------------------------------------
# flame length
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Flame:
    length_m: float
    froude: float
    regime: str
    radiant_power_w: float
    radiant_fraction: float
    nozzle: NotionalNozzle
    provenance: Provenance = field(default_factory=lambda: FIRE_PROV)


def flame_froude(nozzle: NotionalNozzle) -> float:
    """Delichatsios (1993) eq.8a / HyRAM+ eq.107.

    Fr_f = u f_s^(3/2) /
           [(rho_j/rho_a)^(1/4) sqrt(g d (T_ad-T_amb)/T_amb)]

    An earlier version put the unburned jet-to-air density difference in
    the last term. That is not the published equation and made a dense,
    high-pressure notional source spuriously less buoyant. It sent the
    25 mm, 700 bar case to the Fr>5 plateau instead of its Fr=4.4
    transition branch, making the flame 13% too long.
    """
    rho_a = P_AMB * M_AIR / (R_U * T_AMB)
    rho_e = nozzle.density_kg_m3
    temperature_rise = max(
        (float(T_FROUDE_H2) - T_AMB) / T_AMB, 1e-12)
    denom = ((rho_e / rho_a) ** 0.25
             * math.sqrt(G * nozzle.diameter_m * temperature_rise))
    return nozzle.velocity_m_s * H2_STOICH_MASS_FRACTION ** 1.5 / max(denom, 1e-12)


def molkov_flame_length(rate_kg_s: float, hole_diameter_m: float,
                        conservative: bool = True) -> float:
    """L_F = C (mdot D)^0.347, Molkov & Saffers (2013) eq.8.

    conservative selects the development-data upper curve rather than
    the best fit. It is not a probabilistic bound or a universal safety
    limit. Eq.8 was developed at 0.4-10.1 mm; larger holes extrapolate."""
    c = (float(C_MOLKOV_CONSERVATIVE) if conservative
         else float(C_MOLKOV_FIT))
    return c * (max(rate_kg_s, 1e-12) * max(hole_diameter_m, 1e-12)) ** float(
        C_MOLKOV_EXP)


def flame_length(rate_kg_s: float, nozzle: NotionalNozzle,
                 hole_diameter_m: Optional[float] = None,
                 model: str = "molkov",
                 conservative: bool = True) -> Flame:
    """Delichatsios dimensionless flame length.

    L* = 13.5 Fr^(2/5) / (1 + 0.07 Fr^2)^(1/5)   for Fr < 5
    L* = 23                                       for Fr >= 5

    with L* = L * f_s / (d * sqrt(rho_e/rho_a)).
    """
    fr = flame_froude(nozzle)

    if model == "molkov":
        if hole_diameter_m is None:
            raise ValueError(
                "the Molkov correlation is in terms of the ACTUAL leak "
                "diameter, not the notional nozzle. Pass hole_diameter_m, "
                "or select model='delichatsios' deliberately.")
        length = molkov_flame_length(rate_kg_s, hole_diameter_m,
                                     conservative)
        regime = "molkov-conservative" if conservative else "molkov-fit"
        eta = radiant_fraction(rate_kg_s, length)
        return Flame(length_m=length, froude=fr, regime=regime,
                     radiant_power_w=eta * rate_kg_s * H2_HEAT_OF_COMBUSTION,
                     radiant_fraction=eta, nozzle=nozzle)

    if fr < float(FR_TRANSITION):
        l_star = (float(C_FLAME_LOW) * fr ** float(C_FLAME_EXP)
                  / (1.0 + float(C_FLAME_DAMP) * fr ** 2) ** 0.2)
        regime = "buoyancy"
    else:
        l_star = float(C_FLAME_HIGH)
        regime = "momentum"

    rho_a = P_AMB * M_AIR / (R_U * T_AMB)
    length = (l_star * nozzle.diameter_m
              * math.sqrt(nozzle.density_kg_m3 / rho_a)
              / H2_STOICH_MASS_FRACTION)

    eta = radiant_fraction(rate_kg_s, length)
    power = eta * rate_kg_s * H2_HEAT_OF_COMBUSTION
    return Flame(length_m=length, froude=fr, regime=regime,
                 radiant_power_w=power, radiant_fraction=eta, nozzle=nozzle)


# --------------------------------------------------------------------------
# radiation
# --------------------------------------------------------------------------

def transmissivity(path_length_m: float, relative_humidity: float = 0.5,
                   temperature_k: float = T_AMB,
                   co2_ppm: float = 400.0) -> float:
    """Atmospheric attenuation, Wayne (1991), as given in the HyRAM+
    technical reference equations 112 to 115.

    The recalled version of this had the first coefficient ten times too
    large, the sign of the last one flipped, and no CO2 term at all.

        tau = 1.006 - 0.001171 log10(X_H2O) - 0.02368 log10(X_H2O)^2
                    - 0.03188 log10(X_CO2) + 0.001164 log10(X_CO2)^2
    """
    if path_length_m <= 0.0:
        return 1.0
    t = temperature_k
    s_mm = math.exp(10.386 - 5132.0 / t)          # sat. vapour pressure, mmHg
    x_h2o = max(relative_humidity * path_length_m * s_mm * 288.651 / t, 1e-12)
    x_co2 = max(path_length_m * (273.0 / t) * (co2_ppm / 335.0), 1e-12)
    lw, lc = math.log10(x_h2o), math.log10(x_co2)
    tau = (1.006 - 0.001171 * lw - 0.02368 * lw ** 2
           - 0.03188 * lc + 0.001164 * lc ** 2)
    return min(max(tau, 0.0), 1.0)


PEAK_FRACTION = Coefficient(
    0.75, "n / N", "Hankinson & Lowesmith (2012) eq.15, n = 0.75N",
    Confidence.STRUCTURE_SOUND)


def weights_hankinson(n_points: int) -> list[float]:
    """Weighted multi-point source weights, Hankinson & Lowesmith (2012)
    equation 15, read from the paper:

        w_j = j w1                                       j = 1..n
        w_j = [n - (n-1)/(N-(n+1)) (j - (n+1))] w1       j = n+1..N
        sum w_j = 1

    with n = 0.75N. Emission rises linearly to a peak three quarters of
    the way along the flame and falls linearly to w1 at the tip. The
    authors base the peak position on narrow-angle radiometer measurements
    of large jet fires and say plainly that the linear variation either
    side was assumed for simplicity and is not intended as a final answer.

    An assumed triangle peaking at 0.6 stood here before. Its shape was
    close, its peak was in the wrong place, and it had no source.

    Note that the peak fraction of the total shifts with N -- 0.122 at
    N = 15, 0.074 at N = 40 -- so the number of points is part of the
    model rather than a numerical detail. The paper reports the incident
    radiation to be independent of N above about 20.
    """
    if n_points <= 1:
        return [1.0]
    n = max(1, min(n_points - 1, int(round(float(PEAK_FRACTION) * n_points))))
    w = [float(j) for j in range(1, n + 1)]
    denom = n_points - (n + 1)
    for j in range(n + 1, n_points + 1):
        if denom <= 0:
            w.append(float(n))
        else:
            w.append(n - ((n - 1) / denom) * (j - (n + 1)))
    total = sum(w)
    return [x / total for x in w]


def heat_flux(flame: Flame, distance_m: float, height_m: float = 1.0,
              n_points: int = 15, relative_humidity: float = 0.5,
              orientation: str = "HORIZONTAL",
              bearing_deg: float = 90.0,
              source_height_m: float = 0.0) -> float:
    """Incident radiant flux [W/m2] at a receptor on the ground.

    Returns ENGULFED when the receptor lies inside the flame envelope. A
    point source model has nothing to say there: as the separation goes to
    zero the inverse square term diverges, and clamping it produces a
    number that looks like a flux and is not one. Direct flame contact is
    a lethality of one and is handled as such, not as radiation.

    bearing_deg is the angle between the jet axis and the line to the
    receptor: 0 means the jet points straight at them, 90 means across.
    A horizontal jet aimed at a receptor is the worst case and a QRA has
    to average over discharge direction rather than assume it.

    Each point contributes Q_i * tau_i / (4 pi r_i^2), with the receptor
    normal to the line of sight -- the conservative choice, and the one
    the Purple Book probit assumes.
    """
    if distance_m <= 0.0:
        return ENGULFED
    w = weights_hankinson(n_points)
    theta = math.radians(bearing_deg)
    r_flame = float(FLAME_RADIUS_RATIO) * flame.length_m
    total = 0.0
    for i, wi in enumerate(w):
        s = flame.length_m * (i + 0.5) / n_points
        if orientation in ("VERTICAL", "UP"):
            px, py, pz = 0.0, 0.0, source_height_m + s
        elif orientation == "DOWN":
            px, py, pz = 0.0, 0.0, source_height_m - s
        else:
            px, py, pz = (s * math.cos(theta), s * math.sin(theta),
                          source_height_m)
        r = math.sqrt((distance_m - px) ** 2 + py ** 2 + (height_m - pz) ** 2)
        if r < r_flame:
            return ENGULFED
        tau = transmissivity(r, relative_humidity)
        total += wi * flame.radiant_power_w * tau / (4.0 * math.pi * r * r)
    return total


def distance_to_flux(flame: Flame, target_w_m2: float,
                     height_m: float = 1.0, relative_humidity: float = 0.5,
                     orientation: str = "HORIZONTAL",
                     bearing_deg: float = 90.0,
                     x_max: float = 500.0,
                     source_height_m: float = 0.0) -> Optional[float]:
    """Outermost distance at which the incident flux equals a target,
    or None when the target is never reached outside the flame.

    Search starts beyond the flame envelope, because inside it the flux is
    not defined. Returns None when the target is never reached. 35 kW/m2
    is the Purple Book threshold at which clothing and buildings ignite.
    """
    def q(x: float) -> float:
        return heat_flux(flame, x, height_m, 15, relative_humidity,
                         orientation, bearing_deg, source_height_m)

    # Search outward from the flame envelope. Along the jet axis the
    # first point outside it is the flame tip, so a head-on search starts
    # there; across the axis it starts at the flame radius.
    #
    # For hydrogen this matters more than it looks. At 6 mm and 350 bar
    # the flux just past the tip is 24 kW/m2 and falling, so the 35 kW/m2
    # contour does not exist outside the flame at all: at that level the
    # hazard IS flame contact. Reporting None there is the right answer
    # and not a failure to converge. An independent implementation returns
    # 14.0 m for the same case, which is the flame length rather than a
    # radiation distance.
    r_flame = float(FLAME_RADIUS_RATIO) * flame.length_m
    if orientation == "HORIZONTAL":
        axial = flame.length_m * max(math.cos(math.radians(bearing_deg)), 0.0)
        lo = math.hypot(axial, r_flame) + 0.05
    else:
        lo = r_flame + 0.05
    if q(lo) < target_w_m2:
        return None
    hi = x_max
    if q(hi) > target_w_m2:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if q(mid) > target_w_m2:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def heat_flux_direction_averaged(
        flame: Flame, distance_m: float, height_m: float = 1.0,
        n_bearings: int = 12, relative_humidity: float = 0.5,
        orientation: str = "HORIZONTAL",
        source_height_m: float = 0.0) -> tuple[float, float, float]:
    """(mean, worst, engulfed_fraction) over discharge direction.

    A QRA does not know which way the hole points. The Purple Book event
    tree does not treat discharge direction at all, yet for a horizontal
    jet the flux at a fixed receptor varies by an order of magnitude
    between a jet aimed at them and one aimed across, so assuming a single
    direction picks the answer. Averaging uniformly over bearing is the
    minimum defensible treatment; the worst case is reported alongside so
    that the averaging is visible rather than buried.

    Bearings on which the receptor is engulfed are excluded from the mean
    and counted separately, because there the outcome is direct flame
    contact, not a flux.
    """
    vals, engulfed = [], 0
    for i in range(n_bearings):
        b = 360.0 * i / n_bearings
        q = heat_flux(flame, distance_m, height_m, 15, relative_humidity,
                      orientation, b, source_height_m)
        if q == ENGULFED:
            engulfed += 1
        else:
            vals.append(q)
    frac = engulfed / n_bearings
    if not vals:
        return ENGULFED, ENGULFED, frac
    return sum(vals) / len(vals), max(vals), frac


NEEDS_SOURCE_LIST = [MOLINA_UNEXPLAINED_FACTOR, C_XRAD_A, C_XRAD_B]
