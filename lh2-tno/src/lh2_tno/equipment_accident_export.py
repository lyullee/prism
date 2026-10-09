"""Explicit accident-history export boundary for external LH2 equipment models.

The external ``lh2dt`` package currently exposes normal-state and transient
calculation methods such as ``evaluate`` and ``simulate``.  Those methods are
not an accident history.  This module defines the separate method that a
qualified equipment provider must implement before PRISM can promote a result
to the strict gas or liquid release boundary.

The boundary is intentionally small and fail-closed:

* a request must name the component, accident port, opening, horizon and
  provider-owned termination policy;
* the provider must expose ``export_accident_history``; an ``evaluate`` or
  ``simulate`` method is never used as a fallback;
* the response must explicitly declare the accident event and the external
  provider export schema; and
* the existing release adapters perform the final mass, energy, time and
  geometry validation.

This module does not infer a leak size, duration, inventory, frequency or
termination outcome from a process-state snapshot.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import math
from typing import Any, Protocol, runtime_checkable

from .equipment_release_adapter import (
    EquipmentReleaseExportError,
    build_resolved_gas_release_from_provider_response,
    build_resolved_liquid_release_from_provider_response,
)
from .state_snapshot import EquipmentStateSnapshot


ACCIDENT_EXPORT_REQUEST_SCHEMA = "prism.equipment_accident_export_request.v1"
EXTERNAL_ACCIDENT_EXPORT_SCHEMA = "prism.external_accident_history.v1"
PROVIDER_QUALIFICATION_SCHEMA = "prism.provider_qualification_evidence.v1"
_EVIDENCE_STATUSES = {"qualified_actual", "synthetic_diagnostic", "screening_only"}


class EquipmentAccidentExportError(ValueError):
    """Raised when an external model cannot satisfy the accident export contract."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EquipmentAccidentExportError(f"{field} must be a non-empty string")
    return value.strip()


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise EquipmentAccidentExportError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise EquipmentAccidentExportError(f"{field} must be numeric") from error
    if not math.isfinite(number):
        raise EquipmentAccidentExportError(f"{field} must be finite")
    return number


