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
            "_record_path": "benchmark.json",
        },
    }


def test_objective_audit_separates_conditional_chain_from_strict_gates():
    report = build_ijhe_objective_coverage_audit(**_inputs())
    assert report["status"] == "CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN"
    assert report["conditional_chain_complete"] is True
    assert report["strict_facility_qra_claim"] is False
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
