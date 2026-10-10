"""Join available LH2 validation inputs without promoting unsafe claims.

The inspection-centre workbooks and the external equipment-validation ledger
answer different questions.  The workbooks show that process-state samples are
available; the external ledger records whether an independent accident-release
comparison has actually been released.  This module joins their bookkeeping
only.  It never converts normal-operation rows into a release packet, an
initiating frequency, or a facility-QRA result.
"""
from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


AUDIT_SCHEMA = "prism.validation_intake_audit.v1"
INSPECTION_SCHEMA = "prism.inspection_center_timeseries_audit.v1"
EQUIPMENT_SCHEMA = "prism.equipment_validation_audit.v1"
UNIT_MAP_SCHEMA = "prism.observed_state_input_manifest.v1"


class ValidationIntakeAuditError(ValueError):
    """Raised when an intake evidence ledger is malformed."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationIntakeAuditError(f"{label} must be an object")
    return value


def _load(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise ValidationIntakeAuditError(f"evidence file is missing: {resolved}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationIntakeAuditError(f"invalid evidence JSON: {resolved}") from error
    return dict(_mapping(value, str(resolved)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unit_map_summary(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    """Summarize an explicit state-unit manifest without treating it as reviewed."""
    if manifest is None:
        return {
            "supplied": False,
            "schema_version": None,
            "status": "NOT_SUPPLIED",
            "source_count": 0,
            "complete_source_count": 0,
            "declared_signal_count": 0,
            "unit_counts": {},
            "independent_review_required": True,
        }
    if manifest.get("schema_version") != UNIT_MAP_SCHEMA:
        raise ValidationIntakeAuditError(
            f"unsupported unit-map manifest schema: {manifest.get('schema_version')!r}"
        )
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValidationIntakeAuditError("unit-map manifest sources must be a list")
    unit_counts: dict[str, int] = defaultdict(int)
    complete_source_count = 0
    declared_signal_count = 0
    for index, source in enumerate(sources):
        source_map = _mapping(source, f"unit-map manifest sources[{index}]")
        signals = source_map.get("signals")
        if not isinstance(signals, Mapping):
            raise ValidationIntakeAuditError(
                f"unit-map manifest sources[{index}].signals must be an object"
            )
        complete = True
        for signal_name, raw in signals.items():
            signal = _mapping(raw, f"unit-map manifest signal {signal_name}")
            unit = signal.get("unit")
            if not isinstance(unit, str) or not unit.strip():
                complete = False
                continue
            declared_signal_count += 1
            unit_counts[unit.strip()] += 1
        if complete and signals:
            complete_source_count += 1
    return {
        "supplied": True,
        "schema_version": manifest.get("schema_version"),
        "status": "DECLARED_UNIT_MAP_NOT_INDEPENDENTLY_REVIEWED",
        "source_count": len(sources),
        "complete_source_count": complete_source_count,
        "declared_signal_count": declared_signal_count,
        "unit_counts": dict(sorted(unit_counts.items())),
        "independent_review_required": True,
    }


def _group_summary(files: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "workbook_count": 0,
            "sheet_count": 0,
            "row_count": 0,
            "nonempty_row_count": 0,
            "numeric_candidate_column_count": 0,
            "unit_unconfirmed_numeric_column_count": 0,
            "files": [],
        }
    )
    for workbook in files:
        group = str(workbook.get("scenario_group") or "unclassified")
        target = groups[group]
        target["workbook_count"] += 1
        target["sheet_count"] += int(workbook.get("sheet_count") or 0)
        relative_path = workbook.get("relative_path")
        if isinstance(relative_path, str):
            target["files"].append(relative_path)
        for sheet in workbook.get("sheets", []):
            if not isinstance(sheet, Mapping):
                continue
            target["row_count"] += int(sheet.get("row_count") or 0)
            target["nonempty_row_count"] += int(sheet.get("nonempty_row_count") or 0)
            target["numeric_candidate_column_count"] += int(
                sheet.get("numeric_candidate_column_count") or 0
            )
            target["unit_unconfirmed_numeric_column_count"] += int(
                sheet.get("unit_unconfirmed_numeric_column_count") or 0
            )
    return {key: groups[key] for key in sorted(groups)}


def _equipment_summary(equipment: Mapping[str, Any] | None) -> dict[str, Any]:
    if equipment is None:
        return {
            "available": False,
            "schema_version": None,
            "status": "NOT_SUPPLIED",
            "released_scenario_count": None,
            "simulator_invocation_count": None,
            "official_score": None,
            "official_score_status": None,
            "center_binding_ready": None,
            "forward_comparison_allowed": None,
        }
    if equipment.get("schema_version") != EQUIPMENT_SCHEMA:
        raise ValidationIntakeAuditError(
            f"unsupported equipment validation schema: {equipment.get('schema_version')!r}"
        )
    independent = _mapping(equipment.get("independent_validation", {}), "equipment independent_validation")
    summary = _mapping(independent.get("summary", {}), "equipment independent_validation.summary")
    topology = equipment.get("topology")
    topology_map = topology if isinstance(topology, Mapping) else {}
    return {
        "available": True,
        "schema_version": equipment.get("schema_version"),
        "status": equipment.get("status"),
        "released_scenario_count": summary.get("released_scenario_count"),
        "simulator_invocation_count": summary.get("simulator_invocation_count"),
        "official_score": summary.get("official_score"),
        "official_score_status": summary.get("official_score_status"),
        "center_binding_ready": topology_map.get("center_binding_ready"),
        "forward_comparison_allowed": topology_map.get("forward_comparison_allowed"),
        "physical_validation_claim": equipment.get("physical_validation_claim"),
        "accident_release_validation_claim": equipment.get("accident_release_validation_claim"),
    }


def audit_validation_intake(
    inspection_timeseries_audit: Mapping[str, Any],
    equipment_validation_audit: Mapping[str, Any] | None = None,
    unit_map_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a fail-closed inventory of available validation inputs."""

    inspection = _mapping(inspection_timeseries_audit, "inspection timeseries audit")
    if inspection.get("schema_version") != INSPECTION_SCHEMA:
        raise ValidationIntakeAuditError(
            f"unsupported inspection audit schema: {inspection.get('schema_version')!r}"
        )
    files = inspection.get("files", [])
    if not isinstance(files, list):
        raise ValidationIntakeAuditError("inspection audit files must be a list")
    file_maps = [_mapping(item, f"inspection files[{index}]") for index, item in enumerate(files)]
    groups = _group_summary(file_maps)
    aggregate = _mapping(inspection.get("aggregate", {}), "inspection aggregate")
    equipment = _equipment_summary(equipment_validation_audit)
    unit_map = _unit_map_summary(unit_map_manifest)

    inspection_errors = int(aggregate.get("workbook_or_sheet_error_count") or 0)
    unit_map_confirmed = aggregate.get("reviewed_unit_map_supplied") is True
    released = equipment.get("released_scenario_count")
    release_gate_closed = equipment.get("available") is True and released == 0
    blockers = [
        "inspection_unit_basis_unconfirmed" if not unit_map_confirmed else None,
        "inspection_unit_map_declared_not_independently_reviewed"
        if unit_map.get("supplied")
        else None,
        "inspection_workbook_or_sheet_errors" if inspection_errors else None,
        "normal_operation_rows_have_no_accidental_release_boundary",
        "exact_asset_port_tag_crosswalk_not_released",
        "independent_accident_release_scenarios_not_released" if release_gate_closed else None,
        "sensor_frequency_learning_is_prohibited",
    ]
    blockers = [item for item in blockers if item is not None]
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": "SCREENED_NO_PROMOTION",
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "inputs": {
            "inspection_timeseries": {
                "schema_version": inspection.get("schema_version"),
                "status": inspection.get("status"),
                "source_file_count": inspection.get("source_file_count"),
                "aggregate": dict(aggregate),
            },
            "equipment_validation": equipment,
            "unit_map_manifest": unit_map,
        },
        "scenario_groups": groups,
        "promotion_gates": {
            "inspection_audit_read_complete": inspection_errors == 0,
            "reviewed_unit_map_supplied": unit_map_confirmed,
            "state_snapshot_binding_allowed": False,
            "accidental_release_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "blocking_reasons": blockers,
        "required_next_evidence": [
            "reviewed exact tag-to-unit and pressure-basis map",
            "calibration, quality, missing-data, and timestamp-latency record",
            "asset and P&ID port crosswalk for the target general LH2 facility",
            "provider release packet with opening, termination, isolation, and mass-balance evidence",
            "independent holdout comparison that explicitly releases raw historian/DCS/PLC evidence",
        ],
        "policy": {
            "normal_process_time_series_is_state_evidence_only": True,
            "normal_process_time_series_is_not_accident_frequency": True,
            "normal_process_time_series_is_not_a_release_packet": True,
            "no_sensor_inverse_leak_inference": True,
        },
    }


def audit_validation_intake_files(
    inspection_timeseries_audit_path: str | Path,
    equipment_validation_audit_path: str | Path | None = None,
    unit_map_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    inspection = _load(inspection_timeseries_audit_path)
    equipment = _load(equipment_validation_audit_path) if equipment_validation_audit_path else None
    unit_map = _load(unit_map_manifest_path) if unit_map_manifest_path else None
    report = audit_validation_intake(inspection, equipment, unit_map)
    if unit_map_manifest_path is not None:
        path = Path(unit_map_manifest_path).resolve()
        report["inputs"]["unit_map_manifest"]["path"] = str(path)
        report["inputs"]["unit_map_manifest"]["sha256"] = _sha256(path)
    return report


__all__ = [
    "AUDIT_SCHEMA",
    "UNIT_MAP_SCHEMA",
    "ValidationIntakeAuditError",
    "audit_validation_intake",
    "audit_validation_intake_files",
]
