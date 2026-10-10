from copy import deepcopy

import pytest

from lh2_tno.v060_readiness import (
    V060ReadinessError,
    build_v060_readiness_report,
    validate_v060_readiness_report,
)


def _inputs():
    return {
        "objective_audit": {
            "status": "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN",
            "conditional_chain_complete": True,
            "strict_blocking_check_ids": ["qualified_provider_evidence", "strict_facility_qra"],
            "checks": [
                {"id": "equipment_state_to_native_release", "status": "PASS", "evidence_paths": ["state.json"]},
                {"id": "release_to_final_damage", "status": "CONDITIONALLY_COMPLETE", "evidence_paths": ["campaign.json"]},
                {"id": "literature_frequency_uncertainty", "status": "CONDITIONALLY_COMPLETE", "evidence_paths": ["facility.json"]},
                {"id": "realtime_processing", "status": "CONDITIONALLY_COMPLETE", "evidence_paths": ["benchmark.json"]},
            ],
        },
        "union_verification": {"merged_event_count": 2, "merged_case_count": 3, "merged_risk_atom_count": 12, "frequency_inference_performed": False},
        "scope_matrix": {
            "conditional_chain_complete": True,
            "matrix_complete": False,
            "rows": [{"family": "vessel_hole", "status": "PARTIAL", "conditional_status": "EXECUTED", "generated_event_count": 1, "case_count": 1, "conditional_executed_case_count": 1, "not_numerically_executed_case_count": 0, "qualified_evidence_withheld_case_count": 1}],
        },
        "facility_assessment": {
            "facility_total_risk_available": False,
            "complete_facility_qra_claim": False,
            "qualified_provider_packet_case_count": 0,
            "conditional_diagnostic_facility_risk_available": True,
            "conditional_diagnostic_facility_coverage": {
                "conditional_case_count": 3,
                "conditional_executed_case_count": 3,
                "not_numerically_executed_case_count": 0,
                "qualified_evidence_withheld_case_count": 1,
                "annual_condition_count": 2,
                "scenario_branch_status": "EXPLICIT_BRANCH_ACCOUNTING",
                "component_case_accounting": {"tank-1": {"status": "PARTIAL", "event_count": 1, "conditional_case_count": 3, "conditional_executed_case_count": 3, "not_numerically_executed_case_count": 0, "qualified_evidence_withheld_case_count": 1, "risk_atom_count": 12, "strict_gate_categories": ["MISSING_PROVIDER_CASES"]}},
                "observed_component_count": 1,
                "expected_component_count": 1,
                "component_status_counts": {"PARTIAL": 1},
            },
            "timing": {"case_p95_ms": 2000.0, "case_p99_ms": 3000.0, "stage_elapsed_ms": {}},
            "frequency_uncertainty": {"scenario_count": 3, "correlation_comparison_present": True},
            "release_termination_inventory_ledger": {
                "schema_version": "prism.release_termination_inventory_ledger.v1",
                "summary": {
                    "case_count": 3,
                    "complete_row_count": 2,
                    "withheld_case_count": 1,
                    "uncomputed_row_count": 0,
                    "provider_packet_consumed_row_count": 3,
                },
                "rows": [
                    {
                        "termination": {"basis": "inventory_depletion"},
                        "isolation_status": "not_declared",
                        "inventory_status": "provider_declared_inventory_depletion",
                    },
                    {
                        "termination": {"basis": "synthetic_diagnostic_horizon"},
                        "isolation_status": "not_declared",
                        "inventory_status": "not_inventory_termination",
                    },
                    {
                        "termination": {"basis": "inventory_over_600s"},
                        "isolation_status": "reviewed_isolation_success",
                        "inventory_status": "provider_declared_inventory_over_600s",
                    },
                ],
            },
        },
        "completion_audit": {"status": "INCOMPLETE_EVIDENCE"},
        "validation_matrix": {
            "physical_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
            "evidence_domains": [{"id": "slabx_lh2_consequence_component", "status": "RESTRICTED_COMPONENT_EVIDENCE", "physical_validation_claim": False, "facility_qra_claim": False}],
        },
        "realtime_benchmark": {"cache_p95_ms": 20.0, "cache_meets_one_hz_all_samples": True, "fresh_physics_elapsed_ms": 2000.0, "fresh_physics_meets_one_hz": False},
    }