def _positive(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number <= 0.0:
        raise EquipmentAccidentExportError(f"{field} must be positive")
    return number


def _digest(value: Any, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64:
        raise EquipmentAccidentExportError(f"{field} must be a 64-character SHA-256 digest")
    try:
        int(text, 16)
    except ValueError as error:
        raise EquipmentAccidentExportError(f"{field} must be a hexadecimal SHA-256 digest") from error
    return text


def _vector(value: Any, field: str, *, nonzero: bool = False) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise EquipmentAccidentExportError(f"{field} must contain three coordinates")
    vector = tuple(_finite(item, f"{field}[{index}]") for index, item in enumerate(value))
    if nonzero and math.isclose(math.sqrt(sum(item * item for item in vector)), 0.0):
        raise EquipmentAccidentExportError(f"{field} must not be the zero vector")
    return vector


def _coerce_state_snapshot(
    value: EquipmentStateSnapshot | Mapping[str, Any] | None,
    *,
    component_id: str,
    state_snapshot_digest: str,
) -> EquipmentStateSnapshot | None:
    """Validate an optional state snapshot and bind it to its request digest."""
    if value is None:
        return None
    try:
        snapshot = (
            value
            if isinstance(value, EquipmentStateSnapshot)
            else EquipmentStateSnapshot.from_mapping(value)
        )
    except (TypeError, ValueError) as error:
        raise EquipmentAccidentExportError(f"invalid state_snapshot: {error}") from error
    if snapshot.component_id != component_id:
        raise EquipmentAccidentExportError(
            "state_snapshot component_id must match accident export request"
        )
    if snapshot.digest() != state_snapshot_digest:
        raise EquipmentAccidentExportError(
            "state_snapshot_digest does not match canonical state_snapshot payload"
        )
    return snapshot


def _state_snapshot_payload(
    snapshot: EquipmentStateSnapshot | None,
) -> dict[str, Any]:
    """Keep the optional field absent for legacy providers when unused."""
    if snapshot is None:
        return {}
    return {"state_snapshot": snapshot.to_mapping()}


def _require_provider_qualification_if_claimed(
    response: Mapping[str, Any],
    request: Any,
) -> None:
    """Require a provider-owned qualification record before promotion.

    The request flag is necessary but not sufficient.  A provider claiming
    ``qualified_actual`` must echo the source digest and identify the native
    accident export evidence.  This is a provenance gate, not a substitute for
    the independent physical-validation and facility-QRA gates.
    """
    if getattr(request, "evidence_status", None) != "qualified_actual":
        return
    qualification = response.get("provider_qualification")
    if not isinstance(qualification, Mapping):
        raise EquipmentAccidentExportError(
            "qualified_actual requires provider_qualification evidence"
        )
    if qualification.get("schema_version") != PROVIDER_QUALIFICATION_SCHEMA:
        raise EquipmentAccidentExportError(
            f"provider_qualification must declare {PROVIDER_QUALIFICATION_SCHEMA}"
        )
    if qualification.get("status") != "qualified_actual":
        raise EquipmentAccidentExportError(
            "provider_qualification status must be qualified_actual"
        )
    if qualification.get("provider_origin") not in {"native_provider", "reviewed_actual"}:
        raise EquipmentAccidentExportError(
            "provider_qualification provider_origin must identify a native or reviewed actual provider"
        )
    evidence_id = qualification.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise EquipmentAccidentExportError(
            "provider_qualification evidence_id must be a non-empty identifier"
        )
    if qualification.get("provider_source_digest") != request.provider_source_digest:
        raise EquipmentAccidentExportError(
            "provider_qualification provider_source_digest disagrees with request"
        )


@dataclass(frozen=True)
class AccidentReleaseExportRequest:
    """Explicit scenario sent to an external equipment accident exporter."""

    component_id: str
    port_id: str
    event_id: str
    failure_mode: str
    failure_opening_diameter_m: float
    horizon_s: float
    position_enu_m: tuple[float, float, float]
    direction_enu: tuple[float, float, float]
    ambient_pressure_pa_abs: float
    ambient_temperature_k: float
    provider_source_digest: str
    provider_boundary_reference: str
    input_origin: str
    model_package: str
    model_class: str
    model_revision: str
    state_snapshot_digest: str
    evidence_status: str
    scenario_provenance: str
    start_time_s: float = 0.0
    provider_termination_required: bool = True
    state_snapshot: EquipmentStateSnapshot | Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field in (
            "component_id", "port_id", "event_id", "failure_mode",
            "provider_boundary_reference", "input_origin",
            "model_package", "model_class", "model_revision", "state_snapshot_digest",
            "scenario_provenance",
        ):
            _text(getattr(self, field), field)
        _digest(self.provider_source_digest, "provider_source_digest")
        _digest(self.state_snapshot_digest, "state_snapshot_digest")
        _positive(self.failure_opening_diameter_m, "failure_opening_diameter_m")
        start = _finite(self.start_time_s, "start_time_s")
        horizon = _positive(self.horizon_s, "horizon_s")
        if start < 0.0:
            raise EquipmentAccidentExportError("start_time_s must be non-negative")
        if horizon <= start:
            raise EquipmentAccidentExportError("horizon_s must be greater than start_time_s")
        _vector(self.position_enu_m, "position_enu_m")
        _vector(self.direction_enu, "direction_enu", nonzero=True)
        _positive(self.ambient_pressure_pa_abs, "ambient_pressure_pa_abs")
        _positive(self.ambient_temperature_k, "ambient_temperature_k")
        if self.evidence_status not in _EVIDENCE_STATUSES:
            raise EquipmentAccidentExportError(
                f"evidence_status must be one of {sorted(_EVIDENCE_STATUSES)}"
            )
        if self.provider_termination_required is not True:
            raise EquipmentAccidentExportError(
                "provider_termination_required must remain true; PRISM never guesses termination"
            )
        snapshot = _coerce_state_snapshot(
            self.state_snapshot,
            component_id=self.component_id,
            state_snapshot_digest=self.state_snapshot_digest,
        )
        object.__setattr__(self, "state_snapshot", snapshot)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AccidentReleaseExportRequest":
        if not isinstance(value, Mapping):
            raise EquipmentAccidentExportError("accident export request must be an object")
        payload = dict(value)
        if payload.get("schema_version") != ACCIDENT_EXPORT_REQUEST_SCHEMA:
            raise EquipmentAccidentExportError(
                f"schema_version must be {ACCIDENT_EXPORT_REQUEST_SCHEMA}"
            )
        if payload.get("event_kind") != "accidental_leak":
            raise EquipmentAccidentExportError(
                "accident export request requires event_kind=accidental_leak"
            )
        if "provider_termination_required" not in payload:
            raise EquipmentAccidentExportError(
                "accident export request must explicitly set provider_termination_required=true"
            )
        payload.pop("schema_version", None)
        payload.pop("event_kind", None)
        try:
            return cls(**payload)
        except TypeError as error:
            raise EquipmentAccidentExportError(
                f"accident export request has missing or unknown fields: {error}"
            ) from error

    def to_mapping(self) -> dict[str, Any]:
        payload = {
            "schema_version": ACCIDENT_EXPORT_REQUEST_SCHEMA,
            "event_kind": "accidental_leak",
            "component_id": self.component_id,
            "port_id": self.port_id,
            "event_id": self.event_id,
            "failure_mode": self.failure_mode,
            "failure_opening_diameter_m": self.failure_opening_diameter_m,
            "start_time_s": self.start_time_s,
            "horizon_s": self.horizon_s,
            "position_enu_m": list(self.position_enu_m),
            "direction_enu": list(self.direction_enu),
            "ambient_pressure_pa_abs": self.ambient_pressure_pa_abs,
            "ambient_temperature_k": self.ambient_temperature_k,
            "provider_source_digest": self.provider_source_digest,
            "provider_boundary_reference": self.provider_boundary_reference,
            "input_origin": self.input_origin,
            "model_package": self.model_package,
            "model_class": self.model_class,
            "model_revision": self.model_revision,
            "state_snapshot_digest": self.state_snapshot_digest,
            "evidence_status": self.evidence_status,
            "scenario_provenance": self.scenario_provenance,
            "provider_termination_required": self.provider_termination_required,
            **_state_snapshot_payload(self.state_snapshot),
        }
        return payload


@dataclass(frozen=True)
class EmergencyReliefExportRequest:
    """Explicit provider request for a maximum-relief-discharge history.

    Relief is a reviewed initiating event rather than a random leak opening,
    so this request deliberately has no failure diameter field.
    """

    component_id: str
    port_id: str
    event_id: str
    horizon_s: float
    position_enu_m: tuple[float, float, float]
    direction_enu: tuple[float, float, float]
    ambient_pressure_pa_abs: float
    ambient_temperature_k: float
    provider_source_digest: str
    provider_boundary_reference: str
    input_origin: str
    model_package: str
    model_class: str
    model_revision: str
    state_snapshot_digest: str
    evidence_status: str
    scenario_provenance: str
    start_time_s: float = 0.0
    provider_termination_required: bool = True
    state_snapshot: EquipmentStateSnapshot | Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field in (
            "component_id", "port_id", "event_id", "provider_boundary_reference",
            "input_origin", "model_package", "model_class", "model_revision",
            "state_snapshot_digest", "scenario_provenance",
        ):
            _text(getattr(self, field), field)
        _digest(self.provider_source_digest, "provider_source_digest")
        _digest(self.state_snapshot_digest, "state_snapshot_digest")
        _positive(self.horizon_s, "horizon_s")
        _positive(self.ambient_pressure_pa_abs, "ambient_pressure_pa_abs")
        _positive(self.ambient_temperature_k, "ambient_temperature_k")
        if self.start_time_s < 0.0 or self.horizon_s <= self.start_time_s:
            raise EquipmentAccidentExportError("emergency-relief request has invalid start/horizon clock")
        _vector(self.position_enu_m, "position_enu_m")
        _vector(self.direction_enu, "direction_enu", nonzero=True)
        if self.evidence_status not in _EVIDENCE_STATUSES:
            raise EquipmentAccidentExportError(
                f"evidence_status must be one of {sorted(_EVIDENCE_STATUSES)}"
            )
        if self.provider_termination_required is not True:
            raise EquipmentAccidentExportError(
                "provider_termination_required must remain true; PRISM never guesses termination"
            )
        snapshot = _coerce_state_snapshot(
            self.state_snapshot,
            component_id=self.component_id,
            state_snapshot_digest=self.state_snapshot_digest,
        )
        object.__setattr__(self, "state_snapshot", snapshot)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EmergencyReliefExportRequest":
        if not isinstance(value, Mapping):
            raise EquipmentAccidentExportError("emergency-relief request must be an object")
        payload = dict(value)
        if payload.get("schema_version") != "prism.equipment_emergency_relief_export_request.v1":
            raise EquipmentAccidentExportError(
                "emergency-relief request has an invalid schema_version"
            )
        if payload.get("event_kind") != "emergency_relief":
            raise EquipmentAccidentExportError(
                "emergency-relief request requires event_kind=emergency_relief"
            )
        if payload.get("provider_termination_required") is not True:
            raise EquipmentAccidentExportError(
                "emergency-relief request must explicitly set provider_termination_required=true"
            )
        payload.pop("schema_version", None)
        payload.pop("event_kind", None)
        try:
            request = cls(**payload)
        except TypeError as error:
            raise EquipmentAccidentExportError(
                f"emergency-relief request has missing or unknown fields: {error}"
            ) from error
        for field in (
            "component_id", "port_id", "event_id", "provider_boundary_reference",
            "input_origin", "model_package", "model_class", "model_revision",
            "state_snapshot_digest", "scenario_provenance",
        ):
            _text(getattr(request, field), field)
        _digest(request.provider_source_digest, "provider_source_digest")
        _digest(request.state_snapshot_digest, "state_snapshot_digest")
        _positive(request.horizon_s, "horizon_s")
        _positive(request.ambient_pressure_pa_abs, "ambient_pressure_pa_abs")
        _positive(request.ambient_temperature_k, "ambient_temperature_k")
        if request.start_time_s < 0.0:
            raise EquipmentAccidentExportError("start_time_s must be non-negative")
        if request.horizon_s <= request.start_time_s:
            raise EquipmentAccidentExportError("horizon_s must be greater than start_time_s")
        _vector(request.position_enu_m, "position_enu_m")
        _vector(request.direction_enu, "direction_enu", nonzero=True)
        if request.evidence_status not in _EVIDENCE_STATUSES:
            raise EquipmentAccidentExportError(
                f"evidence_status must be one of {sorted(_EVIDENCE_STATUSES)}"
            )
        return request

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "prism.equipment_emergency_relief_export_request.v1",
            "event_kind": "emergency_relief",
            "component_id": self.component_id,
            "port_id": self.port_id,
            "event_id": self.event_id,
            "start_time_s": self.start_time_s,
            "horizon_s": self.horizon_s,
            "position_enu_m": list(self.position_enu_m),
            "direction_enu": list(self.direction_enu),
            "ambient_pressure_pa_abs": self.ambient_pressure_pa_abs,
            "ambient_temperature_k": self.ambient_temperature_k,
            "provider_source_digest": self.provider_source_digest,
            "provider_boundary_reference": self.provider_boundary_reference,
            "input_origin": self.input_origin,
            "model_package": self.model_package,
            "model_class": self.model_class,
            "model_revision": self.model_revision,
            "state_snapshot_digest": self.state_snapshot_digest,
            "evidence_status": self.evidence_status,
            "scenario_provenance": self.scenario_provenance,
            "provider_termination_required": self.provider_termination_required,
            **_state_snapshot_payload(self.state_snapshot),
        }


@dataclass(frozen=True)
class InventoryReleaseExportRequest:
    """Explicit provider request for an inventory-defined accidental release.

    These events intentionally carry no random failure opening.  The provider
    owns the finite inventory and must terminate it with either
    ``inventory_depletion`` or a complete ``inventory_over_600s`` horizon.
    """

    component_id: str
    port_id: str
    event_id: str
    release_mode: str
    horizon_s: float
    position_enu_m: tuple[float, float, float]
    direction_enu: tuple[float, float, float]
    ambient_pressure_pa_abs: float
    ambient_temperature_k: float
    provider_source_digest: str
    provider_boundary_reference: str
    input_origin: str
    model_package: str
    model_class: str
    model_revision: str
    state_snapshot_digest: str
    evidence_status: str
    scenario_provenance: str
    start_time_s: float = 0.0
    provider_termination_required: bool = True
    state_snapshot: EquipmentStateSnapshot | Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field in (
            "component_id", "port_id", "event_id", "provider_boundary_reference",
            "input_origin", "model_package", "model_class", "model_revision",
            "state_snapshot_digest", "scenario_provenance",
        ):
            _text(getattr(self, field), field)
        _digest(self.provider_source_digest, "provider_source_digest")
        _digest(self.state_snapshot_digest, "state_snapshot_digest")
        _positive(self.horizon_s, "horizon_s")
        _positive(self.ambient_pressure_pa_abs, "ambient_pressure_pa_abs")
        _positive(self.ambient_temperature_k, "ambient_temperature_k")
        if self.start_time_s < 0.0 or self.horizon_s <= self.start_time_s:
            raise EquipmentAccidentExportError("inventory release request has invalid start/horizon clock")
        _vector(self.position_enu_m, "position_enu_m")
        _vector(self.direction_enu, "direction_enu", nonzero=True)
        if self.evidence_status not in _EVIDENCE_STATUSES:
            raise EquipmentAccidentExportError(
                f"evidence_status must be one of {sorted(_EVIDENCE_STATUSES)}"
            )
        if self.provider_termination_required is not True:
            raise EquipmentAccidentExportError(
                "provider_termination_required must remain true; PRISM never guesses termination"
            )
        snapshot = _coerce_state_snapshot(
            self.state_snapshot,
            component_id=self.component_id,
            state_snapshot_digest=self.state_snapshot_digest,
        )
        object.__setattr__(self, "state_snapshot", snapshot)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InventoryReleaseExportRequest":
        if not isinstance(value, Mapping):
            raise EquipmentAccidentExportError("inventory release request must be an object")
        payload = dict(value)
        if payload.get("schema_version") != "prism.equipment_inventory_export_request.v1":
            raise EquipmentAccidentExportError("inventory release request has an invalid schema_version")
        if payload.get("event_kind") != "accidental_leak":
            raise EquipmentAccidentExportError("inventory release request requires event_kind=accidental_leak")
        if payload.get("release_mode") not in {"instantaneous_inventory", "inventory_over_600s"}:
            raise EquipmentAccidentExportError("inventory release request has an unsupported release_mode")
        if payload.get("provider_termination_required") is not True:
            raise EquipmentAccidentExportError("inventory release request must explicitly set provider_termination_required=true")
        payload.pop("schema_version", None)
        payload.pop("event_kind", None)
        try:
            request = cls(**payload)
        except TypeError as error:
            raise EquipmentAccidentExportError(f"inventory release request has missing or unknown fields: {error}") from error
        for field in (
            "component_id", "port_id", "event_id", "provider_boundary_reference",
            "input_origin", "model_package", "model_class", "model_revision",
            "state_snapshot_digest", "scenario_provenance",
        ):
            _text(getattr(request, field), field)
        _digest(request.provider_source_digest, "provider_source_digest")
        _digest(request.state_snapshot_digest, "state_snapshot_digest")
        _positive(request.horizon_s, "horizon_s")
        _positive(request.ambient_pressure_pa_abs, "ambient_pressure_pa_abs")
        _positive(request.ambient_temperature_k, "ambient_temperature_k")
        if request.start_time_s < 0.0 or request.horizon_s <= request.start_time_s:
            raise EquipmentAccidentExportError("inventory release request has invalid start/horizon clock")
        _vector(request.position_enu_m, "position_enu_m")
        _vector(request.direction_enu, "direction_enu", nonzero=True)
        if request.evidence_status not in _EVIDENCE_STATUSES:
            raise EquipmentAccidentExportError(f"evidence_status must be one of {sorted(_EVIDENCE_STATUSES)}")
        return request

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "prism.equipment_inventory_export_request.v1",
            "event_kind": "accidental_leak",
            "component_id": self.component_id,
            "port_id": self.port_id,
            "event_id": self.event_id,
            "release_mode": self.release_mode,
            "start_time_s": self.start_time_s,
            "horizon_s": self.horizon_s,
            "position_enu_m": list(self.position_enu_m),
            "direction_enu": list(self.direction_enu),
            "ambient_pressure_pa_abs": self.ambient_pressure_pa_abs,
            "ambient_temperature_k": self.ambient_temperature_k,
            "provider_source_digest": self.provider_source_digest,
            "provider_boundary_reference": self.provider_boundary_reference,
            "input_origin": self.input_origin,
            "model_package": self.model_package,
            "model_class": self.model_class,
            "model_revision": self.model_revision,
            "state_snapshot_digest": self.state_snapshot_digest,
            "evidence_status": self.evidence_status,
            "scenario_provenance": self.scenario_provenance,
            "provider_termination_required": self.provider_termination_required,
            **_state_snapshot_payload(self.state_snapshot),
        }


