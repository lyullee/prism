"""Fail-closed consistency verification for the latest IJHE audit pointer.

This module verifies that the status ledger points to a real audit record, that
its summary counts agree with the stored checks, and that the inspection-center
facility handoff remains diagnostic-only. It never promotes a facility QRA.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "prism.latest_ijhe_audit_verification.v1"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _relative_or_absolute(path_value: str, *, root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def verify_latest_ijhe_audit(
    current_status: Mapping[str, Any] | Path,
    *,
    root: Path | None = None,
    audit: Mapping[str, Any] | Path | None = None,
    handoff: Mapping[str, Any] | Path | None = None,
) -> dict[str, Any]:
    """Verify status/audit/handoff identity without changing qualification gates."""

    base = Path(root or Path.cwd()).resolve()
    status = _read_object(current_status) if isinstance(current_status, Path) else dict(current_status)
    record_value = status.get("latest_ijhe_completion_audit_record")
    reasons: list[str] = []
    if not isinstance(record_value, str) or not record_value.strip():
        reasons.append("current status has no latest_ijhe_completion_audit_record")
        record_path = base / "__missing_latest_audit__.json"
    else:
        record_path = _relative_or_absolute(record_value, root=base)

    if audit is None:
        if record_path.exists():
            audit_value = _read_object(record_path)
        else:
            audit_value = {}
    elif isinstance(audit, Path):
        audit_value = _read_object(audit)
    else:
        audit_value = dict(audit)

    checks = audit_value.get("checks")
    blockers = audit_value.get("blocking_reasons")
    if not isinstance(checks, list):
        reasons.append("latest audit checks must be a list")
        checks = []
    if not isinstance(blockers, list):
        reasons.append("latest audit blocking_reasons must be a list")
        blockers = []
    pass_count = sum(item.get("status") == "PASS" for item in checks if isinstance(item, Mapping))
    blocked_check_count = sum(item.get("status") == "BLOCKED" for item in checks if isinstance(item, Mapping))
    expected_count = status.get("latest_ijhe_completion_audit_check_count")
    expected_blocker_count = status.get("latest_ijhe_completion_audit_blocking_reason_count")
    if expected_count != len(checks):
        reasons.append(f"status check count {expected_count!r} does not match audit count {len(checks)}")
    if expected_blocker_count != len(blockers):
        reasons.append(f"status blocker count {expected_blocker_count!r} does not match audit count {len(blockers)}")
    if audit_value.get("status") != status.get("latest_ijhe_completion_audit_status", "").split(";", 1)[0]:
        reasons.append("status summary and audit status disagree")
    if audit_value.get("complete_facility_qra_claim") is not False:
        reasons.append("latest audit must keep complete_facility_qra_claim=false")
    if audit_value.get("physical_validation_claim") is not False:
        reasons.append("latest audit must keep physical_validation_claim=false")

    handoff_value: dict[str, Any]
    if handoff is None:
        handoff_path_value = status.get("inspection_center_facility_ijhe_handoff_audit_record")
        handoff_path = (
            _relative_or_absolute(handoff_path_value, root=base)
            if isinstance(handoff_path_value, str)
            else base / "__missing_handoff__.json"
        )
        handoff_value = _read_object(handoff_path) if handoff_path.exists() else {}
    elif isinstance(handoff, Path):
        handoff_path = handoff
        handoff_value = _read_object(handoff)
    else:
        handoff_path = None
        handoff_value = dict(handoff)
    handoff_checks = handoff_value.get("checks")
    if handoff_value.get("schema_version") != "prism.inspection_center_facility_ijhe_audit.v1":
        reasons.append("facility handoff schema is not the declared PRISM schema")
    if handoff_value.get("status") != "PASS_WITH_SCOPE_LIMITATIONS":
        reasons.append("facility handoff status is not PASS_WITH_SCOPE_LIMITATIONS")
    if not isinstance(handoff_checks, list) or not handoff_checks or any(
        not isinstance(item, Mapping) or item.get("status") != "PASS" for item in handoff_checks
    ):
        reasons.append("facility handoff checks are not all PASS")
    boundary = handoff_value.get("qualification_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("facility_ir_fn_available") is not False or boundary.get("physical_validation_claim") is not False:
        reasons.append("facility handoff qualification boundary is not fail-closed")

    status_value = "PASS" if not reasons else "BLOCKED_AUDIT_METADATA"
    return {
        "schema_version": SCHEMA,
        "status": status_value,
        "audit_record": str(record_path),
        "audit_status": audit_value.get("status"),
        "check_count": len(checks),
        "pass_check_count": pass_count,
        "blocked_check_count": blocked_check_count,
        "blocking_reason_count": len(blockers),
        "facility_handoff_check_count": len(handoff_checks) if isinstance(handoff_checks, list) else 0,
        "facility_handoff_status": handoff_value.get("status"),
        "complete_facility_qra_claim": audit_value.get("complete_facility_qra_claim"),
        "physical_validation_claim": audit_value.get("physical_validation_claim"),
        "blocking_reasons": reasons,
        "interpretation": (
            "The latest audit pointer, summary counts, and diagnostic facility handoff are internally consistent; "
            "this verification does not promote provider qualification, physical validation, or facility IR/F-N."
            if not reasons
            else "The latest audit metadata is inconsistent or incomplete; no qualification claim is allowed."
        ),
    }
