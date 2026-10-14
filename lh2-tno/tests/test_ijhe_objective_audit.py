from lh2_tno.ijhe_objective_audit import build_ijhe_objective_coverage_audit


def _inputs():
    return {
        "union_verification": {"_record_path": "union-verification.json"},
        "completion_audit": {"status": "INCOMPLETE_EVIDENCE", "_record_path": "completion.json"},
        "scope_matrix": {
            "conditional_chain_complete": True,
            "matrix_complete": False,
            "required_families": ["vessel_hole"],
            "blocking_reasons": ["vessel_hole: PARTIAL"],
            "gap_summary": {"qualification_gap_family_count": 1},
            "rows": [{
                "family": "vessel_hole",
                "gap_class": "QUALIFICATION_EVIDENCE_WITHHELD",
                "case_status_counts": {"EXECUTED_OPERATOR_LIMITED": 1},
                "gap_reasons": ["diagnostic evidence"],
                "closure_requirements": ["qualified packet"],
            }],
            "_record_path": "scope.json",
        },
        "facility_assessment": {
            "conditional_diagnostic_facility_risk_available": True,
            "conditional_diagnostic_facility_expected_death_fn_low_high": [[1.0]],
            "conditional_diagnostic_facility_coverage": {"risk_atom_count": 4},
            "facility_total_risk_available": False,
            "complete_facility_qra_claim": False,
            "physical_validation_claim": False,
            "population_accounting": {
                "status": "RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC",
                "missing_condition_ids": [],
                "missing_population_condition_ids": [],
                "mismatched_receptor_ids": {},
                "annual_condition_count": 1,
            },
            "scenario_branch_accounting": {
                "status": "EXPLICIT_BRANCH_ACCOUNTING",
                "scenario_cross_product_count": 4,
                "missing_dimension_atom_count": 0,
            },
            "frequency_uncertainty": {"scenarios": [{"id": "central"}]},
            "_record_path": "facility.json",
        },
        "native_catalog_verification": {
            "frequency_event_count": 1,
            "exact_native_packet_count": 1,
            "uncomputed_event_count": 0,
            "_record_path": "catalog.json",
        },
        "state_snapshot_audit": {
            "status": "STATE_SNAPSHOT_BOUND_AND_ECHOED",
            "record_count": 1,
            "bound_count": 1,
            "unbound_count": 0,
            "_record_path": "snapshot.json",
        },
        "native_packet_evidence": {
            "status": "EXACT_NATIVE_SCOPE_PACKET_EVIDENCE",
            "event_count": 1,
            "exact_event_count": 1,
            "_record_path": "packet.json",
        },
        "native_packet_campaign_ledger": {
            "event_count": 1,
            "case_count": 1,
            "chain_executed_case_count": 1,
            "uncomputed_case_count": 0,
            "packet_identity_consumed": True,
            "state_snapshot_campaign_reconciliation": {
                "status": "STATE_SNAPSHOT_CAMPAIGN_RECONCILED",
            },
            "qualified_provider_packet_case_count": 0,
            "provider_packet_promoted": False,
            "_record_path": "campaign.json",
        },
        "slabx_validation_evidence": {
            "schema_version": "prism.slabx_lh2_validation_audit.v1",
            "status": "RESTRICTED_SLABX_LH2_CONSEQUENCE_EVIDENCE",
            "checks": [{"name": "model_identity", "status": "PASS"}],
            "metrics": {
                "ffi_case_count": 6,
                "flacs_comparison_row_count": 6,
                "max_scenario_mass_residual_kg": 1.0e-12,
                "runtime_repeat_inventory_difference_kg": 0.0,
            },
            "physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
            "_record_path": "slabx.json",
        },
        "validation_evidence_matrix": {
            "status": "RESTRICTED_EVIDENCE_MATRIX",
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "_record_path": "validation.json",
        },
        "realtime_cache_benchmark": {
            "cache_meets_one_hz_all_samples": True,
            "cache_p95_ms": 10.0,
            "fresh_physics_elapsed_ms": 2000.0,
            "fresh_physics_meets_one_hz": False,
            "mode_contract": {
                "schema": "prism.realtime_mode_contract.v1",
                "observed_evaluation_modes": [
                    "fresh_physics_background",
                    "cached_diagnostic_1hz",
                ],
                "fresh_physics_1hz_claim": False,
                "stale_fallback_used": False,
                "frequency_learning": False,
                "release_inference": False,
            },
            "_record_path": "benchmark.json",
        },
    }