def _evidence_request():
    return {
        "status": "OPEN_EVIDENCE_REQUEST",
        "provider_export_schema_required": "prism.external_accident_history.v1",
        "case_request_count": 3,
        "family_requests": [{"family": "vessel_hole"}],
        "component_requests": [{"component_id": "tank-1"}],
        "blocking_reasons": ["qualified packets remain open"],
        "current_assessment": {"strict_gate_categories": ["MISSING_PROVIDER_CASES"]},
        "promotion_gate": {"facility_promotion_allowed_now": False},
    }


def _scenario_evidence():
    return {
        "schema_version": "prism.inspection_center_screening_summary.v1",
        "status": "SCREENING_EVIDENCE_IMPORTED",
        "source_file_count": 3,
        "record_count": 4,
        "candidate_family_counts": {"pipe_hole": 2, "vent_hole": 1},
        "candidate_monitoring_signal_counts": {"pressure": 4},
        "scope_status_counts": {"CANDIDATE_OUTDOOR_SCREENING": 4},
        "promotion_policy": {
            "frequency_applied": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_created": False,
            "facility_qra_claim": False,
        },
        "limitations": ["candidate hazards only"],
    }


def _atom_chain_audit():
    return {
        "schema_version": "prism.risk_atom_chain_audit.v1",
        "status": "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC",
        "case_count": 3,
        "complete_case_count": 3,
        "incomplete_case_count": 0,
        "risk_atom_count": 12,
        "operator_limited_case_count": 1,
        "blocking_reasons": [],
        "diagnostic_only": True,
        "facility_qra_claim": False,
    }


def _equipment_chain_audit():
    return {
        "schema_version": "prism.equipment_state_release_audit.v1",
        "status": "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC",
        "case_count": 3,
        "complete_case_count": 3,
        "incomplete_case_count": 0,
        "component_count": 1,
        "operator_limited_case_count": 1,
        "blocking_reasons": [],
        "diagnostic_only": True,
        "facility_qra_claim": False,
    }


def _isolation_extension_verification():
    return {
        "schema": "prism.isolation_union_extension_verification.v1",
        "status": "ISOLATION_UNION_EXTENSION_DIAGNOSTIC",
        "base_counts": {"events": 2, "cases": 3, "risk_atoms": 12},
        "isolation_counts": {
            "events": 1,
            "cases": 4,
            "risk_atoms": 16,
            "success_cases": 2,
            "failure_cases": 2,
            "provider_response_consumed": True,
            "state_snapshot_bound_cases": 4,
        },
        "merged_counts": {"events": 3, "cases": 7, "risk_atoms": 28},
        "risk_atom_chain_status": "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC",
        "equipment_state_release_status": "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC",
        "facility_aggregate_closure_status": "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC",
        "facility_component_contribution_status": "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC",
        "qualified_provider_packet_case_count": 0,
        "complete_facility_qra_claim": False,
    }


def _release_closure_worklist():
    return {
        "schema_version": "prism.release_closure_worklist.v1",
        "status": "OPEN_RELEASE_CLOSURE_WORKLIST",
        "case_count": 3,
        "open_case_count": 3,
        "summary": {
            "closure_status_counts": {"ISOLATION_OPEN": 2, "TERMINATION_OPEN": 1},
            "closure_gap_counts": {
                "ISOLATION_OPEN": 3,
                "PROVIDER_QUALIFICATION_OPEN": 3,
                "TERMINATION_OPEN": 1,
            },
            "termination_basis_counts": {"inventory_depletion": 2, "synthetic_diagnostic_horizon": 1},
            "isolation_status_counts": {"not_declared": 3},
            "inventory_status_counts": {"provider_declared_inventory_depletion": 2, "not_inventory_termination": 1},
            "provider_packet_required_case_count": 3,
            "mass_closure_open_case_count": 0,
            "isolation_open_case_count": 3,
            "termination_open_case_count": 1,
            "inventory_closure_open_case_count": 0,
        },
    }


