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
    facility = _load("facility.json")
    scope = _load("scope_matrix.json")
    assessment = _load("facility_assessment.json")
    evidence_request = _load("facility_evidence_request.json")
    validation_matrix = _load("validation_evidence_matrix.json")
    benchmark = _load("realtime_cache_benchmark.json")
    rebound = _load("vertical_handoff_rebound_result.json")
    inventory_rebound = _load("inventory_depletion_rebound_result.json")
    audit = _load("ijhe_completion_audit.json")
    objective_audit = _load("ijhe_objective_coverage_audit.json")
    case_packet_coverage = _load("facility_case_packet_coverage.json")
    base_state_binding = _load("base_result_state_snapshot_binding.json")
    scope_ledger_consistency = _load("scope_ledger_consistency_current.json")
    atom_chain = _load("risk_atom_chain_audit.json")
    equipment_chain = _load("equipment_state_release_audit.json")
    aggregate_chain = _load("facility_aggregate_closure_audit.json")
    component_contribution_chain = _load("facility_component_contribution_audit.json")
    frequency_uncertainty_chain = _load("facility_frequency_uncertainty_audit.json")
    status_consistency = _load("status_consistency_current.json")
    provider_packet_input_audit = _load("provider_packet_input_audit.json")
    observed_state_release_binding_audit = _load("observed_state_release_binding_audit.json")
    observed_component_mapping_audit = _load("observed_component_mapping_audit.json")
    observed_state_model_binding_audit = _load("observed_state_model_binding_audit.json")
    consequence_backend_chain_audit = _load("consequence_backend_chain_audit.json")
    provider_packet_collection_manifest = _load("provider_packet_collection_manifest.json")

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
    assert verification["validation_evidence_matrix_domain_count"] == 7
    assert verification["validation_evidence_matrix_physical_validation_claim"] is False
    assert verification["validation_evidence_matrix_facility_qra_claim"] is False
    assert verification["realtime_cache_benchmark_cache_hits"] == 10
    assert verification["realtime_cache_benchmark_cache_p95_ms"] < 1000.0
    assert verification["realtime_cache_benchmark_fresh_physics_meets_one_hz"] is False
    assert verification["ijhe_audit_status"] == "INCOMPLETE_EVIDENCE"
    assert verification["ijhe_audit_check_count"] == 39
    assert verification["ijhe_audit_pass_count"] == 34
    assert verification["ijhe_audit_blocked_count"] == 5
    assert verification["ijhe_audit_blocked_check_ids"] == [
        "facility_release_boundary",
        "actual_provider_release_packet",
        "declared_major_accident_scope",
        "facility_ir_fn_available",
        "facility_case_provider_packet_coverage",
    ]
    assert verification["facility_case_packet_coverage_status"] == "NO_CASE_MATCH"
    assert verification["facility_case_packet_coverage_case_count"] == 44
    assert verification["facility_case_packet_coverage_qualified_case_count"] == 0
    assert verification["isolation_union_extension_status"] == (
        "ISOLATION_UNION_EXTENSION_DIAGNOSTIC"
    )
    assert verification["isolation_union_extension_merged_event_count"] == 39
    assert verification["isolation_union_extension_merged_case_count"] == 64
    assert verification["isolation_union_extension_merged_risk_atom_count"] == 256
    assert verification["isolation_union_extension_provider_response_consumed"] is True
    assert verification["isolation_union_extension_state_snapshot_bound_cases"] == 20
    assert verification["native_scope_packet_catalog_status"] == (
        "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_EXECUTED"
    )
    assert verification["native_scope_packet_catalog_event_count"] == 24
    assert verification["native_scope_packet_catalog_exact_packet_count"] == 24
    assert verification["state_snapshot_binding_status"] == "STATE_SNAPSHOT_BOUND_AND_ECHOED"
    assert verification["state_snapshot_binding_record_count"] == 24
    assert verification["state_snapshot_binding_bound_count"] == 24
    assert verification["state_snapshot_binding_unbound_count"] == 0
    assert verification["base_result_state_snapshot_binding_status"] == (
        "STATE_SNAPSHOT_RESULT_BOUND_AND_ECHOED"
    )
    assert verification["base_result_state_snapshot_binding_event_count"] == 24
    assert verification["base_result_state_snapshot_binding_case_count"] == 43
    assert verification["base_result_state_snapshot_binding_risk_atom_count"] == 96
    assert verification["scope_ledger_consistency_status"] == "CONSISTENT_SCOPE_LEDGER"
    assert verification["scope_ledger_consistency_blocking_reason_count"] == 0
    assert verification["scope_ledger_consistency_scope_event_count"] == 34
    assert verification["scope_ledger_consistency_ledger_event_count"] == 34
    assert verification["risk_atom_chain_audit_status"] == (
        "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    )
    assert verification["risk_atom_chain_audit_case_count"] == 44
    assert verification["risk_atom_chain_audit_complete_case_count"] == 44
    assert verification["risk_atom_chain_audit_risk_atom_count"] == 176
    assert verification["risk_atom_chain_audit_blocking_reason_count"] == 0
    assert verification["equipment_state_release_audit_status"] == (
        "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
    )
    assert verification["equipment_state_release_audit_case_count"] == 44
    assert verification["equipment_state_release_audit_complete_case_count"] == 44
    assert verification["equipment_state_release_audit_component_count"] == 9
    assert verification["equipment_state_release_audit_blocking_reason_count"] == 0
    assert verification["facility_aggregate_closure_audit_status"] == (
        "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
    )
    assert verification["facility_aggregate_closure_audit_risk_atom_count"] == 176
    assert verification["facility_aggregate_closure_audit_ir_mismatch_count"] == 0
    assert verification["facility_aggregate_closure_audit_fn_mismatch_count"] == 0
    assert verification["facility_aggregate_closure_audit_blocking_reason_count"] == 0
    assert verification["facility_component_contribution_audit_status"] == (
        "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
    )
    assert verification["facility_component_contribution_audit_component_count"] == 9
    assert verification["facility_component_contribution_audit_risk_atom_count"] == 176
    assert verification["facility_component_contribution_audit_mismatch_count"] == 0
    assert verification["facility_component_contribution_audit_blocking_reason_count"] == 0
    assert component_contribution_chain["status"] == (
        "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
    )
    assert component_contribution_chain["component_count"] == 9
    assert component_contribution_chain["mismatch_count"] == 0
    assert verification["facility_frequency_uncertainty_audit_status"] == (
        "FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC"
    )
    assert verification["facility_frequency_uncertainty_audit_scenario_count"] == 5
    assert verification["facility_frequency_uncertainty_audit_risk_atom_count"] == 176
    assert verification["facility_frequency_uncertainty_audit_mismatch_count"] == 0
    assert verification["facility_frequency_uncertainty_audit_blocking_reason_count"] == 0
    assert frequency_uncertainty_chain["status"] == (
        "FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC"
    )
    assert frequency_uncertainty_chain["scenario_count"] == 5
    assert frequency_uncertainty_chain["mismatch_count"] == 0
    assert provider_packet_input_audit["schema"] == "prism.provider_packet_input_audit.v1"
    assert provider_packet_input_audit["status"] == "NO_PROVIDER_PACKET_INPUT"
    assert provider_packet_input_audit["accepted_provider_packet_count"] == 0
    assert observed_state_release_binding_audit["schema"] == (
        "prism.observed_state_release_binding_audit.v1"
    )
    assert observed_state_release_binding_audit["status"] == "NO_STATE_TO_RELEASE_BINDING"
    assert observed_state_release_binding_audit["observed_component_count"] == 3
    assert observed_state_release_binding_audit["mapped_component_count"] == 0
    assert observed_state_release_binding_audit["unmapped_component_count"] == 3
    assert observed_component_mapping_audit["schema"] == (
        "prism.observed_component_mapping_audit.v1"
    )
    assert observed_component_mapping_audit["status"] == (
        "CANDIDATE_COMPONENT_CLASS_MAPPINGS_ONLY"
    )
    assert observed_component_mapping_audit["observed_component_count"] == 3
    assert observed_component_mapping_audit["candidate_mapping_count"] == 3
    assert observed_component_mapping_audit["exact_facility_component_count"] == 0
    assert observed_component_mapping_audit["policy"]["release_event_binding_is_not_created"] is True
    assert consequence_backend_chain_audit["schema"] == (
        "prism.consequence_backend_chain_audit.v1"
    )
    assert consequence_backend_chain_audit["status"] == (
        "FULL_CONSEQUENCE_BACKEND_CHAIN_DIAGNOSTIC"
    )
    assert consequence_backend_chain_audit["case_count"] == 44
    assert consequence_backend_chain_audit["closed_case_count"] == 44
    assert consequence_backend_chain_audit["stage_count"] == 8
    assert provider_packet_collection_manifest["schema"] == (
        "prism.provider_packet_collection_manifest.v1"
    )
    assert provider_packet_collection_manifest["status"] == (
        "OPEN_PROVIDER_PACKET_COLLECTION"
    )
    assert provider_packet_collection_manifest["request_count"] == 44
    assert provider_packet_collection_manifest["open_request_count"] == 44
    assert provider_packet_collection_manifest["qualified_packet_count"] == 0
    assert all(
        row["status"] == "OPEN"
        and row["release_path"] is None
        and row["qualification_path"] is None
        for row in provider_packet_collection_manifest["rows"]
    )
    assert status_consistency["status"] == "CONSISTENT"
    assert len(status_consistency["checks"]) == 25
    assert next(
        row for row in status_consistency["checks"]
        if row["name"] == "provider_packet_input_audit"
    )["status"] == "PASS"
    assert next(
        row for row in status_consistency["checks"]
        if row["name"] == "observed_state_release_binding_audit"
    )["status"] == "PASS"
    assert next(
        row for row in status_consistency["checks"]
        if row["name"] == "observed_component_mapping_audit"
    )["status"] == "PASS"
    assert observed_state_model_binding_audit["schema"] == (
        "prism.observed_state_model_binding_audit.v1"
    )
    assert observed_state_model_binding_audit["status"] == (
        "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY"
    )
    assert observed_state_model_binding_audit["observed_component_count"] == 3
    assert observed_state_model_binding_audit["state_model_bound_component_count"] == 3
    assert observed_state_model_binding_audit["diagnostic_release_adapter_component_count"] == 3
    assert observed_state_model_binding_audit["qualified_provider_packet_count"] == 0
    assert observed_state_model_binding_audit["policy"]["facility_ir_fn_promotion"] is False
    assert next(
        row for row in status_consistency["checks"]
        if row["name"] == "observed_state_model_binding_audit"
    )["status"] == "PASS"
    assert next(
        row for row in status_consistency["checks"]
        if row["name"] == "consequence_backend_chain_audit"
    )["status"] == "PASS"
    assert next(
        row for row in status_consistency["checks"]
        if row["name"] == "provider_packet_collection_manifest"
    )["status"] == "PASS"
    assert status_consistency["blocking_reasons"] == []
    assert status_consistency["facility_ir_fn_promotion"] is False

    assert result["event_count"] == 34
    assert result["case_count"] == 44
    assert len(result["risk_atoms"]) == 176
    assert all(
        atom["provider_packet_identity"].get("state_snapshot") is not None
        and atom["provider_packet_identity"].get("state_snapshot_digest")
        and atom["provider_packet_identity"].get("provider_state_snapshot_digest")
        for atom in result["risk_atoms"]
    )
    assert sum(
        atom["provider_packet_identity"].get("provider_state_snapshot_digests") is not None
        for atom in result["risk_atoms"]
    ) == 8
    assert result["facility_id"] == "generic-lh2-near-receptor-diagnostic"
    assert result["facility_id"] == facility["id"]
    assert base_state_binding["status"] == "STATE_SNAPSHOT_RESULT_BOUND_AND_ECHOED"
    assert base_state_binding["event_count"] == 24
    assert base_state_binding["bound_case_count"] == 43
    assert base_state_binding["bound_risk_atom_count"] == 96
    assert scope_ledger_consistency["status"] == "CONSISTENT_SCOPE_LEDGER"
    assert scope_ledger_consistency["blocking_reasons"] == []
    assert any(
        harm > 0.0
        for atom in result["risk_atoms"]
        for endpoint in atom["receptor_harm_low_high"].values()
        for harm in endpoint
    )
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
    # The final union scope is rebuilt from the merged facility ledger.  This
    # keeps cross-cutting pipe cases and gas-exit packets on the same identity
    # set as the facility assessment rather than the three source matrices.
    assert rows["pipe_hole"]["generated_event_count"] == 15
    assert rows["pipe_hole"]["case_count"] == 25
    assert rows["liquid_two_phase"]["generated_event_count"] == 17
    assert rows["liquid_two_phase"]["case_count"] == 17
    assert scope["provider_worklist_alignment"]["status"] == "ALIGNED"
    assert scope["provider_worklist_alignment"]["facility_merge_alignment_claim"] is False
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
    assert assessment["conditional_diagnostic_facility_annual_ir_low_high"]["worker-01"][0] > 0.0
    assert assessment["population_accounting"]["status"] == "RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC"
    assert assessment["population_accounting"]["mismatched_receptor_ids"] == {}
    assert assessment["facility_total_risk_available"] is False
    assert assessment["complete_facility_qra_claim"] is False
    assert assessment["strict_release_boundary"]["strict_release_boundary_ready"] is False
    assert case_packet_coverage["status"] == "NO_CASE_MATCH"
    assert case_packet_coverage["case_request_count"] == 44
    assert case_packet_coverage["qualified_provider_case_count"] == 0
    assert case_packet_coverage["status_counts"] == {
        "MISSING_QUALIFIED_PROVIDER_EVIDENCE": 44
    }
    assert evidence_request["status"] == "OPEN_EVIDENCE_REQUEST"
    assert evidence_request["case_request_count"] == 44
    assert len(evidence_request["family_requests"]) == 12
    assert evidence_request["promotion_gate"]["facility_ir_fn_remains_withheld_until_all_true"] is True
    assert audit["status"] == "INCOMPLETE_EVIDENCE"
    assert len(audit["checks"]) == 39
    assert sum(check["status"] == "PASS" for check in audit["checks"]) == 34
    assert sum(check["status"] == "BLOCKED" for check in audit["checks"]) == 5
    assert objective_audit["status"] == "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"
    assert len(objective_audit["checks"]) == 13
    assert objective_audit["strict_blocking_check_ids"] == [
        "independent_physical_validation",
        "qualified_provider_evidence",
        "strict_facility_scope",
        "strict_facility_qra",
    ]
    release_boundary_check = next(
        check for check in audit["checks"]
        if check["name"] == "facility_release_boundary"
    )
    assert release_boundary_check["status"] == "BLOCKED"
    coverage_check = next(
        check for check in audit["checks"]
        if check["name"] == "facility_case_provider_packet_coverage"
    )
    assert coverage_check["status"] == "BLOCKED"
    assert coverage_check["evidence"]["case_request_count"] == 44
    consistency_check = next(
        check for check in audit["checks"]
        if check["name"] == "scope_ledger_consistency"
    )
    assert consistency_check["status"] == "PASS"
    assert consistency_check["evidence"]["scope_event_count"] == 34
    assert consistency_check["evidence"]["ledger_event_count"] == 34
    atom_chain_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_risk_atom_chain_closure"
    )
    assert atom_chain_check["status"] == "PASS"
    assert atom_chain_check["evidence"]["case_count"] == 44
    assert atom_chain_check["evidence"]["risk_atom_count"] == 176
    assert atom_chain["status"] == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    assert atom_chain["case_count"] == 44
    assert atom_chain["complete_case_count"] == 44
    assert atom_chain["risk_atom_count"] == 176
    assert atom_chain["operator_limited_case_count"] == 29
    equipment_chain_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_equipment_state_release_chain"
    )
    assert equipment_chain_check["status"] == "PASS"
    assert equipment_chain_check["evidence"]["case_count"] == 44
    assert equipment_chain_check["evidence"]["component_count"] == 9
    assert equipment_chain["status"] == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
    assert equipment_chain["complete_case_count"] == 44
    assert equipment_chain["component_count"] == 9
    assert equipment_chain["provider_termination_echo_gap_case_count"] == 0
    aggregate_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_facility_ir_fn_aggregate_closure"
    )
    assert aggregate_check["status"] == "PASS"
    assert aggregate_check["evidence"]["risk_atom_count"] == 176
    assert aggregate_check["evidence"]["ir_mismatch_count"] == 0
    assert aggregate_check["evidence"]["fn_mismatch_count"] == 0
    assert aggregate_chain["status"] == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
    assert aggregate_chain["risk_atom_count"] == 176
    assert aggregate_chain["ir_mismatch_count"] == 0
    assert aggregate_chain["fn_mismatch_count"] == 0
    assert aggregate_chain["blocking_reasons"] == []
    component_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_facility_component_contribution_closure"
    )
    assert component_check["status"] == "PASS"
    assert component_check["evidence"]["component_count"] == 9
    assert component_check["evidence"]["mismatch_count"] == 0
    frequency_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_facility_frequency_uncertainty_closure"
    )
    assert frequency_check["status"] == "PASS"
    assert frequency_check["evidence"]["scenario_count"] == 5
    assert frequency_check["evidence"]["risk_atom_count"] == 176
    assert frequency_check["evidence"]["mismatch_count"] == 0
    assert release_boundary_check["evidence"]["schema"] == (
        "prism.facility_release_boundary_gate.v1"
    )
    assert release_boundary_check["evidence"]["schema_version"] == (
        "prism.facility_release_boundary_gate.v1"
    )
    assert release_boundary_check["evidence"]["facility_gate_checks"] == {
        "all_rows_complete": False,
        "all_termination_bases_allowed": False,
        "all_isolation_or_inventory_statuses_closed": True,
        "all_mass_residuals_closed": False,
        "no_withheld_cases": False,
    }
    assert release_boundary_check["evidence"]["raw_ledger_reconciliation"]["status"] == (
        "MATCHED"
    )
    state_snapshot_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_equipment_state_snapshot_binding"
    )
    assert state_snapshot_check["status"] == "PASS"
    observed_state_check = next(
        check for check in audit["checks"]
        if check["name"] == "diagnostic_observed_equipment_state_evidence"
    )
    assert observed_state_check["status"] == "PASS"
    assert observed_state_check["evidence"]["sample_count"] == 8955
    assert observed_state_check["evidence"]["component_count"] == 3
    provider_worklist_check = next(
        check for check in audit["checks"]
        if check["name"] == "provider_worklist_coverage"
    )
    assert provider_worklist_check["status"] == "PASS"
    assert provider_worklist_check["evidence"]["native_scope_catalog_structural_coverage"] is True
    actual_provider_check = next(
        check for check in audit["checks"]
        if check["name"] == "actual_provider_release_packet"
    )
    assert actual_provider_check["status"] == "BLOCKED"
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