def _external_intake():
    return {
        "schema_version": "prism.external_release_artifact_intake.v1",
        "status": "EXTERNAL_RELEASE_ARTIFACTS_REQUIRE_QUALIFICATION",
        "diagnostic_only": True,
        "artifact_file_count": 2,
        "release_row_count": 3,
        "qualified_sidecar_row_count": 0,
        "closure_ready_row_count": 0,
        "actual_origin_row_count": 0,
        "synthetic_or_model_prediction_row_count": 3,
        "error_count": 0,
        "errors": [],
        "closure_status_counts": {"SCHEMA_UNQUALIFIED": 3},
        "promotion_policy": {
            "frequency_assigned": False,
            "provider_release_packet_promoted": False,
            "physical_validation_promoted": False,
            "facility_qra_promoted": False,
            "qualification_requires_exact_digest_bound_sidecar": True,
            "provider_ports_never_substituted_for_frequency_ports": True,
        },
        "_record_path": "external-intake.json",
    }


def test_objective_audit_separates_conditional_chain_from_strict_gates():
    inputs = _inputs()
    inputs["external_release_artifact_intake"] = _external_intake()
    report = build_ijhe_objective_coverage_audit(**inputs)
    assert report["status"] == "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"
    assert report["conditional_chain_complete"] is True
    assert report["strict_facility_qra_claim"] is False
    assert [item["status"] for item in report["completion_criteria"]] == [
        "CONDITIONAL_PASS",
        "CONDITIONAL_PASS",
        "CONDITIONAL_PASS",
        "CONDITIONAL_PASS",
        "CONDITIONAL_PASS",
    ]
    assert "detonation_or_DDT" in report["explicit_exclusions"]
    criteria = {item["id"]: item for item in report["completion_criteria"]}
    assert criteria["C_facility_ir_fn_and_scope"]["strict_gate_open"] is True
    assert "strict_facility_scope" in criteria["C_facility_ir_fn_and_scope"]["open_strict_gate_ids"]
    assert criteria["E_validation_and_processing_time"]["strict_gate_open"] is True
    assert "independent_physical_validation" in criteria["E_validation_and_processing_time"]["open_strict_gate_ids"]
    assert "qualified_provider_evidence" in report["strict_blocking_check_ids"]
    assert "release_to_final_damage" not in report["core_blocking_check_ids"]
    assert "slabx_lh2_component_consequence_validation" not in report["core_blocking_check_ids"]
    scope_check = next(row for row in report["checks"] if row["id"] == "generic_lh2_scope")
    assert scope_check["observed"]["scope_gap_summary"]["qualification_gap_family_count"] == 1
    assert scope_check["observed"]["scope_gap_rows"][0]["gap_class"] == "QUALIFICATION_EVIDENCE_WITHHELD"
    weather_check = next(
        row for row in report["checks"] if row["id"] == "weather_ignition_population"
    )
    assert weather_check["status"] == "CONDITIONALLY_COMPLETE"
    assert weather_check["observed"]["scenario_cross_product_count"] == 4
    assert weather_check["observed"]["scenario_missing_dimension_atom_count"] == 0
    intake_check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_external_release_artifact_intake"
    )
    assert intake_check["status"] == "PASS"
    assert intake_check["observed"]["release_row_count"] == 3


def test_objective_audit_blocks_malformed_external_release_intake():
    inputs = _inputs()
    inputs["external_release_artifact_intake"] = _external_intake()
    inputs["external_release_artifact_intake"]["promotion_policy"][
        "facility_qra_promoted"
    ] = True
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_external_release_artifact_intake"
    )
    assert check["status"] == "BLOCKED_EVIDENCE"
    assert report["status"] == "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"


def test_objective_audit_aligns_latest_full_completion_audit():
    inputs = _inputs()
    names = [
        "diagnostic_worklist_packet_coverage_evidence",
        "diagnostic_release_trace_coverage",
        "diagnostic_numerical_scope_coverage",
        "diagnostic_facility_frequency_port_binding",
        "diagnostic_external_release_artifact_intake",
        "diagnostic_facility_evidence_request_coverage",
    ]
    inputs["completion_audit"] = {
        "schema_version": "prism.ijhe_completion_audit.v1",
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [
            {"name": name, "status": (
                "PASS_DIAGNOSTIC_ONLY_WITHHELD"
                if name == "diagnostic_facility_frequency_port_binding"
                else "PASS_DIAGNOSTIC_ONLY"
                if name == "diagnostic_external_release_artifact_intake"
                else "PASS"
            )}
            for name in names
        ] + [{"name": f"other-{i}", "status": "PASS"} for i in range(38)],
        "blocking_reasons": ["a", "b", "c", "d", "e"],
        "physical_validation_claim": False,
        "complete_facility_qra_claim": False,
        "_record_path": "full-completion.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    row = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_full_completion_audit_alignment"
    )
    assert row["status"] == "PASS"
    assert row["observed"]["check_count"] == 44


