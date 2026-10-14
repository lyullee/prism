"""Reconcile native isolation-catalog event rows with their packet artifacts.

The isolation catalog is useful diagnostic evidence, but it is not a field
provider qualification record.  This module checks the stronger claim that
the catalog's event rows, per-event verification files and resolved release
artifacts refer to the same event/component/port and carry the same declared
termination.  Promotion flags remain fail-closed by construction.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prism.native_isolation_event_reconciliation.v1"


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON object required: {path}")
    return value


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _release_summary(release: Mapping[str, Any]) -> dict[str, Any]:
    """Extract only identity and termination evidence from one release file."""

    releases = release.get("releases")
    if isinstance(releases, list):
        endpoint_rows = [item for item in releases if isinstance(item, Mapping)]
        return {
            "event_id": release.get("event_id"),
            "component_id": release.get("component_id"),
            "port_ids": [item.get("port_id") for item in endpoint_rows],
            "termination_bases": [item.get("termination_basis") for item in endpoint_rows],
            "duration_s": [item.get("duration_s") for item in endpoint_rows],
            "available_mass_kg": release.get("available_mass_kg"),
            "cumulative_mass_out_kg": release.get("cumulative_mass_out_kg"),
            "release_file_kind": "resolved_release_set",
        }
    return {
        "event_id": release.get("event_id"),
        "component_id": release.get("component_id"),
        "port_ids": [release.get("port_id")],
        "termination_bases": [release.get("termination_basis")],
        "duration_s": [release.get("duration_s")],
        "available_mass_kg": release.get("available_mass_kg"),
        "cumulative_mass_out_kg": release.get("cumulative_mass_out_kg"),
        "release_file_kind": "resolved_release",
    }


def build_native_isolation_event_reconciliation(
    catalog_dir: str | Path,
) -> dict[str, Any]:
    """Build a deterministic reconciliation record from a native catalog.

    ``catalog_dir`` must contain the catalog ``verification.json`` and
    ``isolation_branch_audit.json`` files plus the event subdirectories listed
    in ``verification.json``.  Missing or inconsistent files make the
    reconciliation blocked; no missing release is converted to zero risk.
    """

    root = Path(catalog_dir)
    verification_path = root / "verification.json"
    isolation_audit_path = root / "isolation_branch_audit.json"
    verification = _load_json(verification_path)
    isolation_audit = _load_json(isolation_audit_path)
    event_rows = verification.get("event_rows")
    if not isinstance(event_rows, list):
        event_rows = []

    rows: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    event_ids: list[str] = []
    for source_row in event_rows:
        if not isinstance(source_row, Mapping):
            mismatches.append({"reason": "event_row_not_object"})
            continue
        event_id = str(source_row.get("event_id", ""))
        event_ids.append(event_id)
        event_dir_value = source_row.get("event_dir")
        event_dir = root / str(event_dir_value) if event_dir_value else None
        event_verification: Mapping[str, Any] = {}
        release: Mapping[str, Any] = {}
        file_errors: list[str] = []
        if event_dir is None:
            file_errors.append("event_dir_missing")
        else:
            event_verification_path = event_dir / "verification.json"
            if event_verification_path.exists():
                event_verification = _load_json(event_verification_path)
            else:
                file_errors.append("event_verification_missing")
            release_path = event_dir / "resolved_release.json"
            release_set_path = event_dir / "resolved_release_set.json"
            if release_path.exists():
                release = _load_json(release_path)
            elif release_set_path.exists():
                release = _load_json(release_set_path)
            else:
                file_errors.append("resolved_release_missing")

        release_summary = _release_summary(release) if release else {
            "event_id": None,
            "component_id": None,
            "port_ids": [],
            "termination_bases": [],
            "duration_s": [],
            "available_mass_kg": None,
            "cumulative_mass_out_kg": None,
            "release_file_kind": None,
        }
        declared_basis = source_row.get("diagnostic_termination_basis")
        observed_bases = [basis for basis in release_summary["termination_bases"] if basis]
        row_mismatches = list(file_errors)
        if source_row.get("status") != "EXACT_NATIVE_PACKET":
            row_mismatches.append("event_row_not_exact_native_packet")
        if release_summary.get("event_id") != event_id:
            row_mismatches.append("event_id_mismatch")
        if source_row.get("component_id") != release_summary.get("component_id"):
            row_mismatches.append("component_id_mismatch")
        if declared_basis and observed_bases and any(basis != declared_basis for basis in observed_bases):
            row_mismatches.append("termination_basis_mismatch")
        for flag_name in (
            "provider_packet_promoted",
            "physical_validation_claim",
            "facility_qra_claim",
        ):
            if event_verification.get(flag_name) is True:
                row_mismatches.append(f"unsafe_{flag_name}")
        if event_verification.get("frequency_inference_performed") is True or event_verification.get(
            "frequency_inference"
        ) is True:
            row_mismatches.append("unsafe_frequency_inference")

        row = {
            "event_id": event_id,
            "component_id": source_row.get("component_id"),
            "port_ids": release_summary.get("port_ids", []),
            "packet_kind": source_row.get("packet_kind"),
            "event_status": source_row.get("status"),
            "diagnostic_termination_basis": declared_basis,
            "resolved_termination_bases": observed_bases,
            "diagnostic_duration_s": source_row.get("diagnostic_duration_s"),
            "resolved_duration_s": release_summary.get("duration_s", []),
            "isolation_requested": source_row.get("isolation_requested"),
            "isolation_success": source_row.get("isolation_success"),
            "verification_status": event_verification.get("status"),
            "provider_packet_promoted": event_verification.get("provider_packet_promoted"),
            "physical_validation_claim": event_verification.get("physical_validation_claim"),
            "facility_qra_claim": event_verification.get("facility_qra_claim"),
            "release_file_kind": release_summary.get("release_file_kind"),
            "available_mass_kg": release_summary.get("available_mass_kg"),
            "cumulative_mass_out_kg": release_summary.get("cumulative_mass_out_kg"),
            "reconciliation_status": "MATCHED" if not row_mismatches else "MISMATCH",
            "mismatch_reasons": row_mismatches,
        }
        rows.append(row)
        if row_mismatches:
            mismatches.append({"event_id": event_id, "reasons": row_mismatches})

    counts = Counter(row.get("diagnostic_termination_basis") for row in rows)
    isolation_success_count = sum(row.get("isolation_success") is True for row in rows)
    exact_count = verification.get("exact_native_packet_count")
    event_count = verification.get("frequency_event_count")
    all_flags_safe = all(
        row.get("provider_packet_promoted") is False
        and row.get("physical_validation_claim") is False
        and row.get("facility_qra_claim") is False
        for row in rows
    )
    checks = {
        "event_rows_present": bool(rows),
        "event_count_matches_root": event_count == len(rows),
        "exact_packet_count_matches_root": exact_count == len(rows),
        "uncomputed_event_count_zero": verification.get("uncomputed_event_count") == 0,
        "event_ids_unique": len(event_ids) == len(set(event_ids)),
        "all_event_artifacts_reconciled": not mismatches,
        "isolation_success_count_matches_root": isolation_success_count
        == isolation_audit.get("isolation_success_count"),
        "state_snapshot_binding_preserved": verification.get("state_snapshot_binding", {}).get("status")
        == "STATE_SNAPSHOT_BOUND_AND_ECHOED"
        if isinstance(verification.get("state_snapshot_binding"), Mapping)
        else False,
        "promotion_flags_withheld": all_flags_safe
        and verification.get("provider_packet_promoted") is False
        and verification.get("physical_validation_claim") is False
        and verification.get("facility_qra_claim") is False,
        "frequency_inference_withheld": verification.get("frequency_inference_performed") is False,
    }
    status = (
        "NATIVE_ISOLATION_EVENT_ROWS_RECONCILED_DIAGNOSTIC"
        if all(checks.values())
        else "NATIVE_ISOLATION_EVENT_ROWS_RECONCILIATION_BLOCKED"
    )
    return {
        "schema_version": SCHEMA,
        "status": status,
        "catalog_dir": str(root),
        "source_verification": str(verification_path),
        "source_isolation_audit": str(isolation_audit_path),
        "event_count": len(rows),
        "exact_native_packet_count": exact_count,
        "uncomputed_event_count": verification.get("uncomputed_event_count"),
        "isolation_success_count": isolation_success_count,
        "termination_basis_counts": dict(sorted((str(k), v) for k, v in counts.items())),
        "checks": checks,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "rows": rows,
        "interpretation": (
            "Per-event native isolation artifacts reconcile to the catalog event rows and resolved "
            "release files. This is diagnostic chain evidence only; provider qualification, independent "
            "physical validation, frequency inference and facility IR/F-N promotion remain withheld."
        ),
    }


__all__ = ["SCHEMA", "build_native_isolation_event_reconciliation"]
