"""Provider-state-aware SLABx-LH2 liquid boundary adapter.

The external ``lh2dt`` model can return a saturated two-phase state for which
pressure and temperature alone do not identify a unique thermodynamic state.
SLABx's public integrated-source entry point accepts only ``P,T`` and can
therefore evaluate a different state at that boundary.  This adapter keeps
the provider enthalpy/entropy as the upstream state, evaluates the same HEM
critical-flow search, and then uses SLABx's downstream flash/droplet helpers.

The equipment provider remains the final mass-rate owner.  The HEM result is
only a compatibility check and the SLABx partition is scaled by the existing
relative-rate gate before a PRISM packet can be created.
"""
from __future__ import annotations

from math import isfinite, pi, sqrt
from typing import Any


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _unit(direction: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = sqrt(sum(value * value for value in direction))
    if norm <= 0.0 or not isfinite(norm):
        raise ValueError("direction_enu must be a non-zero finite vector")
    return tuple(value / norm for value in direction)


def _critical_from_provider_state(
    provider: dict,
    *,
    pressure_pa: float,
    entropy_j_kg_k: float,
    enthalpy_j_kg: float,
    back_pressure_pa: float,
    diameter_m: float,
    discharge_coefficient: float,
    fluid: str,
) -> dict:
    """Search the isentrope using the provider's explicit ``h`` and ``s``."""

    import CoolProp.CoolProp as CP

    if pressure_pa <= back_pressure_pa:
        raise ValueError("provider pressure must exceed ambient pressure")
    if diameter_m <= 0.0 or not 0.0 < discharge_coefficient <= 1.0:
        raise ValueError("positive diameter and 0<Cd<=1 are required")
    low = back_pressure_pa
    high = pressure_pa * (1.0 - 1.0e-9)
    best: tuple[float, float, float, float, float] | None = None
    for iteration in range(3):
        step = (high - low) / 800.0
        candidates: list[tuple[float, float, float, float, float]] = []
        for index in range(1, 800):
            trial_pressure = low + index * step
            try:
                throat_h = float(CP.PropsSI("H", "P", trial_pressure, "S", entropy_j_kg_k, fluid))
                throat_density = float(CP.PropsSI("D", "P", trial_pressure, "S", entropy_j_kg_k, fluid))
            except (ValueError, RuntimeError):
                continue
            delta_h = enthalpy_j_kg - throat_h
            if throat_density <= 0.0 or delta_h <= 0.0:
                continue
            velocity = sqrt(2.0 * delta_h)
            candidates.append((throat_density * velocity, trial_pressure, throat_h, throat_density, velocity))
        if not candidates:
            raise ValueError("no provider-state HEM critical-flow state is available")
        best = max(candidates)
        if iteration < 2:
            half = max(step * 3.0, 1.0)
            low = max(back_pressure_pa, best[1] - half)
            high = min(pressure_pa, best[1] + half)
    assert best is not None
    flux, throat_pressure, throat_h, throat_density, velocity = best
    area = pi * diameter_m**2 / 4.0
    return {
        "model": "provider_state_HEM_isentropic_search",
        "critical_mass_flux_kg_m2_s": flux,
        "mass_flow_kg_s": discharge_coefficient * area * flux,
        "critical_pressure_pa": throat_pressure,
        "mixture_enthalpy_j_kg": throat_h,
        "mixture_density_kg_m3": throat_density,
        "velocity_m_s": velocity,
        "energy_residual_j_kg": enthalpy_j_kg - throat_h - velocity**2 / 2.0,
        "upstream_entropy_j_kg_k": entropy_j_kg_k,
        "upstream_enthalpy_j_kg": enthalpy_j_kg,
        "fluid": fluid,
    }


def evaluate_provider_state_partition(provider: dict, packet: dict) -> tuple[dict, dict]:
    """Return one SLABx partition row and its upstream compatibility audit.

    The caller must have already put the external SLABx source tree on
    ``sys.path``.  This keeps the optional dependency out of the normal PRISM
    import path.
    """

    import CoolProp.CoolProp as CP
    from slabx_lh2.integrated_lh2_source import (
        AmbientState,
        IntegratedSourceInput,
        ModelChoices,
        NozzleGeometry,
        PipeState,
        TankState,
        _droplets,
        _fictitious,
        _trajectory,
    )

    source_pressure = _finite(provider["source_pressure_pa"], "source_pressure_pa")
    source_temperature = _finite(provider["source_temperature_k"], "source_temperature_k")
    source_enthalpy = _finite(provider["source_specific_enthalpy_j_kg"], "source_specific_enthalpy_j_kg")
    source_entropy = _finite(provider["source_specific_entropy_j_kg_k"], "source_specific_entropy_j_kg_k")
    provider_total = _finite(provider["total_mass_flow_kg_s"], "provider total_mass_flow_kg_s")
    if provider_total < 0.0:
        raise ValueError("provider total mass flow must be non-negative")

    geometry = packet["source_geometry"]
    diameter = sqrt(4.0 * _finite(geometry["full_open_area_m2"], "full_open_area_m2") / pi)
    direction = _unit(tuple(_finite(value, "direction_enu") for value in geometry["direction_enu"]))
    fluid = str(packet.get("fluid", "ParaHydrogen"))
    ambient_pressure = _finite(packet["ambient_pressure_pa"], "ambient_pressure_pa")
    ambient_temperature = _finite(packet.get("ambient_temperature_k", 288.15), "ambient_temperature_k")
    discharge_coefficient = _finite(geometry["discharge_coefficient"], "discharge_coefficient")
    critical = _critical_from_provider_state(
        provider,
        pressure_pa=source_pressure,
        entropy_j_kg_k=source_entropy,
        enthalpy_j_kg=source_enthalpy,
        back_pressure_pa=ambient_pressure,
        diameter_m=diameter,
        discharge_coefficient=discharge_coefficient,
        fluid=fluid,
    )
    model_total = critical["mass_flow_kg_s"]
    relative_error = (
        None if provider_total <= 1.0e-12 else abs(model_total - provider_total) / provider_total
    )

    try:
        throat_temperature = float(CP.PropsSI("T", "P", critical["critical_pressure_pa"], "H", critical["mixture_enthalpy_j_kg"], fluid))
        throat_quality = float(CP.PropsSI("Q", "P", critical["critical_pressure_pa"], "H", critical["mixture_enthalpy_j_kg"], fluid))
    except (ValueError, RuntimeError):
        throat_temperature = source_temperature
        throat_quality = _finite(provider.get("source_vapour_quality", 0.0), "source_vapour_quality")
    throat_quality = min(1.0, max(0.0, throat_quality))
    inp = IntegratedSourceInput(
        tank=TankState(
            pressure_pa=source_pressure,
            temperature_k=source_temperature,
            volume_m3=_finite(packet.get("tank_volume_m3", 1.0), "tank_volume_m3"),
            vapour_quality=min(1.0, max(0.0, _finite(provider.get("source_vapour_quality", 0.0), "source_vapour_quality"))),
            fluid=fluid,
        ),
        pipe_sections=(),
        nozzle=NozzleGeometry(
            diameter_m=diameter,
            length_m=_finite(geometry.get("length_m", 0.01), "length_m"),
            height_m=_finite(geometry["nozzle_height_m"], "nozzle_height_m"),
            direction_enu=direction,
            discharge_coefficient=discharge_coefficient,
        ),
        ambient=AmbientState(
            pressure_pa=ambient_pressure,
            temperature_k=ambient_temperature,
            wind_speed_m_s=_finite(packet.get("wind_speed_m_s", 0.0), "wind_speed_m_s"),
            wind_from_bearing_deg=packet.get("wind_from_bearing_deg"),
        ),
        choices=ModelChoices(
            phase_model="HEM",
            fictitious_nozzle="momentum_adiabatic",
            droplet_correlation="rescigno_yellow_book",
            distribution="single_smd",
        ),
        duration_s=_finite(packet.get("time_step_s", 0.05), "time_step_s"),
        time_step_s=_finite(packet.get("time_step_s", 0.05), "time_step_s"),
    )
    real = PipeState(
        pressure_pa=critical["critical_pressure_pa"],
        temperature_k=throat_temperature,
        enthalpy_j_kg=critical["mixture_enthalpy_j_kg"],
        density_kg_m3=critical["mixture_density_kg_m3"],
        velocity_m_s=critical["velocity_m_s"],
        darcy_friction_factor=0.0,
        wall_heat_w=0.0,
        wall_temperature_k=ambient_temperature,
    )
    fictitious = _fictitious(inp, real, model_total, throat_quality)
    droplet, flashed_quality, evaporation_rate, liquid_density = _droplets(
        inp, real, model_total, throat_quality
    )
    base_velocity = fictitious.velocity_m_s if fictitious is not None else real.velocity_m_s
    velocity = tuple(base_velocity * value for value in direction)
    postflash_liquid = model_total * (1.0 - flashed_quality)
    gas_evaporated, ground, impact, _evaporation_heat, _trajectory_residual, outcomes = _trajectory(
        inp,
        droplet,
        postflash_liquid,
        liquid_density,
        evaporation_rate,
        velocity,
    )
    gas = model_total * flashed_quality + gas_evaporated
    airborne = max(0.0, postflash_liquid - ground - gas_evaporated)
    mass_residual = model_total - gas - ground - airborne
    if airborne > 1.0e-12:
        raise ValueError(
            "provider-state SLABx boundary produced airborne liquid; validated droplet handoff is required"
        )
    droplet_outcomes = [
        {
            "ground_liquid_mass_flow_kg_s": outcome.ground_liquid_mass_flow_kg_s,
            "airborne_liquid_mass_flow_kg_s": outcome.airborne_evaporated_mass_flow_kg_s * 0.0,
            "flight_time_s": outcome.flight_time_s,
            "impact_position_m": None if outcome.impact_position_m is None else list(outcome.impact_position_m),
            "droplet_diameter_m": outcome.diameter_m,
        }
        for outcome in outcomes
    ]
    return {
        "time_s": provider["time_s"],
        "total_mass_flow_kg_s": model_total,
        "gas_mass_flow_kg_s": gas,
        "airborne_liquid_mass_flow_kg_s": airborne,
        "ground_liquid_mass_flow_kg_s": ground,
        "mass_residual_kg_s": mass_residual,
        "gas_pressure_pa_abs": None if fictitious is None or gas <= 1.0e-12 else fictitious.pressure_pa,
        "gas_temperature_k": None if fictitious is None or gas <= 1.0e-12 else fictitious.temperature_k,
        "gas_density_kg_m3": None if fictitious is None or gas <= 1.0e-12 else fictitious.density_kg_m3,
        "gas_velocity_m_s": None if fictitious is None or gas <= 1.0e-12 else fictitious.velocity_m_s,
        "droplet_class_outcomes": droplet_outcomes,
        "velocity_vector_m_s": list(velocity),
        "provider_state_boundary": {
            "critical": critical,
            "throat_temperature_k": throat_temperature,
            "throat_quality": throat_quality,
            "provider_mass_flow_kg_s": provider_total,
            "slabx_provider_state_mass_flow_kg_s": model_total,
            "relative_rate_error": relative_error,
            "provider_state_owner": "external_lh2dt",
            "partition_owner": "SLABx-LH2",
        },
    }, {
        "provider_mass_flow_kg_s": provider_total,
        "slabx_mass_flow_kg_s": model_total,
        "relative_rate_error": relative_error,
        "critical_pressure_pa": critical["critical_pressure_pa"],
        "fluid": fluid,
    }


__all__ = ["evaluate_provider_state_partition"]
