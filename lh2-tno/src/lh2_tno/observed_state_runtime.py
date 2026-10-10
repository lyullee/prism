"""Build state-only frames for a realtime digital-twin handoff.

The observed-state evidence ledger is intentionally an aggregate audit.  A
realtime resolver needs one explicit frame, however, so this module selects a
sample from the already-normalized source rows and emits the same ``values``
shape accepted by :func:`lh2_tno.service.validate_equipment_process_state`.

The output contains process state only.  It never derives a leak, a duration,
an isolation result, an inventory boundary, or a frequency from observations.
An equipment provider must still return a resolved release before PRISM can
evaluate consequences.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from typing import Any

from .contracts import canonical_digest
from .observed_state_evidence import build_observed_state_evidence
from .state_snapshot import EquipmentStateSnapshot, StateMeasurement


SCHEMA = "prism.observed_state_runtime_frames.v1"
EVIDENCE_SCHEMA = "prism.observed_equipment_state_evidence.v1"

_QUANTITIES = {
    "pressure",
    "temperature",
    "mass",
    "mass_flow",
    "level_fraction",
    "hydrogen_fraction",
    "differential_pressure",
}

_RUNTIME_FRAME_FORBIDDEN_KEYS = frozenset({
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
})

_ORIGINS = {
    "historian_measured",
    "figure_digitized",
    "video_recovered",
    "reconstructed",
    "model_prediction",
    "synthetic",
}


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _sources(sources: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ValueError(f"sources[{index}] must be an object")
        component_id = str(source.get("component_id") or "").strip()
        source_id = str(source.get("source_id") or "").strip()
        if not component_id or not source_id:
            raise ValueError("each source requires source_id and component_id")
        samples = source.get("samples")
        if not isinstance(samples, list) or not samples:
            raise ValueError(f"source {source_id} requires non-empty samples")
        rows.append(dict(source))
    return rows


def _latest_sample(source: Mapping[str, Any]) -> Mapping[str, Any]:
    samples = source["samples"]
    candidates: list[tuple[float, int, Mapping[str, Any]]] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            raise ValueError(f"source {source.get('source_id')} sample {index} must be an object")
        captured = _finite(sample.get("captured_at_s", index), "captured_at_s")
        candidates.append((captured, index, sample))
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _frame_from_source(source: Mapping[str, Any]) -> dict[str, Any]:
    source_id = str(source["source_id"])
    component_id = str(source["component_id"])
    sample = _latest_sample(source)
    captured_at_s = _finite(sample.get("captured_at_s", 0.0), "captured_at_s")
    raw_values = sample.get("values")
    if not isinstance(raw_values, Mapping) or not raw_values:
        raise ValueError(f"source {source_id} latest sample requires values")

    values: dict[str, dict[str, Any]] = {}
    measurements: dict[str, StateMeasurement] = {}
    state_fields: dict[str, Any] = {}
    for quantity, raw in raw_values.items():
        quantity = str(quantity)
        if quantity not in _QUANTITIES:
            raise ValueError(f"unsupported observed-state quantity: {quantity}")
        if isinstance(raw, Mapping):
            value_si = raw.get("value_si")
            sensor_location = raw.get("sensor_location")
            quality = raw.get("quality", sample.get("quality", "valid"))
        else:
            value_si = raw
            sensor_location = None
            quality = sample.get("quality", "valid")
        if quality not in {"valid", "suspect", "missing"}:
            raise ValueError(f"unsupported state quality: {quality}")
        if quality == "missing":
            continue
        number = _finite(value_si, f"{quantity}.value_si")
        if quantity in {"pressure", "temperature"} and number <= 0:
            raise ValueError(f"{quantity} must be positive")
        values[quantity] = {
            "component_id": component_id,
            "quantity": quantity,
            "value_si": number,
            "sensor_location": sensor_location,
            "quality": quality,
        }
        measurements[quantity] = StateMeasurement(
            quantity=quantity,
            value_si=number,
            sensor_location=sensor_location,
            quality=quality,
        )
        if quantity == "pressure":
            state_fields["pressure_pa_abs"] = number
        elif quantity == "temperature":
            state_fields["temperature_k"] = number
        elif quantity == "mass":
            state_fields["mass_kg"] = max(0.0, number)
        elif quantity == "level_fraction":
            state_fields["liquid_fraction"] = min(1.0, max(0.0, number))
    if not values:
        raise ValueError(f"source {source_id} latest sample has no valid state values")

    origin = source.get("origin", "historian_measured")
    snapshot = EquipmentStateSnapshot(
        schema_version="prism.equipment_state_snapshot.v1",
        component_id=component_id,
        captured_at_s=captured_at_s,
        origin=origin,
        measurements=measurements,
        source_digest=source.get("source_sha256"),
        quality=sample.get("quality", "valid"),
        **state_fields,
    )
    frame = {
        "source_id": source_id,
        "component_id": component_id,
        "captured_at_s": captured_at_s,
        "origin": origin,
        "quality": sample.get("quality", "valid"),
        "values": values,
        "state_snapshot": snapshot.to_mapping(),
        "state_snapshot_digest": snapshot.digest(),
        "source_sha256": source.get("source_sha256"),
    }
    frame["frame_digest"] = canonical_digest(frame)
    return frame


def service_state_from_runtime_frame(
    frame: Mapping[str, Any],
    *,
    now_s: float,
    mapping_digest: str | None = None,
) -> dict[str, Any]:
    """Convert one state-only frame to the service resolver input contract.

    ``now_s`` is supplied by the realtime application. It is never inferred
    from the historical sample clock. The returned mapping is deliberately
    the same shape consumed by ``validate_equipment_process_state`` and
    ``request_from_equipment_resolver``; it contains no accident-owned fields.
    """

    if not isinstance(frame, Mapping):
        raise TypeError("runtime frame must be a mapping")
    for key in frame:
        if str(key).lower() in _RUNTIME_FRAME_FORBIDDEN_KEYS:
            raise ValueError(f"runtime frame contains accident-owned field: {key}")
    component_id = str(frame.get("component_id") or "").strip()
    if not component_id:
        raise ValueError("runtime frame requires component_id")
    captured_at_s = _finite(frame.get("captured_at_s"), "captured_at_s")
    now_s = _finite(now_s, "now_s")
    if now_s < captured_at_s:
        raise ValueError("now_s cannot precede runtime frame captured_at_s")
    origin = frame.get("origin")
    if origin not in _ORIGINS:
        raise ValueError(f"unsupported runtime frame origin: {origin}")
    values = frame.get("values")
    if not isinstance(values, Mapping) or not values:
        raise ValueError("runtime frame requires non-empty values")
    frame_digest = frame.get("frame_digest")
    if not isinstance(frame_digest, str) or not frame_digest:
        raise ValueError("runtime frame requires frame_digest")
    expected_frame_digest = canonical_digest({
        str(key): value for key, value in frame.items() if key != "frame_digest"
    })
    if frame_digest != expected_frame_digest:
        raise ValueError("runtime frame_digest does not match frame contents")
    snapshot = frame.get("state_snapshot")
    snapshot_digest = frame.get("state_snapshot_digest")
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot_digest, str):
        raise ValueError("runtime frame requires state_snapshot and state_snapshot_digest")
    if snapshot_digest != canonical_digest(snapshot):
        raise ValueError("runtime state_snapshot_digest does not match snapshot")
    normalized_values: dict[str, dict[str, Any]] = {}
    for tag, row in values.items():
        if not isinstance(tag, str) or not tag:
            raise ValueError("runtime frame value tags must be nonempty strings")
        if not isinstance(row, Mapping):
            raise ValueError(f"runtime frame value is not a mapping: {tag}")
        if str(row.get("component_id")) != component_id:
            raise ValueError(f"runtime frame value component mismatch: {tag}")
        quantity = row.get("quantity")
        if quantity not in _QUANTITIES:
            raise ValueError(f"unsupported runtime-state quantity: {quantity}")
        value_si = _finite(row.get("value_si"), f"{tag}.value_si")
        quality = row.get("quality", "valid")
        if quality != "valid":
            raise ValueError(f"runtime resolver input requires valid quality: {tag}")
        normalized_values[tag] = {
            "component_id": component_id,
            "quantity": quantity,
            "value_si": value_si,
            "sensor_location": row.get("sensor_location"),
            "quality": quality,
        }
    normalized = {
        "values": normalized_values,
        "origin": origin,
        "captured_at_s": captured_at_s,
        "state_snapshot": dict(snapshot),
        "state_snapshot_digest": snapshot_digest,
        "independent_measurement_claim": origin == "historian_measured",
        "data_age_s": now_s - captured_at_s,
        "frame_digest": frame_digest,
        "mapping_digest": mapping_digest or canonical_digest({
            "component_id": component_id,
            "tags": normalized_values,
            "provenance": "runtime-frame-si-values; mapping review remains separate",
        }),
    }
    from .service import validate_equipment_process_state

    return validate_equipment_process_state(normalized)


def request_from_observed_state_runtime_frame(
    template: Any,
    frame: Mapping[str, Any],
    *,
    now_s: float,
    release_resolver: Any,
    mapping_digest: str | None = None,
) -> Any:
    """Pass one runtime state frame through the explicit provider resolver seam.

    The resolver owns the accident release, duration, isolation and inventory
    boundary. This helper only performs frame integrity/state validation and
    delegates to the existing fail-closed service contract.
    """

    normalized = service_state_from_runtime_frame(
        frame,
        now_s=now_s,
        mapping_digest=mapping_digest,
    )
    from .service import request_from_equipment_resolver

    return request_from_equipment_resolver(template, normalized, release_resolver)


def build_observed_state_runtime_frames(
    sources: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Select one latest state frame per source for an explicit runtime handoff."""

    source_rows = _sources(sources)
    # Reuse the strict state-only validator before selecting a frame.  This
    # rejects accident-owned keys and malformed quantities consistently with
    # the evidence audit.
    evidence = build_observed_state_evidence(source_rows)
    frames = [_frame_from_source(source) for source in source_rows]
    component_ids = [frame["component_id"] for frame in frames]
    if len(set(component_ids)) != len(component_ids):
        raise ValueError("runtime frames require one source per component_id")
    return {
        "schema_version": SCHEMA,
        "status": "STATE_RUNTIME_FRAMES_READY",
        "source_count": len(frames),
        "frame_count": len(frames),
        "frames": frames,
        "evidence_sample_count": evidence["sample_count"],
        "selection": {
            "method": "latest_sample_by_captured_at_s_then_source_order",
            "one_frame_per_source": True,
        },
        "runtime_handoff_contract": {
            "schema": "prism.equipment_process_state.v1",
            "state_adapter": "service_state_from_runtime_frame",
            "resolver_adapter": "request_from_observed_state_runtime_frame",
            "monitor_method": "RealtimeConsequenceMonitor.update_from_runtime_frame",
            "facility_monitor_method": "FacilityRealtimeConsequenceMonitor.update_from_runtime_frames",
            "runtime_clock": "caller_supplied_now_s",
            "provider_release_required_for_consequence": True,
            "frequency_assignment": "rejected_by_request_from_equipment_resolver",
            "termination_and_inventory_owner": "equipment_provider",
        },
        "policy": {
            "state_only": True,
            "release_scenario_generated": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "provider_release_required_for_consequence": True,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Latest observed state frames are ready for an explicit normal-model or "
            "provider-resolver input. They do not create a release, frequency, or QRA result."
        ),
    }


__all__ = [
    "SCHEMA",
    "build_observed_state_runtime_frames",
    "service_state_from_runtime_frame",
    "request_from_observed_state_runtime_frame",
]
