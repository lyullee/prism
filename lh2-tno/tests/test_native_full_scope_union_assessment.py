import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "results" / "20261026" / "native_full_scope_union_assessment"


def _load(name: str) -> dict:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_native_full_scope_union_adds_vertical_handoff_without_qra_promotion():
    verification = _load("verification.json")
    result = _load("campaign_result.json")
    scope = _load("scope_matrix.json")
    assessment = _load("facility_assessment.json")
    evidence_request = _load("facility_evidence_request.json")
    validation_matrix = _load("validation_evidence_matrix.json")
    benchmark = _load("realtime_cache_benchmark.json")
    rebound = _load("vertical_handoff_rebound_result.json")
    inventory_rebound = _load("inventory_depletion_rebound_result.json")
    audit = _load("ijhe_completion_audit.json")

    assert verification["base_event_count"] == 24
    assert verification["vertical_event_count"] == 5
    assert verification["inventory_depletion_event_count"] == 5
    assert verification["merged_event_count"] == 34
    assert verification["merged_case_count"] == 44
    assert verification["merged_risk_atom_count"] == 176
    assert verification["vertical_handoff_status"] == "PARTIAL"
    assert verification["vertical_handoff_conditional_status"] == "EXECUTED"
    assert verification["vertical_handoff_conditional_executed_case_count"] == 10
    assert verification["vertical_handoff_operator_limited_case_count"] == 10
    assert verification["facility_total_risk_available"] is False
    assert verification["complete_facility_qra_claim"] is False
    assert verification["qualified_provider_packet_case_count"] == 0
    assert verification["physical_validation_claim"] is False
    assert verification["facility_evidence_request_status"] == "OPEN_EVIDENCE_REQUEST"
    assert verification["facility_evidence_request_family_count"] == 12
    assert verification["inventory_depletion_status"] == "PARTIAL"
    assert verification["inventory_depletion_conditional_status"] == "EXECUTED"
    assert verification["inventory_depletion_conditional_executed_case_count"] == 28
    assert verification["inventory_depletion_operator_limited_case_count"] == 17
    assert verification["facility_evidence_request_case_count"] == 44
    assert verification["facility_evidence_request_promotion_allowed"] is False
    assert verification["population_accounting_status"] == "RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC"
    assert verification["population_accounting_mismatch_count"] == 0
    assert verification["validation_evidence_matrix_status"] == "RESTRICTED_EVIDENCE_MATRIX"
    assert verification["validation_evidence_matrix_decision"] == "FACILITY_QRA_WITHHELD"
    assert verification["validation_evidence_matrix_domain_count"] == 6
    assert verification["validation_evidence_matrix_physical_validation_claim"] is False
    assert verification["validation_evidence_matrix_facility_qra_claim"] is False
    assert verification["realtime_cache_benchmark_cache_hits"] == 10
    assert verification["realtime_cache_benchmark_cache_p95_ms"] < 1000.0
    assert verification["realtime_cache_benchmark_fresh_physics_meets_one_hz"] is False
    assert verification["ijhe_audit_status"] == "INCOMPLETE_EVIDENCE"
    assert verification["ijhe_audit_check_count"] == 22
    assert verification["ijhe_audit_pass_count"] == 18
    assert verification["native_scope_packet_catalog_status"] == (
        "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_EXECUTED"
    )
    assert verification["native_scope_packet_catalog_event_count"] == 24
    assert verification["native_scope_packet_catalog_exact_packet_count"] == 24
    assert verification["state_snapshot_binding_status"] == "STATE_SNAPSHOT_BOUND_AND_ECHOED"
    assert verification["state_snapshot_binding_record_count"] == 24
    assert verification["state_snapshot_binding_bound_count"] == 24
    assert verification["state_snapshot_binding_unbound_count"] == 0
    assert verification["ijhe_audit_blocked_count"] == 4

    assert result["event_count"] == 34
    assert result["case_count"] == 44
    assert len(result["risk_atoms"]) == 176
    assert result["facility_id"] == "generic-lh2-near-receptor-diagnostic"
    assert rebound["vertical_handoff_rebind"]["diagnostic_only"] is True
    assert rebound["vertical_handoff_rebind"]["facility_qra_claim"] is False
    assert rebound["vertical_handoff_rebind"]["condition_rebind_policy"] == (
        "namespaced_condition_ids_preserve_source_weather"
    )
    assert inventory_rebound["campaign_namespace_rebind"]["diagnostic_only"] is True
    assert inventory_rebound["campaign_namespace_rebind"]["facility_qra_claim"] is False
    assert inventory_rebound["campaign_namespace_rebind"]["condition_rebind_policy"] == (
        "namespaced_condition_ids_preserve_source_weather"
    )

    rows = {row["family"]: row for row in scope["rows"]}
    assert rows["vertical_handoff"]["status"] == "PARTIAL"
    assert rows["vertical_handoff"]["conditional_status"] == "EXECUTED"
    assert rows["vertical_handoff"]["generated_event_count"] == 5
    assert rows["vertical_handoff"]["case_count"] == 10
    assert rows["inventory_depletion"]["status"] == "PARTIAL"
    assert rows["inventory_depletion"]["conditional_status"] == "EXECUTED"
    assert rows["inventory_depletion"]["generated_event_count"] == 23
    assert rows["inventory_depletion"]["case_count"] == 28
    assert rows["inventory_depletion"]["conditional_executed_case_count"] == 28
    assert assessment["conditional_diagnostic_facility_risk_available"] is True
    assert assessment["population_accounting"]["status"] == "RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC"
    assert assessment["population_accounting"]["mismatched_receptor_ids"] == {}
    assert assessment["facility_total_risk_available"] is False
    assert assessment["complete_facility_qra_claim"] is False
    assert evidence_request["status"] == "OPEN_EVIDENCE_REQUEST"
    assert evidence_request["case_request_count"] == 44
    assert len(evidence_request["family_requests"]) == 12
    assert evidence_request["promotion_gate"]["facility_ir_fn_remains_withheld_until_all_true"] is True
    assert audit["status"] == "INCOMPLETE_EVIDENCE"
    assert len(audit["checks"]) == 22
    assert sum(check["status"] == "PASS" for check in audit["checks"]) == 18
    assert sum(check["status"] == "BLOCKED" for check in audit["checks"]) == 4
    vertical_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_vertical_handoff_evidence"
    )
    assert vertical_check["status"] == "PASS"
    realtime_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_realtime_cache_benchmark"
    )
    assert realtime_check["status"] == "PASS"
    matrix_check = next(
        check for check in audit["checks"]
        if check["name"] == "validation_evidence_matrix"
    )
    assert matrix_check["status"] == "PASS"
    full_bore_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_native_full_bore_chain"
    )
    assert full_bore_check["status"] == "PASS"
    assert full_bore_check["diagnostic_only"] is True
    assert validation_matrix["status"] == "RESTRICTED_EVIDENCE_MATRIX"
    assert validation_matrix["decision"] == "FACILITY_QRA_WITHHELD"
    assert validation_matrix["physical_validation_claim"] is False
    assert validation_matrix["facility_qra_claim"] is False
    assert benchmark["cache_hits"] == 10
    assert benchmark["fresh_physics_meets_one_hz"] is False
    assert benchmark["realtime_fresh_physics_claim"] is False
