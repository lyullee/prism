"""Equilibrium air-phase partition for the cryogenic LH2 plug-flow zone.

The usual one-fluid dense-cloud state is inadequate immediately after an LH2
flash: water, oxygen and nitrogen can leave the gas phase while hydrogen
evaporates.  This module determines that partition from species inventories,
one-atmosphere vapour equilibrium and an enthalpy balance.  It does not use a
receptor concentration, cloud width or downstream endpoint.

It is an equilibrium *plug-flow* closure.  Kinetic accommodation, particle
size and slip belong to the following two-fluid transport stage and are kept
explicitly outside this thermodynamic module.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from CoolProp.CoolProp import PropsSI


R_UNIVERSAL = 8.314462618
P_ATM_PA = 101325.0
MW_H2 = .002016
MW_N2 = .0280134
MW_O2 = .0319988
MW_H2O = .01801528
CRITICAL_TEMPERATURE_K = {"Nitrogen": 126.19, "Oxygen": 154.58, "Water": 647.10}
H2_NORMAL_BOILING_TEMPERATURE_K = 20.36890353912107


@dataclass(frozen=True)
class CryogenicPlugFlowInput:
    h2_gas_rate_kg_s: float
    h2_liquid_rate_kg_s: float
    entrained_dry_air_rate_kg_s: float
    h2_source_temperature_K: float
    ambient_temperature_K: float
    relative_humidity_percent: float | None = None
    pressure_pa: float = P_ATM_PA
    # Dry-air mass composition; argon is retained in the N2 remainder because
    # it is small and does not undergo a separate phase calculation here.
    nitrogen_mass_fraction: float = .767
    oxygen_mass_fraction: float = .233
    cp_h2_gas_J_kgK: float = 14300.0
    cp_h2_liquid_J_kgK: float = 9800.0
    latent_h2_J_kg: float = 445000.0
    # Flash-plane inventory that defines the enthalpy reference of the moving
    # parcel.  The current H2 gas/liquid fields may be a d-squared trial state;
    # they must not overwrite the latent energy carried from the source.
    reference_h2_gas_rate_kg_s: float | None = None
    reference_h2_liquid_rate_kg_s: float | None = None
    external_heat_W: float = 0.0

    def __post_init__(self) -> None:
        values = (self.h2_gas_rate_kg_s, self.h2_liquid_rate_kg_s,
                  self.entrained_dry_air_rate_kg_s, self.h2_source_temperature_K,
                  self.ambient_temperature_K, self.pressure_pa,
                  self.cp_h2_gas_J_kgK, self.cp_h2_liquid_J_kgK, self.latent_h2_J_kg,
                  self.external_heat_W)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("all mass rates and thermodynamic values must be finite and non-negative")
        if self.h2_gas_rate_kg_s + self.h2_liquid_rate_kg_s <= 0:
            raise ValueError("hydrogen rate must be positive")
        reference = (self.reference_h2_gas_rate_kg_s, self.reference_h2_liquid_rate_kg_s)
        if (reference[0] is None) != (reference[1] is None):
            raise ValueError("both reference H2 rates must be supplied together")
        if reference[0] is not None:
            if min(reference[0], reference[1]) < 0:
                raise ValueError("reference H2 rates must be non-negative")
            if abs(reference[0] + reference[1] - self.h2_gas_rate_kg_s - self.h2_liquid_rate_kg_s) > 1e-10:
                raise ValueError("reference and current H2 totals must match")
        if self.pressure_pa <= 0 or self.ambient_temperature_K <= 0 or self.h2_source_temperature_K <= 0:
            raise ValueError("pressure and temperatures must be positive")
        if self.external_heat_W < 0:
            raise ValueError("external heat must be non-negative")
        if abs(self.nitrogen_mass_fraction + self.oxygen_mass_fraction - 1.0) > 1e-12:
            raise ValueError("dry-air N2 and O2 fractions must sum to one")
        if self.relative_humidity_percent is not None and not 0 <= self.relative_humidity_percent <= 100:
            raise ValueError("relative humidity must be in [0, 100]")


@dataclass(frozen=True)
class CryogenicPlugFlowState:
    temperature_K: float
    h2_gas_rate_kg_s: float
    h2_liquid_rate_kg_s: float
    nitrogen_gas_rate_kg_s: float
    oxygen_gas_rate_kg_s: float
    water_gas_rate_kg_s: float
    condensed_nitrogen_rate_kg_s: float
    condensed_oxygen_rate_kg_s: float
    condensed_water_rate_kg_s: float
    gas_h2_mole_fraction: float
    gas_density_kg_m3: float
    energy_residual_W: float

    @property
    def condensed_air_rate_kg_s(self) -> float:
        return self.condensed_nitrogen_rate_kg_s + self.condensed_oxygen_rate_kg_s + self.condensed_water_rate_kg_s


def _water_mass_ratio(relative_humidity_percent: float, temperature_K: float, pressure_pa: float) -> float:
    # Murphy--Koop-compatible ice saturation is already used in the LH2
    # package.  Import locally to keep this module's thermodynamic boundary
    # explicit and avoid creating an import cycle.
    from .cryogenic_exchange import saturation_pressure_ice_pa
    pressure_vapour = relative_humidity_percent / 100.0 * saturation_pressure_ice_pa(temperature_K)
    return .62198 * pressure_vapour / max(pressure_pa - pressure_vapour, 1e-12)


def _saturation_mole_fraction(fluid: str, temperature_K: float, pressure_pa: float) -> float:
    """Gas-phase equilibrium mole fraction, zero below a component triple point."""
    if temperature_K >= CRITICAL_TEMPERATURE_K[fluid]:
        # Above a component's critical temperature no condensed equilibrium
        # phase exists at this pressure; CoolProp intentionally has no Q=0
        # state there, which must not be mistaken for complete freezing.
        return 1.0
    try:
        psat = PropsSI("P", "T", temperature_K, "Q", 0, fluid)
    except ValueError:
        # Below the triple point CoolProp does not expose a liquid saturation
        # curve.  The equilibrium vapour inventory is negligible on the
        # one-atmosphere scale used here, so retain no gas component.
        return 0.0
    return min(1.0, max(0.0, psat / pressure_pa))


def _equilibrium_gas_moles(h2_moles: float, total_moles: dict[str, float],
                           temperature_K: float, pressure_pa: float) -> dict[str, float]:
    """Solve species vapour inventories at one total pressure by fixed point."""
    gas = dict(total_moles)
    data = {"n2": ("Nitrogen", MW_N2), "o2": ("Oxygen", MW_O2), "h2o": ("Water", MW_H2O)}
    for _ in range(80):
        n_total = h2_moles + sum(gas.values())
        new: dict[str, float] = {}
        for key, (fluid, _) in data.items():
            y_sat = _saturation_mole_fraction(fluid, temperature_K, pressure_pa)
            # n_i / (n_h2 + sum n_j) = y_sat, subject to inventory.  Picard
            # iteration resolves the shared denominator of all condensables.
            new[key] = min(total_moles[key], y_sat * n_total)
        if max(abs(new[key] - gas[key]) for key in gas) < 1e-13:
            return new
        gas = new
    return gas


def solve_cryogenic_plug_flow(inp: CryogenicPlugFlowInput) -> CryogenicPlugFlowState:
    """Close one LH2/air plug-flow state with phase-separated ambient air."""
    if inp.entrained_dry_air_rate_kg_s == 0.0:
        # Before the first ambient entrainment event, preserve the declared
        # flash state.  Forcing the remaining LH2 liquid to vapour without an
        # energy source would be a source-term error.
        n_h2 = inp.h2_gas_rate_kg_s / MW_H2
        density = inp.pressure_pa * MW_H2 / (R_UNIVERSAL * inp.h2_source_temperature_K)
        return CryogenicPlugFlowState(
            inp.h2_source_temperature_K, inp.h2_gas_rate_kg_s, inp.h2_liquid_rate_kg_s,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            1.0 if n_h2 > 0 else 0.0, density, 0.0,
        )
    water_ratio = (_water_mass_ratio(inp.relative_humidity_percent, inp.ambient_temperature_K, inp.pressure_pa)
                   if inp.relative_humidity_percent is not None else 0.0)
    dry_air = inp.entrained_dry_air_rate_kg_s
    totals = {
        "n2": dry_air * inp.nitrogen_mass_fraction / MW_N2,
        "o2": dry_air * inp.oxygen_mass_fraction / MW_O2,
        "h2o": dry_air * water_ratio / MW_H2O,
    }
    h2_total = inp.h2_gas_rate_kg_s + inp.h2_liquid_rate_kg_s
    h2_moles = h2_total / MW_H2
    # Ambient dry air supplies sensible enthalpy.  Its condensed phase is
    # referenced below the gas phase by its latent heat, so the equilibrium
    # solve adds the released latent heat without a fitted heating factor.
    reference_h2_gas = (inp.h2_gas_rate_kg_s if inp.reference_h2_gas_rate_kg_s is None
                        else inp.reference_h2_gas_rate_kg_s)
    reference_h2_liquid = (inp.h2_liquid_rate_kg_s if inp.reference_h2_liquid_rate_kg_s is None
                           else inp.reference_h2_liquid_rate_kg_s)
    initial_energy = (reference_h2_gas * inp.cp_h2_gas_J_kgK * inp.h2_source_temperature_K
                      + reference_h2_liquid * (inp.cp_h2_liquid_J_kgK * inp.h2_source_temperature_K - inp.latent_h2_J_kg)
                      + dry_air * 1006.0 * inp.ambient_temperature_K
                      + dry_air * water_ratio * 1860.0 * inp.ambient_temperature_K
                      + inp.external_heat_W)
    latent = {"n2": 199000.0, "o2": 213000.0, "h2o": 2.83e6}
    cp_gas = {"n2": 1040.0, "o2": 918.0, "h2o": 1860.0}
    cp_condensed = {"n2": 2000.0, "o2": 1700.0, "h2o": 2100.0}

    def phase_at(temperature_K: float, gas_h2_rate: float):
        gas_moles = _equilibrium_gas_moles(gas_h2_rate / MW_H2, totals, temperature_K, inp.pressure_pa)
        gas_mass = {"n2": gas_moles["n2"] * MW_N2, "o2": gas_moles["o2"] * MW_O2, "h2o": gas_moles["h2o"] * MW_H2O}
        condensed = {key: totals[key] * {"n2": MW_N2, "o2": MW_O2, "h2o": MW_H2O}[key] - gas_mass[key]
                     for key in totals}
        return gas_moles, gas_mass, condensed

    # First test whether the available enthalpy can vaporise all LH2 at the
    # normal boiling temperature.  If not, retain the energy-required liquid
    # inventory at 20.37 K rather than forcing an unpowered gas phase.
    temperature = H2_NORMAL_BOILING_TEMPERATURE_K

    def saturation_energy(gas_h2_rate: float):
        local_moles, local_mass, local_condensed = phase_at(temperature, gas_h2_rate)
        energy = gas_h2_rate * inp.cp_h2_gas_J_kgK * temperature
        energy += (h2_total - gas_h2_rate) * (inp.cp_h2_liquid_J_kgK * temperature - inp.latent_h2_J_kg)
        energy += sum(local_mass[key] * cp_gas[key] * temperature
                      + local_condensed[key] * (cp_condensed[key] * temperature - latent[key])
                      for key in totals)
        return energy, local_moles, local_mass, local_condensed

    # Solve the boiling-temperature liquid inventory as a bracketed enthalpy
    # root.  The former damped fixed-point iteration depended on the trial
    # d-squared gas fraction, violating the state-function character of this
    # equilibrium calculation and allowing artificial flash completion.
    energy_all_gas, _, _, _ = saturation_energy(h2_total)
    if energy_all_gas <= initial_energy:
        gas_h2, liquid_h2 = h2_total, 0.0
    else:
        energy_all_liquid, _, _, _ = saturation_energy(0.0)
        if energy_all_liquid >= initial_energy:
            gas_h2, liquid_h2 = 0.0, h2_total
        else:
            lo, hi = 0.0, h2_total
            for _ in range(100):
                mid = .5 * (lo + hi)
                if saturation_energy(mid)[0] > initial_energy:
                    hi = mid
                else:
                    lo = mid
            gas_h2, liquid_h2 = .5 * (lo + hi), h2_total - .5 * (lo + hi)

    if liquid_h2 <= 1e-12:
        # All LH2 has vaporised: solve the gas/condensate equilibrium
        # temperature with the gas-only H2 heat capacity.
        gas_h2 = h2_total
        def gas_energy(temperature_K: float):
            local_moles, local_mass, local_condensed = phase_at(temperature_K, gas_h2)
            energy = h2_total * inp.cp_h2_gas_J_kgK * temperature_K
            energy += sum(local_mass[key] * cp_gas[key] * temperature_K
                          + local_condensed[key] * (cp_condensed[key] * temperature_K - latent[key])
                          for key in totals)
            return energy, local_moles, local_mass, local_condensed
        lo, hi = H2_NORMAL_BOILING_TEMPERATURE_K, inp.ambient_temperature_K
        f_lo = gas_energy(lo)[0] - initial_energy
        f_hi = gas_energy(hi)[0] - initial_energy
        if f_lo >= 0.0:
            temperature = lo
        elif f_hi <= 0.0:
            temperature = hi
        else:
            for _ in range(100):
                mid = .5 * (lo + hi)
                if gas_energy(mid)[0] > initial_energy:
                    hi = mid
                else:
                    lo = mid
            temperature = .5 * (lo + hi)
        liquid_h2 = 0.0
    else:
        gas_moles, gas_mass, condensed = phase_at(temperature, gas_h2)

    if liquid_h2 <= 1e-12:
        gas_moles, gas_mass, condensed = phase_at(temperature, gas_h2)
    else:
        gas_moles, gas_mass, condensed = phase_at(temperature, gas_h2)
    # Reconstruct energy from the separated phases as an explicit audit.
    reconstructed = (gas_h2 * inp.cp_h2_gas_J_kgK * temperature
                     + liquid_h2 * (inp.cp_h2_liquid_J_kgK * temperature - inp.latent_h2_J_kg)
                     + sum(gas_mass[key] * cp_gas[key] * temperature
                           + condensed[key] * (cp_condensed[key] * temperature - latent[key])
                           for key in totals))
    n_gas_total = gas_h2 / MW_H2 + sum(gas_moles.values())
    x_h2 = (gas_h2 / MW_H2) / max(n_gas_total, 1e-30)
    mw_gas = (gas_h2 + sum(gas_mass.values())) / max(n_gas_total, 1e-30)
    density = inp.pressure_pa * mw_gas / (R_UNIVERSAL * temperature)
    return CryogenicPlugFlowState(
        temperature, gas_h2, liquid_h2, gas_mass["n2"], gas_mass["o2"], gas_mass["h2o"],
        condensed["n2"], condensed["o2"], condensed["h2o"], x_h2, density,
        reconstructed - initial_energy,
    )