def test_objective_audit_blocks_misaligned_full_completion_audit():
    inputs = _inputs()
    inputs["completion_audit"] = {
        "schema_version": "prism.ijhe_completion_audit.v1",
        "status": "INCOMPLETE_EVIDENCE",
        "checks": [{"name": f"other-{i}", "status": "PASS"} for i in range(44)],
        "blocking_reasons": ["a", "b", "c", "d", "e"],
        "physical_validation_claim": False,
        "complete_facility_qra_claim": False,
        "_record_path": "full-completion.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    row = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_full_completion_audit_alignment"
    )
    assert row["status"] == "BLOCKED_EVIDENCE"


def test_objective_audit_blocks_realtime_timing_without_mode_contract():
    inputs = _inputs()
    inputs["realtime_cache_benchmark"]["mode_contract"]["stale_fallback_used"] = True
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(row for row in report["checks"] if row["id"] == "realtime_processing")
    assert check["status"] == "BLOCKED_EVIDENCE"
    assert check["observed"]["mode_contract_valid"] is False


def test_objective_audit_records_field_model_comparison_as_diagnostic_only():
    inputs = _inputs()
    inputs["external_field_model_comparison"] = {
        "schema_version": "prism.external_field_model_comparison.v1",
        "status": "RESTRICTED_FIELD_MODEL_COMPARISON",
        "event_id": "field-trial-01",
        "matching": {"matched_row_count": 4, "matched_fraction": 1.0},
        "metrics": {"rmse_vol_pct": 0.02},
        "source_boundary_binding": {"mode": "measured_source_replay"},
        "independent_physical_validation_review_eligible": False,
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "measured_source_replay_is_not_independent_validation": True,
            "transport_delay_is_declared_not_fitted": True,
            "no_extrapolation_outside_prediction_horizon": True,
            "physical_validation_requires_external_review": True,
            "component_comparison_does_not_validate_facility_qra": True,
        },
        "_record_path": "comparison.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    row = next(row for row in report["checks"] if row["id"] == "diagnostic_external_field_model_comparison")
    assert row["status"] == "PASS"
    assert row["observed"]["matched_row_count"] == 4
    assert report["physical_validation_claim"] is False
    assert report["status"] == "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"


def test_objective_audit_blocks_missing_native_event():
    inputs = _inputs()
    inputs["native_catalog_verification"]["uncomputed_event_count"] = 1
    report = build_ijhe_objective_coverage_audit(**inputs)
    assert report["status"] == "OBJECTIVE_CHAIN_INCOMPLETE"
    assert "equipment_state_to_native_release" in report["core_blocking_check_ids"]


def test_objective_audit_fails_closed_for_missing_optional_structures():
    inputs = _inputs()
    inputs["facility_assessment"].pop("conditional_diagnostic_facility_coverage")
    inputs["native_packet_campaign_ledger"].pop("qualified_provider_packet_case_count")
    report = build_ijhe_objective_coverage_audit(**inputs)
    assert report["status"] == "OBJECTIVE_CHAIN_INCOMPLETE"
    assert "release_to_final_damage" in report["core_blocking_check_ids"]
    assert "qualified_provider_evidence" in report["strict_blocking_check_ids"]


