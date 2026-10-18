"""Non-empirical LH2 cloud exchange with humid air and a wetted ground.

The module is intentionally opt-in: relative humidity and the wetted ground
area must be declared upstream.  It never substitutes a sensor concentration,
nor assumes a humidity value merely because a test was wet or cloudy.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


MW_WATER = .01801528
MW_AIR = .028965
CP_ICE = 2100.0
LATENT_VAPOUR_TO_ICE_J_KG = 2.83e6


def saturation_pressure_ice_pa(temperature_K: float) -> float:
    """Murphy--Koop ice saturation pressure, valid for cryogenic cloud work."""
    if temperature_K <= 0.0:
        raise ValueError("temperature must be positive")
    return math.exp(9.550426 - 5723.265 / temperature_K + 3.53068 * math.log(temperature_K) - .00728332 * temperature_K)


def humidity_ratio(vapour_pressure_pa: float, pressure_pa: float = 101325.0) -> float:
    if not 0.0 <= vapour_pressure_pa < pressure_pa:
        raise ValueError("vapour pressure must be in [0, pressure)")
    return (MW_WATER / MW_AIR) * vapour_pressure_pa / max(pressure_pa - vapour_pressure_pa, 1e-30)


@dataclass(frozen=True)
class HumidAirExchange:
    ambient_temperature_K: float
    relative_humidity_percent: float
    pressure_pa: float = 101325.0

    def __post_init__(self) -> None:
        if self.ambient_temperature_K <= 0 or self.pressure_pa <= 0:
            raise ValueError("temperature and pressure must be positive")
        if not 0 <= self.relative_humidity_percent <= 100:
            raise ValueError("relative humidity must lie in [0, 100]")

    @property
    def ambient_humidity_ratio(self) -> float:
        return humidity_ratio(self.relative_humidity_percent / 100.0 * saturation_pressure_ice_pa(self.ambient_temperature_K), self.pressure_pa)

    def condensation_from_dry_air(self, dry_air_rate_kg_s: float, cloud_temperature_K: float) -> float:
        """Equilibrium upper bound for ice deposition in an equilibrated parcel."""
        if dry_air_rate_kg_s < 0:
            raise ValueError("dry_air_rate_kg_s must be non-negative")
        retained = humidity_ratio(min(saturation_pressure_ice_pa(cloud_temperature_K), .999 * self.pressure_pa), self.pressure_pa)
        return dry_air_rate_kg_s * max(0.0, self.ambient_humidity_ratio - retained)

    def latent_heating_W(self, dry_air_rate_kg_s: float, cloud_temperature_K: float) -> float:
        return self.condensation_from_dry_air(dry_air_rate_kg_s, cloud_temperature_K) * LATENT_VAPOUR_TO_ICE_J_KG


@dataclass(frozen=True)
class WettedGroundExchange:
    """Conduction-limited heat uptake by a declared, wetted concrete surface.

    The semi-infinite-solid expression is only valid over the supplied wetted
    area.  A gas cloud above dry concrete must use zero area, rather than an
    invented thermal-contact coefficient.
    """

    thermal_conductivity_W_mK: float
    thermal_diffusivity_m2_s: float
    initial_ground_temperature_K: float
    wetted_area_m2: float

    def __post_init__(self) -> None:
        if min(self.thermal_conductivity_W_mK, self.thermal_diffusivity_m2_s, self.initial_ground_temperature_K) <= 0:
            raise ValueError("ground properties must be positive")
        if self.wetted_area_m2 < 0:
            raise ValueError("wetted_area_m2 must be non-negative")

    def heat_rate_W(self, interface_temperature_K: float, contact_age_s: float) -> float:
        if contact_age_s <= 0 or self.wetted_area_m2 == 0:
            return 0.0
        q_flux = (self.thermal_conductivity_W_mK * (self.initial_ground_temperature_K - interface_temperature_K)
                  / math.sqrt(math.pi * self.thermal_diffusivity_m2_s * contact_age_s))
        return max(0.0, q_flux) * self.wetted_area_m2
