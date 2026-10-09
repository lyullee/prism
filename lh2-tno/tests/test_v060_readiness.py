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
