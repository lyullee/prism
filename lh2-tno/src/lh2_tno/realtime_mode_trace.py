"""Fail-closed audit for HAZOP operating-mode identity in realtime results.

The audit checks metadata already produced by the realtime monitor.  It does
not infer a mode from sensor values and it does not create a release, a
frequency, or a facility-risk result.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mode(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _row(
    component_id: str,
    telemetry_boundary: Mapping[str, Any],
    release_path: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    telemetry_mode = _mode(telemetry_boundary.get("operating_mode"))
    release_mode = _mode(release_path.get("operating_mode"))
    if telemetry_mode is None:
        reasons.append(f"{component_id}: telemetry_boundary.operating_mode is missing")
    if release_mode is None:
        reasons.append(f"{component_id}: equipment_release_path.operating_mode is missing")
    if telemetry_mode is not None and release_mode is not None and telemetry_mode != release_mode:
        reasons.append(f"{component_id}: telemetry and release-path operating modes differ")
    selected = telemetry_mode or release_mode
    return (
        {
            "component_id": component_id,
            "operating_mode": selected,
            "telemetry_operating_mode": telemetry_mode,
            "release_path_operating_mode": release_mode,
            "mode_match": telemetry_mode is not None
            and telemetry_mode == release_mode,
        },
        reasons,
    )


def audit_realtime_hazop_mode_trace(result: Mapping[str, Any]) -> dict[str, Any]:
    """Audit one monitor result or one facility realtime batch result.

    A facility batch must expose the same mode in each accepted component's
    telemetry boundary and release path, and its aggregate mode counts must
    exactly match the accepted component rows.  The returned record is
    diagnostic evidence only.
    """
    if not isinstance(result, Mapping):
        raise TypeError("realtime result must be a mapping")
    rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    components = result.get("components")
    if isinstance(components, Mapping):
        for component_id, entry in sorted(components.items(), key=lambda item: str(item[0])):
            if not isinstance(entry, Mapping):
                reasons.append(f"{component_id}: component result is not a mapping")
                continue
            if entry.get("status") != "ACCEPTED":
                reasons.append(f"{component_id}: component result is not accepted")
                continue
            nested = entry.get("result")
            telemetry = nested.get("telemetry_boundary") if isinstance(nested, Mapping) else None
            path = entry.get("equipment_release_path")
            if not isinstance(telemetry, Mapping) or not isinstance(path, Mapping):
                reasons.append(f"{component_id}: realtime telemetry or release path is missing")
                continue
            row, row_reasons = _row(str(component_id), telemetry, path)
            rows.append(row)
            reasons.extend(row_reasons)
    else:
        telemetry = result.get("telemetry_boundary")
        path = result.get("equipment_release_path")
        component_id = str(result.get("component_id") or "realtime-component")
        if not isinstance(telemetry, Mapping) or not isinstance(path, Mapping):
            reasons.append("single realtime result lacks telemetry boundary or release path")
        else:
            row, row_reasons = _row(component_id, telemetry, path)
            rows.append(row)
            reasons.extend(row_reasons)

    expected_counts: dict[str, int] = {}
    for row in rows:
        mode = row.get("operating_mode")
        if isinstance(mode, str) and mode:
            expected_counts[mode] = expected_counts.get(mode, 0) + 1

    batch_accounting: Mapping[str, Any] | None = None
    aggregate = result.get("aggregate")
    if isinstance(aggregate, Mapping):
        candidate = aggregate.get("equipment_release_path_accounting")
        if isinstance(candidate, Mapping):
            batch_accounting = candidate
            actual_counts = candidate.get("operating_mode_counts")
            if not isinstance(actual_counts, Mapping):
                reasons.append("facility batch lacks operating_mode_counts")
            elif any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in actual_counts.values()
            ):
                reasons.append("facility batch operating_mode_counts contain non-integer values")
            elif {
                str(key): int(value) for key, value in actual_counts.items()
            } != expected_counts:
                reasons.append(
                    "facility batch operating_mode_counts do not match component rows"
                )
            component_rows = candidate.get("component_rows")
            if not isinstance(component_rows, Mapping):
                reasons.append("facility batch lacks release-path component rows")
            else:
                for row in rows:
                    component_row = component_rows.get(row["component_id"])
                    if not isinstance(component_row, Mapping) or _mode(component_row.get("operating_mode")) != row["operating_mode"]:
                        reasons.append(
                            f"{row['component_id']}: facility component row mode does not match realtime result"
                        )

    valid = bool(rows) and not reasons
    return {
        "schema_version": "prism.realtime_hazop_mode_trace_audit.v1",
        "status": "REALTIME_HAZOP_MODE_TRACE_VERIFIED" if valid else "REALTIME_HAZOP_MODE_TRACE_BLOCKED",
        "diagnostic_only": True,
        "rows": rows,
        "row_count": len(rows),
        "facility_batch_accounting_present": batch_accounting is not None,
        "operating_mode_counts": expected_counts,
        "blocking_reasons": reasons,
        "policy": {
            "mode_is_identity_metadata": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "release_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
    }
