"""
Indoor accumulation.

Every consequence model in this project so far assumes the release goes
into the open air. A release inside an enclosure does not disperse; it
accumulates, and for hydrogen it accumulates at the ceiling because the
gas is fourteen times lighter than air.

Why this cannot be skipped for a hydrogen facility
---------------------------------------------------
The outdoor models all rely on buoyancy carrying the cloud away. Indoors
that same buoyancy works against you: it puts the gas at the ceiling and
holds it there in a stratified layer that mixes only slowly with the air
below. A leak far too small to matter outdoors can fill the top of a room
to the flammable limit given hours, and the Purple Book's outdoor event
tree has nothing to say about it.

The physics
-----------
Two regimes, and which one applies is decided by the ratio of the release
momentum to the buoyancy of the accumulating layer.

    well mixed      the jet stirs the whole enclosure; concentration is
                    uniform and rises as released volume over free volume
    stratified      a layer forms at the ceiling and deepens downward,
                    at close to the pure-fuel concentration at the top

The stratified case is the dangerous one and the one hydrogen tends
toward at low release rates, because a weak jet has no momentum to stir
the room.

Ventilation
-----------
A steady-state concentration exists when ventilation removes gas as fast
as the leak supplies it:

    C_ss = Q_leak / (Q_leak + Q_vent)

which for a small leak is approximately the ratio of the two flows. The
useful question is usually the reverse: what ventilation rate keeps the
enclosure below a fraction of the lower flammability limit.

What is NOT modelled
--------------------
Deflagration inside the enclosure. A confined hydrogen explosion depends
on the vent area, the ignition location and the congestion, and none of
those are in the input. The module reports whether a flammable volume
forms and how large it is; what happens if it ignites is refused.

That is also the gap the Emeryville incident sits in, where hydrogen
premixed inside a vent pipe and detonated before the jet flame
established.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from fire import Coefficient, Confidence
from gating import Gated
from taxonomy import Grade, Provenance, TranscriptionSource

LFL_VOL = 0.04
UFL_VOL = 0.75
P_AMB = 101325.0
R_U = 8.314
M_H2 = 2.016e-3
M_AIR = 0.0289
G = 9.81

# Whether the release is still a jet when it reaches the ceiling, or has
# already become a plume.
#
# A first attempt used a Richardson number built on the HOLE diameter.
# That is a source Richardson number and it came out near 1e-7 for every
# case tried, because a small hole gives a fast jet whatever the leak
# rate -- 1e-5 kg/s through 1 mm is already 152 m/s. The criterion never
# fired and every enclosure came back well mixed, which is the same
# failure as a gate that never triggers.
#
# The right length scale is Morton, Taylor & Turner's: L_M = M^(3/4) /
# B^(1/2), built from the momentum and buoyancy FLUXES rather than from
# the hole. A release is jet-like within L_M of the source and plume-like
# beyond it, so comparing L_M with the ceiling height says which arrives.
MORTON_CRITICAL = Coefficient(
    1.0, "L_M / H", "Morton, Taylor & Turner (1956) length scale against "
                    "ceiling height; the transition is gradual and the "
                    "value of order unity is a convention",
    Confidence.NEEDS_SOURCE)

# Fraction of the LFL that ventilation design usually targets.
DESIGN_FRACTION_OF_LFL = 0.25

INDOOR_PROV = Provenance(
    source="mass balance on an enclosure with the buoyant layer treatment "
           "standard in hydrogen safety",
    grade=Grade.ENGINEERING_JUDGEMENT,
    transcription=TranscriptionSource.UNVERIFIED,
    note="Mass balance is exact; the criterion that decides between well "
         "mixed and stratified is order-unity and unverified. Confined "
         "deflagration is not modelled at all.",
    not_claimable_as=["a validated stratification model",
                      "an indoor explosion consequence"],
)


class MixingRegime(str, Enum):
    WELL_MIXED = "WELL_MIXED"
    STRATIFIED = "STRATIFIED"


@dataclass(frozen=True)
class Enclosure:
    volume_m3: float
    floor_area_m2: float
    height_m: float
    air_changes_per_hour: float = 0.0

    @property
    def ventilation_m3_s(self) -> float:
        return self.volume_m3 * self.air_changes_per_hour / 3600.0


@dataclass(frozen=True)
class IndoorResult:
    regime: MixingRegime
    steady_state_fraction: float          # volume fraction, well mixed
    time_to_lfl_s: Optional[float]
    flammable_volume_m3: Gated[float]
    layer_depth_m: Gated[float]
    ventilation_for_design_m3_s: float
    provenance: Provenance = None

    @property
    def reaches_lfl(self) -> bool:
        return self.steady_state_fraction >= LFL_VOL


def volumetric_rate(rate_kg_s: float, temperature_k: float = 288.15
                    ) -> float:
    """Leak mass flow to volume flow at enclosure conditions.

    Taken at room temperature, not at the release temperature: a cold jet
    warms to the room within a metre or two and it is the warmed volume
    that fills the space."""
    rho = P_AMB * M_H2 / (R_U * temperature_k)
    return rate_kg_s / rho


def regime_stratified(rate_kg_s: float, hole_diameter_m: float,
                      height_m: float, temperature_k: float = 288.15
                      ) -> bool:
    return not jet_reaches_ceiling(rate_kg_s, hole_diameter_m, height_m,
                                   temperature_k)


def morton_length(rate_kg_s: float, hole_diameter_m: float,
                  temperature_k: float = 288.15) -> float:
    """L_M = M^(3/4) / B^(1/2), the distance over which a release stops
    behaving as a jet and starts behaving as a plume.

        M = q u          specific momentum flux, m^4/s^2
        B = g' q         specific buoyancy flux, m^4/s^3
        g' = g (rho_a - rho_j) / rho_a
    """
    q = volumetric_rate(rate_kg_s, temperature_k)
    a = math.pi * max(hole_diameter_m, 1e-6) ** 2 / 4.0
    u = q / a
    rho_h2 = P_AMB * M_H2 / (R_U * temperature_k)
    rho_a = P_AMB * M_AIR / (R_U * temperature_k)
    g_prime = G * (rho_a - rho_h2) / rho_a
    m_flux = q * u
    b_flux = g_prime * q
    if b_flux <= 0.0:
        return math.inf
    return m_flux ** 0.75 / b_flux ** 0.5


def jet_reaches_ceiling(rate_kg_s: float, hole_diameter_m: float,
                        height_m: float,
                        temperature_k: float = 288.15) -> bool:
    """True when the release is still momentum dominated at the ceiling
    and can therefore stir the enclosure."""
    return (morton_length(rate_kg_s, hole_diameter_m, temperature_k)
            >= float(MORTON_CRITICAL) * height_m)


def accumulate(rate_kg_s: float, enclosure: Enclosure,
               hole_diameter_m: float = 0.01,
               temperature_k: float = 288.15,
               duration_s: float = 3600.0) -> IndoorResult:
    """Steady state and time to reach the flammable limit.

    duration_s is how long the leak is allowed to run, and it matters:
    the stratified layer deepens for as long as gas arrives, so a depth
    without a time attached means nothing. An hour is the default because
    an undetected indoor leak running for an hour is the case worth
    asking about."""
    q = volumetric_rate(rate_kg_s, temperature_k)
    v = enclosure.ventilation_m3_s
    regime = (MixingRegime.WELL_MIXED
              if jet_reaches_ceiling(rate_kg_s, hole_diameter_m,
                                     enclosure.height_m, temperature_k)
              else MixingRegime.STRATIFIED)

    # well mixed steady state
    c_ss = q / (q + v) if (q + v) > 0 else 0.0

    # time to the flammable limit, well mixed, from the mass balance
    #   V dC/dt = q (1 - C) - v C
    if v <= 0.0:
        t_lfl = (LFL_VOL * enclosure.volume_m3 / q) if q > 0 else None
        if regime_stratified(rate_kg_s, hole_diameter_m,
                             enclosure.height_m, temperature_k):
            # A stratified layer reaches the flammable limit at the
            # ceiling almost at once; what takes time is the layer
            # reaching down to where people are.
            t_lfl = 0.0
    elif c_ss > LFL_VOL:
        tau = enclosure.volume_m3 / (q + v)
        t_lfl = -tau * math.log(1.0 - LFL_VOL / c_ss)
    else:
        t_lfl = None

    if regime is MixingRegime.STRATIFIED:
        # The layer sits at the ceiling near the pure-fuel concentration
        # and deepens as gas arrives, so the flammable volume is the
        # layer volume rather than a fraction of the room.
        # The layer deepens as gas arrives, capped at the ceiling
        # height. Ventilation removes from the layer, since that is where
        # the gas is, so it subtracts directly from the arriving flow.
        net = max(q - v, 0.0)
        depth = Gated.answer(
            "layer_depth_m",
            min(net * duration_s / max(enclosure.floor_area_m2, 1e-6),
                enclosure.height_m),
            (f"after {duration_s / 60:.0f} minutes; the layer deepens for "
             f"as long as the leak runs, so a depth without a time "
             f"attached means nothing",))
        flam = Gated.answer(
            "flammable_volume_m3",
            depth._value * enclosure.floor_area_m2,
            ("the whole layer is taken as flammable, which is "
             "conservative: the top of it is above the upper limit",))
    else:
        depth = Gated.refuse(
            "layer_depth_m",
            "the enclosure is well mixed, so there is no layer to give a "
            "depth for")
        flam = Gated.answer(
            "flammable_volume_m3",
            enclosure.volume_m3 if c_ss >= LFL_VOL else 0.0,
            ("well mixed: either the whole enclosure is flammable or none "
             "of it is",))

    # ventilation to hold the enclosure at a quarter of the flammable
    # limit, which is the usual design target
    target = DESIGN_FRACTION_OF_LFL * LFL_VOL
    v_design = q * (1.0 - target) / target if target > 0 else math.inf

    return IndoorResult(
        regime=regime, steady_state_fraction=c_ss, time_to_lfl_s=t_lfl,
        flammable_volume_m3=flam, layer_depth_m=depth,
        ventilation_for_design_m3_s=v_design, provenance=INDOOR_PROV)


def confined_explosion(result: IndoorResult) -> Gated[float]:
    """Refused.

    A confined hydrogen deflagration depends on the vent area, where it
    ignites and how congested the space is. None of those are inputs
    here, and hydrogen's laminar burning velocity is high enough that the
    difference between a vented deflagration and a detonation is decided
    by exactly those factors.

    This is the same gap the Emeryville incident sits in, where hydrogen
    premixed inside a vent pipe and detonated before the jet flame
    established."""
    return Gated.refuse(
        "confined_overpressure_pa",
        "confined deflagration needs the vent area, the ignition location "
        "and the congestion, none of which are inputs. For hydrogen those "
        "are what decide between a vented deflagration and a detonation, "
        "so assuming any of them would decide the answer")


WHY_OUTDOOR_MODELS_FAIL_INDOORS = (
    "Every outdoor model here relies on buoyancy carrying the cloud away. "
    "Indoors the same buoyancy puts the gas at the ceiling and holds it "
    "in a stratified layer. A leak too small to matter outdoors can fill "
    "the top of a room to the flammable limit given hours, and the Purple "
    "Book outdoor event tree has nothing to say about it."
)

NEEDS_SOURCE_LIST = [MORTON_CRITICAL]
