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
            _record_path="full-evidence.json",
        ),
    )
    check = next(item for item in report["checks"] if item["name"] == "provider_worklist_coverage")
    assert check["status"] == "PASS"
    assert check["evidence"]["structural_diagnostic_coverage"] is True
    assert check["evidence"]["qualified_provider_packet_count"] == 0
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
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 6


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
