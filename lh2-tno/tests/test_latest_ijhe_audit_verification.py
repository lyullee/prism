from __future__ import annotations

import json
import hashlib
from pathlib import Path

from lh2_tno.latest_ijhe_audit_verification import verify_latest_ijhe_audit


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_latest_ijhe_audit_verification_binds_release_closure_worklist_and_digest(tmp_path: Path):
    _write(
        tmp_path / "audit.json",
        {
            "status": "INCOMPLETE_EVIDENCE",
            "checks": [{"status": "PASS"}],
            "blocking_reasons": [],
            "complete_facility_qra_claim": False,
            "physical_validation_claim": False,
        },
    )
    _write(
        tmp_path / "handoff.json",
        {
            "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
            "status": "PASS_WITH_SCOPE_LIMITATIONS",
            "checks": [{"status": "PASS"}],
            "qualification_boundary": {
                "facility_ir_fn_available": False,
                "physical_validation_claim": False,
            },
        },
    )
    worklist = {
        "schema_version": "prism.release_closure_worklist.v1",
        "status": "OPEN_RELEASE_CLOSURE_WORKLIST",
        "case_count": 1,
        "open_case_count": 1,
        "cases": [{}],
        "summary": {
            "mass_closure_open_case_count": 0,
            "isolation_open_case_count": 1,
            "termination_open_case_count": 0,
            "inventory_closure_open_case_count": 0,
        },
        "promotion_gates": {
            "release_boundary_promotion_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "physical_validation_claim": False,
        },
    }
    worklist_path = _write(tmp_path / "worklist.json", worklist)
    digest = hashlib.sha256(worklist_path.read_bytes()).hexdigest().upper()
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "v060_release_closure_worklist": "worklist.json",
        "v060_release_closure_worklist_sha256": digest,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["release_closure_worklist_case_count"] == 1
    assert result["release_closure_worklist_open_case_count"] == 1
    assert result["release_closure_worklist_termination_open_case_count"] == 0
    assert result["release_closure_worklist_sha256"] == digest

    worklist["open_case_count"] = 0
    _write(worklist_path, worklist)
    drifted = verify_latest_ijhe_audit(status, root=tmp_path)
    assert drifted["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("SHA-256" in reason for reason in drifted["blocking_reasons"])


def test_latest_ijhe_audit_verification_checks_boundary_join_summary(tmp_path: Path):
    _write(
        tmp_path / "audit.json",
        {
            "status": "INCOMPLETE_EVIDENCE",
            "checks": [{"status": "PASS"}],
            "blocking_reasons": [],
            "complete_facility_qra_claim": False,
            "physical_validation_claim": False,
        },
    )
    _write(
        tmp_path / "handoff.json",
        {
            "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
            "status": "PASS_WITH_SCOPE_LIMITATIONS",
            "checks": [{"status": "PASS"}],
            "qualification_boundary": {
                "facility_ir_fn_available": False,
                "physical_validation_claim": False,
            },
        },
    )
    worklist = {
        "schema_version": "prism.release_closure_worklist.v1",
        "status": "OPEN_RELEASE_CLOSURE_WORKLIST",
        "case_count": 2,
        "open_case_count": 2,
        "boundary_audit_record": "boundary.json",
        "cases": [
            {"boundary_audit_join": {"matched": True}},
            {"boundary_audit_join": {"matched": True}},
        ],
        "summary": {
            "mass_closure_open_case_count": 0,
            "isolation_open_case_count": 1,
            "termination_open_case_count": 0,
            "inventory_closure_open_case_count": 1,
            "boundary_audit_join_case_count": 2,
            "boundary_audit_unmatched_case_count": 0,
            "boundary_audit_duplicate_key_count": 0,
            "numerical_closure_status_counts": {
                "NUMERICALLY_CLOSED": 1,
                "NUMERICALLY_OPEN": 1,
            },
            "numerically_closed_case_count": 1,
            "numerically_open_case_count": 1,
            "operator_review_required_case_count": 0,
            "provider_termination_evidence_status_counts": {
                "VALID": 1,
                "INVALID": 1,
            },
            "strict_release_boundary_eligible_case_count": 1,
            "strict_release_boundary_blocked_case_count": 1,
        },
        "promotion_gates": {
            "release_boundary_promotion_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "physical_validation_claim": False,
        },
    }
    worklist_path = _write(tmp_path / "worklist.json", worklist)
    digest = hashlib.sha256(worklist_path.read_bytes()).hexdigest().upper()
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "v060_release_closure_worklist": "worklist.json",
        "v060_release_closure_worklist_sha256": digest,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["release_closure_worklist_boundary_join_case_count"] == 2
    assert result["release_closure_worklist_numerically_open_case_count"] == 1

    worklist["summary"]["numerically_closed_case_count"] = 2
    _write(worklist_path, worklist)
    drifted = verify_latest_ijhe_audit(status, root=tmp_path)
    assert drifted["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("closed/open counts" in reason for reason in drifted["blocking_reasons"])


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


def _native_multi_equipment_recheck() -> dict:
    return {
        "schema_version": "prism.native_external_multi_equipment_recheck_compact.v1",
        "source_repository": "lyullee/lh2dt_models",
        "source_commit": "16f7a4b",
        "external_source_digest": "a" * 64,
        "status": "NATIVE_EXTERNAL_MULTI_EQUIPMENT_RECHECK_EXECUTED_DIAGNOSTIC",
        "equipment_count": 2,
        "equipment": [
            {
                "equipment": "layered_tank",
                "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
                "state_snapshot_digest_match": True,
                "dynamic_state_closure": {
                    "declared_by_provider": True,
                    "prism_source_dynamics_status": "READY",
                    "ready": True,
                    "blocking_reasons": [],
                },
            },
            {
                "equipment": "vent_stack",
                "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
                "state_snapshot_digest_match": True,
                "dynamic_state_closure": None,
            },
        ],
        "provider_packet_promoted_count": 0,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
    }


def _native_clean_full_scope_replay() -> dict:
    return {
        "schema_version": "prism.native_external_facility_full_scope_clean_source_replay.v1",
        "status": "EXECUTED_DIAGNOSTIC_CLEAN_EXTERNAL_SOURCE",
        "source": {
            "repository": "https://github.com/lyullee/lh2dt_models",
            "commit": "16f7a4b",
            "source_tree_sha256": "a" * 64,
        },
        "packet_catalog": {
            "event_count": 24,
            "exact_native_packet_count": 24,
            "uncomputed_event_count": 0,
            "isolation_requested": False,
        },
        "facility_campaign": {
            "packet_count": 24,
            "event_count": 24,
            "matched_event_case_record_count": 24,
            "matched_event_executed_case_count": 24,
            "matched_event_uncomputed_case_count": 0,
            "matched_event_failed_case_count": 0,
            "risk_atom_count": 96,
            "hazop_event_mode_binding": {"bound_event_count": 24, "unbound_event_count": 0},
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
    }


def test_latest_ijhe_audit_verification_binds_clean_full_scope_replay(tmp_path: Path):
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
    _write(tmp_path / "clean_scope.json", _native_clean_full_scope_replay())
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "external_lh2dt_native_clean_full_scope_replay_record": "clean_scope.json",
        "external_lh2dt_native_clean_full_scope_replay_source_digest": "a" * 64,
        "external_lh2dt_native_clean_full_scope_replay_packet_count": 24,
        "external_lh2dt_native_clean_full_scope_replay_executed_case_count": 24,
        "external_lh2dt_native_clean_full_scope_replay_risk_atom_count": 96,
        "external_lh2dt_native_clean_full_scope_replay_facility_qra_claim": False,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["native_external_clean_full_scope_replay_valid"] is True
    assert result["native_external_clean_full_scope_replay_executed_case_count"] == 24


def test_latest_ijhe_audit_verification_blocks_clean_scope_promotion(tmp_path: Path):
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
    bad = _native_clean_full_scope_replay()
    bad["facility_campaign"]["facility_qra_claim"] = True
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    _write(tmp_path / "clean_scope.json", bad)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "external_lh2dt_native_clean_full_scope_replay_record": "clean_scope.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("clean full-scope replay" in reason for reason in result["blocking_reasons"])


def _native_clean_full_scope_isolation_replay() -> dict:
    return {
        "schema_version": "prism.native_external_facility_full_scope_clean_source_isolation_replay.v1",
        "status": "EXECUTED_DIAGNOSTIC_CLEAN_EXTERNAL_SOURCE_WITH_ISOLATION",
        "source": {
            "repository": "https://github.com/lyullee/lh2dt_models",
            "commit": "16f7a4b",
            "source_tree_sha256": "b" * 64,
        },
        "adapter": {"transfer_valve_isolation_success_event_count": 5},
        "facility_risk_summary": {
            "sha256": "c" * 64,
            "conditional_diagnostic_facility_risk_available": True,
            "facility_total_risk_available": False,
            "scenario_count": 3,
            "receptor_count": 1,
            "frequency_reallocation_performed": False,
            "execution_boundary": {
                "assessment_fresh_physics_executed": False,
                "source_campaign_physics_executed": True,
                "source_campaign_fresh_physics_cases": 24,
            },
        },
        "packet_catalog": {
            "event_count": 24,
            "exact_native_packet_count": 24,
            "uncomputed_event_count": 0,
            "isolation_requested": True,
            "isolation_time_s": 0.05,
            "post_isolation_observation_s": 0.1,
        },
        "facility_campaign": {
            "packet_count": 24,
            "event_count": 24,
            "matched_event_case_record_count": 24,
            "matched_event_executed_case_count": 24,
            "matched_event_uncomputed_case_count": 0,
            "matched_event_failed_case_count": 0,
            "risk_atom_count": 96,
            "hazop_event_mode_binding": {"bound_event_count": 24, "unbound_event_count": 0},
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
    }


def test_latest_ijhe_audit_verification_binds_clean_isolation_replay(tmp_path: Path):
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
    _write(tmp_path / "isolation_scope.json", _native_clean_full_scope_isolation_replay())
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "external_lh2dt_native_clean_full_scope_isolation_replay_record": "isolation_scope.json",
        "external_lh2dt_native_clean_full_scope_isolation_replay_source_digest": "b" * 64,
        "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_sha256": "c" * 64,
        "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_scenario_count": 3,
        "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_receptor_count": 1,
        "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_source_campaign_physics_executed": True,
        "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_source_campaign_fresh_physics_cases": 24,
        "external_lh2dt_native_clean_full_scope_isolation_replay_facility_risk_summary_assessment_fresh_physics_executed": False,
        "external_lh2dt_native_clean_full_scope_isolation_replay_packet_count": 24,
        "external_lh2dt_native_clean_full_scope_isolation_replay_executed_case_count": 24,
        "external_lh2dt_native_clean_full_scope_isolation_replay_uncomputed_case_count": 0,
        "external_lh2dt_native_clean_full_scope_isolation_replay_failed_case_count": 0,
        "external_lh2dt_native_clean_full_scope_isolation_replay_risk_atom_count": 96,
        "external_lh2dt_native_clean_full_scope_isolation_replay_transfer_valve_isolation_success_count": 5,
        "external_lh2dt_native_clean_full_scope_isolation_replay_facility_qra_claim": False,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["native_external_clean_full_scope_isolation_replay_valid"] is True
    assert result["native_external_clean_full_scope_isolation_replay_facility_risk_summary_valid"] is True
    assert result["native_external_clean_full_scope_isolation_replay_packet_count"] == 24


def test_latest_ijhe_audit_verification_binds_clean_native_multi_equipment_recheck(tmp_path: Path):
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
    _write(tmp_path / "native_recheck.json", _native_multi_equipment_recheck())
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "external_lh2dt_native_multi_equipment_recheck_compact_record": "native_recheck.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["native_external_multi_equipment_recheck_valid"] is True
    assert result["native_external_multi_equipment_recheck_equipment_count"] == 2
    assert result["native_external_multi_equipment_recheck_dynamic_closure_ready_count"] == 1


def test_latest_ijhe_audit_verification_blocks_native_recheck_promotion_flags(tmp_path: Path):
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
    bad = _native_multi_equipment_recheck()
    bad["facility_qra_claim"] = True
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    _write(tmp_path / "native_recheck.json", bad)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "external_lh2dt_native_multi_equipment_recheck_compact_record": "native_recheck.json",
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("native external multi-equipment recheck" in reason for reason in result["blocking_reasons"])


def test_latest_ijhe_audit_verification_blocks_native_recheck_status_digest_drift(tmp_path: Path):
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
    _write(tmp_path / "native_recheck.json", _native_multi_equipment_recheck())
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "external_lh2dt_native_multi_equipment_recheck_compact_record": "native_recheck.json",
        "external_lh2dt_native_multi_equipment_recheck_compact_source_digest": "b" * 64,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("source_digest" in reason for reason in result["blocking_reasons"])


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


def test_latest_ijhe_audit_verification_accepts_nonpromoting_pseudosource_record(tmp_path: Path):
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
    pseudo = {
        "schema_version": "prism.slabx_lh2_pseudosource_numerical_sensitivity.v1",
        "status": "DIAGNOSTIC_PSEUDOSOURCE_CONVERGENCE_ACCEPTED",
        "accepted": True,
        "promotion_policy": {
            "actual_ffi_test6_source_gate_closed": False,
            "independent_physical_validation_claim": False,
            "facility_qra_claim": False,
        },
    }
    _write(tmp_path / "audit.json", audit)
    _write(tmp_path / "handoff.json", handoff)
    _write(tmp_path / "pseudo.json", pseudo)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "slabx_lh2_pseudosource_numerical_sensitivity_record": "pseudo.json",
        "slabx_lh2_pseudosource_numerical_sensitivity_status": "DIAGNOSTIC_PSEUDOSOURCE_CONVERGENCE_ACCEPTED",
        "slabx_lh2_pseudosource_numerical_sensitivity_accepted": True,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "PASS"
    assert result["pseudo_source_numerical_sensitivity_accepted"] is True


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


def test_latest_ijhe_audit_verification_rejects_asset_summary_count_drift(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"status": "PASS"}],
        "blocking_reasons": [],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    handoff = {
        "schema_version": "prism.inspection_center_facility_ijhe_handoff_audit.v1",
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
        "asset_summary": {
            "tank": {
                "case_count": 1,
                "strict_release_boundary_eligible_case_count": 1,
                "strict_release_boundary_blocked_case_count": 0,
            }
        },
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
    assert any("asset summary case count" in reason for reason in result["blocking_reasons"])


def test_latest_ijhe_audit_verification_rejects_embedded_release_snapshot_drift(tmp_path: Path):
    audit = {
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [
            {
                "name": "diagnostic_release_boundary_case_audit",
                "status": "PASS",
                "evidence": {
                    "case_count": 2,
                    "strict_release_boundary_eligible_case_count": 2,
                    "strict_release_boundary_blocked_case_count": 0,
                    "provider_termination_evidence_status_counts": {"VALID": 2},
                    "provider_termination_evidence_used_case_count": 2,
                },
            }
        ],
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
    release = {
        "schema_version": "prism.release_boundary_case_audit.v1",
        "status": "CASE_BOUNDARY_PARTIAL",
        "case_count": 2,
        "strict_release_boundary_eligible_case_count": 1,
        "strict_release_boundary_blocked_case_count": 1,
        "provider_termination_evidence_status_counts": {"VALID": 1, "INVALID": 1},
        "provider_termination_evidence_used_case_count": 1,
        "facility_ir_fn_promotion": False,
        "provider_qualification_claim": False,
        "independent_physical_validation_claim": False,
    }
    for name, value in {
        "audit.json": audit,
        "handoff.json": handoff,
        "release.json": release,
    }.items():
        _write(tmp_path / name, value)
    status = {
        "latest_ijhe_completion_audit_record": "audit.json",
        "latest_ijhe_completion_audit_status": "INCOMPLETE_EVIDENCE",
        "latest_ijhe_completion_audit_check_count": 1,
        "latest_ijhe_completion_audit_blocking_reason_count": 0,
        "inspection_center_facility_ijhe_handoff_audit_record": "handoff.json",
        "latest_release_boundary_case_audit": "release.json",
        "latest_union_case_count": 2,
        "latest_ijhe_completion_audit_release_boundary_eligible_case_count": 1,
        "latest_ijhe_completion_audit_release_boundary_blocked_case_count": 1,
    }
    result = verify_latest_ijhe_audit(status, root=tmp_path)
    assert result["status"] == "BLOCKED_AUDIT_METADATA"
    assert any("embedded release-boundary" in reason for reason in result["blocking_reasons"])