def test_report_keeps_conditional_chain_and_strict_gate_separate():
    report = build_v060_readiness_report(**_inputs())
    assert report["schema_version"] == "prism.v060_ijhe_readiness_report.v1"
    assert report["conditional_chain_complete"] is True
    assert report["promotion"]["complete_facility_qra_claim"] is False
    assert report["chain"]["event_count"] == 2
    assert report["accident_families"]["rows"][0]["conditional_status"] == "EXECUTED"
    assert report["timing"]["cache_meets_one_hz_all_samples"] is True
    assert report["timing"]["fresh_physics_meets_one_hz"] is False
    profile = report["timing"]["runtime_profile"]
    assert profile["recommended_mode"] == "cached_diagnostic_1hz"
    assert profile["cache_mode"]["one_hz_ready"] is True
    assert profile["fresh_physics_mode"]["one_hz_ready"] is False
    assert profile["campaign_mode"]["online_one_hz_ready"] is False
    assert profile["facility_qra_realtime_claim"] is False
    release = report["chain"]["release_boundary"]
    assert release["status"] == "PARTIAL_RELEASE_BOUNDARY_COVERAGE"
    assert release["termination_basis_counts"]["synthetic_diagnostic_horizon"] == 1
    assert release["isolation_status_counts"]["not_declared"] == 2
    assert release["strict_release_boundary_ready"] is False


def test_report_marks_explicit_exclusions_and_withheld_cases():
    report = build_v060_readiness_report(**_inputs())
    assert "sensor_based_frequency_learning" in report["explicit_exclusions"]
    assert report["chain"]["qualified_evidence_withheld_case_count"] == 1
    assert report["equipment"]["component_rows"][0]["strict_gate_categories"] == ["MISSING_PROVIDER_CASES"]
    assert report["validation_domains"][0]["status"] == "RESTRICTED_COMPONENT_EVIDENCE"


def test_report_validator_accepts_current_fail_closed_shape():
    report = build_v060_readiness_report(**_inputs())
    result = validate_v060_readiness_report(report)
    assert result["status"] == "VALID"
    assert result["strict_blocking_check_count"] == 2
    assert result["accident_family_row_count"] == 1


def test_report_validator_rejects_promotion_while_strict_gates_remain_open():
    report = build_v060_readiness_report(**_inputs())
    report = deepcopy(report)
    report["promotion"]["complete_facility_qra_claim"] = True
    with pytest.raises(V060ReadinessError, match="complete_facility_qra_claim=true"):
        validate_v060_readiness_report(report)


def test_report_validator_rejects_case_accounting_drift():
    report = build_v060_readiness_report(**_inputs())
    report = deepcopy(report)
    report["chain"]["conditional_executed_case_count"] = 2
    with pytest.raises(V060ReadinessError, match="conditional cases"):
        validate_v060_readiness_report(report)


def test_report_validator_rejects_realtime_facility_qra_claim():
    report = build_v060_readiness_report(**_inputs())
    report["timing"]["runtime_profile"]["facility_qra_realtime_claim"] = True
    with pytest.raises(V060ReadinessError, match="real-time facility QRA"):
        validate_v060_readiness_report(report)


