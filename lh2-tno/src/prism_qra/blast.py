"""
Blast wave from a hydrogen tank rupture in a fire, and pressure-impulse
harm criteria.

Molkov & Kashkarov, ICHS 2015, "Blast wave from a high-pressure gas tank
rupture in a fire: stand-alone and under-vehicle hydrogen tanks", read
from the paper.

Why this replaces the Purple Book overpressure route
----------------------------------------------------
Purple Book 5.2.4 gives lethality by zones of peak overpressure and
states plainly that those values do not apply to detonation because the
blast duration differs. Peak pressure alone cannot carry that: two blasts
of equal peak and different duration do different damage, which is why
the criterion is stated over pressure AND impulse in the blast
literature. Hydrogen DDT is credible, so the zone approach was left
unusable here and the radii were computed without lethality attached.

The pressure-impulse thresholds below close that. They are read from
Baker et al. as compiled by Molkov & Kashkarov, and they are functions of
both quantities, so a short intense blast and a long weak one are not
confused.

What the paper establishes about the blast itself
--------------------------------------------------
That combustion feeds it. The prevailing view had been that the shock
outruns the flame and so combustion cannot contribute; the paper shows
that predicting the measured overpressures without it fails, badly. In
the under-vehicle test the chemical energy fed into the blast was THIRTY
times the mechanical energy that got there, because most of the
mechanical energy went into throwing the vehicle 22 m.

So the energy scaling is not the stored gas energy. It is

    alpha E_m + beta (r_sh/r_b)^3 E_ch

with the chemical term growing as the shock sweeps out the volume that
the combustion products will occupy, and saturating once it passes it.

What is NOT implemented here
----------------------------
The decay itself. Baker's dimensionless overpressure and impulse against
dimensionless distance are published as charts, and the method selects a
curve by the starting shock and the scaled vessel radius. Those charts
are not in the retrieved text and cannot be reconstructed from the
equations, so the decay is refused rather than approximated. Everything
that feeds it -- real-gas mechanical energy, chemical energy, r_b, the
starting shock -- is implemented and checked against the paper's own
worked numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from fire import Coefficient, Confidence
from gating import Gated
from taxonomy import Grade, Provenance, TranscriptionSource

P_AMB = 101325.0
R_UNIVERSAL = 8.314
M_H2 = 2.016e-3
M_AIR = 0.0289

# Abel-Noble co-volume for hydrogen
CO_VOLUME_H2 = Coefficient(
    7.69e-3, "b", "Molkov & Kashkarov (2015) nomenclature, m3/kg",
    Confidence.STRUCTURE_SOUND)
GAMMA_H2 = Coefficient(
    1.39, "gamma", "ratio of specific heats for hydrogen at 35 MPa",
    Confidence.STRUCTURE_SOUND)
GAMMA_AIR = 1.4
EXPANSION_H2_AIR = Coefficient(
    6.85, "E_i", "expansion coefficient of stoichiometric H2-air "
                 "combustion products", Confidence.STRUCTURE_SOUND)
HEAT_OF_COMBUSTION = Coefficient(
    1.1993e8, "H_c", "hydrogen lower heating value, J/kg",
    Confidence.STRUCTURE_SOUND)

# Inverse-problem coefficients from the two bonfire tests.
ALPHA_STANDALONE = Coefficient(
    1.8, "alpha", "Molkov & Kashkarov (2015); 2.0 for a perfectly "
                  "reflecting ground, 1.8 allowing for cratering",
    Confidence.STRUCTURE_SOUND)
BETA_STANDALONE = Coefficient(
    0.052, "beta", "fraction of chemical energy feeding the blast, "
                   "stand-alone tank test", Confidence.STRUCTURE_SOUND)
ALPHA_UNDER_VEHICLE = Coefficient(
    0.12, "alpha", "under-vehicle test; most of the mechanical energy went "
                   "into moving the vehicle 22 m", Confidence.STRUCTURE_SOUND)
BETA_UNDER_VEHICLE = Coefficient(
    0.09, "beta", "under-vehicle test; obstruction enhances mixing and the "
                  "weaker shock gives combustion more time",
    Confidence.STRUCTURE_SOUND)

# Two points on the strength class 10 curve, from Purple Book equations
# 4.5 and 4.6, which the book gives in closed form rather than as a chart.
RBAR_ANCHOR_NEAR = 1.5      # 0.3 barg
RBAR_ANCHOR_FAR = 3.0       # 0.1 barg

# Range over which the single-exponent law was CHECKED against published
# hazard distances, rather than assumed valid.
#
# Kashkarov, Li & Molkov (ICHS 2019) publish hazard distances from the
# same methodology this module implements, with the same coefficients --
# 1.8 on mechanical energy and 5.2% of chemical for a stand-alone tank,
# 0.12 and 0.09 under a vehicle. For a 300 L tank at 1000 bar:
#
#     threshold    published   here    ratio   rbar
#     100 kPa          7.0 m   7.0 m    1.01   0.70
#      23 kPa         19.3    21.4      1.11   1.60
#    16.5 kPa         24.0    26.4      1.10   1.98
#     4.8 kPa         59.3    57.6      0.97   4.90
#    1.35 kPa        145.0   108.8      0.75  11.99
#
# Within 15% out to rbar about 5, and 25% LOW by rbar 12. The cause is
# visible in their own points: the local decay exponent falls from 1.83
# at rbar 0.7 to 1.36 at rbar 5, toward the acoustic limit of 1. A single
# exponent fitted between rbar 1.5 and 3.0 decays too fast beyond that.
#
# Twenty-five percent low on the evacuation perimeter is the wrong
# direction, so the far field is refused rather than reported.
RBAR_VALID_NEAR = 0.5
RBAR_VALID_FAR = 5.0

VALIDATION = {
    "source": "Kashkarov, Li & Molkov, ICHS 2019, hazard distance "
              "nomograms, stand-alone 300 L at 1000 bar",
    "100kPa": (7.0, 0.70), "23kPa": (19.3, 1.60), "16.5kPa": (24.0, 1.98),
    "13.8kPa": (27.2, 2.25), "4.8kPa": (59.3, 4.90),
    "1.35kPa": (145.0, 11.99),
    "note": "within 15% to rbar 5; 25% LOW at rbar 12, which is why the "
            "far field is refused",
}
DECAY_B = Coefficient(
    1.5850, "b", "determined by the two Purple Book anchors, not imposed; "
                 "lands between the near-field and far-field asymptotes "
                 "of an ideal blast wave", Confidence.STRUCTURE_SOUND)
DECAY_A = Coefficient(
    0.5630, "a", "same two anchors", Confidence.STRUCTURE_SOUND)

BLAST_PROV = Provenance(
    source="Molkov & Kashkarov, ICHS 2015, paper 329",
    grade=Grade.PUBLISHED_VALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="Validated against the two Weyandt bonfire tests. The empirical "
         "coefficients were fitted to those two configurations and are "
         "not general.",
    not_claimable_as=["a validated model for another configuration"],
)


# --------------------------------------------------------------------------
# stored energy
# --------------------------------------------------------------------------

def hydrogen_mass_abel_noble(volume_m3: float, pressure_pa: float,
                             temperature_k: float = 300.15) -> float:
    """rho = p / (p b + R T / M). The ideal gas law over-states the mass by
    18% at 34.3 MPa and the mechanical energy by 64% at 100 MPa."""
    rho = pressure_pa / (pressure_pa * float(CO_VOLUME_H2)
                         + (R_UNIVERSAL / M_H2) * temperature_k)
    return rho * volume_m3


def mechanical_energy(volume_m3: float, pressure_pa: float,
                      mass_kg: Optional[float] = None,
                      temperature_k: float = 300.15) -> float:
    """E_m = (p_g - p_s)(V - m b)/(gamma - 1), Brode with a real gas.

    The isothermal and thermodynamic-availability routes give more than
    twice this, because both assume the gas returns to ambient
    temperature; the paper excludes them on the grounds that the heating
    happens long after the blast has passed."""
    m = (hydrogen_mass_abel_noble(volume_m3, pressure_pa, temperature_k)
         if mass_kg is None else mass_kg)
    return ((pressure_pa - P_AMB) * (volume_m3 - m * float(CO_VOLUME_H2))
            / (float(GAMMA_H2) - 1.0))


def chemical_energy(mass_kg: float) -> float:
    return mass_kg * float(HEAT_OF_COMBUSTION)


def combustion_products_radius(mass_kg: float) -> float:
    """r_b: the hemisphere the products of complete combustion would fill.

    One mole of hydrogen needs 2.38 moles of air, so the unburnt
    stoichiometric mixture is 3.38 moles per mole of fuel at 22.4 L each,
    and the products expand by 6.85.

    The paper uses this rather than the observed fireball, deliberately:
    measured fireball sizes scatter for reasons nobody can predict, and
    substituting one made the predictions worse."""
    n = mass_kg / M_H2
    v_unburnt = n * 3.38 * 22.4e-3            # m3
    v_burnt = v_unburnt * float(EXPANSION_H2_AIR)
    return (3.0 * v_burnt / (2.0 * math.pi)) ** (1.0 / 3.0)


def speed_of_sound_abel_noble(pressure_pa: float,
                              temperature_k: float = 300.15) -> float:
    rho = pressure_pa / (pressure_pa * float(CO_VOLUME_H2)
                         + (R_UNIVERSAL / M_H2) * temperature_k)
    return math.sqrt(float(GAMMA_H2) * pressure_pa
                     / (rho * (1.0 - float(CO_VOLUME_H2) * rho)))


def speed_of_sound_air(temperature_k: float = 298.15) -> float:
    rho = P_AMB / ((R_UNIVERSAL / M_AIR) * temperature_k)
    return math.sqrt(GAMMA_AIR * P_AMB / rho)


# --------------------------------------------------------------------------
# starting shock
# --------------------------------------------------------------------------

def starting_shock(pressure_pa: float, temperature_k: float = 300.15,
                   ambient_temperature_k: float = 298.15) -> float:
    """Dimensionless starting shock overpressure, from the shock-tube
    relation rather than from the published chart.

        p_i/p_s = S(M) [1 - (g_g-1)(a_s/a_g)(M - 1/M)/(g_s+1)]^(-2g_g/(g_g-1))
        S(M)    = (2 g_s M^2 - (g_s-1))/(g_s+1)
        P_st    = S(M) - 1

    Solving numerically avoids reading a log-log chart by eye, which is
    where this method usually loses its accuracy."""
    a_g = speed_of_sound_abel_noble(pressure_pa, temperature_k)
    a_s = speed_of_sound_air(ambient_temperature_k)
    ratio = pressure_pa / P_AMB
    gs, gg = GAMMA_AIR, float(GAMMA_H2)

    def f(m: float) -> float:
        s = (2.0 * gs * m * m - (gs - 1.0)) / (gs + 1.0)
        inner = 1.0 - (gg - 1.0) * (a_s / a_g) * (m - 1.0 / m) / (gs + 1.0)
        if inner <= 0.0:
            return float("inf")
        return s * inner ** (-2.0 * gg / (gg - 1.0)) - ratio

    lo, hi = 1.0001, 50.0
    if f(lo) > 0:
        return 0.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    m = 0.5 * (lo + hi)
    return (2.0 * gs * m * m - (gs - 1.0)) / (gs + 1.0) - 1.0


@dataclass(frozen=True)
class TankRuptureBlast:
    mass_kg: float
    mechanical_energy_j: float
    chemical_energy_j: float
    products_radius_m: float
    vessel_radius_m: float
    starting_shock: float
    alpha: float
    beta: float
    provenance: Provenance = None

    def scaled_energy(self, distance_m: float) -> float:
        """alpha E_m + beta (r_sh/r_b)^3 E_ch, equation 16.

        The chemical term grows with the swept volume and saturates once
        the shock passes r_b, which is what reproduces the pressure
        plateau seen in the under-vehicle test."""
        f = min((distance_m / self.products_radius_m) ** 3, 1.0)
        return (self.alpha * self.mechanical_energy_j
                + self.beta * f * self.chemical_energy_j)

    def scaled_distance(self, distance_m: float) -> float:
        e = self.scaled_energy(distance_m)
        return distance_m * (P_AMB / max(e, 1e-12)) ** (1.0 / 3.0)

    @property
    def chemical_to_mechanical(self) -> float:
        """How much more chemical than mechanical energy reaches the blast.
        1.4 for the stand-alone test and 30 for the under-vehicle one."""
        m = self.alpha * self.mechanical_energy_j
        return (self.beta * self.chemical_energy_j) / m if m > 0 else math.inf

    def overpressure(self, distance_m: float) -> Gated[float]:
        """Peak side-on overpressure, from the two anchors the Purple Book
        does print.

        The Baker charts cannot be reconstructed and neither can Yellow
        Book Figure 5.8; both select a curve by strength class and read
        it off. But Purple Book equations 4.5 and 4.6 give TWO POINTS on
        the strength class 10 curve in closed form -- 0.3 barg at a Sachs
        scaled distance of 1.5 and 0.1 barg at 3.0 -- and a power law
        through them is determined:

            Ps/pa = 0.563 rbar^-1.585

        The exponent is not imposed. It falls out of the two anchors, and
        it lands between the near-field and far-field asymptotes of an
        ideal blast wave, which is where a real one belongs. That is a
        check, not a derivation.

        VALID BETWEEN THE ANCHORS. Outside 1.5 to 3.0 the law is
        extrapolated and the result is flagged; beyond a factor of three
        either way it is refused, because a two-point fit carries no
        information about curvature.
        """
        e = self.scaled_energy(distance_m)
        if e <= 0.0 or distance_m <= 0.0:
            return Gated.refuse("overpressure_pa",
                                "no energy or no distance")
        rbar = distance_m * (P_AMB / e) ** (1.0 / 3.0)
        ps = float(DECAY_A) * rbar ** -float(DECAY_B) * P_AMB
        if RBAR_ANCHOR_NEAR <= rbar <= RBAR_ANCHOR_FAR:
            return Gated.answer("overpressure_pa", ps,
                                (f"between the Purple Book anchors, "
                                 f"rbar={rbar:.2f}",))
        # Tolerance on the comparison, because valid_distance_range
        # solves for exactly these bounds and a bisection lands on them
        # from either side. Without it the range endpoints refuse and the
        # inverse search cannot start.
        if (rbar < RBAR_VALID_NEAR * (1.0 - 1e-6)
                or rbar > RBAR_VALID_FAR * (1.0 + 1e-6)):
            return Gated.refuse(
                "overpressure_pa",
                f"scaled distance {rbar:.2f} is outside the range this "
                f"power law was checked over, {RBAR_VALID_NEAR} to "
                f"{RBAR_VALID_FAR}. Against Kashkarov et al. the error "
                f"grows to -25% by rbar 12, and the local decay exponent "
                f"falls from 1.83 near field to 1.36 far field, which a "
                f"single exponent cannot follow",
                bound=ps,
                bound_basis="the power law extrapolated, which is what it "
                            "would give if the curvature were zero")
        return Gated.answer("overpressure_pa", ps,
                            (f"EXTRAPOLATED beyond the anchors, "
                             f"rbar={rbar:.2f}",))

    def _rbar(self, distance_m: float) -> float:
        e = self.scaled_energy(distance_m)
        return distance_m * (P_AMB / max(e, 1e-12)) ** (1.0 / 3.0)

    def valid_distance_range(self) -> tuple[float, float]:
        """Physical distances corresponding to the checked scaled range.

        Solved rather than scaled directly, because the scaled energy
        itself depends on distance while the chemical term is growing."""
        def solve(target_rbar: float) -> float:
            lo, hi = 1e-3, 1e5
            for _ in range(120):
                mid = 0.5 * (lo + hi)
                lo, hi = ((mid, hi) if self._rbar(mid) < target_rbar
                          else (lo, mid))
            return 0.5 * (lo + hi)
        return solve(RBAR_VALID_NEAR), solve(RBAR_VALID_FAR)

    def distance_to_overpressure(self, target_pa: float) -> Optional[float]:
        """Inverse, searched inside the checked range only.

        A first version searched from 0.1 m outward and treated a refusal
        as zero overpressure. Beyond the valid range that reads as "the
        target is not reached here" and the search stopped at the near
        edge, returning 60 m where the answer was outside the range
        entirely. Refusing is not the same as reporting zero, and a
        search has to be told the difference."""
        near, far = self.valid_distance_range()
        g_near, g_far = self.overpressure(near), self.overpressure(far)
        if g_near.refused or g_far.refused:
            return None
        if target_pa > g_near._value or target_pa < g_far._value:
            return None            # outside the range that was checked
        lo, hi = near, far
        for _ in range(90):
            mid = 0.5 * (lo + hi)
            g = self.overpressure(mid)
            if g.refused:
                return None
            lo, hi = (mid, hi) if g._value > target_pa else (lo, mid)
        return 0.5 * (lo + hi)


def tank_rupture_blast(volume_m3: float, pressure_pa: float,
                       temperature_k: float = 300.15,
                       under_vehicle: bool = False) -> TankRuptureBlast:
    m = hydrogen_mass_abel_noble(volume_m3, pressure_pa, temperature_k)
    return TankRuptureBlast(
        mass_kg=m,
        mechanical_energy_j=mechanical_energy(volume_m3, pressure_pa, m,
                                              temperature_k),
        chemical_energy_j=chemical_energy(m),
        products_radius_m=combustion_products_radius(m),
        vessel_radius_m=(3.0 * volume_m3 / (4.0 * math.pi)) ** (1.0 / 3.0),
        starting_shock=starting_shock(pressure_pa, temperature_k),
        alpha=(float(ALPHA_UNDER_VEHICLE) if under_vehicle
               else float(ALPHA_STANDALONE)),
        beta=(float(BETA_UNDER_VEHICLE) if under_vehicle
              else float(BETA_STANDALONE)),
        provenance=BLAST_PROV)


# --------------------------------------------------------------------------
# pressure-impulse harm criteria
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PIThreshold:
    """A criterion in pressure AND impulse. Both have to be exceeded.

    This is the point of the diagram: a blast with a high peak and a
    short duration carries little impulse and does different damage from
    a long weak one at the same peak. Purple Book 5.2.4 has only the
    peak, which is why it excludes detonation."""
    name: str
    overpressure_pa: float
    impulse_pa_s: float
    source: str

    def exceeded(self, overpressure_pa: float, impulse_pa_s: float) -> bool:
        return (overpressure_pa >= self.overpressure_pa
                and impulse_pa_s >= self.impulse_pa_s)


# Figure 13 left, from Baker et al. as compiled by Molkov & Kashkarov.
HUMAN_PI = [
    PIThreshold("temporary hearing threshold shift", 1.35e3, 1.0,
                "Baker et al.; taken as the no-harm threshold"),
    PIThreshold("eardrum rupture threshold", 34.0e3, 50.0, "Baker et al."),
    PIThreshold("50% eardrum rupture", 100.0e3, 150.0, "Baker et al."),
    PIThreshold("lung damage threshold", 70.0e3, 125.0,
                "Baker et al., 60 kg body; the pressure asymptote above "
                "1 kPa.s of impulse"),
    PIThreshold("skull fracture threshold", 81.0e3, 1900.0,
                "Baker et al., 60 kg body; impulse governed"),
    PIThreshold("lethality from body translation", 78.0e3, 3900.0,
                "Baker et al., 60 kg body; impulse governed"),
]

# Table 6, peak overpressure only, no impulse condition stated.
HUMAN_PEAK_ONLY_PA = {
    "skin laceration from flying glass": 6.9e3,
    "serious wound from flying glass": 13.8e3,
    "1% eardrum rupture": 16.5e3,
    "50% eardrum rupture": 43.5e3,
    "90% eardrum rupture": 84.0e3,
    "1% fatality, lung haemorrhage": 100.0e3,
    "50% fatality, lung haemorrhage": 140.0e3,
    "99% fatality, lung haemorrhage": 200.0e3,
}

# Table 7. The paper adopts the first, third and last as its separation
# distance criteria.
BUILDING_PEAK_ONLY_PA = {
    "5% window breakage": 0.69e3,
    "50% window breakage": 1.45e3,
    "90% window breakage": 3.7e3,
    "minor damage to house": 4.8e3,
    "failure of doors and window frames": 5.3e3,
    "partial demolition, uninhabitable": 6.9e3,
    "partial collapse of walls and roof": 13.8e3,
    "50% destruction of brickwork": 17.3e3,
    "almost total destruction of house": 34.5e3,
    "possible total destruction": 69.0e3,
}

# Figure 14 left, Baker et al., where both quantities matter.
BUILDING_PI = [
    PIThreshold("minor structural damage", 4.8e3, 130.0, "Baker et al."),
    PIThreshold("major structural damage", 17.0e3, 340.0, "Baker et al."),
    PIThreshold("partial demolition", 40.0e3, 450.0, "Baker et al."),
]


def worst_human_effect(overpressure_pa: float,
                       impulse_pa_s: float) -> Optional[str]:
    """The most severe pressure-impulse threshold exceeded, or None."""
    hit = [t for t in HUMAN_PI if t.exceeded(overpressure_pa, impulse_pa_s)]
    return hit[-1].name if hit else None


def fatality_probability(overpressure_pa: float) -> float:
    """Lung haemorrhage, interpolated on the peak values of Table 6.

    Peak only, so it inherits the limitation this module exists to fix.
    Use the pressure-impulse thresholds where an impulse is available;
    this is for when it is not."""
    pts = [(100.0e3, 0.01), (140.0e3, 0.50), (200.0e3, 0.99)]
    if overpressure_pa < pts[0][0]:
        return 0.0
    if overpressure_pa >= pts[-1][0]:
        return 1.0
    for (p0, f0), (p1, f1) in zip(pts, pts[1:]):
        if p0 <= overpressure_pa < p1:
            return f0 + (f1 - f0) * (overpressure_pa - p0) / (p1 - p0)
    return 1.0


PURPLE_BOOK_COMPARISON = (
    "Purple Book Figure 5.5 puts the indoor fatality fraction at 0.025 "
    "between 0.1 and 0.3 barg and at 1 above 0.3 barg, on peak pressure "
    "alone. Table 6 here puts 1% lung-haemorrhage fatality at 1.0 barg "
    "and 50% at 1.4 barg. The two are not measuring the same thing: the "
    "Purple Book number is dominated by building collapse and applies to "
    "an indoor population, while these are direct pressure effects on a "
    "person outdoors. They should not be mixed in one calculation."
)

NEEDS_SOURCE_LIST = []
