from lh2_tno.v060_readiness import build_v060_readiness_report


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


def test_report_keeps_conditional_chain_and_strict_gate_separate():
    report = build_v060_readiness_report(**_inputs())
    assert report["schema_version"] == "prism.v060_ijhe_readiness_report.v1"
    assert report["conditional_chain_complete"] is True
    assert report["promotion"]["complete_facility_qra_claim"] is False
    assert report["chain"]["event_count"] == 2
    assert report["accident_families"]["rows"][0]["conditional_status"] == "EXECUTED"
    assert report["timing"]["cache_meets_one_hz_all_samples"] is True
    assert report["timing"]["fresh_physics_meets_one_hz"] is False


def test_report_marks_explicit_exclusions_and_withheld_cases():
    report = build_v060_readiness_report(**_inputs())
    assert "sensor_based_frequency_learning" in report["explicit_exclusions"]
    assert report["chain"]["qualified_evidence_withheld_case_count"] == 1
    assert report["equipment"]["component_rows"][0]["strict_gate_categories"] == ["MISSING_PROVIDER_CASES"]
    assert report["validation_domains"][0]["status"] == "RESTRICTED_COMPONENT_EVIDENCE"