def test_report_records_facility_frequency_port_binding_trace():
    inputs = _inputs()
    port_binding = {
        "schema_version": "prism.frequency_port_binding.v1",
        "status": "ALIGNED",
        "port_scoped_event_count": 2,
        "port_unbound_event_count": 0,
        "all_events_port_scoped": True,
        "case_port_binding_mismatch_count": 0,
        "risk_atom_port_binding_mismatch_count": 0,
        "mismatch_count": 0,
    }
    inputs["facility_assessment"]["frequency_port_binding"] = port_binding
    inputs["facility_assessment"]["facility_risk_ledger"] = {
        "frequency_port_binding": port_binding,
    }
    report = build_v060_readiness_report(**inputs)
    trace = report["chain"]["frequency_port_binding"]
    assert trace["schema"] == "prism.frequency_port_binding.v1"
    assert trace["status"] == "ALIGNED"
    assert trace["port_scoped_event_count"] == 2
    assert trace["assessment_nested_mirror_match"] is True
    assert trace["frequency_inference_allowed"] is False
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_uses_evidence_request_port_summary_for_legacy_assessment():
    inputs = _inputs()
    inputs["facility_evidence_request"] = {
        "frequency_port_binding": {
            "schema_version": "prism.frequency_port_binding.v1",
            "status": "PORT_BINDING_WITHHELD",
            "case_count": 44,
            "reviewed_frequency_port_case_count": 0,
            "provider_packet_only_case_count": 44,
            "port_binding_mismatch_case_count": 0,
            "port_binding_withheld_case_count": 0,
            "reviewed_frequency_ports_complete": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
        },
        **_evidence_request(),
    }
    report = build_v060_readiness_report(**inputs)
    trace = report["chain"]["frequency_port_binding"]
    assert trace["source"] == "facility_evidence_request"
    assert trace["status"] == "PORT_BINDING_WITHHELD"
    assert trace["reviewed_frequency_port_case_count"] == 0
    assert trace["provider_packet_only_case_count"] == 44
    assert trace["facility_qra_allowed"] is False
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_validator_rejects_frequency_port_binding_mirror_drift():
    inputs = _inputs()
    port_binding = {
        "schema_version": "prism.frequency_port_binding.v1",
        "status": "ALIGNED",
        "port_scoped_event_count": 2,
        "port_unbound_event_count": 0,
        "all_events_port_scoped": True,
        "case_port_binding_mismatch_count": 0,
        "risk_atom_port_binding_mismatch_count": 0,
        "mismatch_count": 0,
    }
    inputs["facility_assessment"]["frequency_port_binding"] = port_binding
    inputs["facility_assessment"]["facility_risk_ledger"] = {
        "frequency_port_binding": {**port_binding, "port_scoped_event_count": 1},
    }
    report = build_v060_readiness_report(**inputs)
    with pytest.raises(V060ReadinessError, match="assessment and nested ledger"):
        validate_v060_readiness_report(report)


def test_report_records_isolation_union_extension_without_promoting_qra():
    report = build_v060_readiness_report(
        **_inputs(),
        isolation_union_extension_verification=_isolation_extension_verification(),
    )
    extension = report["chain"]["isolation_union_extension"]
    assert extension["isolation_counts"]["success_cases"] == 2
    assert extension["isolation_counts"]["failure_cases"] == 2
    assert extension["provider_response_consumed"] is True
    assert extension["diagnostic_only"] is True
    assert extension["facility_qra_claim"] is False
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_records_release_closure_worklist_without_opening_promotion():
    report = build_v060_readiness_report(
        **_inputs(), release_closure_worklist=_release_closure_worklist()
    )
    worklist = report["chain"]["release_closure_worklist"]
    assert worklist["schema"] == "prism.release_closure_worklist.v1"
    assert worklist["open_case_count"] == 3
    assert worklist["isolation_open_case_count"] == 3
    assert worklist["release_boundary_promotion_allowed"] is False
    assert worklist["diagnostic_only"] is True
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_validator_rejects_release_closure_promotion():
    report = build_v060_readiness_report(
        **_inputs(), release_closure_worklist=_release_closure_worklist()
    )
    report["chain"]["release_closure_worklist"]["facility_qra_allowed"] = True
    with pytest.raises(V060ReadinessError, match="release_closure_worklist.facility_qra_allowed"):
        validate_v060_readiness_report(report)


def test_report_validator_rejects_release_closure_case_count_drift():
    report = build_v060_readiness_report(
        **_inputs(), release_closure_worklist=_release_closure_worklist()
    )
    report["chain"]["release_closure_worklist"]["case_count"] = 2
    with pytest.raises(V060ReadinessError, match="status counts must equal case count"):
        validate_v060_readiness_report(report)


