"""
Gaseous hydrogen jet dispersion.

The last placeholder in the chain. Implemented from the primary
literature, not from HyRAM source, on the same clean-room terms as fire.py.

Physics
-------
A high-pressure hydrogen release is a momentum jet, not a dispersing cloud.
Downstream of the notional nozzle the centreline concentration decays as
the jet entrains air, and for a free turbulent jet that decay is inverse
with distance:

    Y(x) / Y_0 = d_eff / [C1 (x - x0)]                              (1)

where d_eff = d * sqrt(rho_jet / rho_air) is the momentum-equivalent
diameter, which is what makes a light gas jet decay faster than a heavy
one at the same nozzle size. K is around 5 to 6 for the mass fraction of a
round jet.

Hydrogen is buoyant, so the jet eventually stops being a jet. The crossover
is set by the Froude number: above roughly Fr = 10 the release is momentum
dominated over the flammable range and (1) holds; below it the plume lifts
and the ground-level extent is governed by rise rather than by decay.
That is the same buoyancy-versus-advection competition that governs the
LH2 case, and it is gated the same way rather than extrapolated through.

What is gated
-------------
    lfl_distance_m      answered from (1) in the momentum regime
    flammable_mass_kg   from the concentration and mixture-density profile
    footprint_area_m2   steady state, same declared deviation as LH2
    cloud_top_height_m  REFUSED unless the jet is vertical: a buoyant
                        horizontal jet's rise is exactly the closure that
                        is unresolved in the LH2 work, and there is no
                        reason it is better resolved here

References to verify against
----------------------------
    jet decay constant  Chen & Rodi (1980); Birch et al. (1984)
    concentration decay Houf & Schefer (2008)
    buoyancy crossover  Schefer et al. (2008)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import fire
from fire import Coefficient, Confidence, NotionalNozzle, notional_nozzle
from gating import Gated
from taxonomy import Grade, Provenance, TranscriptionSource

P_AMB = fire.P_AMB
T_AMB = fire.T_AMB
R_U = fire.R_U
M_H2 = fire.M_H2
M_AIR = fire.M_AIR
G = fire.G

LFL_VOL_FRACTION = 0.04

# Centreline decay, Schefer, Houf & Williams (2008), IJHE 33, 6373-6384,
# equation 9 and Table 2, read from the paper:
#
#     Y_j / Y_cl = C1 (z - z0,1) / [d (rho_j/rho_a)^(1/2)]
#     d* = d (rho_j/rho_a)^(1/2)          "effective diameter"
#
# The relation is RECIPROCAL: distance goes as d*/(C1 Y), not K d*/Y. The
# first version here had the constant multiplying rather than dividing,
# with K = 5.4. That turned out to be a 12% error and not the factor of
# three suspected, because 5.4 is close to 1/C1 = 4.81. Guessing the wrong
# operation and the wrong constant had nearly cancelled.
#
# Table 2 also gives C2 and z0,2 for equation 10. They were previously
# misread here as a MOLE-fraction centreline correlation. Equation 10 is
# actually the jet SPREADING relation for the mass-fraction half-radius,
# L_1/2/d = C2 (z-z0,2)/d. Equation 11 then supplies the full radial mass-
# fraction profile, Y/Y_cl = exp[-59 (r/(z-z0,1))^2]. The false mole form
# caused the former ~7x disagreement and also hid that the source already
# supplied the radial geometry being approximated by an unsourced angle.
C1_MASS = Coefficient(0.208, "C1", "Schefer, Houf & Williams (2008) Table 2, "
                                   "H2-air, mass fraction",
                      Confidence.STRUCTURE_SOUND)
C2_HALF_RADIUS = Coefficient(
    0.103, "C2", "Schefer, Houf & Williams (2008) eq.10 and Table 2, "
                 "H2-air mass-fraction half-radius",
    Confidence.STRUCTURE_SOUND)
Z0_MASS = Coefficient(4.0, "z0,1/d", "Schefer et al. (2008) Table 2",
                      Confidence.STRUCTURE_SOUND)
Z0_HALF_RADIUS = Coefficient(
    -6.0, "z0,2/d", "Schefer et al. (2008) eq.10 and Table 2",
    Confidence.STRUCTURE_SOUND)
RADIAL_DECAY = Coefficient(
    59.0, "59", "Schefer et al. (2008) eq.11, normalized radial "
                  "mass-fraction profile",
    Confidence.STRUCTURE_SOUND)

# Above this Froude number the jet stays momentum dominated over the
# distance that matters for LFL. Below it the plume lifts.
FR_BUOYANT = Coefficient(10.0, "Fr_crit", "Schefer et al. (2008)")

GH2_PROV = Provenance(
    source="Schefer, Houf & Williams (2008), IJHE 33, 6373-6384, "
           "eqs.9-11 and Table 2",
    grade=Grade.PUBLISHED_UNVALIDATED,
    transcription=TranscriptionSource.REPORT,
    note="Centreline decay read from Schefer, Houf & Williams (2008) "
         "eq.9, spreading from eq.10, and radial mass fraction from eq.11. "
         "An earlier version misread the spreading relation as a mole-"
         "fraction decay equation. Buoyancy crossover remains unverified.",
    not_claimable_as=["a validated dispersion model"],
)

FOOTPRINT_DEVIATION = (
    "Purple Book 4.7.2 B asks for ignition at maximum LFL footprint AREA "
    "over time. The jet solution is steady state, so the steady-state area "
    "is substituted. Declared assumption, not the rule."
)


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


def _mole_to_mass_fraction(y: float) -> float:
    return y * M_H2 / (y * M_H2 + (1.0 - y) * M_AIR)


LFL_MASS_FRACTION = _mole_to_mass_fraction(LFL_VOL_FRACTION)


def mixture_density_kg_m3(mass_fraction: float,
                          temperature_k: float = T_AMB) -> float:
    """Ideal-gas H2-air mixture density at ambient pressure.

    HyRAM+ v5 technical manual equation 76 gives the mixture molecular
    weight as a function of fuel mass fraction and then evaluates density
    with the ideal-gas equation of state. The dispersed far field is at
    ambient pressure; temperature is held at ambient in this similarity
    model because equations 9-11 do not supply an energy equation.
    """
    y = min(max(mass_fraction, 0.0), 1.0)
    molecular_weight = 1.0 / (y / M_H2 + (1.0 - y) / M_AIR)
    return P_AMB * molecular_weight / (R_U * max(temperature_k, 1e-9))


def jet_froude(nozzle: NotionalNozzle) -> float:
    """Fr = u / sqrt(g * d * (rho_air - rho_jet) / rho_jet).

    Momentum over buoyancy at the source. Large means the jet punches
    through before it starts to rise."""
    rho_a = P_AMB * M_AIR / (R_U * T_AMB)
    drho = max(rho_a - nozzle.density_kg_m3, 1e-9)
    return nozzle.velocity_m_s / math.sqrt(
        G * nozzle.diameter_m * drho / nozzle.density_kg_m3)


def effective_diameter(nozzle: NotionalNozzle) -> float:
    """d * sqrt(rho_jet / rho_air): the diameter an air jet of the same
    momentum would have. Hydrogen's low density shrinks it, which is why a
    hydrogen jet dilutes in a shorter distance than its nozzle suggests."""
    rho_a = P_AMB * M_AIR / (R_U * T_AMB)
    return nozzle.diameter_m * math.sqrt(nozzle.density_kg_m3 / rho_a)


def centreline_distance_to_mass(mass_fraction: float,
                                nozzle: NotionalNozzle) -> float:
    """Invert equation 9 for a centreline mass-fraction distance."""
    d_star = effective_diameter(nozzle)
    return (d_star / (float(C1_MASS) * max(mass_fraction, 1e-12))
            + float(Z0_MASS) * nozzle.diameter_m)


def centreline_mass_fraction(distance_m: float,
                             nozzle: NotionalNozzle) -> float:
    """Equation 9, capped at the pure-fuel potential core."""
    axial = distance_m - float(Z0_MASS) * nozzle.diameter_m
    if axial <= 0.0:
        return 1.0
    return min(effective_diameter(nozzle)
               / (float(C1_MASS) * axial), 1.0)


def mass_fraction_half_radius(distance_m: float,
                              nozzle: NotionalNozzle) -> float:
    """Equation 10: radius where Y is half the centreline value."""
    return max(float(C2_HALF_RADIUS)
               * (distance_m
                  - float(Z0_HALF_RADIUS) * nozzle.diameter_m), 0.0)


def radial_mass_fraction(distance_m: float, radius_m: float,
                         nozzle: NotionalNozzle) -> float:
    """Equation 11 combined with the equation 9 centreline value."""
    axial = distance_m - float(Z0_MASS) * nozzle.diameter_m
    if axial <= 0.0:
        return 1.0 if radius_m <= nozzle.diameter_m / 2.0 else 0.0
    eta = max(radius_m, 0.0) / axial
    return centreline_mass_fraction(distance_m, nozzle) * math.exp(
        -float(RADIAL_DECAY) * eta * eta)


def flammable_radius(distance_m: float, threshold_mass_fraction: float,
                     nozzle: NotionalNozzle) -> float:
    """Radius of a mass-fraction contour from equations 9 and 11."""
    y_cl = centreline_mass_fraction(distance_m, nozzle)
    threshold = max(threshold_mass_fraction, 1e-12)
    if y_cl <= threshold:
        return 0.0
    axial = distance_m - float(Z0_MASS) * nozzle.diameter_m
    if axial <= 0.0:
        return nozzle.diameter_m / 2.0
    return axial * math.sqrt(
        math.log(y_cl / threshold) / float(RADIAL_DECAY))


def flammable_profile(threshold_mass_fraction: float,
                      nozzle: NotionalNozzle,
                      n_axial: int = 400
                      ) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Axial coordinates and contour half-widths from equations 9 and 11."""
    if n_axial < 2:
        raise ValueError("n_axial must be at least two")
    x_end = centreline_distance_to_mass(threshold_mass_fraction, nozzle)
    dx = x_end / (n_axial - 1)
    axial = tuple(i * dx for i in range(n_axial))
    radii = tuple(flammable_radius(x, threshold_mass_fraction, nozzle)
                  for x in axial)
    return axial, radii


