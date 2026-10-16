"""Verify a restricted, machine-readable outdoor LH2 field-evidence bundle.

The bundle is an observation package, not a provider release packet.  This
module verifies the file identities and common event clock so a later model
comparison can consume the same evidence without copying raw field data into
PRISM.  It deliberately keeps accident qualification, frequency, ignition,
and facility-QRA promotion closed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "prism.external_field_evidence.v1"
REQUIRED_CHANNELS = (
    "source_boundary",
    "weather",
    "obstacle_geometry",
    "receptor_observations",
    "common_clock",
)


class ExternalFieldEvidenceError(ValueError):
    """Raised when a field-evidence bundle cannot be verified safely."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ExternalFieldEvidenceError(f"{label} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExternalFieldEvidenceError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ExternalFieldEvidenceError(f"{label} must be a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ExternalFieldEvidenceError(f"cannot read evidence file: {path}") from error
    return digest.hexdigest()


def _manifest_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    schema = payload.get("schema")
    if schema == "degali.field-evidence-manifest-execution.v1":
        nested = payload.get("field_evidence_manifest")
        if not isinstance(nested, Mapping):
            raise ExternalFieldEvidenceError(
                "execution wrapper has no field_evidence_manifest object"
            )
        return dict(nested)
    if schema == "degali.field-evidence-manifest.v1":
        return dict(payload)
    raise ExternalFieldEvidenceError(
        "unsupported field-evidence manifest schema; expected a DEGALI manifest"
    )


def _channel_artifacts(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = manifest.get("channel_artifacts")
    if not isinstance(rows, list):
        raise ExternalFieldEvidenceError("field manifest channel_artifacts must be a list")
    channels: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ExternalFieldEvidenceError(f"channel_artifacts[{index}] must be an object")
        channel = raw.get("channel")
        path = raw.get("path")
        sha256 = raw.get("sha256")
        if not isinstance(channel, str) or not channel:
            raise ExternalFieldEvidenceError(f"channel_artifacts[{index}].channel is invalid")
        if channel in channels:
            raise ExternalFieldEvidenceError(f"duplicate field-evidence channel: {channel}")
        if not isinstance(path, str) or not path:
            raise ExternalFieldEvidenceError(f"channel_artifacts[{index}].path is invalid")
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ExternalFieldEvidenceError(f"channel_artifacts[{index}].sha256 is invalid")
        channels[channel] = {"channel": channel, "path": path, "sha256": sha256}
    missing = sorted(set(REQUIRED_CHANNELS) - set(channels))
    if missing:
        raise ExternalFieldEvidenceError(
            "field manifest is missing required channels: " + ", ".join(missing)
        )
    return channels


def _csv_summary(path: Path, *, required_columns: tuple[str, ...], label: str) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = tuple(reader.fieldnames or ())
            missing = sorted(set(required_columns) - set(fieldnames))
            if missing:
                raise ExternalFieldEvidenceError(
                    f"{label} is missing columns: {', '.join(missing)}"
                )
            row_count = 0
            event_ids: set[str] = set()
            for row in reader:
                row_count += 1
                event_id = row.get("event_id")
                if isinstance(event_id, str) and event_id:
                    event_ids.add(event_id)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        if isinstance(error, ExternalFieldEvidenceError):
            raise
        raise ExternalFieldEvidenceError(f"cannot parse {label}: {path}") from error
    if row_count == 0:
        raise ExternalFieldEvidenceError(f"{label} has no data rows: {path}")
    return {
        "row_count": row_count,
        "column_count": len(fieldnames),
        "columns": list(fieldnames),
        "event_ids": sorted(event_ids),
    }


def _source_boundary_observation(path: Path) -> dict[str, Any]:
    """Summarize an observed source clock without turning it into a packet.

    The left-held integral is an observation operator between recorded samples;
    it is not a provider termination or an inventory balance.  A final sample
    is therefore not extended beyond the observed clock window.
    """
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            if "time_s" not in fields or "mass_flow_kg_s" not in fields:
                return {
                    "available": False,
                    "reason": "source_boundary has no explicit time_s and mass_flow_kg_s columns",
                    "termination_evidence_present": False,
                }
            samples: list[tuple[float, float]] = []
            for row_number, row in enumerate(reader, start=2):
                try:
                    time_s = float(row.get("time_s"))
                    mass_flow = float(row.get("mass_flow_kg_s"))
                except (TypeError, ValueError) as error:
                    raise ExternalFieldEvidenceError(
                        f"source_boundary row {row_number} has non-numeric time_s or mass_flow_kg_s"
                    ) from error
                if not math.isfinite(time_s) or not math.isfinite(mass_flow):
                    raise ExternalFieldEvidenceError(
                        f"source_boundary row {row_number} has non-finite time or mass flow"
                    )
                if time_s < 0.0 or mass_flow < 0.0:
                    raise ExternalFieldEvidenceError(
                        f"source_boundary row {row_number} requires non-negative time and mass flow"
                    )
                samples.append((time_s, mass_flow))
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise ExternalFieldEvidenceError(f"cannot parse source_boundary observations: {path}") from error
    if not samples:
        raise ExternalFieldEvidenceError(f"source_boundary has no time-series rows: {path}")
    if any(right[0] <= left[0] for left, right in zip(samples, samples[1:])):
        raise ExternalFieldEvidenceError("source_boundary time_s must be strictly increasing")
    start_s = samples[0][0]
    end_s = samples[-1][0]
    positive = [time_s for time_s, flow in samples if flow > 0.0]
    left_held_mass = sum(flow * (right_time - time_s) for (time_s, flow), (right_time, _) in zip(samples, samples[1:]))
    return {
        "available": True,
        "sample_count": len(samples),
        "observed_window_start_s": start_s,
        "observed_window_end_s": end_s,
        "observed_window_duration_s": end_s - start_s,
        "positive_flow_start_s": min(positive) if positive else None,
        "positive_flow_end_s": max(positive) if positive else None,
        "positive_flow_sample_count": len(positive),
        "integrated_mass_left_hold_kg": left_held_mass,
        "observation_operator": "left_held_between_observed_timestamps_no_final_extension",
        "termination_evidence_present": False,
        "inventory_balance_evidence_present": False,
        "isolation_evidence_present": False,
    }


def build_external_field_evidence_record(
    manifest_path: str | Path,
    *,
    verify_hashes: bool = True,
) -> dict[str, Any]:
    """Verify one external outdoor LH2 observation bundle.

    The returned record is intentionally ``RESTRICTED_EXTERNAL_FIELD_EVIDENCE``.
    It can support a later source-to-dispersion comparison, but it never
    creates an accident frequency, provider release packet, ignition result,
    or facility IR/F-N claim from observations.
    """
    manifest_file = Path(manifest_path).resolve()
    wrapper = _read_json(manifest_file, "field-evidence manifest")
    manifest = _manifest_payload(wrapper)
    readiness = manifest.get("evidence_readiness")
    if not isinstance(readiness, Mapping) or readiness.get("status") != "accepted":
        raise ExternalFieldEvidenceError(
            "field-evidence manifest is not accepted by its source audit"
        )
    if readiness.get("promotion_allowed") is not False or manifest.get("promotion_allowed") is not False:
        raise ExternalFieldEvidenceError(
            "field-evidence manifest must explicitly keep promotion_allowed=false"
        )
    if manifest.get("scope") != "lh2_free_field":
        raise ExternalFieldEvidenceError(
            "only an outdoor lh2_free_field bundle is accepted by this adapter"
        )

    channels = _channel_artifacts(manifest)
    verified_channels: list[dict[str, Any]] = []
    for channel in REQUIRED_CHANNELS:
        row = channels[channel]
        path = Path(str(row["path"])).resolve()
        if not path.is_file():
            raise ExternalFieldEvidenceError(
                f"field-evidence channel file is missing: {channel}: {path}"
            )
        actual_hash = _sha256(path)
        hash_matches = actual_hash == row["sha256"]
        if verify_hashes and not hash_matches:
            raise ExternalFieldEvidenceError(
                f"field-evidence hash mismatch for {channel}: {path}"
            )
        verified_channels.append(
            {
                "channel": channel,
                "path": str(path),
                "declared_sha256": row["sha256"],
                "observed_sha256": actual_hash,
                "hash_verified": hash_matches,
            }
        )

    source = _csv_summary(
        Path(channels["source_boundary"]["path"]).resolve(),
        required_columns=("event_id", "mass_flow_kg_s", "phase", "release_height_m"),
        label="source_boundary",
    )
    source_observation = _source_boundary_observation(
        Path(channels["source_boundary"]["path"]).resolve()
    )
    weather = _csv_summary(
        Path(channels["weather"]["path"]).resolve(),
        required_columns=("event_id", "wind_speed_m_s", "wind_direction"),
        label="weather",
    )
    receptors = _csv_summary(
        Path(channels["receptor_observations"]["path"]).resolve(),
        required_columns=("event_id", "sensor_id", "time_s", "observed_vol_pct"),
        label="receptor_observations",
    )
    obstacle = _read_json(
        Path(channels["obstacle_geometry"]["path"]).resolve(),
        "obstacle_geometry",
    )
    clock = _read_json(
        Path(channels["common_clock"]["path"]).resolve(),
        "common_clock",
    )
    event_id = manifest.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise ExternalFieldEvidenceError("field manifest event_id is missing")
    for label, summary in (("source_boundary", source), ("weather", weather), ("receptor_observations", receptors)):
        if summary["event_ids"] != [event_id]:
            raise ExternalFieldEvidenceError(
                f"{label} event identity does not match manifest event_id"
            )
    if obstacle.get("event_id") != event_id or clock.get("event_id") != event_id:
        raise ExternalFieldEvidenceError(
            "obstacle_geometry/common_clock event identity does not match manifest"
        )

    hash_drift_channels = [
        row["channel"] for row in verified_channels if not row["hash_verified"]
    ]
    observed_hashes = {
        row["channel"]: row["observed_sha256"] for row in verified_channels
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "RESTRICTED_EXTERNAL_FIELD_EVIDENCE"
            if not hash_drift_channels
            else "RESTRICTED_EXTERNAL_FIELD_EVIDENCE_HASH_DRIFT"
        ),
        "event_id": event_id,
        "dataset_id": manifest.get("dataset_id"),
        "scope": "lh2_free_field",
        "channels": verified_channels,
        "source_boundary": {**source, "observed_source_term": source_observation},
        "weather": weather,
        "receptor_observations": receptors,
        "obstacle_geometry": {
            "obstacles_present": obstacle.get("obstacles_present"),
            "coordinate_reference": obstacle.get("coordinate_reference"),
            "promotion_status": obstacle.get("promotion_status"),
        },
        "common_clock": {
            "common_clock_id": clock.get("common_clock_id"),
            "event_clock_origin": clock.get("event_clock_origin"),
            "source_window": clock.get("source_window"),
            "xensor_window": clock.get("xensor_window"),
            "synchronization_method": clock.get("synchronization_method"),
        },
        "model_comparison_ready": False,
        "hash_verification_enforced": verify_hashes,
        "hash_drift_channels": hash_drift_channels,
        "source_boundary_sha256": observed_hashes["source_boundary"],
        "weather_sha256": observed_hashes["weather"],
        "receptor_observation_sha256": observed_hashes["receptor_observations"],
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "observed_source_is_not_provider_release": True,
            "observed_data_is_not_frequency": True,
            "matched_model_prediction_required_for_validation": True,
            "component_evidence_does_not_validate_facility_qra": True,
        },
        "source_manifest": {
            "path": str(manifest_file),
            "sha256": _sha256(manifest_file),
            "source_schema": wrapper.get("schema"),
        },
    }


__all__ = [
    "ExternalFieldEvidenceError",
    "REQUIRED_CHANNELS",
    "SCHEMA_VERSION",
    "build_external_field_evidence_record",
]
