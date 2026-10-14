"""Fail-closed evidence ledger for observed LH2 equipment state.

The ledger accepts already-normalized telemetry samples and turns them into
reviewable :class:`EquipmentStateSnapshot` records.  It is deliberately a
state-evidence boundary: observed process data can support state calibration
and model comparison, but it never creates an accident, learns a frequency,
or promotes a provider packet.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import math
from statistics import mean, median
from typing import Any

from .state_snapshot import EquipmentStateSnapshot, EQUIPMENT_STATE_SNAPSHOT_SCHEMA


OBSERVED_STATE_EVIDENCE_SCHEMA = "prism.observed_equipment_state_evidence.v1"
_QUANTITIES = frozenset(
    {
        "pressure",
        "temperature",
        "mass",
        "mass_flow",
        "level_fraction",
        "hydrogen_fraction",
        "differential_pressure",
    }
)
_FORBIDDEN_KEYS = frozenset(
    {
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
    }
)


def _scan_forbidden(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key).lower()
            if name in _FORBIDDEN_KEYS:
                raise ValueError(f"observed state evidence contains accident-owned field: {path}.{key}")
            _scan_forbidden(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_forbidden(child, path=f"{path}[{index}]")


def _finite_number(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None, "median": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "median": median(values),
    }


def _snapshot_from_sample(
    source: Mapping[str, Any],
    sample: Mapping[str, Any],
    *,
    sample_index: int,
) -> EquipmentStateSnapshot:
    component_id = source.get("component_id")
    if not isinstance(component_id, str) or not component_id.strip():
        raise ValueError("source component_id must be a non-empty string")
    origin = source.get("origin", "historian_measured")
    if origin not in {
        "historian_measured",
        "model_prediction",
        "reconstructed",
        "figure_digitized",
        "video_recovered",
        "synthetic",
    }:
        raise ValueError(f"unsupported observed-state origin: {origin}")
    captured_at_s = _finite_number(sample.get("captured_at_s", sample_index), "captured_at_s")
    if captured_at_s < 0:
        raise ValueError("captured_at_s must be non-negative")
    raw_values = sample.get("values")
    if not isinstance(raw_values, Mapping) or not raw_values:
        raise ValueError("observed state sample requires a non-empty values mapping")
    measurements: dict[str, dict[str, Any]] = {}
    state_fields: dict[str, Any] = {}
    for tag_or_quantity, raw in raw_values.items():
        tag = str(tag_or_quantity)
        quantity = (
            str(raw.get("quantity") or tag)
            if isinstance(raw, Mapping)
            else tag
        )
        if quantity not in _QUANTITIES:
            raise ValueError(
                f"unsupported observed-state quantity: {quantity}; "
                "custom state tags must include raw.values[tag].quantity"
            )
        if isinstance(raw, Mapping):
            value = raw.get("value_si")
            sensor_location = raw.get("sensor_location")
            quality = raw.get("quality", sample.get("quality", "valid"))
        else:
            value = raw
            sensor_location = None
            quality = sample.get("quality", "valid")
        if quality not in {"valid", "suspect", "missing"}:
            raise ValueError(f"unsupported observed-state quality: {quality}")
        if quality == "missing":
            continue
        value_si = _finite_number(value, f"{tag}.value_si")
        if quantity in {"pressure", "temperature"} and value_si <= 0:
            raise ValueError(f"{quantity} must be positive in SI units")
        measurements[tag] = {
            "quantity": quantity,
            "value_si": value_si,
            "sensor_location": sensor_location,
            "quality": quality,
        }
        if quantity == "pressure":
            state_fields["pressure_pa_abs"] = value_si
        elif quantity == "temperature":
            state_fields["temperature_k"] = value_si
        elif quantity == "mass":
            state_fields["mass_kg"] = max(0.0, value_si)
        elif quantity == "level_fraction":
            state_fields["liquid_fraction"] = min(1.0, max(0.0, value_si))
    if not measurements:
        raise ValueError("observed state sample has no valid state measurements")
    return EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id=component_id,
        captured_at_s=captured_at_s,
        origin=origin,
        measurements=measurements,
        source_digest=source.get("source_sha256"),
        quality=sample.get("quality", "valid"),
        **state_fields,
    )


def build_observed_state_evidence(
    sources: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a normalized observed-state evidence ledger.

    Each source must contain ``source_id``, ``component_id`` and a ``samples``
    list.  Samples use SI values under ``values``.  The function keeps only
    state measurements and rejects accident-owned fields recursively.
    """
    source_rows: list[dict[str, Any]] = []
    snapshots: list[tuple[str, EquipmentStateSnapshot]] = []
    component_values: dict[str, dict[str, list[float]]] = {}
    component_snapshot_counts: dict[str, int] = {}
    cadence_values: dict[str, list[float]] = {}
    origins: dict[str, int] = {}
    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("observed-state source must be an object")
        _scan_forbidden(source, path="source")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        samples = source.get("samples")
        if not isinstance(samples, list) or not samples:
            raise ValueError(f"source {source_id} requires a non-empty samples list")
        source_snapshots: list[EquipmentStateSnapshot] = []
        for index, sample in enumerate(samples):
            if not isinstance(sample, Mapping):
                raise ValueError(f"source {source_id} sample {index} must be an object")
            _scan_forbidden(sample, path=f"source.{source_id}.samples[{index}]")
            snapshot = _snapshot_from_sample(source, sample, sample_index=index)
            source_snapshots.append(snapshot)
            snapshots.append((source_id, snapshot))
            component = component_values.setdefault(snapshot.component_id, {})
            component_snapshot_counts[snapshot.component_id] = (
                component_snapshot_counts.get(snapshot.component_id, 0) + 1
            )
            for tag, measurement in snapshot.measurements.items():
                component.setdefault(measurement.quantity, []).append(measurement.value_si)
            origins[snapshot.origin] = origins.get(snapshot.origin, 0) + 1
        ordered_times = [row.captured_at_s for row in source_snapshots]
        deltas = [b - a for a, b in zip(ordered_times, ordered_times[1:]) if b >= a]
        if deltas:
            cadence_values[source_id] = deltas
        source_rows.append(
            {
                "source_id": source_id,
                "source_path": source.get("source_path"),
                "resolved_source_path": source.get("resolved_source_path"),
                "source_sha256": source.get("source_sha256"),
                "format": source.get("format"),
                "component_id": source_snapshots[0].component_id,
                "origin": source_snapshots[0].origin,
                "sample_count": len(source_snapshots),
                "time_start_s": min(ordered_times),
                "time_end_s": max(ordered_times),
                "cadence_s": median(deltas) if deltas else None,
                "signal_map": source.get("signal_map", {}),
                "snapshot_digest_set_sha256": hashlib.sha256(
                    "\n".join(sorted(row.digest() for row in source_snapshots)).encode("utf-8")
                ).hexdigest(),
            }
        )
    component_rows = []
    for component_id in sorted(component_values):
        quantities = component_values[component_id]
        component_rows.append(
            {
                "component_id": component_id,
                "source_ids": sorted(
                    {source_id for source_id, snapshot in snapshots if snapshot.component_id == component_id}
                ),
                "sample_count": component_snapshot_counts[component_id],
                "measurement_count": sum(len(values) for values in quantities.values()),
                "quantity_statistics": {
                    quantity: _stats(values) for quantity, values in sorted(quantities.items())
                },
            }
        )
    sample_count = len(snapshots)
    return {
        "schema_version": OBSERVED_STATE_EVIDENCE_SCHEMA,
        "status": "OBSERVATION_STATE_EVIDENCE_ONLY" if sample_count else "NO_OBSERVED_STATE_SAMPLES",
        "source_count": len(source_rows),
        "sample_count": sample_count,
        "component_count": len(component_rows),
        "source_rows": source_rows,
        "component_rows": component_rows,
        "origin_counts": origins,
        "policy": {
            "canonical_snapshot_schema": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
            "state_only": True,
            "release_scenario_generated": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Observed process data are normalized into equipment-state evidence for calibration and "
            "snapshot review. No accident, release duration, frequency, provider qualification, or "
            "facility QRA claim is derived from these observations."
        ),
    }


__all__ = ["OBSERVED_STATE_EVIDENCE_SCHEMA", "build_observed_state_evidence"]