def test_objective_audit_requires_extension_state_coverage_for_full_union():
    inputs = _inputs()
    inputs["union_verification"]["merged_event_count"] = 2
    inputs["native_packet_campaign_ledger"]["event_count"] = 1
    inputs["native_packet_campaign_ledger"]["case_count"] = 1
    inputs["native_packet_campaign_ledger"]["chain_executed_case_count"] = 1
    inputs["native_packet_campaign_ledger"]["state_snapshot_campaign_reconciliation"] = {
        "status": "STATE_SNAPSHOT_CAMPAIGN_RECONCILED",
        "bound_event_count": 1,
    }
    inputs["native_state_snapshot_campaign_ledger"] = {
        "status": "PARTIAL_NATIVE_PACKET_CAMPAIGN_EXECUTED",
        "event_count": 1,
        "state_snapshot_campaign_reconciliation": {
            "status": "STATE_SNAPSHOT_CAMPAIGN_RECONCILED",
            "bound_event_count": 1,
            "provider_result_digest_mismatch_event_ids": [],
        },
        "_record_path": "native-state.json",
    }
    inputs["extension_state_snapshot_coverage"] = {
        "status": "EXTENSION_STATE_SNAPSHOT_COVERAGE_INCOMPLETE",
        "event_count": 1,
        "bound_event_count": 0,
        "unbound_event_count": 1,
        "missing_event_ids": ["facility/extension/AREA_1%"],
        "_record_path": "extension-state.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "strict_facility_state_snapshot_coverage"
    )
    assert check["status"] == "BLOCKED_EVIDENCE"
    assert check["observed"]["extension_state_snapshot_unbound_event_count"] == 1

    inputs["extension_state_snapshot_coverage"].update({
        "status": "EXTENSION_STATE_SNAPSHOT_COVERAGE_COMPLETE",
        "bound_event_count": 1,
        "unbound_event_count": 0,
        "missing_event_ids": [],
    })
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "strict_facility_state_snapshot_coverage"
    )
    assert check["status"] == "PASS"


