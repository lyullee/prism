"""Promote an equipment-twin accident history to a PRISM gas boundary.

The external equipment model owns the transient calculation.  This adapter
only maps an already resolved provider response to the strict
``prism.resolved_release.v1`` contract.  It never estimates a leak rate,
extends a provider history, or turns a normal-flow result into an accident.
"""
from __future__ import annotations

import math
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import canonical_digest
from .equipment_boundary import (
    ProviderTerminationBasis,
    ResolvedGasRelease,
    ResolvedLiquidRelease,
)


class EquipmentReleaseExportError(ValueError):
    """Raised when a provider response cannot be promoted to a gas packet."""


_STEP_FIELDS = (
    "time_s",
    "mass_flow_kg_s",
    "pressure_pa_abs",
    "specific_enthalpy_j_kg",
    "temperature_k",
    "density_kg_m3",
    "effective_area_m2",
    "velocity_m_s",
    "area_provenance",
    "velocity_origin",
)

_LIQUID_STEP_FIELDS = (
    "time_s",
    "total_mass_flow_kg_s",
    "gas_mass_flow_kg_s",
    "ground_liquid_mass_flow_kg_s",
    "airborne_liquid_mass_flow_kg_s",
    "specific_enthalpy_j_kg",
    "droplet_class_outcomes",
)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EquipmentReleaseExportError(f"{field} must be a non-empty string")
    return value.strip()


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise EquipmentReleaseExportError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise EquipmentReleaseExportError(f"{field} must be numeric") from error
    if not math.isfinite(number):
        raise EquipmentReleaseExportError(f"{field} must be finite")
    return number


