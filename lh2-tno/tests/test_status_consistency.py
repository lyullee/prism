"""Tests for the cross-artifact readiness ledger audit."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from lh2_tno.status_consistency import build_status_consistency_report, load_json_object


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json"
ASSESSMENT = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json"
EVIDENCE_REQUEST = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_evidence_request.json"
LEDGER = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/campaign_result.json"
COVERAGE = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_case_packet_coverage.json"
CURRENT_PROVIDER_INPUT_AUDIT = ROOT / "results/20261026/native_full_scope_union_assessment/provider_packet_input_audit.json"
CURRENT_STATE_RELEASE_BINDING_AUDIT = ROOT / "results/20261026/native_full_scope_union_assessment/observed_state_release_binding_audit.json"
CURRENT_COMPONENT_MAPPING_AUDIT = ROOT / "results/20261026/native_full_scope_union_assessment/observed_component_mapping_audit.json"
CURRENT_STATE_MODEL_BINDING_AUDIT = ROOT / "results/20261026/native_full_scope_union_assessment/observed_state_model_binding_audit.json"
CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT = ROOT / "results/20261026/native_full_scope_union_assessment/consequence_backend_chain_audit.json"
CURRENT_PROVIDER_PACKET_COLLECTION_MANIFEST = ROOT / "results/20261026/native_full_scope_union_assessment/provider_packet_collection_manifest.json"
CURRENT_AUDIT = ROOT / "results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json"
CURRENT_ASSESSMENT = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json"
CURRENT_EVIDENCE_REQUEST = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_evidence_request.json"
CURRENT_LEDGER = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/campaign_result.json"
CURRENT_COVERAGE = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_case_packet_coverage.json"


def _report(**overrides):
    values = {
        "current_status": load_json_object(ROOT / "CURRENT_STATUS.json"),
        "development_goal": load_json_object(ROOT / "DEVELOPMENT_GOAL.json"),
        "audit": load_json_object(AUDIT),
        "assessment": load_json_object(ASSESSMENT),
        "evidence_request": load_json_object(EVIDENCE_REQUEST),
        "ledger": load_json_object(LEDGER),
        "coverage": load_json_object(COVERAGE),
        "audit_filename": AUDIT.name,
        "assessment_filename": ASSESSMENT.name,
        "evidence_request_filename": EVIDENCE_REQUEST.name,
        "ledger_filename": LEDGER.name,
        "coverage_filename": COVERAGE.name,
    }
    values.update(overrides)
    return build_status_consistency_report(**values)


def test_current_published_artifacts_are_consistent() -> None:
    report = _report()
    assert report["status"] == "CONSISTENT"
    assert report["blocking_reasons"] == []
    assert report["facility_ir_fn_promotion"] is False
    assert all(row["status"] == "PASS" for row in report["checks"])


def test_current_status_aliases_match_authoritative_union_and_audit() -> None:
    """Prevent a current-status alias from silently reverting to an old snapshot."""
    status = load_json_object(ROOT / "CURRENT_STATUS.json")
    audit = load_json_object(CURRENT_AUDIT)
    assessment = load_json_object(CURRENT_ASSESSMENT)
    assert status["full_portable_test_count_latest"] == status["current_union_full_test_count"]
    assert str(status["full_portable_test_count_latest"]) in status["full_portable_test_status_latest"]
    assert status["latest_ijhe_audit_metadata_verifier_check_count"] == len(audit["checks"])
    assert status["latest_union_event_count"] == assessment["event_count"]
    assert status["latest_union_case_count"] == assessment["case_count"]
    assert status["latest_union_risk_atom_count"] == assessment["risk_atom_count"]
    population_status = status["facility_population_accounting_latest_status"]
    assert f"{assessment['event_count']} events" in population_status
    assert f"{assessment['case_count']} cases" in population_status
    assert f"{assessment['risk_atom_count']} risk atoms" in population_status


def test_latest_external_evidence_recheck_includes_separate_equipment_model_root() -> None:
    status = load_json_object(ROOT / "CURRENT_STATUS.json")
    record_path = ROOT / status["latest_external_evidence_recheck_record"]
    record = load_json_object(record_path)
    summary = record["summary"]
    assert record["root_count"] == 6
    assert summary["artifact_count"] == 707
    assert summary["provider_response_count"] == 7
    assert summary["qualification_artifact_count"] == 0
    assert summary["physical_validation_artifact_count"] == 0
    equipment_root = record["roots"]["inspection_center_equipment_model"]
    assert equipment_root["artifact_count"] == 662
    assert equipment_root["provider_response_count"] == 7
    assert equipment_root["qualification_artifact_count"] == 0
    assert status["latest_external_evidence_recheck_facility_ir_fn_allowed"] is False


def test_latest_github_actions_run_is_bound_to_both_status_ledgers() -> None:
    report = _report()
    check = next(
        row for row in report["checks"] if row["name"] == "latest_github_actions_run"
    )
    assert check["status"] == "PASS"
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["latest_github_actions_run"]["conclusion"] = "failure"
    drifted = _report(current_status=current_status)
    drifted_check = next(
        row
        for row in drifted["checks"]
        if row["name"] == "latest_github_actions_run"
    )
    assert drifted_check["status"] == "FAIL"
    assert drifted["status"] == "INCONSISTENT"


def test_latest_case_coverage_pointer_carries_current_counts() -> None:
    report = _report()
    check = next(
        row for row in report["checks"]
        if row["name"] == "latest_facility_case_packet_coverage_pointer"
    )
    assert check["status"] == "PASS"
    assert check["evidence"]["published_case_count"] == 44
    assert check["evidence"]["published_qualified_case_count"] == 0


def test_latest_case_coverage_pointer_drift_is_blocked() -> None:
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["latest_facility_case_packet_coverage_case_count"] = 34
    report = _report(current_status=current_status)
    check = next(
        row for row in report["checks"]
        if row["name"] == "latest_facility_case_packet_coverage_pointer"
    )
    assert check["status"] == "FAIL"
    assert report["status"] == "INCONSISTENT"


def test_current_union_pointer_evidence_reports_current_audit_counts() -> None:
    report = build_status_consistency_report(
        current_status=load_json_object(ROOT / "CURRENT_STATUS.json"),
        development_goal=load_json_object(ROOT / "DEVELOPMENT_GOAL.json"),
        audit=load_json_object(CURRENT_AUDIT),
        assessment=load_json_object(CURRENT_ASSESSMENT),
        evidence_request=load_json_object(CURRENT_EVIDENCE_REQUEST),
        ledger=load_json_object(CURRENT_LEDGER),
        coverage=load_json_object(CURRENT_COVERAGE),
        audit_filename=CURRENT_AUDIT.name,
        assessment_filename=CURRENT_ASSESSMENT.name,
        evidence_request_filename=CURRENT_EVIDENCE_REQUEST.name,
        ledger_filename=CURRENT_LEDGER.name,
        coverage_filename=CURRENT_COVERAGE.name,
    )
    assert report["status"] == "CONSISTENT"
    for name in ("current_status_audit_pointer", "development_goal_audit_pointer"):
        evidence = next(row for row in report["checks"] if row["name"] == name)["evidence"]
        assert evidence["check_count"] == 60
        assert evidence["blocking_reason_count"] == 5
        gate_check = next(
            row for row in load_json_object(CURRENT_AUDIT)["checks"]
            if row["name"] == "diagnostic_forecast_facility_campaign_evidence_gate"
        )
        assert gate_check["status"] == "PASS"
        assert gate_check["evidence"]["computed_gate_status"] == (
            "WITHHELD_FORECAST_FACILITY_CAMPAIGN_MISSING_QUANTITATIVE_EVIDENCE"
        )
        assert gate_check["evidence"]["downstream_campaign_input_allowed"] is False


def test_current_provider_packet_input_audit_is_bound_to_status_ledgers() -> None:
    report = _report(
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
    )
    check = next(row for row in report["checks"] if row["name"] == "provider_packet_input_audit")
    assert check["status"] == "PASS"
    assert report["status"] == "CONSISTENT"


def test_provider_packet_input_audit_pointer_drift_is_blocked() -> None:
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["current_union_provider_packet_input_audit_record"] = "stale.json"
    report = _report(
        current_status=current_status,
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
    )
    check = next(row for row in report["checks"] if row["name"] == "provider_packet_input_audit")
    assert check["status"] == "FAIL"
    assert report["status"] == "INCONSISTENT"


def test_observed_state_release_binding_audit_is_bound_to_status_ledgers() -> None:
    report = _report(
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "observed_state_release_binding_audit"
    )
    assert check["status"] == "PASS"
    assert report["status"] == "CONSISTENT"


def test_observed_state_release_binding_pointer_drift_is_blocked() -> None:
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["current_union_observed_state_release_binding_audit_record"] = "stale.json"
    report = _report(
        current_status=current_status,
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "observed_state_release_binding_audit"
    )
    assert check["status"] == "FAIL"
    assert report["status"] == "INCONSISTENT"


def test_observed_component_mapping_audit_is_bound_to_status_ledgers() -> None:
    report = _report(
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        observed_component_mapping_audit=load_json_object(CURRENT_COMPONENT_MAPPING_AUDIT),
        observed_component_mapping_audit_filename=CURRENT_COMPONENT_MAPPING_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "observed_component_mapping_audit"
    )
    assert check["status"] == "PASS"
    assert report["status"] == "CONSISTENT"


def test_observed_component_mapping_pointer_drift_is_blocked() -> None:
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["current_union_observed_component_mapping_audit_record"] = "stale.json"
    report = _report(
        current_status=current_status,
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        observed_component_mapping_audit=load_json_object(CURRENT_COMPONENT_MAPPING_AUDIT),
        observed_component_mapping_audit_filename=CURRENT_COMPONENT_MAPPING_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "observed_component_mapping_audit"
    )
    assert check["status"] == "FAIL"
    assert report["status"] == "INCONSISTENT"


def test_observed_state_model_binding_audit_is_bound_to_status_ledgers() -> None:
    report = _report(
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        observed_component_mapping_audit=load_json_object(CURRENT_COMPONENT_MAPPING_AUDIT),
        observed_component_mapping_audit_filename=CURRENT_COMPONENT_MAPPING_AUDIT.name,
        observed_state_model_binding_audit=load_json_object(CURRENT_STATE_MODEL_BINDING_AUDIT),
        observed_state_model_binding_audit_filename=CURRENT_STATE_MODEL_BINDING_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "observed_state_model_binding_audit"
    )
    assert check["status"] == "PASS"
    assert report["status"] == "CONSISTENT"


def test_observed_state_model_binding_pointer_drift_is_blocked() -> None:
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["current_union_observed_state_model_binding_audit_record"] = "stale.json"
    report = _report(
        current_status=current_status,
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        observed_component_mapping_audit=load_json_object(CURRENT_COMPONENT_MAPPING_AUDIT),
        observed_component_mapping_audit_filename=CURRENT_COMPONENT_MAPPING_AUDIT.name,
        observed_state_model_binding_audit=load_json_object(CURRENT_STATE_MODEL_BINDING_AUDIT),
        observed_state_model_binding_audit_filename=CURRENT_STATE_MODEL_BINDING_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "observed_state_model_binding_audit"
    )
    assert check["status"] == "FAIL"
    assert report["status"] == "INCONSISTENT"


def test_consequence_backend_chain_audit_is_bound_to_status_ledgers() -> None:
    report = _report(
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        consequence_backend_chain_audit=load_json_object(
            CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT
        ),
        consequence_backend_chain_audit_filename=CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "consequence_backend_chain_audit"
    )
    assert check["status"] == "PASS"
    assert report["status"] == "CONSISTENT"


def test_consequence_backend_chain_pointer_drift_is_blocked() -> None:
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["current_union_consequence_backend_chain_audit_record"] = "stale.json"
    report = _report(
        current_status=current_status,
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        consequence_backend_chain_audit=load_json_object(
            CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT
        ),
        consequence_backend_chain_audit_filename=CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "consequence_backend_chain_audit"
    )
    assert check["status"] == "FAIL"
    assert report["status"] == "INCONSISTENT"


def test_provider_packet_collection_manifest_is_bound_to_status_ledgers() -> None:
    report = _report(
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        consequence_backend_chain_audit=load_json_object(
            CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT
        ),
        consequence_backend_chain_audit_filename=CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT.name,
        provider_packet_collection_manifest=load_json_object(
            CURRENT_PROVIDER_PACKET_COLLECTION_MANIFEST
        ),
        provider_packet_collection_manifest_filename=CURRENT_PROVIDER_PACKET_COLLECTION_MANIFEST.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "provider_packet_collection_manifest"
    )
    assert check["status"] == "PASS"
    assert report["status"] == "CONSISTENT"


def test_provider_packet_collection_pointer_drift_is_blocked() -> None:
    current_status = load_json_object(ROOT / "CURRENT_STATUS.json")
    current_status["current_union_provider_packet_collection_manifest_record"] = "stale.json"
    report = _report(
        current_status=current_status,
        provider_packet_input_audit=load_json_object(CURRENT_PROVIDER_INPUT_AUDIT),
        provider_packet_input_audit_filename=CURRENT_PROVIDER_INPUT_AUDIT.name,
        observed_state_release_binding_audit=load_json_object(
            CURRENT_STATE_RELEASE_BINDING_AUDIT
        ),
        observed_state_release_binding_audit_filename=CURRENT_STATE_RELEASE_BINDING_AUDIT.name,
        consequence_backend_chain_audit=load_json_object(
            CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT
        ),
        consequence_backend_chain_audit_filename=CURRENT_CONSEQUENCE_BACKEND_CHAIN_AUDIT.name,
        provider_packet_collection_manifest=load_json_object(
            CURRENT_PROVIDER_PACKET_COLLECTION_MANIFEST
        ),
        provider_packet_collection_manifest_filename=CURRENT_PROVIDER_PACKET_COLLECTION_MANIFEST.name,
    )
    check = next(
        row for row in report["checks"]
        if row["name"] == "provider_packet_collection_manifest"
    )
    assert check["status"] == "FAIL"
    assert report["status"] == "INCONSISTENT"


def test_changed_case_coverage_cannot_pass() -> None:
    coverage = deepcopy(load_json_object(COVERAGE))
    coverage["qualified_provider_case_count"] = 1
    report = _report(coverage=coverage)
    assert report["status"] == "INCONSISTENT"
    assert "coverage_gate" in report["blocking_reasons"]


def test_changed_risk_atom_chain_cannot_pass() -> None:
    audit = deepcopy(load_json_object(AUDIT))
    combined = next(
        row for row in audit["checks"]
        if row["name"] == "diagnostic_risk_atom_chain_closure"
    )
    combined["evidence"]["complete_case_count"] = 43
    report = _report(audit=audit)
    assert report["status"] == "INCONSISTENT"
    assert "audit_combined_chain_gate" in report["blocking_reasons"]


def test_changed_slabx_validation_cannot_pass() -> None:
    audit = deepcopy(load_json_object(AUDIT))
    slabx = next(
        row for row in audit["checks"]
        if row["name"] == "diagnostic_slabx_lh2_validation_evidence"
    )
    slabx["evidence"]["metrics"]["ffi_case_count"] = 5
    report = _report(audit=audit)
    assert report["status"] == "INCONSISTENT"
    assert "audit_slabx_validation_gate" in report["blocking_reasons"]


def test_changed_realtime_cache_benchmark_cannot_pass() -> None:
    audit = deepcopy(load_json_object(AUDIT))
    benchmark = next(
        row for row in audit["checks"]
        if row["name"] == "diagnostic_realtime_cache_benchmark"
    )
    benchmark["evidence"]["cache_p95_ms"] = 1001.0
    report = _report(audit=audit)
    assert report["status"] == "INCONSISTENT"
    assert "audit_realtime_cache_benchmark_gate" in report["blocking_reasons"]


def test_changed_domain_recovery_cannot_pass() -> None:
    audit = deepcopy(load_json_object(AUDIT))
    recovery = next(
        row for row in audit["checks"]
        if row["name"] == "diagnostic_domain_recovery_audit"
    )
    recovery["evidence"]["recovery_domain_incomplete_event_count"] = 5
    report = _report(audit=audit)
    assert report["status"] == "INCONSISTENT"
    assert "audit_domain_recovery_gate" in report["blocking_reasons"]


def test_changed_flammability_proof_cannot_pass() -> None:
    audit = deepcopy(load_json_object(AUDIT))
    recovery = next(
        row for row in audit["checks"]
        if row["name"] == "diagnostic_domain_recovery_audit"
    )
    recovery["evidence"]["recovery_flammability_proven_event_count"] = 21
    report = _report(audit=audit)
    assert report["status"] == "INCONSISTENT"
    assert "audit_domain_recovery_gate" in report["blocking_reasons"]