def test_objective_audit_records_observed_state_source_replay():
    inputs = _inputs()
    inputs["observed_state_replay_audit"] = {
        "schema_version": "prism.observed_state_source_replay_audit.v1",
        "status": "SOURCE_REPLAY_MATCHED",
        "source_count": 3,
        "matched_source_count": 3,
        "evidence_policy_valid": True,
        "regeneration": {"canonical_digest_match": True},
        "_record_path": "observed-state-replay.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_observed_state_source_replay"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["matched_source_count"] == 3


def test_objective_audit_records_observed_state_runtime_frames_without_promotion():
    inputs = _inputs()
    inputs["observed_state_runtime_frames"] = {
        "schema_version": "prism.observed_state_runtime_frames.v1",
        "status": "STATE_RUNTIME_FRAMES_READY",
        "source_count": 1,
        "frame_count": 1,
        "evidence_sample_count": 10,
        "runtime_handoff_contract": {
            "schema": "prism.equipment_process_state.v1",
            "state_adapter": "service_state_from_runtime_frame",
            "resolver_adapter": "request_from_observed_state_runtime_frame",
            "monitor_method": "RealtimeConsequenceMonitor.update_from_runtime_frame",
            "facility_monitor_method": "FacilityRealtimeConsequenceMonitor.update_from_runtime_frames",
            "runtime_clock": "caller_supplied_now_s",
            "provider_release_required_for_consequence": True,
            "frequency_assignment": "rejected_by_request_from_equipment_resolver",
        },
        "frames": [{
            "component_id": "tank-1",
            "frame_digest": "frame-digest",
            "state_snapshot_digest": "snapshot-digest",
            "values": {"pressure": {"value_si": 500000.0}},
            "state_snapshot": {"schema_version": "prism.equipment_state_snapshot.v1"},
        }],
        "policy": {
            "state_only": True,
            "release_scenario_generated": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "provider_release_required_for_consequence": True,
        },
        "_record_path": "observed-state-runtime.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_observed_state_runtime_frames"
    )
    assert check["status"] == "PASS"
    assert report["frequency_inference_performed"] is False


def test_objective_audit_records_external_field_evidence_without_promotion():
    inputs = _inputs()
    inputs["external_field_evidence"] = {
        "schema_version": "prism.external_field_evidence.v1",
        "status": "RESTRICTED_EXTERNAL_FIELD_EVIDENCE_HASH_DRIFT",
        "event_id": "field-event-1",
        "dataset_id": "field-dataset-1",
        "scope": "lh2_free_field",
        "source_boundary": {"row_count": 10},
        "weather": {"row_count": 3},
        "receptor_observations": {"row_count": 40},
        "hash_verification_enforced": False,
        "hash_drift_channels": ["weather"],
        "model_comparison_ready": False,
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "observed_source_is_not_provider_release": True,
            "observed_data_is_not_frequency": True,
            "matched_model_prediction_required_for_validation": True,
            "component_evidence_does_not_validate_facility_qra": True,
        },
        "_record_path": "external-field.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_external_outdoor_field_evidence"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["hash_drift_channels"] == ["weather"]
    assert len(report["checks"]) == 16
    assert report["strict_blocking_check_ids"] == [
        "independent_physical_validation",
        "qualified_provider_evidence",
        "strict_facility_scope",
        "strict_facility_qra",
        "strict_facility_state_snapshot_coverage",
        "diagnostic_observed_state_source_replay",
        "diagnostic_observed_state_runtime_frames",
    ]


def test_objective_audit_records_validation_intake_without_opening_qra():
    inputs = _inputs()
    inputs["validation_intake_audit"] = {
        "schema_version": "prism.validation_intake_audit.v1",
        "status": "SCREENED_NO_PROMOTION",
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "inputs": {
            "inspection_timeseries": {
                "source_file_count": 17,
                "aggregate": {
                    "workbook_count": 17,
                    "sheet_count": 78,
                    "numeric_signal_unit_status_count": {
                        "MISSING_OR_UNCONFIRMED": 522,
                    },
                },
            },
        },
        "promotion_gates": {"promotion_allowed": False},
        "_record_path": "validation-intake.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_validation_intake_readiness"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["workbook_count"] == 17
    assert check["observed"]["promotion_allowed"] is False
    assert report["strict_facility_qra_claim"] is False


def test_objective_audit_records_external_equipment_readiness_without_release_promotion():
    inputs = _inputs()
    inputs["external_equipment_model_audit"] = {
        "schema_version": "prism.external_equipment_model_audit.v1",
        "status": "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED",
        "asset_count": 12,
        "state_model_ready_asset_count": 2,
        "event_register": {
            "physical_time_status": "unassigned",
            "valve_event_count": 36,
            "physical_time_assigned_event_count": 0,
        },
        "observation_provenance": {
            "verified_raw_historian_session_count": 0,
        },
        "pid_identity_evidence": {
            "exact_asset_id_overlap_count": 9,
            "source_backed_overlap_count": 9,
            "unmatched_external_asset_ids": ["PIPE-CATALOG", "VALVE-CATALOG"],
            "identity_is_general_facility_resolved": False,
        },
        "pid_port_evidence": {
            "confirmed_port_mapping_count": 14,
            "candidate_port_mapping_count": 13,
        },
        "component_binding_evidence": {
            "enabled_edge_count": 0,
            "unresolved_edge_count": 27,
        },
        "flow_crosswalk_evidence": {
            "candidate_pairing_count": 10,
            "unresolved_flow_tag_count": 11,
        },
        "promotion_gates": {
            "state_model_input_allowed": True,
            "accident_release_packet_allowed": False,
            "provider_qualification_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "_record_path": "external-equipment-model.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_external_equipment_model_readiness"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["state_model_ready_asset_count"] == 2
    assert check["observed"]["physical_time_assigned_event_count"] == 0
    assert check["observed"]["pid_exact_asset_id_overlap_count"] == 9
    assert check["observed"]["pid_confirmed_port_mapping_count"] == 14
    assert check["observed"]["component_binding_enabled_edge_count"] == 0
    assert check["observed"]["flow_unresolved_tag_count"] == 11
    assert check["observed"]["general_facility_identity_resolved"] is False
    assert report["strict_blocking_check_ids"] == [
        "independent_physical_validation",
        "qualified_provider_evidence",
        "strict_facility_scope",
        "strict_facility_qra",
        "strict_facility_state_snapshot_coverage",
        "diagnostic_observed_state_source_replay",
        "diagnostic_observed_state_runtime_frames",
    ]


def test_objective_audit_records_equipment_scenario_coverage_without_inference():
    inputs = _inputs()
    inputs["equipment_scenario_coverage_audit"] = {
        "schema_version": "prism.equipment_scenario_coverage_audit.v1",
        "status": "CROSSWALK_REQUIRED",
        "scenario_catalog_schema": "prism.accident_scenario_catalog.v1",
        "asset_count": 12,
        "mapped_asset_count": 0,
        "resolved_asset_count": 0,
        "scenario_family_count": 12,
        "promotion_gates": {
            "accident_release_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "policy": {
            "component_kind_is_never_inferred_from_tag": True,
            "candidate_identity_is_not_resolved_identity": True,
            "scenario_catalog_does_not_create_release": True,
            "scenario_mapping_is_not_frequency": True,
            "no_automatic_facility_qra_promotion": True,
        },
        "_record_path": "equipment-scenario-coverage.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_equipment_scenario_coverage"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["scenario_family_count"] == 12
    assert report["strict_blocking_check_ids"] == [
        "independent_physical_validation",
        "qualified_provider_evidence",
        "strict_facility_scope",
        "strict_facility_qra",
        "strict_facility_state_snapshot_coverage",
        "diagnostic_observed_state_source_replay",
        "diagnostic_observed_state_runtime_frames",
    ]


def test_objective_audit_records_equipment_frequency_binding_without_qra_promotion():
    inputs = _inputs()
    inputs["equipment_frequency_binding_audit"] = {
        "schema_version": "prism.equipment_frequency_binding_audit.v1",
        "status": "FREQUENCY_BINDING_WITHHELD",
        "resolved_asset_count": 0,
        "frequency_event_count": 0,
        "valid_frequency_event_count": 0,
        "uncomputed_family_count": 12,
        "promotion_gates": {
            "provider_release_required": True,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "provider_packet_promoted": False,
        "policy": {
            "literature_frequency_is_not_field_validated": True,
            "sensor_frequency_learning_used": False,
            "normal_state_observations_do_not_create_frequency": True,
            "unresolved_assets_do_not_receive_zero_frequency": True,
            "unmapped_families_remain_uncomputed": True,
            "frequency_does_not_create_provider_release": True,
            "provider_release_required_before_consequence": True,
            "facility_qra_requires_complete_family_and_packet_coverage": True,
        },
        "_record_path": "equipment-frequency-binding.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_equipment_frequency_binding"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["uncomputed_family_count"] == 12
    assert report["strict_blocking_check_ids"] == [
        "independent_physical_validation",
        "qualified_provider_evidence",
        "strict_facility_scope",
        "strict_facility_qra",
        "strict_facility_state_snapshot_coverage",
        "diagnostic_observed_state_source_replay",
        "diagnostic_observed_state_runtime_frames",
    ]


def test_objective_audit_records_generic_equipment_scope_and_literature_frequency():
    inputs = _inputs()
    inputs["generic_equipment_scenario_coverage_audit"] = {
        "schema_version": "prism.equipment_scenario_coverage_audit.v1",
        "status": "SCENARIO_CATALOG_BOUND_RELEASE_BOUNDARY_UNVERIFIED",
        "scenario_catalog_schema": "prism.accident_scenario_catalog.v1",
        "asset_count": 7,
        "mapped_asset_count": 7,
        "resolved_asset_count": 7,
        "state_model_ready_mapped_asset_count": 7,
        "scenario_family_count": 12,
        "promotion_gates": {
            "scenario_mapping_allowed": True,
            "accident_release_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "policy": {
            "component_kind_is_never_inferred_from_tag": True,
            "candidate_identity_is_not_resolved_identity": True,
            "scenario_catalog_does_not_create_release": True,
            "scenario_mapping_is_not_frequency": True,
            "no_automatic_facility_qra_promotion": True,
        },
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "_record_path": "generic-scenario-coverage.json",
    }
    inputs["generic_equipment_frequency_binding_audit"] = {
        "schema_version": "prism.equipment_frequency_binding_audit.v1",
        "status": "LITERATURE_FREQUENCY_BOUND_RELEASE_UNVERIFIED",
        "asset_count": 7,
        "resolved_asset_count": 7,
        "frequency_event_count": 24,
        "valid_frequency_event_count": 24,
        "uncomputed_family_count": 1,
        "promotion_gates": {
            "literature_frequency_binding_allowed": True,
            "provider_release_required": True,
            "consequence_binding_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "policy": {
            "literature_frequency_is_not_field_validated": True,
            "sensor_frequency_learning_used": False,
            "normal_state_observations_do_not_create_frequency": True,
            "unresolved_assets_do_not_receive_zero_frequency": True,
            "unmapped_families_remain_uncomputed": True,
            "frequency_does_not_create_provider_release": True,
            "provider_release_required_before_consequence": True,
            "facility_qra_requires_complete_family_and_packet_coverage": True,
        },
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "provider_packet_promoted": False,
        "_record_path": "generic-frequency-binding.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    scenario_check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_equipment_scenario_coverage"
    )
    frequency_check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_equipment_frequency_binding"
    )
    assert scenario_check["status"] == "PASS"
    assert scenario_check["observed"]["resolved_asset_count"] == 7
    assert frequency_check["status"] == "PASS"
    assert frequency_check["observed"]["valid_frequency_event_count"] == 24
    assert report["strict_facility_qra_claim"] is False


def test_objective_audit_records_open_release_closure_worklist_without_promotion():
    inputs = _inputs()
    inputs["release_closure_worklist"] = {
        "schema_version": "prism.release_closure_worklist.v1",
        "status": "OPEN_RELEASE_CLOSURE_WORKLIST",
        "case_count": 4,
        "open_case_count": 4,
        "summary": {
            "closure_status_counts": {"TERMINATION_OPEN": 4},
            "closure_gap_counts": {
                "ISOLATION_OPEN": 4,
                "TERMINATION_OPEN": 4,
                "PROVIDER_QUALIFICATION_OPEN": 4,
            },
            "mass_closure_open_case_count": 0,
            "isolation_open_case_count": 4,
            "termination_open_case_count": 4,
            "inventory_closure_open_case_count": 0,
            "provider_packet_required_case_count": 4,
        },
        "promotion_gates": {
            "release_boundary_promotion_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "physical_validation_claim": False,
            "diagnostic_only": True,
        },
        "_record_path": "release-closure-worklist.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_release_closure_worklist"
    )
    assert check["status"] == "BLOCKED_EVIDENCE"
    assert check["observed"]["open_case_count"] == 4
    assert check["observed"]["closure_gap_counts"]["ISOLATION_OPEN"] == 4
    assert report["status"] == "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"
    assert "diagnostic_release_closure_worklist" not in report["strict_blocking_check_ids"]


def test_objective_audit_marks_closed_release_closure_worklist_as_diagnostic_pass():
    inputs = _inputs()
    inputs["release_closure_worklist"] = {
        "schema_version": "prism.release_closure_worklist.v1",
        "status": "CLOSED_DIAGNOSTIC_BOUNDARY_WORKLIST",
        "case_count": 1,
        "open_case_count": 0,
        "summary": {
            "closure_status_counts": {"READY_FOR_STRICT_REVIEW": 1},
            "closure_gap_counts": {},
            "mass_closure_open_case_count": 0,
            "isolation_open_case_count": 0,
            "termination_open_case_count": 0,
            "inventory_closure_open_case_count": 0,
            "provider_packet_required_case_count": 0,
        },
        "promotion_gates": {
            "release_boundary_promotion_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "physical_validation_claim": False,
            "diagnostic_only": True,
        },
        "_record_path": "closed-release-closure-worklist.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_release_closure_worklist"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["closure_closed"] is True


def test_objective_audit_records_provider_evidence_catalog_without_promotion():
    inputs = _inputs()
    inputs["generic_provider_evidence_requests"] = {
        "schema_version": "prism.generic_provider_evidence_requests.v1",
        "status": "OPEN_PROVIDER_EVIDENCE_REQUESTS",
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
        "_record_path": "provider-evidence-requests.json",
    }
    inputs["generic_provider_closure_audit"] = {
        "schema_version": "prism.generic_provider_release_closure_audit.v1",
        "provider_packet_count": 3,
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_provider_evidence_requests"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["request_count"] == 3
    assert check["observed"]["catalog_matches_closure"] is True
    assert report["strict_facility_qra_claim"] is False


def test_objective_audit_blocks_provider_evidence_catalog_packet_drift():
    inputs = _inputs()
    inputs["generic_provider_evidence_requests"] = {
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
        "_record_path": "provider-evidence-requests.json",
    }
    inputs["generic_provider_closure_audit"] = {
        "schema_version": "prism.generic_provider_release_closure_audit.v1",
        "provider_packet_count": 2,
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_provider_evidence_requests"
    )
    assert check["status"] == "BLOCKED_EVIDENCE"
    assert report["status"] == "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"


def test_objective_audit_records_event_level_provider_release_closure():
    inputs = _inputs()
    inputs["generic_provider_closure_audit"] = {
        "schema_version": "prism.generic_provider_release_closure_audit.v1",
        "status": "CLOSURE_EVIDENCE_OPEN",
        "event_count": 2,
        "event_closure_status_counts": {
            "CLOSURE_EVIDENCE_OPEN": 1,
            "CLOSURE_READY_FOR_QUALIFICATION": 1,
        },
        "closure_ready_event_count": 1,
        "closure_open_event_count": 1,
        "packet_path_count": 2,
        "provider_packet_count": 2,
        "closure_ready_packet_path_count": 1,
        "closure_ready_provider_packet_count": 1,
        "qualified_provider_packet_count": 0,
        "frequency_from_provider_packet": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "promotion_gates": {
            "closure_ready": False,
            "qualified_provider_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "diagnostic_only": True,
        },
        "_record_path": "provider-release-closure.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    row = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_provider_release_closure"
    )
    assert row["status"] == "PASS"
    assert row["observed"]["closure_open_event_count"] == 1
    assert row["observed"]["closure_counts_match"] is True
    assert report["strict_facility_qra_claim"] is False


def test_objective_audit_blocks_provider_release_closure_count_drift():
    inputs = _inputs()
    inputs["generic_provider_closure_audit"] = {
        "schema_version": "prism.generic_provider_release_closure_audit.v1",
        "status": "CLOSURE_EVIDENCE_OPEN",
        "event_count": 2,
        "event_closure_status_counts": {"CLOSURE_EVIDENCE_OPEN": 2},
        "closure_ready_event_count": 0,
        "closure_open_event_count": 1,
        "packet_path_count": 2,
        "provider_packet_count": 2,
        "closure_ready_packet_path_count": 0,
        "closure_ready_provider_packet_count": 0,
        "qualified_provider_packet_count": 0,
        "frequency_from_provider_packet": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "promotion_gates": {
            "closure_ready": False,
            "qualified_provider_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "diagnostic_only": True,
        },
        "_record_path": "provider-release-closure-drift.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    row = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_provider_release_closure"
    )
    assert row["status"] == "BLOCKED_EVIDENCE"
    assert row["observed"]["closure_counts_match"] is False
    assert report["strict_facility_qra_claim"] is False


def test_objective_audit_records_provider_sidecar_audit_without_promotion():
    inputs = _inputs()
    inputs["generic_provider_evidence_requests"] = {
        "schema_version": "prism.generic_provider_evidence_requests.v1",
        "packet_count": 2,
        "request_count": 2,
        "closure_open_request_count": 1,
        "qualification_open_request_count": 1,
        "qualified_provider_packet_count": 0,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "diagnostic_only": True,
    }
    inputs["generic_provider_evidence_audit"] = {
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
        "_record_path": "provider-evidence-audit.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_provider_evidence_audit"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["exact_match_count"] == 0
    assert report["strict_facility_qra_claim"] is False


def test_objective_audit_accepts_sidecar_match_count_as_diagnostic_progress():
    inputs = _inputs()
    inputs["generic_provider_evidence_requests"] = {
        "schema_version": "prism.generic_provider_evidence_requests.v1",
        "packet_count": 2,
        "request_count": 2,
        "closure_open_request_count": 1,
        "qualification_open_request_count": 1,
        "qualified_provider_packet_count": 0,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "diagnostic_only": True,
    }
    inputs["generic_provider_evidence_audit"] = {
        "schema_version": "prism.generic_provider_evidence_audit.v1",
        "status": "QUALIFIED_SIDECAR_EVIDENCE_FOUND",
        "packet_count": 2,
        "request_count": 2,
        "qualification_sidecar_present_count": 1,
        "exact_match_count": 1,
        "qualified_provider_packet_count": 1,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "diagnostic_only": True,
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_generic_provider_evidence_audit"
    )
    assert check["status"] == "PASS"


def test_objective_audit_records_observed_state_model_binding_without_release_promotion():
    inputs = _inputs()
    inputs["observed_state_model_binding_audit"] = {
        "schema": "prism.observed_state_model_binding_audit.v1",
        "status": "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY",
        "observed_component_count": 3,
        "state_model_bound_component_count": 3,
        "diagnostic_release_adapter_component_count": 3,
        "facility_component_identity_resolved_count": 0,
        "qualified_provider_packet_count": 0,
        "rows": [
            {"status": "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE"},
            {"status": "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE"},
            {"status": "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE"},
        ],
        "policy": {
            "normal_state_model_is_not_accident_release": True,
            "diagnostic_adapter_is_not_qualified_provider": True,
            "facility_component_identity_is_not_resolved": True,
            "facility_identity_required_for_accident_binding": True,
            "release_event_binding_is_not_created": True,
            "frequency_is_not_assigned": True,
            "facility_ir_fn_promotion": False,
            "diagnostic_only": True,
        },
        "_record_path": "observed-state-model-binding.json",
    }
    report = build_ijhe_objective_coverage_audit(**inputs)
    check = next(
        row for row in report["checks"]
        if row["id"] == "diagnostic_observed_state_model_binding"
    )
    assert check["status"] == "PASS"
    assert check["observed"]["state_model_bound_component_count"] == 3
    assert report["strict_facility_qra_claim"] is False
