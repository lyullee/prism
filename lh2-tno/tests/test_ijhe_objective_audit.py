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
