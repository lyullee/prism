"""
LEGACY PLACEHOLDER physics, gated.

Every function here returns a number of the right shape and the wrong
value, so that the pipeline can be wired and tested before the real models
exist. Each carries Grade.PLACEHOLDER, which propagates to the final risk
number, so a result computed with these can never be mistaken for a result.

What is NOT placeholder is the gating: the premise test u > u_crit and the
per-quantity refusal are the real structure, and the real slabx-lh2 adapter
should keep them exactly as they are here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gating import (GROUND_DISTANCE_NOTE, Gated, critical_wind_speed)
from taxonomy import Grade, Provenance, TranscriptionSource

STUB = Provenance(
    source="PLACEHOLDER -- not a model",
    grade=Grade.PLACEHOLDER,
    transcription=TranscriptionSource.UNVERIFIED,
    note="Dimensional filler used to wire the pipeline.",
    not_claimable_as=["a distance", "a heat flux", "any physical quantity"],
)

H2_HEAT_OF_COMBUSTION_J_KG = 120e6      # a real property
SAFETY_FACTOR_LFL = 1.25                # from the FFI trials


@dataclass(frozen=True)
class DispersionResult:
    """Each quantity is gated separately: the premise fails for the cloud
    height well before it fails for the ground-level distance."""
    lfl_distance_m: Gated[float]
    flammable_mass_kg: Gated[float]
    footprint_area_m2: Gated[float]
    cloud_top_height_m: Gated[float]
    u_crit_m_s: float
    wind_m_s: float
    provenance: Provenance

    @property
    def any_refused(self) -> bool:
        return any(g.refused for g in (self.lfl_distance_m,
                                       self.flammable_mass_kg,
                                       self.footprint_area_m2,
                                       self.cloud_top_height_m))


def lfl_distance(rate_kg_s: float, wind_m_s: float,
                 stability: str = "D") -> DispersionResult:
    """PLACEHOLDER values, REAL gating."""
    u_crit = critical_wind_speed(rate_kg_s)
    bent_over = wind_m_s >= u_crit

    raw = 25.0 * (max(rate_kg_s, 1e-9) ** 0.5) * (5.0 / max(wind_m_s, 0.5)) ** 0.3
    d = raw * SAFETY_FACTOR_LFL
    mass = rate_kg_s * (d / max(wind_m_s, 0.5))
    area = math.pi * d * d / 4.0
    height = 8.0 * (max(rate_kg_s, 1e-9) ** 0.3)

    if bent_over:
        flags = (f"x{SAFETY_FACTOR_LFL} safety factor",)
        return DispersionResult(
            lfl_distance_m=Gated.answer("lfl_distance_m", d, flags),
            flammable_mass_kg=Gated.answer("flammable_mass_kg", mass, flags),
            footprint_area_m2=Gated.answer("footprint_area_m2", area, flags),
            cloud_top_height_m=Gated.answer("cloud_top_height_m", height,
                                            ("rise closure unresolved",)),
            u_crit_m_s=u_crit, wind_m_s=wind_m_s, provenance=STUB)

    reason = (f"w_c/u > 1: u={wind_m_s:.2f} < u_crit={u_crit:.2f} m/s. "
              f"The bent-over plume premise does not hold.")
    # A ground-level bound is defensible here and a height bound is not:
    # the cloud lifts, so ground reach is bounded by the value at the
    # premise edge, whereas the rise itself is the unresolved quantity.
    edge = (25.0 * (max(rate_kg_s, 1e-9) ** 0.5)
            * (5.0 / u_crit) ** 0.3 * SAFETY_FACTOR_LFL)
    return DispersionResult(
        lfl_distance_m=Gated.refuse(
            "lfl_distance_m", reason, bound=edge,
            bound_basis="value at the premise edge u = u_crit. " +
                        GROUND_DISTANCE_NOTE),
        flammable_mass_kg=Gated.refuse("flammable_mass_kg", reason),
        footprint_area_m2=Gated.refuse("footprint_area_m2", reason),
        cloud_top_height_m=Gated.refuse(
            "cloud_top_height_m", reason +
            " Rise is the unresolved quantity here; no bound is defined."),
        u_crit_m_s=u_crit, wind_m_s=wind_m_s, provenance=STUB)


def jet_flame_length(rate_kg_s: float) -> float:
    return 15.0 * max(rate_kg_s, 1e-9) ** 0.4


def heat_flux(rate_kg_s: float, distance_m: float) -> float:
    if distance_m <= 0.1:
        return 1e6
    power = rate_kg_s * H2_HEAT_OF_COMBUSTION_J_KG
    return 0.15 * power / (4.0 * math.pi * distance_m ** 2)


def fire_duration(rate_kg_s: float, released_kg: float) -> float:
    return released_kg / max(rate_kg_s, 1e-9)


def combustion_energy(flammable_mass_kg: float) -> float:
    return flammable_mass_kg * H2_HEAT_OF_COMBUSTION_J_KG