def flammable_geometry(threshold_mass_fraction: float,
                       nozzle: NotionalNozzle,
                       n_axial: int = 400) -> tuple[float, float, float]:
    """Return maximum width, plan area and H2 mass inside a contour.

    The plan area follows the measured radial profile rather than an
    assumed triangular jet angle. Hydrogen mass integrates that Gaussian
    profile with local ideal-gas H2-air mixture density. Ambient
    temperature is retained because the similarity correlations do not
    include an energy equation.
    """
    axial_coordinates, profile_radii = flammable_profile(
        threshold_mass_fraction, nozzle, n_axial)
    dx = axial_coordinates[1] - axial_coordinates[0]
    radii = list(profile_radii)
    mass_per_length: list[float] = []
    rho_a = mixture_density_kg_m3(0.0)
    density_ratio_slope = M_AIR / M_H2 - 1.0
    for x in axial_coordinates:
        y_cl = centreline_mass_fraction(x, nozzle)
        radius = flammable_radius(x, threshold_mass_fraction, nozzle)
        axial = max(x - float(Z0_MASS) * nozzle.diameter_m, 0.0)
        if radius <= 0.0 or axial <= 0.0:
            mass_per_length.append(0.0)
            continue
        # For rho_mix = rho_air/(1 + aY), integrate
        # 2*pi*r*rho_mix*Y with Y = Y_cl*exp[-k(r/s)^2] from
        # the centreline to the threshold contour. This is the closed-form
        # result of HyRAM+ v5 eq.76 combined with Schefer eq.11.
        mass_per_length.append(
            rho_a * math.pi * axial * axial
            / (float(RADIAL_DECAY) * density_ratio_slope)
            * math.log((1.0 + density_ratio_slope * y_cl)
                       / (1.0 + density_ratio_slope
                          * threshold_mass_fraction)))

    def trapz(values: list[float]) -> float:
        return dx * (sum(values) - 0.5 * values[0] - 0.5 * values[-1])

    return 2.0 * max(radii), trapz([2.0 * r for r in radii]), trapz(
        mass_per_length)


