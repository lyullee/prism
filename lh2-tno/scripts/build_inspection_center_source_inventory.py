"""Build a conservative suitability record for inspection-centre source data.

The inspection-centre files contain useful timestamped process signals, but
their presence must not be confused with an accident-release experiment or a
failure-frequency data set.  This script joins the existing source audit and
the separate reconstructed-state evidence into one machine-readable boundary
record.  It deliberately never creates a release packet, estimates a leak
frequency, or promotes facility QRA evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "prism.inspection_center_source_inventory_suitability.v1"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def build_record(
    *,
    timeseries_audit: dict[str, Any],
    timeseries_path: Path,
    reviewed_unit_evidence: dict[str, Any] | None,
    reviewed_unit_path: Path | None,
    reconstructed_state_evidence: dict[str, Any] | None,
    reconstructed_state_path: Path | None,
) -> dict[str, Any]:
    aggregate = timeseries_audit.get("aggregate", {})
    raw_gates = timeseries_audit.get("promotion_gates", {})
    reviewed_gates = (reviewed_unit_evidence or {}).get("promotion_gates", {})

    source_file_count = timeseries_audit.get("source_file_count", aggregate.get("workbook_count", 0))
    workbook_count = aggregate.get("workbook_count", source_file_count)
    sheet_count = aggregate.get("sheet_count", 0)
    unit_status = aggregate.get("numeric_signal_unit_status_count", {})
    signal_categories = aggregate.get("signal_category_count", {})

    references: dict[str, Any] = {
        "timeseries_audit": {
            "path": timeseries_path.as_posix(),
            "sha256": sha256_file(timeseries_path),
            "schema": timeseries_audit.get("schema_version"),
            "status": timeseries_audit.get("status"),
        }
    }
    if reviewed_unit_evidence is not None and reviewed_unit_path is not None:
        references["reviewed_signal_unit_evidence"] = {
            "path": reviewed_unit_path.as_posix(),
            "sha256": sha256_file(reviewed_unit_path),
            "schema": reviewed_unit_evidence.get("schema_version"),
            "status": reviewed_unit_evidence.get("status"),
        }
    if reconstructed_state_evidence is not None and reconstructed_state_path is not None:
        references["reconstructed_state_evidence"] = {
            "path": reconstructed_state_path.as_posix(),
            "sha256": sha256_file(reconstructed_state_path),
            "schema": reconstructed_state_evidence.get("schema_version"),
            "status": reconstructed_state_evidence.get("status"),
        }

    return {
        "schema_version": SCHEMA,
        "status": "NORMAL_OPERATION_SOURCE_SCREENED_DIAGNOSTIC_ONLY",
        "purpose": "Bound the inspection-centre data before it is used by the generic outdoor LH2 PRISM chain.",
        "source_identity": {
            "display_name": "LH2 Inspection Support Center data",
            "source_root_label": "액화수소검사지원센터 데이터",
            "source_kind": "normal_operation_and_training_or_recovery_time_series",
            "independent_historian_measurement_claim": False,
            "source_owner_review_required": True,
        },
        "inventory": {
            "source_file_count": source_file_count,
            "workbook_count": workbook_count,
            "sheet_count": sheet_count,
            "signal_category_count": signal_categories,
            "numeric_signal_unit_status_count": unit_status,
            "timestamps_or_sequence_columns_observed": signal_categories.get("time", 0) > 0 or signal_categories.get("sequence_metadata", 0) > 0,
            "pressure_temperature_and_differential_signals_observed": any(
                signal_categories.get(name, 0) > 0 for name in ("pressure", "temperature", "differential_pressure")
            ),
        },
        "evidence_suitability": {
            "timestamped_process_state_screening": {
                "available": True,
                "promotion": "diagnostic_only",
                "reason": "The audit found timestamped process and sequence columns, but not a complete reviewed tag/unit/calibration map.",
            },
            "explicit_operating_mode_and_hazop_diagnostic": {
                "available": bool(reconstructed_state_evidence),
                "promotion": "diagnostic_only",
                "reason": "Explicit modes and a reconstructed state adapter may select a HAZOP branch; this does not turn normal rows into an accident.",
            },
            "accident_release_boundary": {
                "available": False,
                "promotion": "withheld",
                "missing_fields": [
                    "initiating_failure_or_aperture_definition",
                    "mass_flow_or_release_rate_time_history",
                    "release_duration_and_termination_evidence",
                    "isolation_and_inventory_depletion_evidence",
                    "phase_and_source_term_validation_context",
                ],
            },
            "failure_frequency": {
                "available": False,
                "promotion": "withheld",
                "reason": "Normal-operation time series do not provide a counted failure population, exposure denominator, or qualified event-frequency record.",
                "sensor_frequency_learning_used": False,
            },
            "independent_physical_validation": {
                "available": False,
                "promotion": "withheld",
                "reason": "The source package is not an independent accident-release validation campaign.",
            },
        },
        "promotion_gates": {
            "raw_state_snapshot_binding_allowed": _bool(raw_gates.get("state_snapshot_binding_allowed")),
            "reviewed_numeric_state_binding_allowed": _bool(reviewed_gates.get("numeric_state_binding_allowed")),
            "reconstructed_state_evidence_only": bool(reconstructed_state_evidence),
            "frequency_applied": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_created": False,
            "provider_packet_qualified": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "reason": "Use the files for state/HAZOP diagnostics only until source-owner unit, tag, calibration, identity, and accident-release evidence are separately reviewed.",
        },
        "allowed_uses": [
            "screen timestamped process-state patterns",
            "reconstruct an explicitly labelled state frame",
            "pass an explicit operating mode to a HAZOP diagnostic gate",
            "exercise the fail-closed provider/consequence interface with a separately identified diagnostic packet",
        ],
        "forbidden_implicit_promotions": [
            "infer a leak size or release duration from pressure or temperature alone",
            "learn annual failure frequency from alarms or normal-operation samples",
            "treat reconstructed/training data as independent accident measurements",
            "promote a provider packet or facility IR/F-N result from this source inventory",
        ],
        "references": references,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeseries-audit", type=Path, required=True)
    parser.add_argument("--reviewed-unit-evidence", type=Path)
    parser.add_argument("--reconstructed-state-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reviewed = load_json(args.reviewed_unit_evidence) if args.reviewed_unit_evidence else None
    reconstructed = load_json(args.reconstructed_state_evidence) if args.reconstructed_state_evidence else None
    record = build_record(
        timeseries_audit=load_json(args.timeseries_audit),
        timeseries_path=args.timeseries_audit,
        reviewed_unit_evidence=reviewed,
        reviewed_unit_path=args.reviewed_unit_evidence,
        reconstructed_state_evidence=reconstructed,
        reconstructed_state_path=args.reconstructed_state_evidence,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "output": str(args.output), "schema": SCHEMA}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
