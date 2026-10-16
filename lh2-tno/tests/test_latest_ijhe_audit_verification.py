from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.latest_ijhe_audit_verification import verify_latest_ijhe_audit


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_latest_ijhe_audit_verification_passes_without_opening_qualification(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [
            {"status": "PASS"},
            {"status": "BLOCKED"},
        ],
        "blocking_reasons": ["provider"],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "physical_validation_claim": False,
        },
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE; 2 checks, 1 BLOCKED",
        "latest_ijhe_completion_audit_check_count": 2,
        "latest_ijhe_completion_audit_blocking_reason_count": 1,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["check_count"] == 2
    assert result["pass_check_count"] == 1
    assert result["blocked_check_count"] == 1
    assert result["complete_facility_qra_claim"] is False


def test_latest_ijhe_audit_verification_blocks_count_drift(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "physical_validation_claim": False,
        },
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 99,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("check count" in reason for reason in result["blocking_reasons"])


def test_latest_ijhe_audit_verification_checks_receptor_geometry_pointer(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {"facility_ir_fn_available": False, "physical_validation_claim": False},
    }
    geometry = {
        "schema_version": "prism.receptor_geometry_interpretation.v1",
        "status": "PASS_DIAGNOSTIC_ONLY",
        "checks": [{"status": "PASS"}],
        "promotion_boundary": {
            "facility_total_risk_claim": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
        },
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    _write(tmp_path / "geometry.json", geometry)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "receptor_geometry_interpretation_record": "geometry.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["receptor_geometry_interpretation_status"] == "PASS_DIAGNOSTIC_ONLY"


def test_latest_ijhe_audit_verification_checks_actual_ffi_gate_identity(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "physical_validation_claim": False,
        },
    }
    gate = {
        "schema_version": "prism.slabx_lh2_ffi_test6_actual_source_numerical_gate.v1",
        "status": "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_OPEN",
        "accepted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    _write(tmp_path / "gate.json", gate)
    _write(tmp_path / "refinement.json", {"levels": []})
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "slabx_lh2_test6_actual_source_numerical_gate_record": "gate.json",
        "slabx_lh2_test6_actual_source_numerical_gate_status": "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_OPEN",
        "slabx_lh2_test6_actual_source_numerical_gate_accepted": False,
        "slabx_lh2_test6_actual_source_numerical_gate_physical_validation_claim": False,
        "slabx_lh2_test6_actual_source_numerical_gate_facility_qra_claim": False,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["actual_ffi_numerical_gate_accepted"] is False


def test_latest_ijhe_audit_verification_rejects_gate_acceptance_drift(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "physical_validation_claim": False,
        },
    }
    gate = {
        "schema_version": "prism.slabx_lh2_ffi_test6_actual_source_numerical_gate.v1",
        "status": "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_OPEN",
        "accepted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    _write(tmp_path / "gate.json", gate)
    _write(tmp_path / "refinement.json", {"levels": []})
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "slabx_lh2_test6_actual_source_numerical_gate_record": "gate.json",
        "slabx_lh2_test6_actual_source_numerical_gate_status": "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_ACCEPTED",
        "slabx_lh2_test6_actual_source_numerical_gate_accepted": True,
        "slabx_lh2_test6_actual_source_numerical_gate_physical_validation_claim": False,
        "slabx_lh2_test6_actual_source_numerical_gate_facility_qra_claim": False,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("gate status" in reason or "acceptance" in reason for reason in result["blocking_reasons"])


def test_latest_ijhe_audit_verification_binds_scope_and_release_ledgers(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {
            "facility_ir_fn_available": False,
            "physical_validation_claim": False,
        },
    }
    scope = {
        "schema_version": "prism.major_accident_scope.v1",
        "rows": [{"family": "vessel_hole"}],
        "conditional_chain_complete": True,
        "facility_total_risk_available": False,
        "physical_validation_claim": False,
        "case_count": 2,
    }
    release = {
        "schema_version": "prism.release_boundary_case_audit.v1",
        "status": "CASE_BOUNDARY_PARTIAL",
        "case_count": 2,
        "strict_release_boundary_eligible_case_count": 1,
        "strict_release_boundary_blocked_case_count": 1,
        "facility_ir_fn_promotion": False,
        "provider_qualification_claim": False,
        "independent_physical_validation_claim": False,
    }
    for name, value in {
        "audit.json": audit,
        "handoff.json": handoff,
        "scope.json": scope,
        "release.json": release,
    }.items():
        _write(tmp_path / name, value)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "latest_union_scope_matrix_record": "scope.json",
        "latest_release_boundary_case_audit": "release.json",
        "latest_union_case_count": 2,
        "latest_ijhe_completion_audit_release_boundary_eligible_case_count": 1,
        "latest_ijhe_completion_audit_release_boundary_blocked_case_count": 1,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["facility_scope_matrix_case_count"] == 2
    assert result["facility_scope_matrix_status"] == "INCOMPLETE_DECLARED_SCOPE"
    assert result["release_boundary_case_count"] == 2


def test_latest_ijhe_audit_verification_rejects_release_scope_count_drift(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
        "status": "PASS_WITH_SCOPE_LIMITATIONS",
        "checks": [{"status": "PASS"}],
        "qualification_boundary": {"facility_ir_fn_available": False, "physical_validation_claim": False},
    }
    scope = {
        "schema_version": "prism.major_accident_scope.v1",
        "rows": [{"family": "vessel_hole"}],
        "conditional_chain_complete": True,
        "facility_total_risk_available": False,
        "physical_validation_claim": False,
        "case_count": 3,
    }
    release = {
        "schema_version": "prism.release_boundary_case_audit.v1",
        "status": "CASE_BOUNDARY_PARTIAL",
        "case_count": 3,
        "strict_release_boundary_eligible_case_count": 1,
        "strict_release_boundary_blocked_case_count": 2,
        "facility_ir_fn_promotion": False,
        "provider_qualification_claim": False,
        "independent_physical_validation_claim": False,
    }
    for name, value in {
        "audit.json": audit,
        "handoff.json": handoff,
        "scope.json": scope,
        "release.json": release,
    }.items():
        _write(tmp_path / name, value)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "latest_union_scope_matrix_record": "scope.json",
        "latest_release_boundary_case_audit": "release.json",
        "latest_union_case_count": 2,
        "latest_ijhe_completion_audit_release_boundary_eligible_case_count": 1,
        "latest_ijhe_completion_audit_release_boundary_blocked_case_count": 1,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("case count" in reason for reason in result["blocking_reasons"])
