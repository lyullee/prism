from lh2_tno.completion_audit import build_ijhe_completion_audit


def _campaign_result(total=True):
    return {
        "events": [{"id": "event-1"}],
        "cases": [{
            "status": "EXECUTED",
            "termination": {"basis": "synthetic", "time_s": 0.2},
            "mass_ledger": {"end_to_end_residual_kg": 0.0},
        }],
        "timing": {"fresh_physics_cases": 1, "campaign_elapsed_ms": 12.5},
        "total_facility_annual_ir_low_high": {"r1": [1e-6, 2e-6]} if total else None,
        "total_facility_expected_death_fn_low_high": [[], []] if total else None,
    }


def _matrix(complete=True):
    return {
        "matrix_complete": complete,
        "blocking_reasons": [] if complete else ["pipe_hole: UNCOMPUTED"],
        "required_families": ["pipe_hole"],
    }


def test_completion_audit_records_worklist_scope_alignment_as_diagnostic_evidence():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        {
            **_matrix(complete=False),
            "provider_worklist_alignment": {
                "status": "ALIGNED",
                "worklist_event_count": 2,
                "campaign_event_count": 2,
                "aligned_event_count": 2,
                "missing_event_ids": [],
                "primary_family_mismatches": [],
                "provider_packet_created": False,
                "frequency_inference_performed": False,
            },
        },
        _campaign_result(total=False),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "provider_worklist_scope_alignment"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_forecast_hazop_trigger_without_qra_promotion():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        hazop_forecast_scan={
            "schema_version": "prism.hazop_forecast_risk_scan.v1",
            "status": "FORECAST_RISK_SCAN_COMPLETE",
            "forecast_origin": "model_prediction",
            "steps": [{"forecast_time_s": 10.0}],
            "scenario_entries": [{
                "trigger_type": "RISK_CONDITION_REACHED",
                "evaluation": {"status": "WITHHELD_NO_QUANTITATIVE_EVALUATOR"},
            }],
            "trigger_count": 1,
            "evaluated_count": 0,
            "withheld_count": 1,
            "timing": {
                "wall_elapsed_ms": 0.8,
                "quantitative_evaluation_elapsed_ms": 0.0,
                "fresh_physics_claim": False,
            },
            "policy": {
                "operating_mode_taken_from_forecast_input": True,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "facility_qra_promotion": False,
                "diagnostic_only": True,
            },
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_hazop_forecast_risk_scan"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_domain_recovery_without_promoting_qra():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        domain_recovery_audit={
            "schema": "prism.domain_recovery_audit.v1",
            "status": "DOMAIN_RECOVERY_REVIEWED",
            "event_count": 2,
            "baseline_domain_incomplete_event_count": 1,
            "recovery_domain_incomplete_event_count": 1,
            "persistent_domain_incomplete_event_ids": ["event-1"],
            "recovered_event_ids": [],
            "facility_ir_fn_promotion": False,
            "qualified_provider_packet_promotion": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_domain_recovery_audit"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_blocks_inconsistent_scope_ledger():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        scope_ledger_consistency={
            "status": "INCONSISTENT_SCOPE_LEDGER",
            "scope_matrix_event_count": 50,
            "facility_ledger_event_count": 41,
            "scope_matrix_conditional_uncomputed_case_count": 0,
            "facility_ledger_conditional_uncomputed_case_count": 2,
            "blocking_reasons": ["event IDs disagree"],
            "facility_qra_claim": False,
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "scope_ledger_consistency")
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is False
    assert any("scope matrix and merged facility ledger" in reason for reason in report["blocking_reasons"])


def test_completion_audit_accepts_consistent_scope_ledger_without_opening_qra():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        scope_ledger_consistency={
            "status": "CONSISTENT_SCOPE_LEDGER",
            "scope_matrix_event_count": 1,
            "facility_ledger_event_count": 1,
            "scope_matrix_conditional_uncomputed_case_count": 0,
            "facility_ledger_conditional_uncomputed_case_count": 0,
            "blocking_reasons": [],
            "facility_qra_claim": False,
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "scope_ledger_consistency")
    assert check["status"] == "PASS"


def test_completion_audit_records_conditional_scope_accounting_without_opening_facility_gate():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        {
            **_matrix(complete=False),
            "conditional_chain_complete": False,
            "conditional_chain_blocking_reasons": ["pipe_hole: PARTIAL"],
            "rows": [{
                "family": "pipe_hole",
                "conditional_status": "PARTIAL",
                "conditional_executed_case_count": 1,
                "conditional_uncomputed_case_count": 2,
            }],
        },
        _campaign_result(total=False),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "conditional_accident_scope_accounting"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["conditional_chain_complete"] is False
    assert any("declared accident families" in reason for reason in report["blocking_reasons"])


def test_completion_audit_records_native_model_contract_audit_as_diagnostic_evidence():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        native_model_contract_audit={
            "schema_version": "prism.external_model_contract_audit.v1",
            "status": "NATIVE_ACCIDENT_EXPORT_MISSING",
            "binding_count": 8,
            "rows": [{}] * 8,
            "native_accident_export_component_count": 0,
            "diagnostic_adapter_contract_verified_count": 7,
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "external_native_model_contract_audit"
    )
    assert check["status"] == "PASS"