def test_report_validator_rejects_release_closure_open_status_drift():
    report = build_v060_readiness_report(
        **_inputs(), release_closure_worklist=_release_closure_worklist()
    )
    report["chain"]["release_closure_worklist"]["open_case_count"] = 2
    with pytest.raises(V060ReadinessError, match="open cases must equal non-ready status counts"):
        validate_v060_readiness_report(report)


def test_report_validator_rejects_release_closure_gap_summary_drift():
    report = build_v060_readiness_report(
        **_inputs(), release_closure_worklist=_release_closure_worklist()
    )
    report["chain"]["release_closure_worklist"]["termination_open_case_count"] = 0
    with pytest.raises(V060ReadinessError, match="termination_open_case_count"):
        validate_v060_readiness_report(report)


def test_report_records_actionable_evidence_request_without_opening_promotion():
    report = build_v060_readiness_report(
        **_inputs(), facility_evidence_request=_evidence_request()
    )
    request = report["evidence_request"]
    assert request["case_request_count"] == 3
    assert request["family_request_count"] == 1
    assert request["component_request_count"] == 1
    assert request["facility_promotion_allowed_now"] is False
    result = validate_v060_readiness_report(report)
    assert result["status"] == "VALID"


def test_report_validator_rejects_evidence_request_that_allows_promotion():
    report = build_v060_readiness_report(
        **_inputs(), facility_evidence_request=_evidence_request()
    )
    report["evidence_request"]["facility_promotion_allowed_now"] = True
    with pytest.raises(V060ReadinessError, match="cannot allow facility promotion"):
        validate_v060_readiness_report(report)


def test_report_records_scenario_evidence_without_frequency_or_qra_promotion():
    report = build_v060_readiness_report(
        **_inputs(), scenario_evidence_audit=_scenario_evidence()
    )
    evidence = report["scenario_evidence"]
    assert evidence["schema"] == "prism.inspection_center_screening_summary.v1"
    assert evidence["scenario_row_count"] == 4
    assert evidence["candidate_accident_family_counts"] == {"pipe_hole": 2, "vent_hole": 1}
    assert evidence["frequency_assigned"] is False
    assert evidence["sensor_frequency_learning_used"] is False
    assert evidence["facility_qra_claim"] is False
    assert evidence["candidate_only"] is True
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_records_atom_level_release_to_damage_closure():
    report = build_v060_readiness_report(
        **_inputs(), risk_atom_chain_audit=_atom_chain_audit()
    )
    closure = report["chain"]["risk_atom_chain_closure"]
    assert closure["status"] == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    assert closure["case_count"] == 3
    assert closure["complete_case_count"] == 3
    assert closure["risk_atom_count"] == 12
    assert closure["diagnostic_only"] is True
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_validator_rejects_atom_chain_qra_promotion():
    report = build_v060_readiness_report(
        **_inputs(), risk_atom_chain_audit=_atom_chain_audit()
    )
    report["chain"]["risk_atom_chain_closure"]["facility_qra_claim"] = True
    with pytest.raises(V060ReadinessError, match="risk atom chain closure cannot claim facility QRA"):
        validate_v060_readiness_report(report)


def test_report_records_equipment_state_release_chain():
    report = build_v060_readiness_report(
        **_inputs(), equipment_state_release_audit=_equipment_chain_audit()
    )
    chain = report["chain"]["equipment_state_release_chain"]
    assert chain["status"] == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC"
    assert chain["case_count"] == 3
    assert chain["complete_case_count"] == 3
    assert chain["component_count"] == 1
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_uses_facility_release_boundary_gate_when_present():
    inputs = _inputs()
    inputs["facility_assessment"]["release_termination_inventory_ledger"][
        "strict_release_boundary"
    ] = {
        "schema_version": "prism.facility_release_boundary_gate.v1",
        "strict_release_boundary_ready": False,
        "checks": {"all_mass_residuals_closed": False},
        "blocking_reasons": ["tank-01: end-to-end mass residual is not closed"],
    }
    report = build_v060_readiness_report(**inputs)
    boundary = report["chain"]["release_boundary"]
    assert boundary["facility_gate_schema"] == "prism.facility_release_boundary_gate.v1"
    assert boundary["strict_release_boundary_ready"] is False
    assert any(
        "mass residual is not closed" in reason
        for reason in boundary["blocking_reasons"]
    )
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_rejects_scenario_evidence_promotion_flags():
    report = build_v060_readiness_report(
        **_inputs(), scenario_evidence_audit=_scenario_evidence()
    )
    report["scenario_evidence"]["frequency_assigned"] = True
    with pytest.raises(V060ReadinessError, match="scenario_evidence.frequency_assigned"):
        validate_v060_readiness_report(report)


