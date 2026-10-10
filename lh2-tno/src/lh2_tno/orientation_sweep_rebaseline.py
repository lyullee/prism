"""Rebind a coordinate-orientation diagnostic to reverified field evidence.

The orientation sweep is a derived diagnostic, so it can retain useful
metrics after the field manifest is rebaselined.  This adapter only checks
that event and channel digests agree with the new field record and updates the
provenance labels.  It does not refit a bearing or promote the comparison.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "prism.external_field_orientation_sweep.v1"


class OrientationSweepRebaselineError(ValueError):
    """Raised when a sweep cannot be safely rebound."""


def _read(path: str | Path, label: str) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OrientationSweepRebaselineError(f"invalid {label}: {resolved}") from error
    if not isinstance(value, Mapping):
        raise OrientationSweepRebaselineError(f"{label} must be an object")
    return resolved, dict(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _channel_hash(field: Mapping[str, Any], channel: str) -> str | None:
    rows = field.get("channels")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, Mapping) and row.get("channel") == channel:
            value = row.get("observed_sha256")
            return value if isinstance(value, str) else None
    return None


def rebaseline_orientation_sweep(
    sweep_path: str | Path,
    field_evidence_path: str | Path,
    *,
    acknowledged: bool = False,
) -> dict[str, Any]:
    """Rebind ``sweep_path`` to an explicitly reverified field record."""
    if not acknowledged:
        raise OrientationSweepRebaselineError(
            "explicit acknowledgement is required to rebind an orientation sweep"
        )
    sweep_file, sweep = _read(sweep_path, "orientation sweep")
    field_file, field = _read(field_evidence_path, "field evidence")
    if sweep.get("schema_version") != SCHEMA_VERSION:
        raise OrientationSweepRebaselineError("unsupported orientation sweep schema")
    if field.get("schema_version") != "prism.external_field_evidence.v1":
        raise OrientationSweepRebaselineError("unsupported field evidence schema")
    if field.get("status") != "RESTRICTED_EXTERNAL_FIELD_EVIDENCE":
        raise OrientationSweepRebaselineError(
            "field evidence must be hash-reverified before sweep rebaseline"
        )
    if field.get("hash_drift_channels") != []:
        raise OrientationSweepRebaselineError("field evidence still contains hash drift")
    if sweep.get("event_id") != field.get("event_id"):
        raise OrientationSweepRebaselineError("event_id does not match field evidence")
    source_hash = _channel_hash(field, "source_boundary")
    receptor_hash = _channel_hash(field, "receptor_observations")
    if not source_hash or not receptor_hash:
        raise OrientationSweepRebaselineError("field evidence channel hashes are incomplete")
    reports = sweep.get("reports")
    if not isinstance(reports, list) or not reports:
        raise OrientationSweepRebaselineError("orientation sweep reports are missing")
    updated = copy.deepcopy(sweep)
    for index, raw in enumerate(updated["reports"]):
        if not isinstance(raw, Mapping):
            raise OrientationSweepRebaselineError(f"reports[{index}] must be an object")
        row = dict(raw)
        binding = row.get("source_boundary_binding")
        if not isinstance(binding, Mapping):
            raise OrientationSweepRebaselineError(
                f"reports[{index}].source_boundary_binding is missing"
            )
        if binding.get("source_boundary_sha256") != source_hash:
            raise OrientationSweepRebaselineError(
                f"reports[{index}] source boundary hash does not match field evidence"
            )
        if binding.get("receptor_observation_sha256") != receptor_hash:
            raise OrientationSweepRebaselineError(
                f"reports[{index}] receptor hash does not match field evidence"
            )
        if row.get("status") == "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT":
            row["status"] = "RESTRICTED_FIELD_MODEL_COMPARISON"
        row["source_boundary_binding"] = dict(binding)
        updated["reports"][index] = row
    updated["field_evidence_status"] = field.get("status")
    updated["rebaseline"] = {
        "schema_version": "prism.external_field_orientation_sweep_rebaseline.v1",
        "status": "REBOUND_TO_REVERIFIED_FIELD_EVIDENCE",
        "previous_sweep_path": str(sweep_file),
        "previous_sweep_sha256": _sha256(sweep_file),
        "field_evidence_path": str(field_file),
        "field_evidence_sha256": _sha256(field_file),
        "hash_drift_reports_cleared": sum(
            1 for row in reports
            if isinstance(row, Mapping)
            and row.get("status") == "RESTRICTED_FIELD_MODEL_COMPARISON_HASH_DRIFT"
        ),
        "bearing_is_not_fitted": True,
        "independent_reverification": False,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "promotion_allowed": False,
    }
    updated["promotion_policy"] = dict(updated.get("promotion_policy") or {})
    updated["promotion_policy"].update({
        "bearing_is_not_fitted": True,
        "measured_source_replay_is_not_independent_validation": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
    })
    return updated


__all__ = [
    "OrientationSweepRebaselineError",
    "SCHEMA_VERSION",
    "rebaseline_orientation_sweep",
]
