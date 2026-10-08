"""Combine a provider liquid flow history with an explicit SLABx partition.

The equipment model owns the total mass rate and its time clock.  SLABx-LH2
owns only the atmospheric flash, droplet fate and gas/ground partition.  This
module joins those two contracts without silently replacing one rate with the
other: a relative-rate gate is required, and the equipment rate is retained
in every returned interval.  No SLABx dependency is imported here.
"""

from __future__ import annotations

import math
from typing import Any, Sequence


def _number(value: Any, field: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or (nonnegative and result < 0.0):
        raise ValueError(f"{field} must be finite and {'non-negative' if nonnegative else 'finite'}")
    return result


def _rows_close(left: Sequence[dict], right: Sequence[dict]) -> None:
    if len(left) != len(right):
        raise ValueError("provider and SLABx partition histories have different lengths")
    for index, (provider, partition) in enumerate(zip(left, right)):
        t_provider = _number(provider["time_s"], f"provider[{index}].time_s")
        t_partition = _number(partition["time_s"], f"partition[{index}].time_s")
        if not math.isclose(t_provider, t_partition, rel_tol=0.0, abs_tol=1.0e-12):
            raise ValueError("provider and SLABx partition clocks do not match")


def combine_provider_liquid_partition(
    provider_rows: Sequence[dict],
    slabsx_rows: Sequence[dict],
    *,
    ambient_pressure_pa: float,
    rate_relative_tolerance: float = 0.05,
) -> tuple[list[dict], dict]:
    """Return ``ResolvedLiquidStep``-compatible rows and an audit ledger.

    ``provider_rows`` must contain ``time_s``, ``total_mass_flow_kg_s`` and
    ``specific_enthalpy_j_kg``.  ``slabsx_rows`` must contain the same clock,
    total/gas/airborne/ground rates and, when gas is present, a complete
    atmospheric gas state.  Positive airborne liquid is rejected because PRISM
    has no validated airborne-droplet handoff in this scope.
    """

    if not provider_rows:
        raise ValueError("provider liquid history is empty")
    if rate_relative_tolerance < 0.0 or not math.isfinite(rate_relative_tolerance):
        raise ValueError("rate_relative_tolerance must be finite and non-negative")
    ambient = _number(ambient_pressure_pa, "ambient_pressure_pa")
    _rows_close(provider_rows, slabsx_rows)
    rows: list[dict] = []
    audit_rows: list[dict] = []
    for index, (provider, partition) in enumerate(zip(provider_rows, slabsx_rows)):
        prefix = f"interval {index}"
        provider_total = _number(provider["total_mass_flow_kg_s"], f"{prefix}.provider total", nonnegative=True)
        provider_h = _number(provider["specific_enthalpy_j_kg"], f"{prefix}.provider enthalpy")
        model_total = _number(partition["total_mass_flow_kg_s"], f"{prefix}.SLABx total", nonnegative=True)
        model_gas = _number(partition["gas_mass_flow_kg_s"], f"{prefix}.SLABx gas", nonnegative=True)
        model_airborne = _number(partition["airborne_liquid_mass_flow_kg_s"], f"{prefix}.SLABx airborne", nonnegative=True)
        model_ground = _number(partition["ground_liquid_mass_flow_kg_s"], f"{prefix}.SLABx ground", nonnegative=True)
        if not math.isclose(model_total, model_gas + model_airborne + model_ground, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError(f"{prefix} SLABx mass partition does not close")
        if model_airborne > 1e-12:
            raise ValueError("SLABx airborne liquid requires a validated droplet adapter")
        if provider_total <= 1e-12:
            if model_total > 1e-12:
                raise ValueError(f"{prefix} zero equipment flow has a positive SLABx partition")
            scale = 0.0
        else:
            if model_total <= 1e-12:
                raise ValueError(f"{prefix} positive equipment flow has zero SLABx partition")
            relative_error = abs(model_total - provider_total) / provider_total
            if relative_error > rate_relative_tolerance:
                raise ValueError(
                    f"{prefix} provider/SLABx rate mismatch {relative_error:.6g} exceeds "
                    f"tolerance {rate_relative_tolerance:.6g}"
                )
            scale = provider_total / model_total
        gas = model_gas * scale
        airborne = model_airborne * scale
        ground = model_ground * scale
        outcomes = []
        for raw in partition.get("droplet_class_outcomes", ()):
            outcome = dict(raw)
            outcome["ground_liquid_mass_flow_kg_s"] = _number(
                outcome.get("ground_liquid_mass_flow_kg_s", 0.0), f"{prefix}.droplet ground", nonnegative=True
            ) * scale
            outcome["airborne_liquid_mass_flow_kg_s"] = _number(
                outcome.get("airborne_liquid_mass_flow_kg_s", 0.0), f"{prefix}.droplet airborne", nonnegative=True
            ) * scale
            outcomes.append(outcome)
        if not math.isclose(sum(x["ground_liquid_mass_flow_kg_s"] for x in outcomes), ground, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError(f"{prefix} droplet ground classes do not close")
        if not math.isclose(sum(x["airborne_liquid_mass_flow_kg_s"] for x in outcomes), airborne, rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError(f"{prefix} droplet airborne classes do not close")
        if gas > 1e-12:
            pressure = _number(partition["gas_pressure_pa_abs"], f"{prefix}.gas pressure")
            if not math.isclose(pressure, ambient, rel_tol=1e-6, abs_tol=1e-3):
                raise ValueError(f"{prefix} SLABx gas state is not an atmospheric boundary")
            temperature = _number(partition["gas_temperature_k"], f"{prefix}.gas temperature")
            density = _number(partition["gas_density_kg_m3"], f"{prefix}.gas density")
            velocity = _number(partition["gas_velocity_m_s"], f"{prefix}.gas velocity")
            if density <= 0.0 or velocity <= 0.0:
                raise ValueError(f"{prefix} positive gas flow requires positive density and velocity")
            area = gas / (density * velocity)
            gas_area_provenance = "provider-total-rate-scaled-SLABx-velocity-density"
        else:
            pressure = temperature = density = velocity = area = 0.0
            gas_area_provenance = "zero-gas-interval"
        rows.append({
            "time_s": _number(provider["time_s"], f"{prefix}.time_s"),
            "total_mass_flow_kg_s": provider_total,
            "gas_mass_flow_kg_s": gas,
            "airborne_liquid_mass_flow_kg_s": airborne,
            "ground_liquid_mass_flow_kg_s": ground,
            "mass_residual_kg_s": provider_total - gas - airborne - ground,
            "real_nozzle": None if gas <= 1e-12 else {
                "pressure_pa": pressure,
                "temperature_k": temperature,
                "density_kg_m3": density,
                "velocity_m_s": velocity,
                "enthalpy_j_kg": provider_h,
                "effective_area_m2": area,
            },
            "fictitious_nozzle": None,
            "velocity_vector_m_s": list(partition.get("velocity_vector_m_s", (0.0, 0.0, 0.0))),
            "gas_boundary_temperature_k": temperature,
            "gas_boundary_density_kg_m3": density,
            "gas_boundary_area_m2": area,
            "droplet_class_outcomes": outcomes,
            "discharge_recalculated": False,
            "gas_area_provenance": gas_area_provenance,
        })
        audit_rows.append({
            "time_s": rows[-1]["time_s"],
            "provider_mass_flow_kg_s": provider_total,
            "slabsx_mass_flow_kg_s": model_total,
            "rate_scale_provider_over_slabsx": scale,
            "relative_rate_error": (None if provider_total <= 1e-12 else abs(model_total - provider_total) / provider_total),
            "provider_rate_owner": "equipment_twin",
            "partition_owner": "SLABx-LH2",
        })
    return rows, {
        "model_name": "layered-tank-equipment-rate-plus-slabx-lh2-partition",
        "provider_rate_owner": "equipment_twin",
        "partition_owner": "SLABx-LH2",
        "rate_relative_tolerance": rate_relative_tolerance,
        "intervals": audit_rows,
        "discharge_recalculated": False,
        "equipment_dynamics_recalculated": False,
        "airborne_liquid_policy": "reject-until-validated-droplet-adapter",
        "limitations": [
            "provider time semantics must declare whether endpoint states represent preceding intervals",
            "SLABx partition is scaled to the equipment total rate only within the declared rate tolerance",
            "gas source area is recomputed from provider rate and SLABx provider-resolved velocity/density",
        ],
    }


__all__ = ["combine_provider_liquid_partition"]