def test_report_records_external_equipment_pid_and_frequency_readiness():
    external = {
        "status": "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED",
        "asset_count": 12,
        "state_model_ready_asset_count": 2,
        "event_register": {"physical_time_assigned_event_count": 0},
        "pid_identity_evidence": {
            "exact_asset_id_overlap_count": 9,
            "source_backed_overlap_count": 9,
            "unmatched_external_asset_ids": ["PIPE-CATALOG", "VALVE-CATALOG"],
            "identity_is_general_facility_resolved": False,
        },
        "pid_port_evidence": {
            "confirmed_port_mapping_count": 14,
            "candidate_port_mapping_count": 13,
            "port_crosswalk_promotion_allowed": False,
        },
        "component_binding_evidence": {
            "enabled_edge_count": 0,
            "unresolved_edge_count": 27,
            "numerical_topology_promotion_allowed": False,
        },
        "promotion_gates": {
            "accident_release_packet_allowed": False,
            "frequency_inference_allowed": False,
        },
        "facility_qra_claim": False,
    }
    scenario = {
        "status": "CROSSWALK_REQUIRED",
        "asset_count": 12,
        "mapped_asset_count": 0,
        "resolved_asset_count": 0,
        "scenario_family_count": 12,
        "promotion_gates": {
            "accident_release_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
        },
    }
    frequency = {
        "status": "FREQUENCY_BINDING_WITHHELD",
        "resolved_asset_count": 0,
        "frequency_event_count": 0,
        "valid_frequency_event_count": 0,
        "uncomputed_family_count": 12,
        "promotion_gates": {
            "provider_release_required": True,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
        },
    }
    report = build_v060_readiness_report(
        **_inputs(),
        external_equipment_model_audit=external,
        equipment_scenario_coverage_audit=scenario,
        equipment_frequency_binding_audit=frequency,
    )
    chain = report["chain"]
    assert chain["external_equipment_model_readiness"]["pid_identity_evidence"][
        "exact_asset_id_overlap_count"
    ] == 9
    assert chain["external_equipment_model_readiness"]["pid_port_evidence"][
        "confirmed_port_mapping_count"
    ] == 14
    assert chain["equipment_scenario_coverage"]["resolved_asset_count"] == 0
    assert chain["equipment_frequency_binding"]["uncomputed_family_count"] == 12
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_rejects_external_equipment_promotion_flag():
    report = build_v060_readiness_report(
        **_inputs(),
        external_equipment_model_audit={
            "status": "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED",
            "asset_count": 1,
            "state_model_ready_asset_count": 1,
            "promotion_gates": {"accident_release_packet_allowed": True},
            "facility_qra_claim": False,
        },
    )
    with pytest.raises(V060ReadinessError, match="cannot open accident release"):
        validate_v060_readiness_report(report)