def dispersion(rate_kg_s: float, wind_m_s: float,
               temperature_c: float = 15.0, relative_humidity: float = 50.0,
               duration_s: float = 300.0, *, stability: str = "D",
               throat_pressure_pa: Optional[float] = None,
               throat_velocity_m_s: Optional[float] = None,
               throat_density_kg_m3: Optional[float] = None,
               hole_diameter_m: float = 0.01,
               available_mass_kg: Optional[float] = None) -> DispersionResult:
    """LFL extent of a gaseous hydrogen jet."""
    if None in (throat_pressure_pa, throat_velocity_m_s, throat_density_kg_m3):
        raise ValueError("throat state is required; pass the Discharge result")
    if (not math.isfinite(duration_s) or duration_s <= 0.0
            or not math.isfinite(rate_kg_s) or rate_kg_s <= 0.0):
        raise ValueError("release duration and rate must be finite and positive")
    if available_mass_kg is not None and (
            not math.isfinite(available_mass_kg) or available_mass_kg < 0.0):
        raise ValueError("available release mass must be finite and non-negative")

    nz = notional_nozzle(rate_kg_s, throat_pressure_pa, throat_velocity_m_s,
                         throat_density_kg_m3, hole_diameter_m)
    fr = jet_froude(nz)
    x_lfl = centreline_distance_to_mass(LFL_MASS_FRACTION, nz)

    # premise: the jet must still be momentum dominated where LFL sits
    ratio = float(FR_BUOYANT) / max(fr, 1e-9)
    momentum = fr >= float(FR_BUOYANT)

    if not momentum:
        reason = (f"jet Froude number {fr:.1f} is below {float(FR_BUOYANT):g}: "
                  f"the release is buoyancy dominated and the momentum jet "
                  f"decay does not describe it")
        return DispersionResult(
            lfl_distance_m=Gated.refuse(
                "lfl_distance_m", reason, bound=x_lfl,
                bound_basis="momentum-jet value at the crossover; this is "
                            "where the MODEL's premise fails, not a physical "
                            "limit"),
            flammable_mass_kg=Gated.refuse("flammable_mass_kg", reason),
            footprint_area_m2=Gated.refuse("footprint_area_m2", reason),
            cloud_top_height_m=Gated.refuse(
                "cloud_top_height_m",
                reason + " Rise is the unresolved quantity; no bound."),
            u_crit_m_s=None, wind_m_s=wind_m_s, status="OUT_OF_SCOPE",
            premise_ratio=ratio, provenance=GH2_PROV)

    flags = (f"momentum jet, Fr={fr:.0f}",
             "Schefer et al. (2008) eq.9 centreline and eq.11 radial "
             "mass-fraction profile")
    _width, area, mass = flammable_geometry(LFL_MASS_FRACTION, nz)
    available = rate_kg_s * duration_s
    if available_mass_kg is not None:
        available = min(available, available_mass_kg)
    mass_result = Gated.answer("flammable_mass_kg", mass, flags)
    status = "VALID"
    if mass > available * (1.0 + 1e-9):
        reason = (f"steady cloud requires {mass:.6g} kg but only "
                  f"{available:.6g} kg is available; no cloud build-up model")
        mass_result = Gated.refuse(
            "flammable_mass_kg", reason, bound=available,
            bound_basis="all released hydrogen; inventory bound, not a predicted flammable cloud")
        flags += (reason, "LFL geometry is a steady reference envelope, not a formed transient cloud")
        status = "STEADY_REFERENCE_ONLY"

    return DispersionResult(
        lfl_distance_m=Gated.answer("lfl_distance_m", x_lfl, flags),
        flammable_mass_kg=mass_result,
        footprint_area_m2=Gated.answer(
            "footprint_area_m2", area,
            flags + ("steady state area; see FOOTPRINT_DEVIATION",)),
        cloud_top_height_m=Gated.refuse(
            "cloud_top_height_m",
            "rise of a buoyant horizontal jet is the same unresolved "
            "closure as in the LH2 case and is not better resolved here"),
        u_crit_m_s=None, wind_m_s=wind_m_s, status=status,
        premise_ratio=ratio, provenance=GH2_PROV)


NEEDS_SOURCE_LIST = [FR_BUOYANT]
