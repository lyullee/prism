"""Compare one outdoor LH2 field observation bundle with model predictions.

This module is a deliberately narrow observation operator.  It joins a
previously verified field bundle to a separately exported PRISM prediction by
event, common clock, receptor geometry, and an explicit transport delay.  It
does not fit the delay, extrapolate outside the prediction horizon, or turn a
measured-source replay into independent physical validation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "prism.external_field_model_comparison.v1"
FIELD_EVIDENCE_SCHEMA = "prism.external_field_evidence.v1"
SUPPORTED_TIME_METHODS = {"exact", "linear"}


class FieldModelComparisonError(ValueError):
    """Raised when a field/model comparison contract is unsafe or malformed."""


def _read_object(value: Mapping[str, Any] | str | Path, label: str) -> tuple[dict[str, Any], Path | None]:
    if isinstance(value, (str, Path)):
        path = Path(value).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FieldModelComparisonError(f"cannot read {label}: {path}") from error
    elif isinstance(value, Mapping):
        payload = dict(value)
        path = None
    else:
        raise FieldModelComparisonError(f"{label} must be a JSON object or path")
    if not isinstance(payload, dict):
        raise FieldModelComparisonError(f"{label} must be a JSON object")
    return payload, path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise FieldModelComparisonError(f"cannot read field channel: {path}") from error
    return digest.hexdigest()


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise FieldModelComparisonError(f"{label} must be numeric") from error
    if not math.isfinite(number):
        raise FieldModelComparisonError(f"{label} must be finite")
    return number


def _channel_path(field: Mapping[str, Any], channel_name: str) -> tuple[Path, dict[str, Any]]:
    rows = field.get("channels")
    if not isinstance(rows, list):
        raise FieldModelComparisonError("field evidence has no channels list")
    for raw in rows:
        if isinstance(raw, Mapping) and raw.get("channel") == channel_name:
            path_value = raw.get("path")
            if not isinstance(path_value, str) or not path_value:
                raise FieldModelComparisonError(f"field channel path is missing: {channel_name}")
            path = Path(path_value).resolve()
            if not path.is_file():
                raise FieldModelComparisonError(f"field channel is missing: {channel_name}: {path}")
            return path, dict(raw)
    raise FieldModelComparisonError(f"field evidence is missing channel: {channel_name}")


def _read_observations(path: Path, event_id: str, expected_clock_id: str | None) -> tuple[list[dict[str, Any]], str, str | None]:
    required = {
        "event_id",
        "receptor_geometry_id",
        "sensor_id",
        "common_clock_id",
        "time_s",
        "x_m",
        "y_m",
        "height_m",
        "observed_vol_pct",
    }
    observations: list[dict[str, Any]] = []
    geometry_ids: set[str] = set()
    clock_ids: set[str] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or ())
            missing = sorted(required - columns)
            if missing:
                raise FieldModelComparisonError(
                    "receptor_observations is missing columns: " + ", ".join(missing)
                )
            for index, row in enumerate(reader, start=2):
                if row.get("event_id") != event_id:
                    raise FieldModelComparisonError(
                        f"receptor row {index} event_id does not match field evidence"
                    )
                geometry_id = str(row["receptor_geometry_id"])
                clock_id = str(row["common_clock_id"])
                if not geometry_id or not clock_id:
                    raise FieldModelComparisonError(f"receptor row {index} has blank geometry/clock id")
                geometry_ids.add(geometry_id)
                clock_ids.add(clock_id)
                observations.append({
                    "event_id": event_id,
                    "receptor_geometry_id": geometry_id,
                    "sensor_id": str(row["sensor_id"]),
                    "common_clock_id": clock_id,
                    "time_s": _finite(row["time_s"], f"receptor row {index} time_s"),
                    "position_enu_m": [
                        _finite(row["x_m"], f"receptor row {index} x_m"),
                        _finite(row["y_m"], f"receptor row {index} y_m"),
                        _finite(row["height_m"], f"receptor row {index} height_m"),
                    ],
                    "observed_vol_pct": _finite(
                        row["observed_vol_pct"], f"receptor row {index} observed_vol_pct"
                    ),
                })
    except OSError as error:
        raise FieldModelComparisonError(f"cannot read receptor observations: {path}") from error
    if not observations:
        raise FieldModelComparisonError("receptor_observations has no rows")
    if len(geometry_ids) != 1:
        raise FieldModelComparisonError("receptor_observations must contain one receptor_geometry_id")
    if len(clock_ids) != 1:
        raise FieldModelComparisonError("receptor_observations must contain one common_clock_id")
    clock_id = next(iter(clock_ids))
    if expected_clock_id is not None and clock_id != expected_clock_id:
        raise FieldModelComparisonError("receptor common_clock_id does not match field evidence")
    return observations, next(iter(geometry_ids)), clock_id


def _prediction_receptors(prediction: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_receptors = prediction.get("receptors")
    if not isinstance(raw_receptors, list) or not raw_receptors:
        raise FieldModelComparisonError("model prediction receptors must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_receptors):
        if not isinstance(raw, Mapping):
            raise FieldModelComparisonError(f"model prediction receptor {index} must be an object")
        receptor_id = raw.get("id")
        position = raw.get("position_enu_m")
        history = raw.get("concentration_history")
        if not isinstance(receptor_id, str) or not receptor_id:
            raise FieldModelComparisonError(f"model prediction receptor {index} has invalid id")
        if receptor_id in result:
            raise FieldModelComparisonError(f"duplicate model prediction receptor: {receptor_id}")
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            raise FieldModelComparisonError(f"model prediction receptor {receptor_id} position is invalid")
        position_values = [_finite(value, f"model receptor {receptor_id} position") for value in position]
        if not isinstance(history, list) or not history:
            raise FieldModelComparisonError(
                f"model prediction receptor {receptor_id} concentration_history is empty"
            )
        rows: list[dict[str, float]] = []
        previous_time = -math.inf
        for row_index, raw_row in enumerate(history):
            if not isinstance(raw_row, Mapping):
                raise FieldModelComparisonError(
                    f"model receptor {receptor_id} history row {row_index} must be an object"
                )
            time_s = _finite(raw_row.get("time_s"), f"model receptor {receptor_id} time_s")
            concentration = _finite(
                raw_row.get("h2_volume_percent"),
                f"model receptor {receptor_id} h2_volume_percent",
            )
            if concentration < 0:
                raise FieldModelComparisonError(
                    f"model receptor {receptor_id} h2_volume_percent cannot be negative"
                )
            if time_s <= previous_time:
                raise FieldModelComparisonError(
                    f"model receptor {receptor_id} concentration_history must be strictly ordered"
                )
            previous_time = time_s
            rows.append({"time_s": time_s, "h2_volume_percent": concentration})
        result[receptor_id] = {
            "id": receptor_id,
            "position_enu_m": position_values,
            "concentration_history": rows,
        }
    return result


def _value_at(history: list[dict[str, float]], target_time: float, method: str, tolerance: float) -> float | None:
    if method == "exact":
        nearest = min(history, key=lambda row: abs(row["time_s"] - target_time))
        return nearest["h2_volume_percent"] if abs(nearest["time_s"] - target_time) <= tolerance else None
    if target_time < history[0]["time_s"] - tolerance or target_time > history[-1]["time_s"] + tolerance:
        return None
    for left, right in zip(history, history[1:]):
        if left["time_s"] - tolerance <= target_time <= right["time_s"] + tolerance:
            span = right["time_s"] - left["time_s"]
            if span <= 0:
                return None
            fraction = min(1.0, max(0.0, (target_time - left["time_s"]) / span))
            return left["h2_volume_percent"] + fraction * (
                right["h2_volume_percent"] - left["h2_volume_percent"]
            )
    if abs(target_time - history[-1]["time_s"]) <= tolerance:
        return history[-1]["h2_volume_percent"]
    if abs(target_time - history[0]["time_s"]) <= tolerance:
        return history[0]["h2_volume_percent"]
    return None


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "sample_count": 0,
            "sensor_count": 0,
            "mean_error_vol_pct": None,
            "mae_vol_pct": None,
            "rmse_vol_pct": None,
            "max_abs_error_vol_pct": None,
            "observed_peak_vol_pct": None,
            "predicted_peak_vol_pct": None,
            "peak_bias_vol_pct": None,
        }
    errors = [row["predicted_vol_pct"] - row["observed_vol_pct"] for row in rows]
    observed_peak = max(row["observed_vol_pct"] for row in rows)
    predicted_peak = max(row["predicted_vol_pct"] for row in rows)
    return {
        "sample_count": len(rows),
        "sensor_count": len({row["sensor_id"] for row in rows}),
        "mean_error_vol_pct": sum(errors) / len(errors),
        "mae_vol_pct": sum(abs(error) for error in errors) / len(errors),
        "rmse_vol_pct": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "max_abs_error_vol_pct": max(abs(error) for error in errors),
        "observed_peak_vol_pct": observed_peak,
        "predicted_peak_vol_pct": predicted_peak,
        "peak_bias_vol_pct": predicted_peak - observed_peak,
    }


def build_field_model_comparison_record(
    field_evidence: Mapping[str, Any] | str | Path,
    model_prediction: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Compare verified field observations to an explicit model prediction.

    The returned record is always diagnostic.  Even a numerically complete
    comparison has ``physical_validation_claim=false``; an independent
    provider, a reviewed source boundary, and an IJHE evidence review are
    required before that gate can be opened.
    """
    field, field_path = _read_object(field_evidence, "field evidence")
    prediction, prediction_path = _read_object(model_prediction, "model prediction")
    field_evidence_sha256 = _sha256(field_path) if field_path is not None else None
    model_prediction_sha256 = _sha256(prediction_path) if prediction_path is not None else None
    if field.get("schema_version") != FIELD_EVIDENCE_SCHEMA:
        raise FieldModelComparisonError("field evidence schema_version is unsupported")
    if field.get("status") not in {
        "RESTRICTED_EXTERNAL_FIELD_EVIDENCE",
        "RESTRICTED_EXTERNAL_FIELD_EVIDENCE_HASH_DRIFT",
    }:
        raise FieldModelComparisonError("field evidence is not a restricted observation record")
    if field.get("physical_validation_claim") is True or field.get("facility_qra_claim") is True:
        raise FieldModelComparisonError("field evidence contains a prohibited promotion claim")
    event_id = field.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise FieldModelComparisonError("field evidence event_id is missing")
    if prediction.get("schema_version") != "prism.external_field_model_prediction.v1":
        raise FieldModelComparisonError("model prediction schema_version is unsupported")
    if prediction.get("event_id") != event_id:
        raise FieldModelComparisonError("model prediction event_id does not match field evidence")
    common_clock = field.get("common_clock") if isinstance(field.get("common_clock"), Mapping) else {}
    expected_clock_id = common_clock.get("common_clock_id")
    if not isinstance(expected_clock_id, str) or not expected_clock_id:
        raise FieldModelComparisonError("field evidence common_clock_id is missing")
    if prediction.get("common_clock_id") != expected_clock_id:
        raise FieldModelComparisonError("model prediction common_clock_id does not match field evidence")

    observations_path, source_channel = _channel_path(field, "receptor_observations")
    observations, geometry_id, clock_id = _read_observations(
        observations_path, event_id, expected_clock_id
    )
    if prediction.get("receptor_geometry_id") != geometry_id:
        raise FieldModelComparisonError("model prediction receptor_geometry_id does not match field evidence")
    obstacle_geometry = (
        field.get("obstacle_geometry")
        if isinstance(field.get("obstacle_geometry"), Mapping)
        else {}
    )
    field_coordinate_reference = obstacle_geometry.get("coordinate_reference")
    prediction_coordinate_reference = prediction.get("coordinate_reference")
    if not isinstance(field_coordinate_reference, str) or not field_coordinate_reference:
        raise FieldModelComparisonError("field evidence coordinate_reference is missing")
    if prediction_coordinate_reference != field_coordinate_reference:
        raise FieldModelComparisonError(
            "model prediction coordinate_reference does not match field evidence"
        )
    geometry_tolerance = _finite(
        prediction.get("geometry_tolerance_m"), "model prediction geometry_tolerance_m"
    )
    time_tolerance = _finite(
        prediction.get("time_tolerance_s"), "model prediction time_tolerance_s"
    )
    if geometry_tolerance <= 0 or time_tolerance <= 0:
        raise FieldModelComparisonError("geometry and time tolerances must be positive")
    alignment = prediction.get("time_alignment")
    if not isinstance(alignment, Mapping):
        raise FieldModelComparisonError("model prediction time_alignment is missing")
    method = alignment.get("method")
    if method not in SUPPORTED_TIME_METHODS:
        raise FieldModelComparisonError("time_alignment.method must be exact or linear")
    transport_delay = _finite(alignment.get("transport_delay_s"), "transport_delay_s")
    if transport_delay < 0:
        raise FieldModelComparisonError("transport_delay_s cannot be negative")
    prediction_time_offset = _finite(
        alignment.get("prediction_time_offset_s"),
        "prediction_time_offset_s",
    )
    receptors = _prediction_receptors(prediction)
    sensor_positions: dict[str, list[float]] = {}
    for row in observations:
        sensor_id = row["sensor_id"]
        existing = sensor_positions.setdefault(sensor_id, row["position_enu_m"])
        if any(abs(a - b) > geometry_tolerance for a, b in zip(existing, row["position_enu_m"])):
            raise FieldModelComparisonError(f"sensor {sensor_id} has inconsistent geometry")
    missing = sorted(set(sensor_positions) - set(receptors))
    extra = sorted(set(receptors) - set(sensor_positions))
    if missing or extra:
        raise FieldModelComparisonError(
            f"model receptor set does not match field sensors; missing={missing}, extra={extra}"
        )
    geometry_errors: dict[str, float] = {}
    for sensor_id, position in sensor_positions.items():
        model_position = receptors[sensor_id]["position_enu_m"]
        error = math.sqrt(sum((a - b) ** 2 for a, b in zip(position, model_position)))
        geometry_errors[sensor_id] = error
        if error > geometry_tolerance:
            raise FieldModelComparisonError(
                f"model receptor {sensor_id} is outside geometry tolerance: {error} m"
            )

    matched: list[dict[str, Any]] = []
    unmatched = 0
    for row in observations:
        target_time = row["time_s"] - transport_delay - prediction_time_offset
        predicted = _value_at(
            receptors[row["sensor_id"]]["concentration_history"],
            target_time,
            method,
            time_tolerance,
        )
        if predicted is None:
            unmatched += 1
            continue
        matched.append({
            "sensor_id": row["sensor_id"],
            "observed_time_s": row["time_s"],
            "prediction_time_s": target_time,
            "observed_vol_pct": row["observed_vol_pct"],
            "predicted_vol_pct": predicted,
            "error_vol_pct": predicted - row["observed_vol_pct"],
        })
    source_mode = prediction.get("source_boundary_binding")
    if not isinstance(source_mode, Mapping):
        raise FieldModelComparisonError("source_boundary_binding is missing")
    mode = source_mode.get("mode")
    if mode not in {"independent_model", "measured_source_replay"}:
        raise FieldModelComparisonError(
            "source_boundary_binding.mode must be independent_model or measured_source_replay"
        )
    declared_source_hash = source_mode.get("receptor_source_channel_sha256")
    actual_source_hash = source_channel.get("observed_sha256")
    if not isinstance(actual_source_hash, str) or len(actual_source_hash) != 64:
        actual_source_hash = _sha256(observations_path)
    if declared_source_hash != actual_source_hash:
        raise FieldModelComparisonError(
            "model prediction receptor_source_channel_sha256 does not match observations"
        )
    source_binding_declared = source_mode.get("source_boundary_sha256")
    if not isinstance(source_binding_declared, str) or len(source_binding_declared) != 64:
        raise FieldModelComparisonError("source_boundary_binding.source_boundary_sha256 is invalid")
    provider_verified = source_mode.get("provider_release_contract_verified") is True
    field_source_hash = field.get("source_boundary_sha256")
    source_boundary_hash_matches = source_binding_declared == field_source_hash
    hash_drift = (
        field.get("status") == "RESTRICTED_EXTERNAL_FIELD_EVIDENCE_HASH_DRIFT"
        or not source_boundary_hash_matches
    )
    metrics = _metrics(matched)
    per_sensor = {
        sensor_id: _metrics([row for row in matched if row["sensor_id"] == sensor_id])
        for sensor_id in sorted(sensor_positions)
    }
    status = (
        "BLOCKED_NO_MATCHED_SAMPLES"
        if not matched
        else "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT"
        if hash_drift
        else "RESTRICTED_FIELD_MODEL_COMPARISON"
    )
    review_eligible = bool(
        matched
        and not hash_drift
        and mode == "independent_model"
        and provider_verified
        and source_binding_declared == field.get("source_boundary_sha256")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "event_id": event_id,
        "dataset_id": field.get("dataset_id"),
        "common_clock_id": clock_id,
        "receptor_geometry_id": geometry_id,
        "coordinate_reference": field_coordinate_reference,
        "field_evidence_status": field.get("status"),
        "field_evidence_path": str(field_path) if field_path else None,
        "field_evidence_sha256": field_evidence_sha256,
        "model_prediction_path": str(prediction_path) if prediction_path else None,
        "model_prediction_sha256": model_prediction_sha256,
        "source_boundary_binding": {
            "mode": mode,
            "source_boundary_sha256": source_binding_declared,
            "field_source_boundary_sha256": field_source_hash,
            "source_boundary_hash_matches": source_boundary_hash_matches,
            "receptor_observation_sha256": actual_source_hash,
            "receptor_source_channel_sha256_declared": declared_source_hash,
            "provider_release_contract_verified": provider_verified,
        },
        "time_alignment": {
            "method": method,
            "transport_delay_s": transport_delay,
            "prediction_time_offset_s": prediction_time_offset,
            "time_tolerance_s": time_tolerance,
        },
        "geometry": {
            "tolerance_m": geometry_tolerance,
            "sensor_count": len(sensor_positions),
            "maximum_position_error_m": max(geometry_errors.values()) if geometry_errors else None,
            "position_error_m": geometry_errors,
        },
        "matching": {
            "observed_row_count": len(observations),
            "matched_row_count": len(matched),
            "unmatched_row_count": unmatched,
            "matched_fraction": len(matched) / len(observations),
        },
        "metrics": metrics,
        "per_sensor_metrics": per_sensor,
        "matched_samples": matched,
        "independent_physical_validation_review_eligible": review_eligible,
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "field_observations_are_not_frequency": True,
            "measured_source_replay_is_not_independent_validation": True,
            "transport_delay_is_declared_not_fitted": True,
            "no_extrapolation_outside_prediction_horizon": True,
            "physical_validation_requires_external_review": True,
            "component_comparison_does_not_validate_facility_qra": True,
        },
    }


__all__ = [
    "FieldModelComparisonError",
    "SCHEMA_VERSION",
    "build_field_model_comparison_record",
]