def test_report_records_generic_equipment_crosswalk_and_frequency_readiness():
    report = build_v060_readiness_report(
        **_inputs(),
        generic_equipment_scenario_coverage_audit={
            "status": "SCENARIO_CATALOG_BOUND_RELEASE_BOUNDARY_UNVERIFIED",
            "asset_count": 7,
            "mapped_asset_count": 7,
            "resolved_asset_count": 7,
            "scenario_family_count": 12,
            "promotion_gates": {
                "accident_release_packet_allowed": False,
                "frequency_inference_allowed": False,
                "facility_qra_allowed": False,
            },
        },
        generic_equipment_frequency_binding_audit={
            "status": "LITERATURE_FREQUENCY_BOUND_RELEASE_UNVERIFIED",
            "resolved_asset_count": 7,
            "frequency_event_count": 24,
            "valid_frequency_event_count": 24,
            "uncomputed_family_count": 1,
            "frequency_port_binding": {
                "schema_version": "prism.frequency_port_binding.v1",
                "reviewed_port_bound_event_count": 24,
                "port_unbound_event_count": 0,
                "port_binding_withheld_event_count": 0,
                "all_supplied_port_scopes_valid": True,
                "strict_facility_qra_gate": False,
            },
            "promotion_gates": {
                "provider_release_required": True,
                "frequency_inference_allowed": False,
                "facility_qra_allowed": False,
            },
        },
        generic_diagnostic_campaign_binding={
            "schema_version": "prism.diagnostic_campaign_binding.v1",
            "status": "PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING",
            "diagnostic_only": True,
            "packet_event_count": 24,
            "campaign_event_count": 24,
            "campaign_case_count": 24,
            "campaign_risk_atom_count": 96,
            "structural_binding_complete": True,
            "packet_identity_consumed": True,
            "packet_digest_checked_event_count": 24,
            "packet_digest_match_event_count": 24,
            "packet_value_checked_event_count": 24,
            "packet_value_consumed_event_count": 24,
            "packet_subset_value_consumed": True,
            "qualified_provider_packet_count": 0,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "frequency_from_provider_packet": False,
            "packet_claims_preserved": True,
        },
        generic_chain_closure_audit={
            "schema_version": "prism.facility_chain_closure_audit.v1",
            "status": "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED",
            "diagnostic_only": True,
            "campaign_event_count": 24,
            "campaign_case_count": 24,
            "campaign_risk_atom_count": 96,
            "packet_event_count": 24,
            "packet_chain_closed_event_count": 24,
            "packet_chain_mismatch_event_count": 0,
            "campaign_events_without_packet_count": 0,
            "facility_ir_aggregate_closed": True,
            "facility_fn_aggregate_closed": True,
            "facility_total_risk_available": False,
            "complete_facility_qra_claim": False,
            "qualified_provider_packet_count": 0,
            "frequency_from_provider_packet": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
    )
    assert report["chain"]["generic_equipment_scenario_coverage"]["resolved_asset_count"] == 7
    assert report["chain"]["generic_equipment_frequency_binding"]["valid_frequency_event_count"] == 24
    assert report["chain"]["generic_equipment_frequency_binding"]["frequency_port_binding"]["reviewed_port_bound_event_count"] == 24
    assert report["chain"]["generic_equipment_frequency_binding"]["frequency_port_binding"]["port_unbound_event_count"] == 0
    assert report["chain"]["generic_diagnostic_campaign_binding"]["packet_event_count"] == 24
    assert report["chain"]["generic_diagnostic_campaign_binding"]["campaign_risk_atom_count"] == 96
    assert report["chain"]["generic_diagnostic_campaign_binding"]["packet_identity_consumed"] is True
    assert report["chain"]["generic_diagnostic_campaign_binding"]["packet_digest_match_event_count"] == 24
    assert report["chain"]["generic_diagnostic_campaign_binding"]["packet_value_consumed_event_count"] == 24
    assert report["chain"]["generic_release_to_final_damage_closure"]["packet_chain_closed_event_count"] == 24
    assert report["chain"]["generic_release_to_final_damage_closure"]["facility_ir_aggregate_closed"] is True
    assert report["chain"]["generic_release_to_final_damage_closure"]["facility_fn_aggregate_closed"] is True
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_records_generic_provider_release_closure_without_promotion():
    report = build_v060_readiness_report(
        **_inputs(),
        generic_provider_closure_audit={
            "schema_version": "prism.generic_provider_release_closure_audit.v1",
            "status": "CLOSURE_EVIDENCE_OPEN",
            "event_count": 24,
            "closure_ready_event_count": 3,
            "closure_open_event_count": 21,
            "packet_path_count": 24,
            "provider_packet_count": 26,
            "closure_ready_packet_path_count": 3,
            "closure_ready_provider_packet_count": 5,
            "closure_gap_counts": {
                "provider mass balance is required for inventory depletion": 6,
            },
            "qualified_provider_packet_count": 0,
            "frequency_from_provider_packet": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
    )
    closure = report["chain"]["generic_provider_release_closure"]
    assert closure["closure_ready_event_count"] == 3
    assert closure["closure_open_event_count"] == 21
    assert closure["qualified_provider_packet_count"] == 0
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_binds_every_provider_packet_to_evidence_request_catalog():
    report = build_v060_readiness_report(
        **_inputs(),
        generic_provider_closure_audit={
            "schema_version": "prism.generic_provider_release_closure_audit.v1",
            "status": "CLOSURE_EVIDENCE_OPEN",
            "event_count": 2,
            "closure_ready_event_count": 1,
            "closure_open_event_count": 1,
            "packet_path_count": 2,
            "provider_packet_count": 3,
            "closure_ready_packet_path_count": 1,
            "closure_ready_provider_packet_count": 2,
            "qualified_provider_packet_count": 0,
            "frequency_from_provider_packet": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        generic_provider_evidence_requests={
            "schema_version": "prism.generic_provider_evidence_requests.v1",
            "status": "OPEN_PROVIDER_EVIDENCE_REQUESTS",
            "source_status": "CLOSURE_EVIDENCE_OPEN",
            "event_count": 2,
            "packet_path_count": 2,
            "packet_count": 3,
            "request_count": 3,
            "closure_open_request_count": 1,
            "qualification_open_request_count": 2,
            "qualified_provider_packet_count": 0,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "diagnostic_only": True,
        },
    )
    catalog = report["chain"]["generic_provider_evidence_requests"]
    assert catalog["packet_count"] == 3
    assert catalog["request_count"] == 3
    assert catalog["closure_open_request_count"] == 1
    assert catalog["qualification_open_request_count"] == 2
    assert validate_v060_readiness_report(report)["status"] == "VALID"


def test_report_rejects_provider_evidence_request_packet_drift():
    report = build_v060_readiness_report(
        **_inputs(),
        generic_provider_closure_audit={
            "schema_version": "prism.generic_provider_release_closure_audit.v1",
            "status": "CLOSURE_EVIDENCE_OPEN",
            "event_count": 1,
            "closure_ready_event_count": 0,
            "closure_open_event_count": 1,
            "packet_path_count": 1,
            "provider_packet_count": 2,
            "closure_ready_packet_path_count": 0,
            "closure_ready_provider_packet_count": 0,
            "qualified_provider_packet_count": 0,
            "frequency_from_provider_packet": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        generic_provider_evidence_requests={
            "schema_version": "prism.generic_provider_evidence_requests.v1",
            "status": "OPEN_PROVIDER_EVIDENCE_REQUESTS",
            "event_count": 1,
            "packet_path_count": 1,
            "packet_count": 1,
            "request_count": 1,
            "closure_open_request_count": 1,
            "qualification_open_request_count": 0,
            "qualified_provider_packet_count": 0,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "diagnostic_only": True,
        },
    )
    with pytest.raises(V060ReadinessError, match="disagrees with closure audit"):
        validate_v060_readiness_report(report)


def test_report_binds_provider_sidecar_audit_to_evidence_catalog():
    report = build_v060_readiness_report(
        **_inputs(),
        generic_provider_evidence_requests={
            "schema_version": "prism.generic_provider_evidence_requests.v1",
            "packet_count": 2,
            "request_count": 2,
            "closure_open_request_count": 1,
            "qualification_open_request_count": 1,
            "qualified_provider_packet_count": 0,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "diagnostic_only": True,
        },
        generic_provider_evidence_audit={
            "schema_version": "prism.generic_provider_evidence_audit.v1",
            "status": "NO_QUALIFIED_PROVIDER_EVIDENCE",
            "packet_count": 2,
            "request_count": 2,
            "qualification_sidecar_present_count": 0,
            "exact_match_count": 0,
            "qualified_provider_packet_count": 0,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "diagnostic_only": True,
        },
    )
    audit = report["chain"]["generic_provider_evidence_audit"]
    assert audit["request_count"] == 2
    assert validate_v060_readiness_report(report)["status"] == "VALID"