def bind_state_snapshot_to_export_request(
    request: AccidentReleaseExportRequest
    | EmergencyReliefExportRequest
    | InventoryReleaseExportRequest
    | Mapping[str, Any],
    snapshot: EquipmentStateSnapshot,
) -> AccidentReleaseExportRequest | EmergencyReliefExportRequest | InventoryReleaseExportRequest:
    """Attach one canonical process state to an explicit export request.

    This helper is intentionally the only convenience path that changes a
    request's state digest.  It never creates or changes accident geometry,
    frequency, duration, or termination policy.
    """
    if not isinstance(snapshot, EquipmentStateSnapshot):
        raise EquipmentAccidentExportError(
            "snapshot must be an EquipmentStateSnapshot"
        )
    if isinstance(request, AccidentReleaseExportRequest):
        return replace(
            request,
            state_snapshot=snapshot,
            state_snapshot_digest=snapshot.digest(),
        )
    if isinstance(request, EmergencyReliefExportRequest):
        return replace(
            request,
            state_snapshot=snapshot,
            state_snapshot_digest=snapshot.digest(),
        )
    if isinstance(request, InventoryReleaseExportRequest):
        return replace(
            request,
            state_snapshot=snapshot,
            state_snapshot_digest=snapshot.digest(),
        )
    if not isinstance(request, Mapping):
        raise EquipmentAccidentExportError("export request must be an object")
    payload = dict(request)
    schema = payload.get("schema_version")
    payload["state_snapshot"] = snapshot.to_mapping()
    payload["state_snapshot_digest"] = snapshot.digest()
    if schema == ACCIDENT_EXPORT_REQUEST_SCHEMA:
        return AccidentReleaseExportRequest.from_mapping(payload)
    if schema == "prism.equipment_emergency_relief_export_request.v1":
        return EmergencyReliefExportRequest.from_mapping(payload)
    if schema == "prism.equipment_inventory_export_request.v1":
        return InventoryReleaseExportRequest.from_mapping(payload)
    raise EquipmentAccidentExportError("export request has an unsupported schema_version")