def _positive(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number <= 0.0:
        raise EquipmentReleaseExportError(f"{field} must be positive")
    return number


def _vector(value: Any, field: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise EquipmentReleaseExportError(f"{field} must contain three coordinates")
    return [_finite(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _termination_basis(value: Any, field: str) -> ProviderTerminationBasis | None:
    """Validate an optional provider-owned termination classification."""

    if value is None:
        return None
    # The external LayeredTank diagnostic used descriptive branch names before
    # the strict packet field was introduced.  Normalize those two names at
    # the adapter boundary while keeping the original prose provenance.
    aliases = {
        "isolation_success": "reviewed_isolation_success",
        "isolation_failure_diagnostic_horizon": "synthetic_diagnostic_horizon",
    }
    normalized = aliases.get(value, value)
    allowed = {
        "synthetic_diagnostic_horizon",
        "reviewed_isolation_success",
        "inventory_depletion",
        "inventory_over_600s",
        "model_pressure_equalization",
        "two_sided_rupture",
        "emergency_relief_discharge",
    }
    if normalized not in allowed:
        raise EquipmentReleaseExportError(
            f"{field} must be a supported provider termination basis"
        )
    return normalized  # type: ignore[return-value]


def build_resolved_gas_release_from_provider_response(
    provider_response: Mapping[str, Any],
    *,
    component_id: str,
    port_id: str,
    event_id: str,
    provider_source_digest: str,
    upstream_service_provenance: str,
    provider_boundary_reference: str,
    input_origin: str,
    position_enu_m: Sequence[float],
    direction_enu: Sequence[float],
    ambient_pressure_pa_abs: float,
    ambient_temperature_k: float,
    failure_opening_diameter_m: float,
    provider_result: Any | None = None,
    provider_result_digest: str | None = None,
) -> ResolvedGasRelease:
    """Build one strict accidental gas release from a provider history.

    ``provider_response`` must contain the provider's ``data`` object and its
    complete left-held ``steps`` history.  The adapter copies the declared
    cumulative mass/enthalpy and termination provenance; it does not derive
    them from a requested duration.  Strict PRISM validation then checks the
    interval integrals and continuity.
    """

    if not isinstance(provider_response, Mapping):
        raise EquipmentReleaseExportError("provider_response must be an object")
    data = provider_response.get("data")
    if not isinstance(data, Mapping):
        raise EquipmentReleaseExportError("provider_response.data must be an object")
    if data.get("event_kind") != "accidental_leak":
        raise EquipmentReleaseExportError(
            "provider data must explicitly declare event_kind=accidental_leak"
        )
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)) or not raw_steps:
        raise EquipmentReleaseExportError("provider data must contain a non-empty steps history")
    steps: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, Mapping):
            raise EquipmentReleaseExportError(f"provider data.steps[{index}] must be an object")
        missing = [field for field in _STEP_FIELDS if field not in raw]
        if missing:
            raise EquipmentReleaseExportError(
                f"provider data.steps[{index}] missing required fields: {', '.join(missing)}"
            )
        row = dict(raw)
        for field in _STEP_FIELDS[:8]:
            row[field] = _finite(row[field], f"provider data.steps[{index}].{field}")
        if row["mass_flow_kg_s"] < 0.0:
            raise EquipmentReleaseExportError(
                f"provider data.steps[{index}].mass_flow_kg_s must be non-negative"
            )
        row["area_provenance"] = _text(
            row["area_provenance"], f"provider data.steps[{index}].area_provenance"
        )
        row["velocity_origin"] = _text(
            row["velocity_origin"], f"provider data.steps[{index}].velocity_origin"
        )
        steps.append(row)

    duration_s = _positive(data.get("duration_s"), "provider data.duration_s")
    available_mass_kg = _positive(data.get("available_mass_kg"), "provider data.available_mass_kg")
    cumulative_mass = _finite(
        data.get("cumulative_mass_out_kg"), "provider data.cumulative_mass_out_kg"
    )
    cumulative_enthalpy = _finite(
        data.get("cumulative_static_enthalpy_out_j"),
        "provider data.cumulative_static_enthalpy_out_j",
    )
    termination = _text(
        data.get("termination_provenance"), "provider data.termination_provenance"
    )
    termination_basis = _termination_basis(
        data.get("termination_basis"), "provider data.termination_basis"
    )
    result_payload = provider_response if provider_result is None else provider_result
    result_digest = provider_result_digest or canonical_digest(result_payload)
    if not isinstance(result_digest, str) or len(result_digest) != 64:
        raise EquipmentReleaseExportError("provider_result_digest must be a 64-character digest")

    packet = {
        "component_id": _text(component_id, "component_id"),
        "port_id": _text(port_id, "port_id"),
        "event_id": _text(event_id, "event_id"),
        "event_kind": "accidental_leak",
        "enthalpy_convention": "static_exit_enthalpy",
        "property_basis": {
            "fluid": "ParaHydrogen",
            "backend": "CoolProp-HEOS",
            "energy_reference": "CoolProp-HEOS:ParaHydrogen:native",
        },
        "upstream_service": "LH2",
        "upstream_service_provenance": _text(
            upstream_service_provenance, "upstream_service_provenance"
        ),
        "provider_source_digest": _text(provider_source_digest, "provider_source_digest"),
        "provider_result_digest": result_digest,
        "provider_boundary_reference": _text(
            provider_boundary_reference, "provider_boundary_reference"
        ),
        "input_origin": _text(input_origin, "input_origin"),
        "position_enu_m": _vector(position_enu_m, "position_enu_m"),
        "direction_enu": _vector(direction_enu, "direction_enu"),
        "ambient_pressure_pa_abs": _positive(
            ambient_pressure_pa_abs, "ambient_pressure_pa_abs"
        ),
        "ambient_temperature_k": _positive(
            ambient_temperature_k, "ambient_temperature_k"
        ),
        "duration_s": duration_s,
        "available_mass_kg": available_mass_kg,
        "cumulative_mass_out_kg": cumulative_mass,
        "cumulative_static_enthalpy_out_j": cumulative_enthalpy,
        "steps": steps,
        "termination_provenance": termination,
        "termination_basis": termination_basis,
        "failure_opening_diameter_m": _positive(
            failure_opening_diameter_m, "failure_opening_diameter_m"
        ),
    }
    try:
        # Validate through JSON because provider exports are JSON objects and
        # the strict contract intentionally requires tuple-shaped fields after
        # parsing.  This keeps the adapter's boundary identical to
        # ``load_provider_release``.
        return ResolvedGasRelease.model_validate_json(
            json.dumps(packet, allow_nan=False)
        )
    except (TypeError, ValueError) as error:
        raise EquipmentReleaseExportError(
            f"provider gas history failed strict PRISM validation: {error}"
        ) from error


def build_resolved_liquid_release_from_provider_response(
    provider_response: Mapping[str, Any],
    *,
    component_id: str,
    port_id: str,
    event_id: str,
    provider_source_digest: str,
    upstream_service_provenance: str,
    provider_boundary_reference: str,
    input_origin: str,
    position_enu_m: Sequence[float],
    direction_enu: Sequence[float],
    ambient_pressure_pa_abs: float,
    ambient_temperature_k: float,
    failure_opening_diameter_m: float,
    provider_result: Any | None = None,
    provider_result_digest: str | None = None,
) -> ResolvedLiquidRelease:
    """Build a strict liquid/two-phase packet from provider-owned rows.

    The provider response must explicitly declare the accident kind, phase
    partition, liquid/gas mass split, droplet classes, and termination
    provenance.  In particular, a positive airborne-liquid rate is rejected
    by the downstream contract until a validated droplet adapter exists.
    """

    if not isinstance(provider_response, Mapping):
        raise EquipmentReleaseExportError("provider_response must be an object")
    data = provider_response.get("data")
    if not isinstance(data, Mapping):
        raise EquipmentReleaseExportError("provider_response.data must be an object")
    if data.get("event_kind") != "accidental_leak":
        raise EquipmentReleaseExportError(
            "provider data must explicitly declare event_kind=accidental_leak"
        )
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)) or not raw_steps:
        raise EquipmentReleaseExportError("provider data must contain a non-empty liquid steps history")
    steps: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, Mapping):
            raise EquipmentReleaseExportError(f"provider data.steps[{index}] must be an object")
        missing = [field for field in _LIQUID_STEP_FIELDS if field not in raw]
        if missing:
            raise EquipmentReleaseExportError(
                f"provider data.steps[{index}] missing required fields: {', '.join(missing)}"
            )
        row = dict(raw)
        for field in _LIQUID_STEP_FIELDS[:6]:
            row[field] = _finite(row[field], f"provider data.steps[{index}].{field}")
            if row[field] < 0.0 and field != "specific_enthalpy_j_kg":
                raise EquipmentReleaseExportError(
                    f"provider data.steps[{index}].{field} must be non-negative"
                )
        if not isinstance(row["droplet_class_outcomes"], Sequence) or isinstance(
            row["droplet_class_outcomes"], (str, bytes)
        ):
            raise EquipmentReleaseExportError(
                f"provider data.steps[{index}].droplet_class_outcomes must be an array"
            )
        steps.append(row)

    duration_s = _positive(data.get("duration_s"), "provider data.duration_s")
    available_mass_kg = _positive(data.get("available_mass_kg"), "provider data.available_mass_kg")
    cumulative_mass = _finite(
        data.get("cumulative_mass_out_kg"), "provider data.cumulative_mass_out_kg"
    )
    cumulative_enthalpy = _finite(
        data.get("cumulative_specific_enthalpy_out_j"),
        "provider data.cumulative_specific_enthalpy_out_j",
    )
    phase_basis = _text(data.get("phase_basis"), "provider data.phase_basis")
    upstream_service = _text(data.get("upstream_service"), "provider data.upstream_service")
    fluid = _text(data.get("fluid"), "provider data.fluid")
    reference_area = _positive(
        data.get("reference_area_m2"), "provider data.reference_area_m2"
    )
    reference_area_provenance = _text(
        data.get("reference_area_provenance"),
        "provider data.reference_area_provenance",
    )
    termination = _text(
        data.get("termination_provenance"), "provider data.termination_provenance"
    )
    termination_basis = _termination_basis(
        data.get("termination_basis"), "provider data.termination_basis"
    )
    droplet_provenance = _text(
        data.get("droplet_partition_provenance"),
        "provider data.droplet_partition_provenance",
    )
    result_payload = provider_response if provider_result is None else provider_result
    result_digest = provider_result_digest or canonical_digest(result_payload)
    if not isinstance(result_digest, str) or len(result_digest) != 64:
        raise EquipmentReleaseExportError("provider_result_digest must be a 64-character digest")

    packet = {
        "component_id": _text(component_id, "component_id"),
        "port_id": _text(port_id, "port_id"),
        "event_id": _text(event_id, "event_id"),
        "event_kind": "accidental_leak",
        "upstream_service": upstream_service,
        "upstream_service_provenance": _text(
            upstream_service_provenance, "upstream_service_provenance"
        ),
        "boundary_kind": "resolved_atmospheric_liquid_exit",
        "phase_basis": phase_basis,
        "enthalpy_convention": "provider_total_outlet_enthalpy",
        "property_basis": {
            "fluid": fluid,
            "backend": "CoolProp-HEOS",
            "energy_reference": f"CoolProp-HEOS:{fluid}:native",
        },
        "provider_source_digest": _text(provider_source_digest, "provider_source_digest"),
        "provider_result_digest": result_digest,
        "provider_boundary_reference": _text(
            provider_boundary_reference, "provider_boundary_reference"
        ),
        "input_origin": _text(input_origin, "input_origin"),
        "position_enu_m": _vector(position_enu_m, "position_enu_m"),
        "direction_enu": _vector(direction_enu, "direction_enu"),
        "ambient_pressure_pa_abs": _positive(
            ambient_pressure_pa_abs, "ambient_pressure_pa_abs"
        ),
        "ambient_temperature_k": _positive(
            ambient_temperature_k, "ambient_temperature_k"
        ),
        "duration_s": duration_s,
        "available_mass_kg": available_mass_kg,
        "cumulative_mass_out_kg": cumulative_mass,
        "cumulative_specific_enthalpy_out_j": cumulative_enthalpy,
        "reference_area_m2": reference_area,
        "reference_area_provenance": reference_area_provenance,
        "steps": steps,
        "termination_provenance": termination,
        "droplet_partition_provenance": droplet_provenance,
        "termination_basis": termination_basis,
        "failure_opening_diameter_m": _positive(
            failure_opening_diameter_m, "failure_opening_diameter_m"
        ),
    }
    try:
        return ResolvedLiquidRelease.model_validate_json(
            json.dumps(packet, allow_nan=False)
        )
    except (TypeError, ValueError) as error:
        raise EquipmentReleaseExportError(
            f"provider liquid history failed strict PRISM validation: {error}"
        ) from error


__all__ = [
    "EquipmentReleaseExportError",
    "build_resolved_gas_release_from_provider_response",
    "build_resolved_liquid_release_from_provider_response",
]
