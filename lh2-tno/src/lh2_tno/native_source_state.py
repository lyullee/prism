"""Complete provider source/throat trace fields without inventing a jet.

Some native equipment exporters already return the upstream state and the
isentropic throat pressure, but omit the thermodynamic state at the throat.
This adapter fills only those deterministic property fields from the same
provider property backend.  It never infers a throat pressure, opening, or
near-field plane from the atmospheric packet velocity.
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
import math
from typing import Any, Protocol


class NativeSourceStateCompletionError(ValueError):
    """Raised when a native source trace cannot be completed safely."""


class NativePropertyResolver(Protocol):
    def from_pT(self, pressure_pa: float, temperature_k: float) -> Any: ...
    def from_ps(self, pressure_pa: float, entropy_j_kgk: float) -> Any: ...


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise NativeSourceStateCompletionError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise NativeSourceStateCompletionError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise NativeSourceStateCompletionError(f"{field} must be finite")
    return result


def _positive(value: Any, field: str) -> float:
    result = _finite(value, field)
    if result <= 0.0:
        raise NativeSourceStateCompletionError(f"{field} must be positive")
    return result


def _check_or_fill(state: dict[str, Any], field: str, value: float, *, tolerance: float = 1.0e-8) -> None:
    existing = state.get(field)
    if existing is not None:
        existing_value = _finite(existing, field)
        if not math.isclose(existing_value, value, rel_tol=tolerance, abs_tol=1.0e-9):
            raise NativeSourceStateCompletionError(
                f"native source trace {field} disagrees with provider property state"
            )
    else:
        state[field] = float(value)


def complete_isentropic_throat_source_states(
    response: Mapping[str, Any],
    *,
    properties: NativePropertyResolver,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fill missing entropy and throat thermodynamic fields for every interval.

    The provider must already expose ``source_pressure_pa_abs``,
    ``source_temperature_k`` and ``throat_pressure_pa_abs``.  This function
    refuses compact traces without those anchors and returns a copied response
    plus an auditable completion record.
    """
    if not isinstance(response, Mapping):
        raise NativeSourceStateCompletionError("native response must be an object")
    completed = copy.deepcopy(dict(response))
    data = completed.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or not data["steps"]:
        raise NativeSourceStateCompletionError("native response data.steps must be a non-empty list")
    interval_audits: list[dict[str, Any]] = []
    for index, step in enumerate(data["steps"]):
        if not isinstance(step, dict):
            raise NativeSourceStateCompletionError(f"data.steps[{index}] must be an object")
        trace = step.get("provider_source_state")
        if not isinstance(trace, dict):
            raise NativeSourceStateCompletionError(
                f"data.steps[{index}] has no provider_source_state"
            )
        source_pressure = _positive(
            trace.get("source_pressure_pa_abs"),
            f"data.steps[{index}].provider_source_state.source_pressure_pa_abs",
        )
        source_temperature = _positive(
            trace.get("source_temperature_k"),
            f"data.steps[{index}].provider_source_state.source_temperature_k",
        )
        throat_pressure = _positive(
            trace.get("throat_pressure_pa_abs"),
            f"data.steps[{index}].provider_source_state.throat_pressure_pa_abs",
        )
        source = properties.from_pT(source_pressure, source_temperature)
        entropy = _positive(
            getattr(source, "specific_entropy_J_kgK"),
            f"source[{index}].specific_entropy_J_kgK",
        )
        throat = properties.from_ps(throat_pressure, entropy)
        phase = str(getattr(throat, "phase", ""))
        if phase not in {"gas", "supercritical_gas", "supercritical"}:
            raise NativeSourceStateCompletionError(
                f"data.steps[{index}] throat property state is not gas-like: {phase}"
            )
        _check_or_fill(trace, "source_density_kg_m3", _positive(getattr(source, "density_kg_m3"), f"source[{index}].density_kg_m3"))
        _check_or_fill(trace, "source_specific_enthalpy_j_kg", _finite(getattr(source, "specific_enthalpy_J_kg"), f"source[{index}].specific_enthalpy_J_kg"))
        _check_or_fill(trace, "source_specific_entropy_j_kgk", entropy)
        _check_or_fill(trace, "throat_temperature_k", _positive(getattr(throat, "temperature_K"), f"throat[{index}].temperature_K"))
        _check_or_fill(trace, "throat_density_kg_m3", _positive(getattr(throat, "density_kg_m3"), f"throat[{index}].density_kg_m3"))
        _check_or_fill(trace, "throat_specific_enthalpy_j_kg", _finite(getattr(throat, "specific_enthalpy_J_kg"), f"throat[{index}].specific_enthalpy_J_kg"))
        trace.setdefault(
            "provider_source_state_provenance",
            "native provider source pressure/temperature/throat pressure; entropy and throat state completed by the same provider property backend",
        )
        interval_audits.append({
            "interval": index,
            "time_s": step.get("time_s"),
            "source_entropy_completed": trace.get("source_specific_entropy_j_kgk") is not None,
            "throat_state_completed": all(
                trace.get(field) is not None
                for field in (
                    "throat_temperature_k",
                    "throat_density_kg_m3",
                    "throat_specific_enthalpy_j_kg",
                )
            ),
        })
    return completed, {
        "schema_version": "prism.native_source_state_completion.v1",
        "status": "COMPLETED_ISENTROPIC_THROAT_FIELDS",
        "interval_count": len(interval_audits),
        "intervals": interval_audits,
        "source_pressure_inferred": False,
        "throat_pressure_inferred": False,
        "near_field_plane_generated": False,
        "physical_validation_claim": False,
        "provider_packet_qualified": False,
        "facility_qra_claim": False,
    }


__all__ = [
    "NativePropertyResolver",
    "NativeSourceStateCompletionError",
    "complete_isentropic_throat_source_states",
]
