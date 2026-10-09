"""Build an explicit compressible-plane diagnostic from provider source states.

This module is an optional boundary adapter, not a replacement for a validated
near-field solver.  It accepts only a provider response that contains the
upstream and throat state for every resolved interval.  In particular, it
never infers a source pressure from the atmospheric packet velocity.

The default ``birch_momentum_energy`` construction uses the published
notional-nozzle bookkeeping: mass and momentum determine the equivalent
ambient-plane velocity, while the provider property backend closes the static
enthalpy at that plane.  The result is explicitly marked synthetic until the
provider and the near-field correlation have independent validation.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from typing import Any, Protocol

from .compressible_handoff import COMPRESSIBLE_HANDOFF_SCHEMA
from .contracts import canonical_digest
from .equipment_boundary import ResolvedGasRelease


class CompressibleSourceAdapterError(ValueError):
    """Raised when provider source/throat evidence is incomplete or invalid."""


class PropertyState(Protocol):
    temperature_K: float
    density_kg_m3: float
    specific_enthalpy_J_kg: float
    specific_entropy_J_kgK: float
    phase: str


class PropertyResolver(Protocol):
    def from_ph(self, pressure_pa: float, enthalpy_j_kg: float) -> PropertyState: ...
    def from_ps(self, pressure_pa: float, entropy_j_kgk: float) -> PropertyState: ...


@dataclass(frozen=True)
class CompressibleAdapterResult:
    export: dict[str, Any]
    audit: dict[str, Any]


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise CompressibleSourceAdapterError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CompressibleSourceAdapterError(f"{field} must be numeric") from error
    if not math.isfinite(number):
        raise CompressibleSourceAdapterError(f"{field} must be finite")
    return number


def _positive(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number <= 0.0:
        raise CompressibleSourceAdapterError(f"{field} must be positive")
    return number


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise CompressibleSourceAdapterError(f"{field} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise CompressibleSourceAdapterError(f"{field} must be a lowercase SHA-256 digest") from error
    return value


def _state_value(state: PropertyState, attribute: str, field: str) -> float:
    return _positive(getattr(state, attribute), field)


def build_compressible_plane_handoff(
    packet: Mapping[str, Any] | ResolvedGasRelease,
    provider_response: Mapping[str, Any],
    *,
    properties: PropertyResolver,
    algorithm: str = "birch_momentum_energy",
    handoff_model: str = "prism-notional-plane-adapter",
    handoff_revision: str = "0.1.0",
    adapter_source_digest: str | None = None,
    evidence_status: str = "synthetic_diagnostic",
) -> CompressibleAdapterResult:
    """Construct one handoff after checking exact provider identity.

    ``provider_response`` must contain ``data.steps[*].provider_source_state``
    records produced by the equipment provider.  A missing record, a zero-flow
    interval, or a property failure blocks the export.  No fallback to the
    packet's atmospheric continuity velocity is permitted.
    """
    if isinstance(packet, ResolvedGasRelease):
        release = packet
    else:
        try:
            release = ResolvedGasRelease.model_validate_json(
                json.dumps(dict(packet), allow_nan=False)
            )
        except Exception as error:
            raise CompressibleSourceAdapterError(
                f"upstream gas packet is not a valid ResolvedGasRelease: {error}"
            ) from error
    if not isinstance(provider_response, Mapping):
        raise CompressibleSourceAdapterError("provider_response must be an object")
    if canonical_digest(provider_response) != release.provider_result_digest:
        raise CompressibleSourceAdapterError(
            "provider response digest does not match the exact resolved gas packet"
        )
    data = provider_response.get("data")
    if not isinstance(data, Mapping):
        raise CompressibleSourceAdapterError("provider_response.data must be an object")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) != len(release.steps):
        raise CompressibleSourceAdapterError(
            "provider source-state interval count must match the resolved gas packet"
        )
    if algorithm not in {"birch_momentum_energy", "birch_momentum_isentropic"}:
        raise CompressibleSourceAdapterError(
            "algorithm must be birch_momentum_energy or birch_momentum_isentropic"
        )
    if evidence_status not in {"qualified_actual", "synthetic_diagnostic", "screening_only"}:
        raise CompressibleSourceAdapterError("unsupported evidence_status")

    states: list[dict[str, Any]] = []
    max_energy_residual = 0.0
    max_entropy_residual = 0.0
    for index, (step, raw) in enumerate(zip(release.steps, raw_steps)):
        if not isinstance(raw, Mapping):
            raise CompressibleSourceAdapterError(f"provider data.steps[{index}] must be an object")
        if not math.isclose(_finite(raw.get("time_s"), f"steps[{index}].time_s"), step.time_s, rel_tol=0.0, abs_tol=1e-12):
            raise CompressibleSourceAdapterError(f"provider source clock disagrees at interval {index}")
        source = raw.get("provider_source_state")
        if not isinstance(source, Mapping):
            raise CompressibleSourceAdapterError(
                f"provider data.steps[{index}] has no provider_source_state; atmospheric packet velocity cannot be used"
            )
        p_t = _positive(source.get("throat_pressure_pa_abs"), f"steps[{index}].throat_pressure_pa_abs")
        rho_t = _positive(source.get("throat_density_kg_m3"), f"steps[{index}].throat_density_kg_m3")
        h_t = _finite(source.get("throat_specific_enthalpy_j_kg"), f"steps[{index}].throat_specific_enthalpy_j_kg")
        s_t = _finite(source.get("source_specific_entropy_j_kgk"), f"steps[{index}].source_specific_entropy_j_kgk")
        area = _positive(step.effective_area_m2, f"steps[{index}].effective_area_m2")
        mdot = _positive(step.mass_flow_kg_s, f"steps[{index}].mass_flow_kg_s")
        u_t = mdot / (rho_t * area)
        u_plane = u_t + (p_t - release.ambient_pressure_pa_abs) * area / mdot
        if not math.isfinite(u_plane) or u_plane <= 0.0:
            raise CompressibleSourceAdapterError(
                f"provider source state produces no positive ambient-plane velocity at interval {index}"
            )
        total_h = h_t + 0.5 * u_t * u_t
        plane_h = total_h - 0.5 * u_plane * u_plane
        if algorithm == "birch_momentum_energy":
            plane = properties.from_ph(release.ambient_pressure_pa_abs, plane_h)
        else:
            plane = properties.from_ps(release.ambient_pressure_pa_abs, s_t)
        phase = str(getattr(plane, "phase", ""))
        if phase not in {"gas", "supercritical_gas", "supercritical"}:
            raise CompressibleSourceAdapterError(
                f"provider property backend returned non-gas plane state at interval {index}: {phase}"
            )
        rho_plane = _state_value(plane, "density_kg_m3", f"plane[{index}].density_kg_m3")
        temp_plane = _state_value(plane, "temperature_K", f"plane[{index}].temperature_k")
        area_plane = mdot / (rho_plane * u_plane)
        if not math.isfinite(area_plane) or area_plane <= 0.0:
            raise CompressibleSourceAdapterError(f"plane[{index}] has invalid equivalent area")
        width = math.sqrt(area_plane)
        # The SLABx carrier is rectangular.  Setting depth=width gives the
        # exact provider mass section while retaining a transparent geometry.
        energy_residual = (h_t + 0.5 * u_t * u_t) - (
            float(getattr(plane, "specific_enthalpy_J_kg")) + 0.5 * u_plane * u_plane
        )
        entropy_residual = float(getattr(plane, "specific_entropy_J_kgK")) - s_t
        max_energy_residual = max(max_energy_residual, abs(energy_residual))
        max_entropy_residual = max(max_entropy_residual, abs(entropy_residual))
        provenance = (
            f"{handoff_model}:{handoff_revision}; {algorithm}; provider source/throat state; "
            "not an independently validated near-field result"
        )
        states.append({
            "time_s": step.time_s,
            "direction_enu": list(release.direction_enu),
            "velocity_m_s": u_plane,
            "density_kg_m3": rho_plane,
            "temperature_k": temp_plane,
            "h2_mass_fraction": 1.0,
            "half_width_m": width / 2.0,
            "depth_m": width,
            "provenance": provenance,
        })

    handoff = {
        "position_enu_m": list(release.position_enu_m),
        "direction_enu": list(release.direction_enu),
        "velocity_m_s": states[0]["velocity_m_s"],
        "density_kg_m3": states[0]["density_kg_m3"],
        "temperature_k": states[0]["temperature_k"],
        "h2_mass_fraction": 1.0,
        "half_width_m": states[0]["half_width_m"],
        "depth_m": states[0]["depth_m"],
        "provenance": states[0]["provenance"],
        "states": states,
    }
    source_digest = adapter_source_digest or canonical_digest({
        "handoff_model": handoff_model,
        "handoff_revision": handoff_revision,
        "algorithm": algorithm,
    })
    _digest(source_digest, "handoff_provider_source_digest")
    result_digest = canonical_digest(handoff)
    export = {
        "schema_version": COMPRESSIBLE_HANDOFF_SCHEMA,
        "component_id": release.component_id,
        "port_id": release.port_id,
        "event_id": release.event_id,
        "upstream_provider_source_digest": release.provider_source_digest,
        "upstream_provider_result_digest": release.provider_result_digest,
        "handoff_provider_source_digest": source_digest,
        "handoff_provider_result_digest": result_digest,
        "handoff_model": handoff_model,
        "handoff_revision": handoff_revision,
        "evidence_status": evidence_status,
        "scenario_provenance": (
            "Optional source-state notional-plane diagnostic; provider source/throat states were captured, "
            "but provider qualification and independent near-field validation are pending"
        ),
        "handoff": handoff,
    }
    audit = {
        "status": "COMPRESSIBLE_PLANE_HANDOFF_GENERATED_SOURCE_STATE_BOUND",
        "schema_version": COMPRESSIBLE_HANDOFF_SCHEMA,
        "algorithm": algorithm,
        "component_id": release.component_id,
        "port_id": release.port_id,
        "event_id": release.event_id,
        "upstream_provider_source_digest": release.provider_source_digest,
        "upstream_provider_result_digest": release.provider_result_digest,
        "handoff_provider_source_digest": source_digest,
        "handoff_provider_result_digest": result_digest,
        "interval_count": len(states),
        "max_energy_residual_j_per_kg": max_energy_residual,
        "max_entropy_residual_j_per_kgk": max_entropy_residual,
        "evidence_status": evidence_status,
        "provider_source_state_required": True,
        "provider_packet_qualified": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }
    return CompressibleAdapterResult(export=export, audit=audit)


__all__ = [
    "CompressibleAdapterResult",
    "CompressibleSourceAdapterError",
    "build_compressible_plane_handoff",
]