def test_completion_audit_records_native_full_bore_chain_as_diagnostic_evidence():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        native_full_bore_result={
            "schema_version": "prism.native_lh2dt_dynamic_pipe_full_bore_case.v1",
            "status": "END_TO_END_DIAGNOSTIC_EXECUTED",
            "event_id": "full-bore-01",
            "component_id": "pipe-01",
            "provider_termination_basis": "model_pressure_equalization",
            "provider_duration_s": 0.04,
            "provider_final_pressure_pa_abs": 101000.0,
            "provider_pressure_equalized": True,
            "provider_final_pressure_matches_ambient": True,
            "provider_mass_residual_kg": 0.0,
            "consequence_chain_executed": True,
            "frequency_applied": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "diagnostic_native_full_bore_chain")
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_state_snapshot_binding_as_diagnostic_evidence():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        state_snapshot_binding_audit={
            "schema_version": "prism.state_snapshot_binding_audit.v1",
            "status": "PARTIAL_STATE_SNAPSHOT_BINDING",
            "record_count": 25,
            "bound_count": 1,
            "declared_digest_only_count": 0,
            "unbound_count": 24,
            "digest_mismatch_count": 0,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "policy": {
                "digest_only_is_binding": False,
                "provider_echo_required": True,
            },
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_equipment_state_snapshot_binding"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_native_binding_reconciliation_as_diagnostic_evidence():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        native_binding_reconciliation={
            "schema_version": "prism.native_binding_reconciliation.v1",
            "status": "RECONCILED_NATIVE_INTERFACES",
            "rows": [{}],
            "native_accident_export_component_count": 1,
            "reconciled_native_component_count": 1,
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
        },
    )
    check = next(
        item for item in report["checks"] if item["name"] == "native_model_binding_reconciliation"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None


def test_completion_audit_records_native_full_bore_literature_frequency_binding():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        native_full_bore_frequency_result={
            "schema_version": "prism.native_lh2dt_dynamic_pipe_full_bore_frequency_case.v1",
            "status": "END_TO_END_DIAGNOSTIC_EXECUTED",
            "event_id": "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%",
            "frequency_event_id": "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%",
            "full_bore_match": True,
            "provider_termination_basis": "model_pressure_equalization",
            "provider_pressure_equalized": True,
            "provider_final_pressure_matches_ambient": True,
            "provider_mass_residual_kg": 0.0,
            "annual_frequency_per_year": 1.9e-7,
            "annual_frequency_provenance": "LH2_PIPE AREA_100% literature row",
            "frequency_applied": True,
            "frequency_exact_opening_match": True,
            "consequence_chain_executed": True,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_native_full_bore_frequency_binding"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None


def test_completion_audit_records_native_packet_coverage_ledger():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        provider_worklist={"generated_event_count": 1},
        native_packet_coverage_ledger={
            "schema_version": "prism.native_lh2dt_packet_coverage_ledger.v1",
            "status": "PARTIAL_NATIVE_DIAGNOSTIC_EVIDENCE",
            "packet_count": 1,
            "exact_worklist_event_count": 1,
            "consequence_chain_event_count": 1,
            "frequency_bound_event_count": 0,
            "provider_packet_promoted_count": 0,
            "physical_validation_claim_count": 0,
            "facility_qra_claim_count": 0,
            "rows": [{
                "diagnostic_only": True,
                "provider_packet_promoted": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
            }],
            "policy": {
                "diagnostic_only": True,
                "frequency_inference_performed": False,
                "provider_packet_promoted": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
            },
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "diagnostic_native_lh2dt_packet_coverage")
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_native_packet_campaign_execution():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        provider_worklist={"generated_event_count": 1},
        native_packet_campaign_ledger={
            "schema_version": "prism.native_lh2dt_packet_campaign_execution.v1",
            "status": "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED",
            "event_count": 1,
            "case_count": 1,
            "chain_executed_case_count": 0,
            "packet_identity_case_count": 1,
            "packet_digest_case_count": 1,
            "packet_identity_consumed": True,
            "failed_case_count": 1,
            "failed_cases": [{"event_id": "event-1", "reason": "handoff required"}],
            "facility_total_risk_available": False,
            "provider_packet_promoted": False,
            "frequency_from_provider_packet": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "policy": {
                "provider_packet_promoted": False,
                "frequency_inference_performed": False,
                "frequency_from_provider_packet": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
            },
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "diagnostic_native_packet_campaign_execution")
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_compressible_handoff_rebind_controls():
    report = build_ijhe_completion_audit(
        _status(validated=False),
        _matrix(complete=False),
        _campaign_result(total=False),
        provider_worklist={"generated_event_count": 1},
        native_packet_campaign_ledger={
            "schema_version": "prism.native_lh2dt_packet_campaign_execution.v1",
            "status": "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED",
            "event_count": 1,
            "case_count": 1,
            "chain_executed_case_count": 1,
            "packet_identity_case_count": 1,
            "packet_digest_case_count": 1,
            "packet_identity_consumed": True,
            "failed_case_count": 0,
            "failed_cases": [],
            "facility_total_risk_available": False,
            "provider_packet_promoted": False,
            "frequency_from_provider_packet": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "policy": {
                "provider_packet_promoted": False,
                "frequency_inference_performed": False,
                "frequency_from_provider_packet": False,
                "facility_qra_claim": False,
                "physical_validation_claim": False,
            },
            "compressible_handoff_rebind": {
                "consumed": True,
                "event_id": "event-1",
                "original_provider_result_digest": "a" * 64,
                "handoff_provider_result_digest": "b" * 64,
                "physical_validation_claim": False,
                "frequency_inference": False,
            },
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "diagnostic_native_packet_compressible_handoff_rebind")
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_frequency_provenance_as_diagnostic_evidence():
    report = build_ijhe_completion_audit(
        {"physical_validation_claim": False},
        {},
        {"cases": [], "events": []},
        frequency_provenance_report={
            "schema_version": "prism.frequency_provenance.v1",
            "status": "PASS_WITH_SCOPE_LIMITATIONS",
            "profile_provenance": [{"profile": "LH2_VESSEL"}],
            "generated_events": [{"id": "event-1"}],
            "checks": [{"passed": True}],
            "catalogue": {"digest": "a" * 64},
            "policy": {
                "field_frequency_collection_used": False,
                "sensor_frequency_learning_used": False,
                "physical_validation_claim": False,
            },
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "literature_frequency_provenance_evidence")
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_records_external_scenario_evidence_as_non_promoting_evidence():
    report = build_ijhe_completion_audit(
        {"physical_validation_claim": False},
        {},
        {"cases": [], "events": []},
        scenario_evidence_report={
            "schema_version": "prism.external_scenario_evidence.v1",
            "status": "SCREENING_EVIDENCE_IMPORTED",
            "source_files": [{"path": "sequence.csv"}],
            "records": [{"id": "sequence.csv:2"}],
            "summary": {"scope_status_counts": {"CANDIDATE_OUTDOOR_SCREENING": 1}},
            "policy": {
                "facility_neutral": True,
                "frequency_applied": False,
                "sensor_frequency_learning_used": False,
                "provider_packet_created": False,
                "facility_qra_claim": False,
                "candidate_family_map_is_not_a_frequency_map": True,
            },
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "external_scenario_evidence_import")
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def _status(validated=True):
    return {
        "physical_validation_claim": validated,
        "physical_validation_evidence_status": "INDEPENDENT_END_TO_END" if validated else "RESTRICTED",
        "equipment_model_binding_status": "ACCIDENT_RELEASE_INTERFACE_BOUND" if validated else "STATE_ONLY_BOUND",
        "equipment_model_binding_component_count": 1,
        "equipment_model_binding_state_supported_component_count": 1,
        "equipment_model_binding_accident_release_supported_component_count": 1 if validated else 0,
        "equipment_model_binding_record": "model_binding.json",
        "provider_release_contract_actual_facility_packet_available": validated,
        "external_provider_evidence_release_inventory_status": "QUALIFIED_ACCIDENT_RELEASE_EXPORT" if validated else "NO_ACCIDENT_RELEASE_EXPORT",
        "one_hz_fresh_physics_demonstrated": False,
        "realtime_monitor_implemented": True,
        "realtime_monitor_module": "src/lh2_tno/service.py",
        "realtime_monitor_test_status": "contract",
        "realtime_monitor_one_hz_claim": False,
        "equipment_provider_release_worklist_status": "READY_FOR_PROVIDER_PACKETS",
        "equipment_provider_release_worklist_event_count": 1,
        "equipment_provider_release_worklist_provider_packet_count": 1,
        "equipment_provider_release_worklist_uncomputed_count": 0,
    }


def _diagnostic_execution(**overrides):
    execution = {
        "status": "EXECUTED_OPERATOR_LIMITED_DIAGNOSTIC",
        "adapter_execution": {
            "provider_instance_id": "storage-tank-01",
        },
        "worklist_item_id": "scope/storage-shell/AREA_0.01%/provider-release",
        "worklist_exact_match": {
            "event_id": True,
            "component_id": True,
            "port_id": True,
            "opening_diameter_m": True,
        },
        "consequence_chain_executed": True,
        "consequence_chain_status": "END_TO_END_DIAGNOSTIC_EXECUTED",
        "consequence_chain_elapsed_ms": 2000.0,
        "fresh_execution_elapsed_ms": 1000.0,
        "qualified_provider_packet_count": 0,
        "provider_packet_promoted": False,
        "worklist_frequency_bound": False,
        "consequence_context_frequency_bound": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    execution.update(overrides)
    return execution


def _worklist_evidence(**overrides):
    evidence = {
        "status": "PARTIAL_DIAGNOSTIC_EVIDENCE",
        "worklist_event_count": 24,
        "candidate_event_count": 19,
        "exact_match_event_count": 19,
        "strict_packet_valid_event_count": 19,
        "consequence_chain_event_count": 10,
        "qualified_provider_packet_count": 0,
        "frequency_bound": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }
    evidence.update(overrides)
    return evidence


def _facility_assessment(**overrides):
    assessment = {
        "status": "PARTIAL_FACILITY_SCOPE",
        "facility_total_risk_available": False,
        "complete_facility_qra_claim": False,
        "conditional_diagnostic_facility_risk_available": True,
        "conditional_diagnostic_facility_annual_ir_low_high": {
            "worker-01": [1.0e-6, 2.0e-6]
        },
        "conditional_diagnostic_facility_expected_death_fn_low_high": [
            [[0.0, 0.0]],
            [[0.0, 0.0]],
        ],
        "conditional_diagnostic_facility_expected_death_fn_diagnostics": {
            "status": "ZERO_EXPECTED_DEATH_AT_DECLARED_RECEPTORS",
            "endpoint_level_count_low_high": [0, 0],
            "max_expected_deaths_low_high": [0.0, 0.0],
            "curve_uses_threshold": "N >= 1 expected deaths",
        },
        "population_accounting": {
            "status": "NOT_RECORDED_IN_INPUT",
            "annual_condition_count": 0,
            "referenced_condition_count": 1,
            "referenced_condition_ids": ["weather-1"],
        },
        "scenario_branch_accounting": {
            "status": "EXPLICIT_BRANCH_ACCOUNTING",
            "cross_product_count": 1,
            "annual_conditions": {"weather-1": {"weather": {"wind_speed_m_per_s": 3.0}}},
            "release_branches": {"release-1": {"termination_basis_counts": {"inventory_depletion": 1}}},
            "ignition_branches": {"direct_fire": {"risk_atom_count": 96}},
        },
        "release_termination_inventory_ledger": {
            "schema_version": "prism.release_termination_inventory_ledger.v1",
            "summary": {"case_count": 24, "complete_row_count": 24},
        },
        "timing": {
            "fresh_physics_cases": 24,
            "case_p95_ms": 120.0,
            "stage_elapsed_ms": {
                "provider_release": {"sample_count": 24, "p95_ms": 35.0}
            },
        },
        "conditional_diagnostic_facility_coverage": {
            "event_count": 24,
            "case_count": 24,
            "risk_atom_count": 96,
            "uncomputed_case_count": 20,
        },
    }
    assessment.update(overrides)
    return assessment


def _campaign_binding(**overrides):
    binding = {
        "status": "PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING",
        "packet_event_count": 24,
        "campaign_event_count": 24,
        "campaign_case_count": 24,
        "campaign_risk_atom_count": 96,
        "packet_event_to_campaign_event_match_count": 24,
        "packet_event_to_campaign_case_match_count": 24,
        "packet_event_to_campaign_risk_atom_match_count": 24,
        "structural_binding_complete": True,
        "packet_identity_consumed": False,
        "frequency_from_provider_packet": False,
        "packet_claims_preserved": True,
        "executed_case_count": 24,
    }
    binding.update(overrides)
    return binding


def test_completion_audit_blocks_incomplete_facility_claim():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        {"scenarios": [{"id": "known"}], "facility_credible_interval": False},
    )
    assert report["status"] == "INCOMPLETE_EVIDENCE"
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_exposes_facility_frequency_port_binding_diagnostic():
    port_binding = {
        "schema_version": "prism.frequency_port_binding.v1",
        "status": "ALIGNED",
        "port_scoped_event_count": 1,
        "port_unbound_event_count": 0,
        "mismatch_count": 0,
        "frequency_inference_allowed": False,
    }
    assessment = _facility_assessment(
        frequency_port_binding=port_binding,
        facility_risk_ledger={"frequency_port_binding": port_binding},
    )
    report = build_ijhe_completion_audit(
        _status(False), _matrix(False), _campaign_result(False),
        facility_assessment=assessment,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_facility_frequency_port_binding"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None


def test_completion_audit_blocks_unbound_facility_frequency_ports():
    port_binding = {
        "schema_version": "prism.frequency_port_binding.v1",
        "status": "ALIGNED",
        "port_scoped_event_count": 0,
        "port_unbound_event_count": 1,
        "mismatch_count": 0,
        "frequency_inference_allowed": False,
    }
    assessment = _facility_assessment(
        frequency_port_binding=port_binding,
        facility_risk_ledger={"frequency_port_binding": port_binding},
    )
    report = build_ijhe_completion_audit(
        _status(False), _matrix(False), _campaign_result(False),
        facility_assessment=assessment,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_facility_frequency_port_binding"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True


def test_completion_audit_accepts_restricted_component_evidence_without_promoting_full_chain():
    status = _status(False)
    status.update({
        "physical_validation_evidence_status": "RESTRICTED_COMPONENT_EVIDENCE_WITH_SOURCE_HASH_DRIFT",
        "physical_validation_evidence_record": "results/validation_record.json",
        "physical_validation_evidence_component": "DynamicLH2PoolX pool/spreading only",
    })
    report = build_ijhe_completion_audit(
        status,
        _matrix(False),
        _campaign_result(False),
        {"scenarios": [{"id": "known"}], "facility_credible_interval": False},
    )
    check = next(item for item in report["checks"] if item["name"] == "physical_validation_evidence")
    assert check["status"] == "PASS"
    assert check["evidence"]["restricted_component_evidence"] is True
    assert report["physical_validation_claim"] is False
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 5


def test_completion_audit_records_validation_evidence_matrix_without_opening_qra():
    matrix = {
        "status": "RESTRICTED_EVIDENCE_MATRIX",
        "decision": "FACILITY_QRA_WITHHELD",
        "evidence_domains": [{"id": "pool"}, {"id": "facility"}],
        "blocking_reasons": [],
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
    }
    report = build_ijhe_completion_audit(
        _status(False), _matrix(False), _campaign_result(False),
        validation_evidence_matrix=matrix,
    )
    check = next(item for item in report["checks"] if item["name"] == "validation_evidence_matrix")
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert report["complete_facility_qra_claim"] is False
    assert report["physical_validation_claim"] is False


def test_completion_audit_blocks_unsafe_validation_evidence_matrix():
    matrix = {
        "status": "RESTRICTED_EVIDENCE_MATRIX",
        "decision": "FACILITY_QRA_WITHHELD",
        "evidence_domains": [],
        "blocking_reasons": [],
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": True,
        "frequency_inference_performed": False,
    }
    report = build_ijhe_completion_audit(
        _status(False), _matrix(False), _campaign_result(False),
        validation_evidence_matrix=matrix,
    )
    check = next(item for item in report["checks"] if item["name"] == "validation_evidence_matrix")
    assert check["status"] == "BLOCKED"
    assert "validation evidence matrix" in check["blocking_reason"]
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_passes_only_when_every_claim_gate_is_present():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
    )
    assert report["status"] == "READY_FOR_IJHE_SCOPE"


def test_completion_audit_blocks_missing_facility_case_provider_packets():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        facility_case_packet_coverage={
            "schema": "prism.facility_case_provider_coverage.v1",
            "status": "NO_CASE_MATCH",
            "case_request_count": 2,
            "qualified_provider_event_count": 0,
            "qualified_provider_case_count": 0,
            "provider_evidence_row_count": 0,
            "status_counts": {"MISSING_QUALIFIED_PROVIDER_EVIDENCE": 2},
            "blocking_reasons": ["one or more facility cases have no qualified provider evidence"],
            "promotion_policy": {
                "frequency_is_not_assigned": True,
                "physical_validation_claim": False,
                "facility_ir_fn_promotion": "requires this full case gate plus independent scope and validation gates",
            },
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "facility_case_provider_packet_coverage")
    assert check["status"] == "BLOCKED"
    assert report["status"] == "INCOMPLETE_EVIDENCE"


def test_completion_audit_accepts_full_facility_case_provider_coverage():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        facility_case_packet_coverage={
            "schema": "prism.facility_case_provider_coverage.v1",
            "status": "QUALIFIED_FULL_CASE_COVERAGE",
            "case_request_count": 2,
            "qualified_provider_event_count": 1,
            "qualified_provider_case_count": 2,
            "provider_evidence_row_count": 1,
            "status_counts": {"QUALIFIED_CASE_COVERAGE": 2},
            "blocking_reasons": [],
            "promotion_policy": {
                "frequency_is_not_assigned": True,
                "physical_validation_claim": False,
                "facility_ir_fn_promotion": "requires this full case gate plus independent scope and validation gates",
            },
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "facility_case_provider_packet_coverage")
    assert check["status"] == "PASS"
    assert report["status"] == "READY_FOR_IJHE_SCOPE"
    assert report["complete_facility_qra_claim"] is True
    assert not report["blocking_reasons"]


def test_completion_audit_reads_legacy_provider_inventory_alias_fail_closed():
    status = _status(False)
    status.pop("provider_release_contract_actual_facility_packet_available")
    status["external_provider_evidence_accident_release_promotion_status"] = "NO_ACCIDENT_RELEASE_EXPORT"
    status["external_provider_evidence_accident_release_qualified_files"] = 0
    report = build_ijhe_completion_audit(
        status,
        _matrix(False),
        _campaign_result(False),
        None,
    )
    packet_check = next(item for item in report["checks"] if item["name"] == "actual_provider_release_packet")
    assert packet_check["status"] == "BLOCKED"
    assert packet_check["evidence"] == {
        "actual_facility_packet_available": False,
        "release_inventory_status": "NO_ACCIDENT_RELEASE_EXPORT",
        "qualified_packet_count": 0,
    }


def test_completion_audit_reads_partial_provider_qualification_coverage():
    status = _status(False)
    status["provider_release_contract_actual_facility_packet_available"] = False
    status["equipment_provider_release_worklist_provider_packet_count"] = 0
    status["equipment_provider_release_worklist_uncomputed_count"] = 1
    report = build_ijhe_completion_audit(
        status,
        _matrix(False),
        _campaign_result(False),
        provider_qualification_coverage={
            "qualification_status": "QUALIFIED_PARTIAL_OR_BLOCKED",
            "worklist_event_count": 2,
            "exact_match_count": 1,
            "qualified_provider_packet_count": 1,
            "unqualified_exact_match_count": 0,
        },
    )

    packet_check = next(item for item in report["checks"] if item["name"] == "actual_provider_release_packet")
    coverage_check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert packet_check["status"] == "BLOCKED"
    assert packet_check["evidence"]["qualification_coverage_qualified_packet_count"] == 1
    assert coverage_check["status"] == "BLOCKED"


def test_completion_audit_accepts_full_provider_qualification_coverage_for_worklist_gate():
    status = _status(False)
    status["provider_release_contract_actual_facility_packet_available"] = False
    report = build_ijhe_completion_audit(
        status,
        _matrix(False),
        _campaign_result(False),
        provider_qualification_coverage={
            "qualification_status": "QUALIFIED_FULL_WORKLIST",
            "worklist_event_count": 1,
            "exact_match_count": 1,
            "qualified_provider_packet_count": 1,
            "unqualified_exact_match_count": 0,
        },
    )

    coverage_check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert coverage_check["status"] == "PASS"
    assert coverage_check["evidence"]["qualification_coverage_complete"] is True


def test_completion_audit_unwraps_campaign_uncertainty_ledger():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        {
            "literature_frequency_uncertainty": {
                "scenarios": [{"id": "known"}],
                "facility_credible_interval": False,
            }
        },
    )
    uncertainty_check = next(
        item for item in report["checks"] if item["name"] == "frequency_uncertainty_reported"
    )
    assert uncertainty_check["status"] == "BLOCKED"
    assert uncertainty_check["evidence"] == {
        "uncertainty_result_present": True,
        "scenario_count": 1,
        "facility_credible_interval": False,
        "conditional_frequency_uncertainty": False,
    }


def test_completion_audit_unwraps_facility_assessment_uncertainty_ledger():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        {
            "frequency_uncertainty": {
                "scenarios": [{"id": "known"}],
                "facility_credible_interval": False,
            },
            "assessment_digest": "assessment-wrapper",
        },
    )
    uncertainty_check = next(
        item for item in report["checks"] if item["name"] == "frequency_uncertainty_reported"
    )
    assert uncertainty_check["status"] == "BLOCKED"
    assert uncertainty_check["evidence"]["scenario_count"] == 1


def test_completion_audit_blocks_provider_worklist_with_uncomputed_events():
    status = _status(True)
    status["equipment_provider_release_worklist_provider_packet_count"] = 0
    status["equipment_provider_release_worklist_uncomputed_count"] = 1
    report = build_ijhe_completion_audit(
        status,
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
    )
    assert report["status"] == "INCOMPLETE_EVIDENCE"
    check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["provider_packet_count"] == 0


def test_completion_audit_prefers_provider_worklist_file_over_stale_status():
    status = _status(True)
    report = build_ijhe_completion_audit(
        status,
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        {
            "status": "READY_FOR_PROVIDER_PACKETS",
            "generated_event_count": 2,
            "provider_packet_count": 0,
            "status_counts": {"UNCOMPUTED_PROVIDER_PACKET": 2},
            "model_binding_diagnostic_release_adapter_component_count": 7,
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["source"] == "provider_worklist"
    assert check["evidence"]["frequency_event_count"] == 2
    assert check["evidence"]["diagnostic_release_adapter_component_count"] == 7


def test_completion_audit_uses_exact_native_catalog_for_structural_worklist_coverage():
    status = _status(True)
    report = build_ijhe_completion_audit(
        status,
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        {
            "status": "READY_FOR_PROVIDER_PACKETS",
            "generated_event_count": 2,
            "provider_packet_count": 0,
            "status_counts": {"UNCOMPUTED_PROVIDER_PACKET": 2},
        },
        native_scope_packet_catalog_verification={
            "schema_version": "prism.native_generic_scope_packet_catalog.v1",
            "status": "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_EXECUTED",
            "frequency_event_count": 2,
            "exact_native_packet_count": 2,
            "uncomputed_event_count": 0,
            "event_rows": [
                {"event_id": "e1", "status": "EXACT_NATIVE_PACKET"},
                {"event_id": "e2", "status": "EXACT_NATIVE_PACKET"},
            ],
            "state_snapshot_binding": {
                "status": "STATE_SNAPSHOT_BOUND_AND_ECHOED",
                "record_count": 2,
                "bound_count": 2,
                "unbound_count": 0,
                "digest_mismatch_count": 0,
            },
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
    )
    check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert check["status"] == "PASS"
    assert check["evidence"]["native_scope_catalog_structural_coverage"] is True
    assert check["evidence"]["native_scope_catalog_evidence"]["exact_native_packet_count"] == 2


def test_completion_audit_records_resolved_diagnostic_adapter_execution_contract():
    status = _status(False)
    status.update({
        "diagnostic_adapter_runner_implemented": True,
        "diagnostic_adapter_registry_live_audit_status": (
            "DECLARED_ADAPTERS_RESOLVED_PROVIDER_INSTANCES_REQUIRED; 7/7"
        ),
        "diagnostic_adapter_registry_adapter_count": 7,
        "diagnostic_adapter_registry_resolved_adapter_count": 7,
        "diagnostic_adapter_registry_provider_instance_count": 0,
        "diagnostic_adapter_registry_qualified_packet_count": 0,
        "diagnostic_adapter_registry_live_audit_record": "registry.json",
    })
    report = build_ijhe_completion_audit(
        status,
        _matrix(False),
        _campaign_result(False),
        None,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_adapter_execution_contract"
    )
    assert check["status"] == "PASS"
    assert check["evidence"]["resolved_adapter_count"] == 7


def test_completion_audit_records_nonqualifying_worklist_chain_execution():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        diagnostic_adapter_execution=_diagnostic_execution(_record_path="runner.json"),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_execution_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert check["evidence"]["record"] == "runner.json"
    assert check["evidence"]["provider_instance_id"] == "storage-tank-01"
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_rejects_invalid_diagnostic_execution_without_promoting_it():
    execution = _diagnostic_execution(
        worklist_exact_match={
            "event_id": True,
            "component_id": True,
            "port_id": False,
            "opening_diameter_m": True,
        },
        worklist_frequency_bound=True,
    )
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        diagnostic_adapter_execution=execution,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_execution_evidence"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["status"] == "READY_FOR_IJHE_SCOPE"


def test_completion_audit_records_partial_provider_worklist_coverage():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        diagnostic_worklist_evidence=_worklist_evidence(_record_path="evidence.json"),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_packet_coverage_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["exact_match_event_count"] == 19
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_accepts_complete_structural_worklist_without_qualifying_provider():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        diagnostic_worklist_evidence=_worklist_evidence(
            worklist_event_count=24,
            candidate_event_count=24,
            exact_match_event_count=24,
            strict_packet_valid_event_count=24,
            consequence_chain_event_count=15,
            qualification_readiness={
                "status_counts": {"BLOCKED_REVIEW": 24},
                "blocker_counts": {"qualification_sidecar_missing": 24},
            },
            _record_path="full-evidence.json",
        ),
    )
    check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert check["status"] == "PASS"
    assert check["evidence"]["structural_diagnostic_coverage"] is True
    assert check["evidence"]["qualified_provider_packet_count"] == 0
    assert check["evidence"]["qualification_readiness"]["status_counts"] == {
        "BLOCKED_REVIEW": 24
    }
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_records_conditional_facility_ir_fn_without_promoting_total():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        facility_assessment=_facility_assessment(),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_conditional_facility_risk_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert check["evidence"]["coverage"]["risk_atom_count"] == 96
    assert check["evidence"][
        "conditional_diagnostic_facility_expected_death_fn_diagnostics"
    ]["status"] == "ZERO_EXPECTED_DEATH_AT_DECLARED_RECEPTORS"
    assert check["evidence"]["population_accounting"]["status"] == (
        "NOT_RECORDED_IN_INPUT"
    )
    assert check["evidence"]["scenario_branch_accounting"]["status"] == (
        "EXPLICIT_BRANCH_ACCOUNTING"
    )
    assert check["evidence"]["release_termination_inventory_ledger"][
        "schema_version"
    ] == "prism.release_termination_inventory_ledger.v1"
    assert check["evidence"]["timing"]["stage_elapsed_ms"]["provider_release"][
        "p95_ms"
    ] == 35.0
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_records_facility_release_boundary_gate():
    assessment = _facility_assessment(
        strict_release_boundary={
            "schema_version": "prism.facility_release_boundary_gate.v1",
            "strict_release_boundary_ready": False,
            "case_count": 24,
            "checks": {
                "all_rows_complete": False,
                "all_termination_bases_allowed": False,
                "all_isolation_or_inventory_statuses_closed": True,
                "all_mass_residuals_closed": False,
                "no_withheld_cases": False,
            },
            "blocking_reasons": ["synthetic diagnostic horizon remains"],
            "policy": {
                "frequency_is_not_inferred": True,
                "facility_ir_fn_promotion": "requires independent gates",
            },
        }
    )
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        facility_assessment=assessment,
    )
    check = next(item for item in report["checks"] if item["name"] == "facility_release_boundary")
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is False
    assert check["evidence"]["case_count"] == 24
    assert check["evidence"]["schema"] == "prism.facility_release_boundary_gate.v1"
    assert check["evidence"]["schema_version"] == "prism.facility_release_boundary_gate.v1"
    assert check["evidence"]["facility_gate_checks"]["all_rows_complete"] is False
    assert check["evidence"]["promotion_policy"]["frequency_is_not_inferred"] is True
    assert "facility release boundary is not closed across all declared cases" in report["blocking_reasons"]


def test_completion_audit_accepts_closed_facility_release_boundary_gate():
    assessment = _facility_assessment(
        strict_release_boundary={
            "schema_version": "prism.facility_release_boundary_gate.v1",
            "strict_release_boundary_ready": True,
            "case_count": 1,
            "checks": {
                "all_rows_complete": True,
                "all_termination_bases_allowed": True,
                "all_isolation_or_inventory_statuses_closed": True,
                "all_mass_residuals_closed": True,
                "no_withheld_cases": True,
            },
            "blocking_reasons": [],
            "policy": {
                "frequency_is_not_inferred": True,
                "facility_ir_fn_promotion": "requires independent gates",
            },
        }
    )
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        facility_assessment=assessment,
    )
    check = next(item for item in report["checks"] if item["name"] == "facility_release_boundary")
    assert check["status"] == "PASS"
    assert check["blocking_reason"] is None


def test_completion_audit_rejects_release_boundary_with_missing_gate_check():
    assessment = _facility_assessment(
        strict_release_boundary={
            "schema_version": "prism.facility_release_boundary_gate.v1",
            "strict_release_boundary_ready": True,
            "case_count": 1,
            "checks": {
                "all_rows_complete": True,
                "all_termination_bases_allowed": True,
                "all_isolation_or_inventory_statuses_closed": True,
                "all_mass_residuals_closed": True,
                # no_withheld_cases is intentionally omitted
            },
            "blocking_reasons": [],
            "policy": {},
        }
    )
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        facility_assessment=assessment,
    )
    check = next(item for item in report["checks"] if item["name"] == "facility_release_boundary")
    assert check["status"] == "BLOCKED"
    assert check["blocking_reason"] == (
        "facility release boundary is not closed across all declared cases"
    )


def test_completion_audit_blocks_stale_release_boundary_summary_against_raw_ledger():
    raw_ledger = {
        "schema_version": "prism.release_termination_inventory_ledger.v1",
        "rows": [{
            "event_id": "tank/hole",
            "status": "EXECUTED",
            "termination": {
                "basis": "reviewed_isolation_success",
                "time_s": 0.25,
            },
            "isolation_status": "provider_declared_isolation_success",
            "mass_ledger": {
                "end_to_end_residual_kg": 0.0,
            },
        }],
        "summary": {
            "withheld_case_count": 0,
            "termination_basis_counts": {"reviewed_isolation_success": 1},
        },
    }
    assessment = _facility_assessment(
        release_termination_inventory_ledger=raw_ledger,
        strict_release_boundary={
            "schema_version": "prism.facility_release_boundary_gate.v1",
            "strict_release_boundary_ready": True,
            "case_count": 99,
            "withheld_case_count": 0,
            "checks": {
                "all_rows_complete": True,
                "all_termination_bases_allowed": True,
                "all_isolation_or_inventory_statuses_closed": True,
                "all_mass_residuals_closed": True,
                "no_withheld_cases": True,
            },
            "blocking_reasons": [],
            "residual_tolerance_kg": 1.0e-8,
            "policy": {},
        },
    )
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        facility_assessment=assessment,
    )
    check = next(item for item in report["checks"] if item["name"] == "facility_release_boundary")
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["raw_ledger_reconciliation"]["status"] == "MISMATCHED"
    assert "case_count" in check["evidence"]["raw_ledger_reconciliation"]["mismatched_fields"]


def test_completion_audit_records_diagnostic_frequency_uncertainty():
    uncertainty = {
        "scenarios": [
            {
                "scenario": {"id": "central"},
                "conditional_diagnostic_facility_annual_ir_low_high": {
                    "worker-01": [1.0e-6, 2.0e-6]
                },
                "conditional_diagnostic_facility_expected_death_fn_low_high": [
                    {}, {}
                ],
                "asset_rank_by_known_expected_fatalities_low_high": [{}, {}],
            }
        ],
        "facility_credible_interval": False,
        "fresh_physics_executed": False,
        "physical_validation_claim": False,
        "correlation_comparison_present": True,
        "conditional_diagnostic_facility_risk": "saved atoms",
    }
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        uncertainty,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_frequency_uncertainty_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["scenario_count"] == 1
    frequency_check = next(
        item for item in report["checks"]
        if item["name"] == "frequency_uncertainty_reported"
    )
    assert frequency_check["status"] == "PASS"
    assert frequency_check["evidence"]["conditional_frequency_uncertainty"] is True
    assert len(report["blocking_reasons"]) == 5


def test_completion_audit_records_vertical_handoff_diagnostic_without_scope_promotion():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        vertical_handoff_result={
            "status": "PARTIAL_DECLARED_SCOPE",
            "generated_events": 5,
            "executed_cases": 2,
            "provider_vertical_handoff_consumed": True,
            "operator_limited": True,
            "facility_total_risk_withheld": True,
            "physical_validation_claim": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_vertical_handoff_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_consumes_combined_chain_closure_without_qra_promotion():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        combined_chain_closure={
            "schema_version": "prism.facility_combined_chain_closure_audit.v1",
            "status": "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED",
            "declared_event_count": 29,
            "packet_subset_closed_event_count": 24,
            "vertical_handoff_closed_event_count": 5,
            "combined_diagnostic_closed_event_count": 29,
            "event_count_matches_declared_scope": True,
            "mismatch_event_ids": [],
            "facility_ir_aggregate_closed": True,
            "facility_fn_aggregate_closed": True,
            "qualified_provider_packet_count": 0,
            "frequency_from_provider_packet": False,
            "physical_validation_claim": False,
            "facility_total_risk_available": False,
            "complete_facility_qra_claim": False,
            "facility_qra_claim": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_combined_chain_closure"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["combined_diagnostic_closed_event_count"] == 29
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_keeps_malformed_combined_chain_diagnostic_only():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        combined_chain_closure={
            "schema_version": "prism.facility_combined_chain_closure_audit.v1",
            "status": "BLOCKED_COMBINED_CHAIN_CLOSURE",
            "declared_event_count": 29,
            "combined_diagnostic_closed_event_count": 28,
            "mismatch_event_ids": ["event-29"],
            "facility_qra_claim": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_combined_chain_closure"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_consumes_restricted_slabx_evidence_without_qra_promotion():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        slabx_validation_evidence={
            "schema_version": "prism.slabx_lh2_validation_audit.v1",
            "status": "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE",
            "checks": [{"name": "model_identity", "status": "PASS"}],
            "model": {"name": "SLABx-LH2"},
            "metrics": {"ffi_case_count": 6},
            "physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_slabx_lh2_validation_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_keeps_malformed_slabx_evidence_diagnostic_only():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        slabx_validation_evidence={
            "schema_version": "prism.slabx_lh2_validation_audit.v1",
            "status": "BLOCKED_SLABX_LH2_CONSEQUENCE_EVIDENCE",
            "checks": [{"name": "model_identity", "status": "BLOCKED"}],
            "physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_slabx_lh2_validation_evidence"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_consumes_realtime_cache_benchmark_without_fresh_physics_claim():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        realtime_cache_benchmark={
            "schema_version": "prism.realtime_cache_benchmark.v1",
            "facility_id": "generic-lh2-near-receptor-diagnostic",
            "request_event_id": "event-01",
            "fresh_physics_elapsed_ms": 2685.5,
            "cache_elapsed_ms_values": [31.0, 33.0],
            "cache_hits": 2,
            "cache_median_ms": 32.0,
            "cache_p95_ms": 33.0,
            "one_hz_deadline_s": 1.0,
            "fresh_physics_meets_one_hz": False,
            "cache_meets_one_hz_all_samples": True,
            "realtime_fresh_physics_claim": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_realtime_cache_benchmark"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["cache_hits"] == 2
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_keeps_invalid_realtime_cache_benchmark_diagnostic_only():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        realtime_cache_benchmark={
            "schema_version": "prism.realtime_cache_benchmark.v1",
            "fresh_physics_elapsed_ms": 2685.5,
            "cache_elapsed_ms_values": [31.0],
            "cache_hits": 0,
            "cache_median_ms": 31.0,
            "cache_p95_ms": 31.0,
            "one_hz_deadline_s": 1.0,
            "fresh_physics_meets_one_hz": True,
            "cache_meets_one_hz_all_samples": True,
            "realtime_fresh_physics_claim": True,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_realtime_cache_benchmark"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_marks_vertical_handoff_as_merged_when_scope_row_exists():
    report = build_ijhe_completion_audit(
        _status(False),
        {
            **_matrix(complete=False),
            "rows": [{"family": "vertical_handoff", "generated_event_count": 5}],
        },
        _campaign_result(False),
        None,
        vertical_handoff_result={
            "status": "PARTIAL_DECLARED_SCOPE",
            "generated_events": 5,
            "executed_cases": 10,
            "provider_vertical_handoff_consumed": True,
            "operator_limited": True,
            "facility_total_risk_withheld": True,
            "physical_validation_claim": False,
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_vertical_handoff_evidence"
    )
    assert check["status"] == "PASS"
    assert "merged facility scope matrix" in check["interpretation"]


def test_completion_audit_records_packet_to_campaign_structural_binding():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        diagnostic_campaign_binding=_campaign_binding(_record_path="binding.json"),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_campaign_binding_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["record"] == "binding.json"
    assert len(report["blocking_reasons"]) == 6


def test_completion_audit_accepts_separate_vertical_subset_when_combined_chain_closes_scope():
    binding = _campaign_binding(
        campaign_event_count=29,
        campaign_case_count=34,
        campaign_risk_atom_count=136,
        structural_binding_complete=False,
        packet_scope_subset_complete=True,
        campaign_scope_packet_coverage_complete=False,
        packet_subset_identity_consumed=True,
        unbound_campaign_event_count=5,
    )
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        None,
        diagnostic_campaign_binding=binding,
        combined_chain_closure={
            "schema_version": "prism.facility_combined_chain_closure_audit.v1",
            "status": "FULL_DIAGNOSTIC_CHAIN_CLOSED_OPERATOR_LIMITED",
            "declared_event_count": 29,
            "packet_subset_event_count": 24,
            "packet_subset_closed_event_count": 24,
            "vertical_handoff_event_count": 5,
            "vertical_handoff_closed_event_count": 5,
            "combined_diagnostic_closed_event_count": 29,
            "event_count_matches_declared_scope": True,
            "mismatch_event_ids": [],
            "frequency_from_provider_packet": False,
            "physical_validation_claim": False,
            "facility_total_risk_available": False,
            "complete_facility_qra_claim": False,
            "facility_qra_claim": False,
            "_record_path": "combined.json",
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_campaign_binding_evidence"
    )
    assert check["status"] == "PASS"
    assert check["evidence"]["union_chain_closure_used"] is True
    assert check["evidence"]["diagnostic_scope_closure_complete"] is True
    assert "does not qualify packets" in check["interpretation"]
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_accepts_packet_identity_consumption_without_promoting_qra():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        diagnostic_campaign_binding=_campaign_binding(packet_identity_consumed=True),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_campaign_binding_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["status"] == "READY_FOR_IJHE_SCOPE"


def test_completion_audit_rejects_worklist_evidence_without_chain_or_strict_packets():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
        diagnostic_worklist_evidence=_worklist_evidence(
            strict_packet_valid_event_count=18,
            consequence_chain_event_count=0,
        ),
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_worklist_packet_coverage_evidence"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True
    assert check["blocking_reason"] is None
    assert report["status"] == "READY_FOR_IJHE_SCOPE"


def test_completion_audit_records_exact_native_scope_catalog_separately_from_provider_gate():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        native_scope_packet_catalog_verification={
            "schema_version": "prism.native_generic_scope_packet_catalog.v1",
            "status": "NATIVE_GENERIC_SCOPE_PACKET_CATALOG_EXECUTED",
            "frequency_event_count": 24,
            "exact_native_packet_count": 24,
            "uncomputed_event_count": 0,
            "state_snapshot_binding": {
                "status": "STATE_SNAPSHOT_BOUND_AND_ECHOED",
                "record_count": 24,
                "bound_count": 24,
                "unbound_count": 0,
            },
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "_record_path": "catalog.json",
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_native_scope_packet_catalog_coverage"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_records_observed_state_evidence_without_accident_promotion():
    model_binding = {
        "schema": "prism.observed_state_model_binding_audit.v1",
        "status": "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY",
        "observed_component_count": 3,
        "state_model_bound_component_count": 3,
        "diagnostic_release_adapter_component_count": 3,
        "qualified_provider_packet_count": 0,
        "rows": [
            {
                "status": "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE",
                "state_export_status": "supported",
                "diagnostic_release_adapter_status": "available",
                "accident_release_export_status": "missing",
            }
        ] * 3,
        "blocking_reasons": [],
        "policy": {
            "normal_state_model_is_not_accident_release": True,
            "diagnostic_adapter_is_not_qualified_provider": True,
            "release_event_binding_is_not_created": True,
            "frequency_is_not_assigned": True,
            "facility_ir_fn_promotion": False,
        },
    }
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        observed_state_evidence={
            "schema_version": "prism.observed_equipment_state_evidence.v1",
            "status": "OBSERVATION_STATE_EVIDENCE_ONLY",
            "source_count": 3,
            "sample_count": 8955,
            "component_count": 3,
            "source_rows": [
                {"source_id": "inspection-center-intake-10-runs"},
                {"source_id": "inspection-center-storage-vent-10-runs"},
                {"source_id": "inspection-center-supply-10-runs"},
            ],
            "component_rows": [
                {"component_id": "lh2-intake-tank"},
                {"component_id": "lh2-storage-vent"},
                {"component_id": "lh2-supply-vaporizer-boundary"},
            ],
            "policy": {
                "canonical_snapshot_schema": "prism.equipment_state_snapshot.v1",
                "state_only": True,
                "release_scenario_generated": False,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "provider_packet_promoted": False,
                "physical_validation_claim": False,
                "facility_qra_claim": False,
                "diagnostic_only": True,
            },
        },
        observed_state_model_binding_audit=model_binding,
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_observed_equipment_state_evidence"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["model_binding"]["valid"] is True
    assert report["complete_facility_qra_claim"] is False


def test_completion_audit_blocks_malformed_observed_state_model_binding():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        observed_state_evidence={
            "schema_version": "prism.observed_equipment_state_evidence.v1",
            "status": "OBSERVATION_STATE_EVIDENCE_ONLY",
            "source_count": 1,
            "sample_count": 1,
            "component_count": 1,
            "source_rows": [{"source_id": "source-1"}],
            "component_rows": [{"component_id": "component-1"}],
            "policy": {
                "canonical_snapshot_schema": "prism.equipment_state_snapshot.v1",
                "state_only": True,
                "release_scenario_generated": False,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "provider_packet_promoted": False,
                "physical_validation_claim": False,
                "facility_qra_claim": False,
                "diagnostic_only": True,
            },
        },
        observed_state_model_binding_audit={
            "schema": "prism.observed_state_model_binding_audit.v1",
            "status": "PARTIAL_STATE_MODEL_BINDINGS",
            "observed_component_count": 1,
            "state_model_bound_component_count": 0,
            "diagnostic_release_adapter_component_count": 0,
            "qualified_provider_packet_count": 0,
            "rows": [],
            "blocking_reasons": ["component-1: missing state quantities"],
            "policy": {"facility_ir_fn_promotion": False},
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_observed_equipment_state_evidence"
    )
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["model_binding"]["valid"] is False


def test_completion_audit_blocks_external_normal_model_without_native_release_export():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        external_equipment_model_contract_audit={
            "schema_version": "prism.external_model_contract_audit.v1",
            "status": "NATIVE_ACCIDENT_EXPORT_MISSING",
            "native_accident_export_component_count": 0,
            "native_accident_export_missing_components": ["storage_tank"],
            "_record_path": "external-model-contract.json",
        },
    )
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "equipment_model_binding_to_accident_release"
    )
    assert check["status"] == "BLOCKED"
    assert check["evidence"]["external_model_contract_status"] == (
        "NATIVE_ACCIDENT_EXPORT_MISSING"
    )
    assert report["complete_facility_qra_claim"] is False
