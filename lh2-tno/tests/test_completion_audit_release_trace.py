from lh2_tno.completion_audit import build_ijhe_completion_audit


def _status() -> dict:
    return {
        "physical_validation_claim": False,
        "provider_release_contract_actual_facility_packet_available": False,
        "external_provider_evidence_release_inventory_status": "NO_ACCIDENT_RELEASE_EXPORT",
    }


def test_completion_audit_checks_case_keyed_conditional_release_trace() -> None:
    trace = {
        "schema_version": "prism.conditional_facility_release_trace.v1",
        "source_status": "CASE_BOUNDARY_PARTIAL",
        "case_key_definition": "event_id|release_branch_id|annual_condition_id",
        "summary": {
            "case_count": 1,
            "risk_atom_count": 1,
            "facility_ir_fn_promotion": False,
        },
        "rows": [
            {
                "case_key": "event-1||weather-1",
                "numerical_release_closed": True,
                "risk_atom_accounting": {"risk_atom_count": 1},
                "facility_qra_promotion_eligible": False,
            }
        ],
        "semantics": {"promotion": "diagnostic only"},
    }
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        facility_assessment={
            "conditional_diagnostic_facility_coverage": {
                "case_count": 1,
                "risk_atom_count": 1,
            }
        },
        conditional_facility_release_trace=trace,
    )
    check = next(
        row
        for row in report["checks"]
        if row["name"] == "diagnostic_conditional_facility_release_trace"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True


def test_completion_audit_rejects_release_trace_promotion_claim() -> None:
    trace = {
        "schema_version": "prism.conditional_facility_release_trace.v1",
        "source_status": "CASE_BOUNDARY_PARTIAL",
        "case_key_definition": "event_id|release_branch_id|annual_condition_id",
        "summary": {"case_count": 1, "risk_atom_count": 1, "facility_ir_fn_promotion": True},
        "rows": [
            {
                "case_key": "event-1||weather-1",
                "numerical_release_closed": True,
                "risk_atom_accounting": {"risk_atom_count": 1},
                "facility_qra_promotion_eligible": False,
            }
        ],
        "semantics": {},
    }
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        conditional_facility_release_trace=trace,
    )
    check = next(
        row
        for row in report["checks"]
        if row["name"] == "diagnostic_conditional_facility_release_trace"
    )
    assert check["status"] == "BLOCKED"
    assert "unsafe promotion" in check["blocking_reason"]


def test_completion_audit_checks_literature_frequency_trace() -> None:
    view = {
        "release_trace": {
            "schema_version": "prism.conditional_facility_release_trace.v1",
            "source_status": "CASE_BOUNDARY_PARTIAL",
            "case_key_definition": "event_id|release_branch_id|annual_condition_id",
            "summary": {
                "case_count": 1,
                "risk_atom_count": 1,
                "facility_ir_fn_promotion": False,
            },
            "rows": [
                {
                    "case_key": "event-1||weather-1",
                    "numerical_release_closed": True,
                    "risk_atom_accounting": {"risk_atom_count": 1},
                    "facility_qra_promotion_eligible": False,
                }
            ],
            "semantics": {"promotion": "diagnostic only"},
        },
        "promotion_gates": {
            "release_boundary": {
                "status": "BLOCKED",
                "promotion_allowed": False,
            },
            "provider_qualification": {
                "status": "BLOCKED",
                "promotion_allowed": False,
            },
            "independent_physical_validation": {
                "status": "BLOCKED",
                "promotion_allowed": False,
            },
            "facility_ir_fn": {
                "status": "BLOCKED",
                "promotion_allowed": False,
            },
            "all_gates_closed": False,
            "promotion_allowed": False,
        },
        "frequency_uncertainty": {
            "schema_version": "prism.conditional_facility_frequency_trace.v1",
            "scenario_count": 1,
            "scenario_ids": ["published"],
            "statistical_confidence_interval": False,
            "facility_credible_interval": False,
            "frequency_port_binding": {
                "status": "ALIGNED",
                "frequency_inference_allowed": False,
            },
            "provider_packet_promoted": False,
            "complete_facility_qra_claim": False,
            "physical_validation_claim": False,
            "asset_rank_stability": {
                "scenario_count": 1,
                "top_ids_by_endpoint": [["asset-1"]],
                "top_id_consistent_by_endpoint": [True],
                "top_id_consistent": True,
            },
            "scenario_family_rank_stability": {
                "scenario_count": 1,
                "top_ids_by_endpoint": [["family-1"]],
                "top_id_consistent_by_endpoint": [True],
                "top_id_consistent": True,
            },
            "uncomputed_case_count_by_scenario": {"published": 1},
            "uncomputed_case_unique_key_count_by_scenario": {"published": 1},
            "uncomputed_case_duplicate_row_count_by_scenario": {"published": 0},
            "uncomputed_case_union_count": 1,
            "uncomputed_case_status_counts_by_scenario": {
                "published": {"EXECUTED_OPERATOR_LIMITED": 1}
            },
            "uncomputed_case_policy": "explicit status; no substitution",
            "scenarios": [
                {
                    "id": "published",
                    "asset_quantiles": {"asset-1": "published"},
                    "event_quantiles": {},
                    "provenance": "literature catalogue",
                    "correlation_assumption": "within_asset_shared_quantile",
                    "conditional_diagnostic_facility_annual_ir_low_high": {
                        "worker-1": [0.0, 0.0]
                    },
                    "conditional_diagnostic_facility_expected_death_fn_low_high": [
                        {},
                        {},
                    ],
                    "uncomputed_case_count": 1,
                    "uncomputed_case_keys": ["event-1|branch-1|weather-1"],
                    "uncomputed_case_status_counts": {
                        "EXECUTED_OPERATOR_LIMITED": 1
                    },
                }
            ],
            "semantics": "explicit literature rates; no inference",
        },
    }
    report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        conditional_facility_release_trace=view,
    )
    check = next(
        row
        for row in report["checks"]
        if row["name"] == "diagnostic_conditional_facility_frequency_trace"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    gates_check = next(
        row
        for row in report["checks"]
        if row["name"] == "diagnostic_conditional_facility_promotion_gates"
    )
    assert gates_check["status"] == "PASS"

    view["frequency_uncertainty"]["frequency_port_binding"][
        "frequency_inference_allowed"
    ] = True
    blocked_report = build_ijhe_completion_audit(
        _status(),
        {"matrix_complete": False, "blocking_reasons": ["scope open"]},
        {"events": [], "cases": [], "timing": {}},
        conditional_facility_release_trace=view,
    )
    blocked_check = next(
        row
        for row in blocked_report["checks"]
        if row["name"] == "diagnostic_conditional_facility_frequency_trace"
    )
    assert blocked_check["status"] == "BLOCKED"