@runtime_checkable
class AccidentHistoryProvider(Protocol):
    """Protocol implemented by a qualified external equipment model."""

    def export_accident_history(
        self, request: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class AccidentReleaseExportResult:
    """Strict release plus promotion metadata for one provider export."""

    release: Any
    request: AccidentReleaseExportRequest | EmergencyReliefExportRequest | InventoryReleaseExportRequest
    provider_response: Mapping[str, Any]
    provider_result_digest: str
    provider_class: str
    provider_method: str
    provider_export_schema: str
    promotion_status: str

    @property
    def provider_packet_promoted(self) -> bool:
        return self.promotion_status == "QUALIFIED_PROVIDER_PACKET"


def _normalise_request(
    request: AccidentReleaseExportRequest | Mapping[str, Any],
) -> AccidentReleaseExportRequest:
    if isinstance(request, AccidentReleaseExportRequest):
        return request
    return AccidentReleaseExportRequest.from_mapping(request)


def _call_provider(
    provider: AccidentHistoryProvider,
    request: AccidentReleaseExportRequest,
) -> tuple[Mapping[str, Any], str]:
    exporter = getattr(provider, "export_accident_history", None)
    if not callable(exporter):
        raise EquipmentAccidentExportError(
            "provider model has no export_accident_history(request); evaluate/simulate/advance "
            "cannot be used as an accident packet"
        )
    try:
        response = exporter(request.to_mapping())
    except EquipmentAccidentExportError:
        raise
    except Exception as error:  # provider errors are reported without promotion
        raise EquipmentAccidentExportError(
            f"provider accident export failed: {type(error).__name__}: {error}"
        ) from error
    if not isinstance(response, Mapping):
        raise EquipmentAccidentExportError("provider accident export must return an object")
    if response.get("provider_export_schema") != EXTERNAL_ACCIDENT_EXPORT_SCHEMA:
        raise EquipmentAccidentExportError(
            f"provider accident export must declare {EXTERNAL_ACCIDENT_EXPORT_SCHEMA}"
        )
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise EquipmentAccidentExportError("provider accident export must contain a data object")
    if data.get("event_kind") != "accidental_leak":
        raise EquipmentAccidentExportError(
            "provider accident export data must explicitly declare event_kind=accidental_leak"
        )
    for key in ("event_id", "component_id", "port_id"):
        declared = data.get(key, response.get(key))
        expected = getattr(request, key)
        if declared is not None and declared != expected:
            raise EquipmentAccidentExportError(
                f"provider accident export {key} disagrees with request"
            )
    if data.get("normal_state_snapshot") is True or response.get("normal_state_snapshot") is True:
        raise EquipmentAccidentExportError(
            "normal-state snapshot cannot be promoted as an accident history"
        )
    if getattr(request, "state_snapshot", None) is not None:
        declared_snapshot_digest = response.get("provider_state_snapshot_digest")
        if declared_snapshot_digest is None:
            declared_snapshot_digest = data.get("provider_state_snapshot_digest")
        if declared_snapshot_digest != request.state_snapshot_digest:
            raise EquipmentAccidentExportError(
                "provider state snapshot digest must echo the request snapshot digest"
            )
    _require_provider_qualification_if_claimed(response, request)
    return response, type(provider).__module__ + "." + type(provider).__qualname__


def _call_emergency_relief_provider(
    provider: AccidentHistoryProvider,
    request: EmergencyReliefExportRequest,
) -> tuple[Mapping[str, Any], str]:
    exporter = getattr(provider, "export_accident_history", None)
    if not callable(exporter):
        raise EquipmentAccidentExportError(
            "provider model has no export_accident_history(request); relief export cannot use evaluate/simulate"
        )
    try:
        response = exporter(request.to_mapping())
    except EquipmentAccidentExportError:
        raise
    except Exception as error:
        raise EquipmentAccidentExportError(
            f"provider emergency-relief export failed: {type(error).__name__}: {error}"
        ) from error
    if not isinstance(response, Mapping):
        raise EquipmentAccidentExportError("provider emergency-relief export must return an object")
    if response.get("provider_export_schema") != EXTERNAL_ACCIDENT_EXPORT_SCHEMA:
        raise EquipmentAccidentExportError(
            f"provider emergency-relief export must declare {EXTERNAL_ACCIDENT_EXPORT_SCHEMA}"
        )
    data = response.get("data")
    if not isinstance(data, Mapping) or data.get("event_kind") != "emergency_relief":
        raise EquipmentAccidentExportError(
            "provider emergency-relief export data must explicitly declare event_kind=emergency_relief"
        )
    if data.get("failure_opening_diameter_m") is not None:
        raise EquipmentAccidentExportError(
            "provider emergency-relief export must not carry a random opening"
        )
    for key in ("event_id", "component_id", "port_id"):
        declared = data.get(key, response.get(key))
        expected = getattr(request, key)
        if declared is not None and declared != expected:
            raise EquipmentAccidentExportError(
                f"provider emergency-relief export {key} disagrees with request"
            )
    if data.get("normal_state_snapshot") is True or response.get("normal_state_snapshot") is True:
        raise EquipmentAccidentExportError(
            "normal-state snapshot cannot be promoted as an emergency-relief history"
        )
    if getattr(request, "state_snapshot", None) is not None:
        declared_snapshot_digest = response.get("provider_state_snapshot_digest")
        if declared_snapshot_digest is None:
            declared_snapshot_digest = data.get("provider_state_snapshot_digest")
        if declared_snapshot_digest != request.state_snapshot_digest:
            raise EquipmentAccidentExportError(
                "provider state snapshot digest must echo the request snapshot digest"
            )
    _require_provider_qualification_if_claimed(response, request)
    return response, type(provider).__module__ + "." + type(provider).__qualname__


def _export(
    provider: AccidentHistoryProvider,
    request: AccidentReleaseExportRequest | Mapping[str, Any],
    *,
    release_kind: str,
) -> AccidentReleaseExportResult:
    scenario = _normalise_request(request)
    response, provider_class = _call_provider(provider, scenario)
    common = {
        "provider_response": response,
        "component_id": scenario.component_id,
        "port_id": scenario.port_id,
        "event_id": scenario.event_id,
        "provider_source_digest": scenario.provider_source_digest,
        "upstream_service_provenance": scenario.scenario_provenance,
        "provider_boundary_reference": scenario.provider_boundary_reference,
        "input_origin": scenario.input_origin,
        "position_enu_m": scenario.position_enu_m,
        "direction_enu": scenario.direction_enu,
        "ambient_pressure_pa_abs": scenario.ambient_pressure_pa_abs,
        "ambient_temperature_k": scenario.ambient_temperature_k,
        "failure_opening_diameter_m": scenario.failure_opening_diameter_m,
        "provider_result": response,
    }
    try:
        if release_kind == "gas":
            release = build_resolved_gas_release_from_provider_response(**common)
        elif release_kind == "liquid":
            release = build_resolved_liquid_release_from_provider_response(**common)
        else:
            raise EquipmentAccidentExportError("release_kind must be gas or liquid")
    except EquipmentReleaseExportError as error:
        raise EquipmentAccidentExportError(str(error)) from error
    from .contracts import canonical_digest

    result_digest = canonical_digest(response)
    promotion_status = (
        "QUALIFIED_PROVIDER_PACKET"
        if scenario.evidence_status == "qualified_actual"
        else "DIAGNOSTIC_PACKET_NOT_PROMOTED"
    )
    return AccidentReleaseExportResult(
        release=release,
        request=scenario,
        provider_response=response,
        provider_result_digest=result_digest,
        provider_class=provider_class,
        provider_method="export_accident_history",
        provider_export_schema=EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
        promotion_status=promotion_status,
    )


def export_equipment_gas_accident_history(
    provider: AccidentHistoryProvider,
    request: AccidentReleaseExportRequest | Mapping[str, Any],
) -> AccidentReleaseExportResult:
    """Run an explicit provider gas accident export and validate its packet."""

    return _export(provider, request, release_kind="gas")


def export_equipment_liquid_accident_history(
    provider: AccidentHistoryProvider,
    request: AccidentReleaseExportRequest | Mapping[str, Any],
) -> AccidentReleaseExportResult:
    """Run an explicit provider liquid/two-phase accident export and validate it."""

    return _export(provider, request, release_kind="liquid")


def export_equipment_emergency_relief_history(
    provider: AccidentHistoryProvider,
    request: EmergencyReliefExportRequest | Mapping[str, Any],
) -> AccidentReleaseExportResult:
    """Run a strict provider-owned maximum-relief-discharge history."""

    scenario = (
        request if isinstance(request, EmergencyReliefExportRequest)
        else EmergencyReliefExportRequest.from_mapping(request)
    )
    response, provider_class = _call_emergency_relief_provider(provider, scenario)
    common = {
        "provider_response": response,
        "component_id": scenario.component_id,
        "port_id": scenario.port_id,
        "event_id": scenario.event_id,
        "provider_source_digest": scenario.provider_source_digest,
        "upstream_service_provenance": scenario.scenario_provenance,
        "provider_boundary_reference": scenario.provider_boundary_reference,
        "input_origin": scenario.input_origin,
        "position_enu_m": scenario.position_enu_m,
        "direction_enu": scenario.direction_enu,
        "ambient_pressure_pa_abs": scenario.ambient_pressure_pa_abs,
        "ambient_temperature_k": scenario.ambient_temperature_k,
        "failure_opening_diameter_m": None,
        "event_kind": "emergency_relief",
        "provider_result": response,
    }
    try:
        release = build_resolved_gas_release_from_provider_response(**common)
    except EquipmentReleaseExportError as error:
        raise EquipmentAccidentExportError(str(error)) from error
    from .contracts import canonical_digest

    result_digest = canonical_digest(response)
    promotion_status = (
        "QUALIFIED_PROVIDER_PACKET"
        if scenario.evidence_status == "qualified_actual"
        else "DIAGNOSTIC_PACKET_NOT_PROMOTED"
    )
    return AccidentReleaseExportResult(
        release=release,
        request=scenario,
        provider_response=response,
        provider_result_digest=result_digest,
        provider_class=provider_class,
        provider_method="export_accident_history",
        provider_export_schema=EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
        promotion_status=promotion_status,
    )


def export_equipment_inventory_release_history(
    provider: AccidentHistoryProvider,
    request: InventoryReleaseExportRequest | Mapping[str, Any],
    *,
    release_kind: str = "gas",
) -> AccidentReleaseExportResult:
    """Run a strict provider-owned inventory accidental-release history."""

    scenario = (
        request if isinstance(request, InventoryReleaseExportRequest)
        else InventoryReleaseExportRequest.from_mapping(request)
    )
    response, provider_class = _call_provider(provider, scenario)  # type: ignore[arg-type]
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise EquipmentAccidentExportError("provider inventory export must contain data")
    basis = data.get("termination_basis")
    if scenario.release_mode == "instantaneous_inventory":
        if basis != "inventory_depletion":
            raise EquipmentAccidentExportError("instantaneous inventory export requires inventory_depletion termination")
    elif basis != "inventory_over_600s" or not math.isclose(float(data.get("duration_s", -1.0)), 600.0, rel_tol=0.0, abs_tol=1.0e-9):
        raise EquipmentAccidentExportError("inventory_over_600s export requires a 600 s inventory_over_600s history")
    common = {
        "provider_response": response,
        "component_id": scenario.component_id,
        "port_id": scenario.port_id,
        "event_id": scenario.event_id,
        "provider_source_digest": scenario.provider_source_digest,
        "upstream_service_provenance": scenario.scenario_provenance,
        "provider_boundary_reference": scenario.provider_boundary_reference,
        "input_origin": scenario.input_origin,
        "position_enu_m": scenario.position_enu_m,
        "direction_enu": scenario.direction_enu,
        "ambient_pressure_pa_abs": scenario.ambient_pressure_pa_abs,
        "ambient_temperature_k": scenario.ambient_temperature_k,
        "failure_opening_diameter_m": None,
        "event_kind": "accidental_leak",
        "provider_result": response,
    }
    try:
        if release_kind == "gas":
            release = build_resolved_gas_release_from_provider_response(**common)
        elif release_kind == "liquid":
            release = build_resolved_liquid_release_from_provider_response(**common)
        else:
            raise EquipmentAccidentExportError("release_kind must be gas or liquid")
    except EquipmentReleaseExportError as error:
        raise EquipmentAccidentExportError(str(error)) from error
    from .contracts import canonical_digest

    result_digest = canonical_digest(response)
    promotion_status = (
        "QUALIFIED_PROVIDER_PACKET"
        if scenario.evidence_status == "qualified_actual"
        else "DIAGNOSTIC_PACKET_NOT_PROMOTED"
    )
    return AccidentReleaseExportResult(
        release=release,
        request=scenario,
        provider_response=response,
        provider_result_digest=result_digest,
        provider_class=provider_class,
        provider_method="export_accident_history",
        provider_export_schema=EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
        promotion_status=promotion_status,
    )


__all__ = [
    "ACCIDENT_EXPORT_REQUEST_SCHEMA",
    "EXTERNAL_ACCIDENT_EXPORT_SCHEMA",
    "PROVIDER_QUALIFICATION_SCHEMA",
    "AccidentHistoryProvider",
    "EquipmentAccidentExportError",
    "AccidentReleaseExportRequest",
    "EmergencyReliefExportRequest",
    "InventoryReleaseExportRequest",
    "EquipmentStateSnapshot",
    "bind_state_snapshot_to_export_request",
    "AccidentReleaseExportResult",
    "export_equipment_gas_accident_history",
    "export_equipment_liquid_accident_history",
    "export_equipment_emergency_relief_history",
    "export_equipment_inventory_release_history",
]
