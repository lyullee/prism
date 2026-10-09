"""Strict process-state snapshot contract for external LH2 equipment models.

An equipment digital twin may provide the state at which an accident export
is evaluated.  The state snapshot is deliberately separate from the accident
scenario: it carries measured or model-predicted thermodynamic state only and
never carries a hole, frequency, duration, termination, or resolved release.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, model_validator

from .contracts import Contract, Fraction, Name, Nonnegative, Positive, Vector


EQUIPMENT_STATE_SNAPSHOT_SCHEMA = "prism.equipment_state_snapshot.v1"

_ORIGINS = Literal[
    "historian_measured",
    "model_prediction",
    "reconstructed",
    "figure_digitized",
    "video_recovered",
    "synthetic",
]
_PHASES = Literal["liquid", "vapour", "two_phase", "unknown"]
_QUALITIES = Literal["valid", "suspect", "missing"]
_QUANTITIES = Literal[
    "pressure",
    "temperature",
    "mass",
    "mass_flow",
    "level_fraction",
    "hydrogen_fraction",
    "differential_pressure",
]


class StateMeasurement(Contract):
    """One normalized SI measurement belonging to the parent component."""

    quantity: _QUANTITIES
    value_si: float
    sensor_location: Name | None = None
    quality: _QUALITIES = "valid"


class EquipmentStateSnapshot(Contract):
    """A hashable, state-only snapshot handed to an accident provider.

    ``pressure_pa_abs`` and ``temperature_k`` are optional because some
    equipment (for example a boundary or a passive vent) may only expose one
    state variable.  At least one state field or normalized measurement must be
    present.  The canonical :meth:`digest` includes the schema and all values.
    """

    schema_version: Literal[EQUIPMENT_STATE_SNAPSHOT_SCHEMA]
    component_id: Name
    captured_at_s: Nonnegative
    origin: _ORIGINS
    pressure_pa_abs: Positive | None = None
    temperature_k: Positive | None = None
    mass_kg: Nonnegative | None = None
    liquid_fraction: Fraction | None = None
    phase: _PHASES | None = None
    position_enu_m: Vector | None = None
    measurements: dict[str, StateMeasurement] = Field(default_factory=dict)
    source_digest: str | None = Field(default=None, min_length=64, max_length=64)
    quality: _QUALITIES = "valid"

    @model_validator(mode="before")
    @classmethod
    def reject_accident_fields(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        _scan_forbidden_keys(value)
        return value

    @model_validator(mode="after")
    def validate_state(self) -> "EquipmentStateSnapshot":
        if (
            self.pressure_pa_abs is None
            and self.temperature_k is None
            and self.mass_kg is None
            and self.liquid_fraction is None
            and not self.measurements
        ):
            raise ValueError("equipment state snapshot requires at least one state field")
        if self.source_digest is not None:
            _validate_digest(self.source_digest, "source_digest")
        for tag, measurement in self.measurements.items():
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("state measurement tags must be non-empty strings")
            if measurement.quantity == "pressure" and measurement.value_si <= 0:
                raise ValueError("pressure measurement must be positive absolute pressure")
            if measurement.quantity == "temperature" and measurement.value_si <= 0:
                raise ValueError("temperature measurement must be positive")
        return self

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EquipmentStateSnapshot":
        if not isinstance(value, Mapping):
            raise ValueError("equipment state snapshot must be an object")
        if value.get("schema_version") != EQUIPMENT_STATE_SNAPSHOT_SCHEMA:
            raise ValueError(
                f"schema_version must be {EQUIPMENT_STATE_SNAPSHOT_SCHEMA}"
            )
        return cls.model_validate(dict(value))

    def to_mapping(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


_FORBIDDEN_STATE_KEYS = frozenset({
    "annual_frequency_per_year",
    "frequency_event",
    "initiation_intensity_per_s",
    "failure_opening_diameter_m",
    "failure_area_m2",
    "hole_diameter_m",
    "leak_diameter_m",
    "resolved_release",
    "resolved_release_set",
    "resolved_liquid_release",
    "provider_release",
    "provider_release_packet",
    "release_termination",
    "termination_provenance",
    "event_id",
    "event_kind",
    "duration_s",
    "steps",
    "cumulative_mass_out_kg",
    "provider_export_schema",
})


def _scan_forbidden_keys(value: Any, *, path: str = "state_snapshot") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text.lower() in _FORBIDDEN_STATE_KEYS:
                raise ValueError(
                    f"state snapshot contains accident-owned field: {path}.{key_text}"
                )
            _scan_forbidden_keys(child, path=f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_forbidden_keys(child, path=f"{path}[{index}]")


def _validate_digest(value: str, field: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{field} must be a 64-character SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{field} must be a hexadecimal SHA-256 digest") from error


def build_state_snapshot_from_normalized(
    normalized: Mapping[str, Any],
    *,
    component_id: str,
    captured_at_s: float,
    pressure_tag: str | None = None,
    temperature_tag: str | None = None,
    position_enu_m: Vector | None = None,
) -> EquipmentStateSnapshot:
    """Convert a validated telemetry-normalizer result into state-only data.

    Tag selection is explicit when multiple pressure or temperature values are
    present.  The function copies only normalized state rows and never derives
    an accident scenario from them.
    """
    if not isinstance(normalized, Mapping):
        raise ValueError("normalized telemetry must be an object")
    values = normalized.get("values")
    if not isinstance(values, Mapping) or not values:
        raise ValueError("normalized telemetry requires non-empty values")
    rows: dict[str, StateMeasurement] = {}
    by_quantity: dict[str, list[str]] = {}
    for tag, raw in values.items():
        if not isinstance(tag, str) or not isinstance(raw, Mapping):
            raise ValueError("normalized telemetry rows must be named objects")
        if raw.get("component_id") != component_id:
            raise ValueError(f"normalized telemetry component mismatch: {tag}")
        quantity = raw.get("quantity")
        if quantity not in {
            "pressure", "temperature", "mass", "mass_flow",
            "level_fraction", "hydrogen_fraction", "differential_pressure",
        }:
            raise ValueError(f"unsupported normalized state quantity: {quantity}")
        try:
            measurement = StateMeasurement(
                quantity=quantity,
                value_si=float(raw["value_si"]),
                sensor_location=raw.get("sensor_location"),
                quality="valid",
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid normalized state row: {tag}") from error
        rows[tag] = measurement
        by_quantity.setdefault(quantity, []).append(tag)

    def select(quantity: str, tag: str | None) -> tuple[str | None, StateMeasurement | None]:
        candidates = by_quantity.get(quantity, [])
        if tag is not None:
            if tag not in rows or rows[tag].quantity != quantity:
                raise ValueError(f"{tag} is not a normalized {quantity} tag")
            return tag, rows[tag]
        if len(candidates) > 1:
            raise ValueError(f"multiple normalized {quantity} tags require explicit selection")
        if not candidates:
            return None, None
        return candidates[0], rows[candidates[0]]

    _, pressure = select("pressure", pressure_tag)
    _, temperature = select("temperature", temperature_tag)
    source_digest = normalized.get("frame_digest")
    if source_digest is not None:
        _validate_digest(source_digest, "frame_digest")
    origin = normalized.get("origin")
    if origin not in {
        "historian_measured", "model_prediction", "reconstructed",
        "figure_digitized", "video_recovered", "synthetic",
    }:
        raise ValueError("normalized telemetry origin is missing or unsupported")
    return EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id=component_id,
        captured_at_s=captured_at_s,
        origin=origin,
        pressure_pa_abs=None if pressure is None else pressure.value_si,
        temperature_k=None if temperature is None else temperature.value_si,
        measurements=rows,
        source_digest=source_digest,
        position_enu_m=position_enu_m,
    )


__all__ = [
    "EQUIPMENT_STATE_SNAPSHOT_SCHEMA",
    "StateMeasurement",
    "EquipmentStateSnapshot",
    "build_state_snapshot_from_normalized",
]
