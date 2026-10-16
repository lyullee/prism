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
    receptor_geometry: Mapping[str, Any] | Path | None = None,
    scope_matrix: Mapping[str, Any] | Path | None = None,
    release_boundary: Mapping[str, Any] | Path | None = None,
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

    geometry_value: dict[str, Any] = {}
    geometry_path: Path | None = None
    geometry_pointer = status.get("receptor_geometry_interpretation_record")
    if receptor_geometry is None and isinstance(geometry_pointer, str):
        geometry_path = _relative_or_absolute(geometry_pointer, root=base)
        geometry_value = _read_object(geometry_path) if geometry_path.exists() else {}
    elif isinstance(receptor_geometry, Path):
        geometry_path = receptor_geometry
        geometry_value = _read_object(receptor_geometry)
    elif isinstance(receptor_geometry, Mapping):
        geometry_value = dict(receptor_geometry)
    if geometry_pointer is not None or receptor_geometry is not None:
        if geometry_value.get("schema_version") != "prism.receptor_geometry_interpretation.v1":
            reasons.append("receptor geometry interpretation schema is not the declared PRISM schema")
        if geometry_value.get("status") != "PASS_DIAGNOSTIC_ONLY":
            reasons.append("receptor geometry interpretation is not PASS_DIAGNOSTIC_ONLY")
        geometry_checks = geometry_value.get("checks")
        if not isinstance(geometry_checks, list) or not geometry_checks or any(
            not isinstance(item, Mapping) or item.get("status") != "PASS" for item in geometry_checks
        ):
            reasons.append("receptor geometry interpretation checks are not all PASS")
        promotion = geometry_value.get("promotion_boundary")
        if not isinstance(promotion, Mapping) or any(
            promotion.get(key) is not False
            for key in ("facility_total_risk_claim", "facility_qra_claim", "physical_validation_claim")
        ):
            reasons.append("receptor geometry interpretation promotion boundary is not fail-closed")

    # Bind the latest facility-level scope and release-boundary ledgers when
    # the current status ledger exposes their pointers.  These are diagnostic
    # consistency checks only: a numerically executed row is never promoted to
    # qualified provider evidence or facility QRA here.
    def _load_optional(
        supplied: Mapping[str, Any] | Path | None,
        pointer_keys: tuple[str, ...],
    ) -> tuple[dict[str, Any], Path | None, bool]:
        if supplied is not None:
            if isinstance(supplied, Path):
                return _read_object(supplied), supplied, True
            return dict(supplied), None, True
        for key in pointer_keys:
            pointer = status.get(key)
            if isinstance(pointer, str) and pointer.strip():
                path = _relative_or_absolute(pointer, root=base)
                if not path.exists():
                    reasons.append(f"{key} does not exist")
                    return {}, path, True
                return _read_object(path), path, True
        return {}, None, False

    scope_value, scope_path, scope_present = _load_optional(
        scope_matrix,
        ("latest_union_scope_matrix_record", "scope_matrix_latest_record"),
    )
    release_value, release_path, release_present = _load_optional(
        release_boundary,
        ("latest_release_boundary_case_audit",),
    )
    if scope_present:
        if scope_value.get("schema_version") != "prism.major_accident_scope.v1":
            reasons.append("latest facility scope matrix schema is not the declared PRISM schema")
        if not isinstance(scope_value.get("rows"), list) or not scope_value.get("rows"):
            reasons.append("latest facility scope matrix has no family rows")
        if not isinstance(scope_value.get("conditional_chain_complete"), bool):
            reasons.append("latest facility scope matrix conditional-chain flag is missing")
        if scope_value.get("facility_total_risk_available") is not False:
            reasons.append("latest facility scope matrix must keep facility_total_risk_available=false")
        if scope_value.get("physical_validation_claim") is not False:
            reasons.append("latest facility scope matrix must keep physical_validation_claim=false")
        expected_cases = status.get("latest_union_case_count")
        if expected_cases is not None and scope_value.get("case_count") != expected_cases:
            reasons.append("latest facility scope matrix case count disagrees with status ledger")
    if release_present:
        if release_value.get("schema_version") != "prism.release_boundary_case_audit.v1":
            reasons.append("latest release-boundary audit schema is not the declared PRISM schema")
        if release_value.get("facility_ir_fn_promotion") is not False:
            reasons.append("latest release-boundary audit must keep facility_ir_fn_promotion=false")
        if release_value.get("provider_qualification_claim") is not False:
            reasons.append("latest release-boundary audit must keep provider_qualification_claim=false")
        if release_value.get("independent_physical_validation_claim") is not False:
            reasons.append("latest release-boundary audit must keep independent_physical_validation_claim=false")
        expected_cases = status.get("latest_union_case_count")
        if expected_cases is not None and release_value.get("case_count") != expected_cases:
            reasons.append("latest release-boundary audit case count disagrees with status ledger")
        for status_key, audit_key in (
            ("latest_ijhe_completion_audit_release_boundary_eligible_case_count", "strict_release_boundary_eligible_case_count"),
            ("latest_ijhe_completion_audit_release_boundary_blocked_case_count", "strict_release_boundary_blocked_case_count"),
        ):
            expected = status.get(status_key)
            if expected is not None and release_value.get(audit_key) != expected:
                reasons.append(f"latest release-boundary audit {audit_key} disagrees with status ledger")
        # Newer release audits include a per-case evidence-request contract
        # check.  Consume it when present while keeping historical records
        # readable; a blocked contract must never be mistaken for aligned
        # evidence coverage.
        if "facility_evidence_request_contract_blocked_case_count" in release_value:
            if release_value.get("facility_evidence_request_contract_blocked_case_count") != 0:
                reasons.append("latest release-boundary audit has blocked evidence-request contracts")
            contract_counts = release_value.get(
                "facility_evidence_request_contract_status_counts"
            )
            if not isinstance(contract_counts, Mapping) or contract_counts.get("BLOCKED", 0) != 0:
                reasons.append("latest release-boundary audit evidence-request contract status is not aligned")

    # The actual FFI Test 6 convergence record is optional for historical
    # callers, but when the current status ledger points to it we verify the
    # identity and fail-closed claims here as well.  This keeps a stale or
    # hand-edited status file from silently presenting an unresolved numerical
    # source as accepted physical validation.
    gate_record_value = status.get("slabx_lh2_test6_actual_source_numerical_gate_record")
    gate_status_value = status.get("slabx_lh2_test6_actual_source_numerical_gate_status")
    gate_accepted_value = status.get("slabx_lh2_test6_actual_source_numerical_gate_accepted")
    gate_record: dict[str, Any] = {}
    gate_path: Path | None = None
    if gate_record_value is not None:
        if not isinstance(gate_record_value, str) or not gate_record_value.strip():
            reasons.append("actual FFI numerical gate record pointer is not a non-empty string")
        else:
            gate_path = _relative_or_absolute(gate_record_value, root=base)
            if not gate_path.exists():
                reasons.append("actual FFI numerical gate record does not exist")
            else:
                gate_record = _read_object(gate_path)
                if gate_record.get("schema_version") != (
                    "prism.slabx_lh2_ffi_test6_actual_source_numerical_gate.v1"
                ):
                    reasons.append("actual FFI numerical gate schema is not the declared schema")
                if gate_status_value != gate_record.get("status"):
                    reasons.append("status ledger and actual FFI numerical gate status disagree")
                if gate_accepted_value != gate_record.get("accepted"):
                    reasons.append("status ledger and actual FFI numerical gate acceptance disagree")
                if status.get("slabx_lh2_test6_actual_source_numerical_gate_physical_validation_claim") is not False:
                    reasons.append("status ledger actual FFI gate must keep physical_validation_claim=false")
                if status.get("slabx_lh2_test6_actual_source_numerical_gate_facility_qra_claim") is not False:
                    reasons.append("status ledger actual FFI gate must keep facility_qra_claim=false")
                refinement_path = gate_path.with_name("refinement.json")
                if not refinement_path.exists():
                    reasons.append("actual FFI numerical gate refinement record does not exist")

    status_value = "PASS" if not reasons else "BLOCKED_AUDIT_METADATA"
    scope_status = scope_value.get("status") if scope_value else None
    if scope_value and scope_status is None:
        scope_status = (
            "COMPLETE_DECLARED_SCOPE"
            if scope_value.get("matrix_complete") is True
            else "INCOMPLETE_DECLARED_SCOPE"
        )

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
        "receptor_geometry_interpretation_record": str(geometry_path) if geometry_path else None,
        "receptor_geometry_interpretation_status": geometry_value.get("status") if geometry_value else None,
        "actual_ffi_numerical_gate_record": str(gate_path) if gate_path else None,
        "actual_ffi_numerical_gate_status": gate_record.get("status") if gate_record else gate_status_value,
        "actual_ffi_numerical_gate_accepted": gate_record.get("accepted") if gate_record else gate_accepted_value,
        "facility_scope_matrix_record": str(scope_path) if scope_path else None,
        "facility_scope_matrix_status": scope_status,
        "facility_scope_matrix_case_count": scope_value.get("case_count") if scope_value else None,
        "release_boundary_audit_record": str(release_path) if release_path else None,
        "release_boundary_audit_status": release_value.get("status") if release_value else None,
        "release_boundary_case_count": release_value.get("case_count") if release_value else None,
        "release_boundary_request_contract_status_counts": (
            release_value.get("facility_evidence_request_contract_status_counts")
            if release_value else None
        ),
        "release_boundary_request_contract_blocked_case_count": (
            release_value.get("facility_evidence_request_contract_blocked_case_count")
            if release_value else None
        ),
        "blocking_reasons": reasons,
        "interpretation": (
            "The latest audit pointer, summary counts, diagnostic facility handoff, scope matrix, and "
            "release-boundary ledger are internally consistent; this verification does not promote provider "
            "qualification, physical validation, or facility IR/F-N."
            if not reasons
            else "The latest audit metadata is inconsistent or incomplete; no qualification claim is allowed."
        ),
    }
