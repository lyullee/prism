from __future__ import annotations

import pytest

from lh2_tno.conditional_facility_risk_view import (
    build_conditional_facility_risk_view,
)


def _assessment() -> dict:
    return {
        "schema_version": "prism.facility_assessment.v1",
        "facility_id": "facility-01",
        "assessment_digest": "a" * 64,
        "event_count": 2,
        "case_count": 3,
        "conditional_diagnostic_facility_risk_available": True,
        "conditional_diagnostic_facility_annual_ir_low_high": {
            "worker-01": [1.0e-6, 2.0e-6]
        },
        "conditional_diagnostic_facility_expected_death_fn_low_high": [
            [{"expected_deaths": [1.0], "cumulative_frequency_per_year": [1.0e-6]}],
            [{"expected_deaths": [1.0], "cumulative_frequency_per_year": [2.0e-6]}],
        ],
        "conditional_diagnostic_facility_expected_death_fn_diagnostics": {
            "status": "CURVE_AVAILABLE"
        },
        "facility_total_risk_available": False,
        "qualified_facility_qra_available": False,
        "complete_facility_qra_claim": False,
        "provider_packet_promoted": False,
        "provider_packet_case_count": 3,
        "qualified_provider_packet_case_count": 0,
        "physical_validation_claim": False,
        "provider_qualification_blocking_reasons": ["qualification withheld"],
        "component_risk_ranking": {"status": "AVAILABLE", "rows": []},
        "scenario_branch_accounting": {"status": "EXPLICIT_BRANCH_ACCOUNTING"},
        "release_termination_inventory_ledger": {"status": "AVAILABLE"},
        "conditional_diagnostic_facility_coverage": {
            "risk_atom_count": 4,
            "case_count": 3,
        },
        "strict_release_boundary": {"status": "WITHHELD"},
        "facility_risk_ledger": {
            "event_count": 2,
            "case_count": 3,
            "cases": [
                {"event_id": "event-1", "elapsed_ms": 12.5, "stage_elapsed_ms": {"source": 4.0}}
            ],
            "component_contributions": {"tank-01": {"risk_atom_count": 4}},
            "scenario_family_contributions": {"vessel_hole": {"risk_atom_count": 4}},
            "scenario_branch_accounting": {"status": "EXPLICIT_BRANCH_ACCOUNTING"},
            "release_termination_inventory_ledger": {"status": "AVAILABLE"},
            "synthetic_release_horizon_present": True,
            "strict_release_boundary": {"status": "WITHHELD"},
        },
    }


def test_view_keeps_conditional_risk_and_qualification_separate() -> None:
    view = build_conditional_facility_risk_view(_assessment())
    assert view["status"] == "CONDITIONAL_DIAGNOSTIC_FACILITY_RISK"
    assert view["conditional_annual_ir_low_high"]["worker-01"] == [1.0e-6, 2.0e-6]
    assert view["risk_atom_count"] == 4
    assert view["component_contributions"]["tank-01"]["risk_atom_count"] == 4
    assert view["qualification"]["facility_total_risk_available"] is False
    assert view["qualification"]["promotion_allowed"] is False


def test_view_rejects_missing_conditional_fn() -> None:
    assessment = _assessment()
    assessment.pop("conditional_diagnostic_facility_expected_death_fn_low_high")
    with pytest.raises(ValueError, match="expected-death F/N"):
        build_conditional_facility_risk_view(assessment)


def test_view_carries_mass_balance_qualification_boundary() -> None:
    view = build_conditional_facility_risk_view(
        _assessment(),
        provider_mass_balance_audit={
            "schema_version": "prism.provider_mass_balance_audit.v1",
            "record_count": 7,
            "status_counts": {"CLOSED": 3, "PARTIAL": 3, "UNBALANCED": 1},
            "diagnostic_only": True,
            "promotion_allowed": False,
        },
    )
    assert view["provider_mass_balance_audit"]["status_counts"]["UNBALANCED"] == 1
    assert view["qualification"]["provider_mass_balance_promotion_allowed"] is False


def test_view_exposes_case_release_trace_without_opening_facility_promotion() -> None:
    assessment = _assessment()
    assessment["facility_risk_ledger"]["risk_atoms"] = [
        {
            "event_id": "event-1",
            "receptor_harm_low_high": {"worker-01": [0.1, 0.2]},
        }
    ]
    audit = {
        "schema_version": "prism.release_boundary_case_audit.v1",
        "status": "CASE_BOUNDARY_PARTIAL",
        "case_key_definition": "event_id|release_branch_id|annual_condition_id",
        "case_count": 1,
        "strict_release_boundary_eligible_case_count": 0,
        "strict_release_boundary_blocked_case_count": 1,
        "numerically_closed_case_count": 1,
        "numerically_open_case_count": 0,
        "operator_review_required_case_count": 1,
        "consequence_domain_truncated_case_count": 0,
        "facility_ir_fn_promotion": False,
        "rows": [
            {
                "event_id": "event-1",
                "release_branch_id": None,
                "annual_condition_id": None,
                "release_duration_s": [0.3],
                "available_mass_kg": [2.0],
                "cumulative_mass_out_kg": [1.0],
                "residual_mass_kg": [1.0],
                "numerical_closure_status": "NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED",
                "strict_release_boundary_eligible": False,
            }
        ],
    }
    view = build_conditional_facility_risk_view(
        assessment,
        release_boundary_case_audit=audit,
    )
    trace = view["release_trace"]
    assert trace["schema_version"] == "prism.conditional_facility_release_trace.v1"
    assert trace["summary"]["operator_review_required_case_count"] == 1
    assert trace["rows"][0]["release_duration_s"] == [0.3]
    assert trace["rows"][0]["risk_atom_accounting"] == {
        "risk_atom_count": 1,
        "nonzero_receptor_harm_atom_count": 1,
    }
    assert trace["rows"][0]["calculation_timing"] == {
        "elapsed_ms": 12.5,
        "stage_elapsed_ms": {"source": 4.0},
    }
    assert view["qualification"]["promotion_allowed"] is False


def test_view_preserves_literature_frequency_scenarios_and_rank_stability() -> None:
    assessment = _assessment()
    assessment["frequency_port_binding"] = {"frequency_inference_allowed": False}
    assessment["frequency_uncertainty"] = {
        "campaign_digest": "c" * 64,
        "physical_risk_atoms_digest": "d" * 64,
        "scenarios": [
            {
                "scenario": {
                    "id": "published",
                    "asset_quantiles": {"tank-01": "published"},
                    "event_quantiles": {},
                    "provenance": "literature catalogue; no inference",
                    "correlation_assumption": "within_asset_shared_quantile",
                },
                "conditional_diagnostic_facility_annual_ir_low_high": {
                    "worker-01": [1.0e-6, 2.0e-6]
                },
                "conditional_diagnostic_facility_expected_death_fn_low_high": [[], []],
                "uncomputed_cases": [
                    {
                        "event_id": "event-1",
                        "release_branch_id": "branch-1",
                        "annual_condition_id": "weather-1",
                        "status": "EXECUTED_OPERATOR_LIMITED",
                    },
                    {
                        "event_id": "event-1",
                        "release_branch_id": "branch-1",
                        "annual_condition_id": "weather-1",
                        "status": "EXECUTED_OPERATOR_LIMITED",
                    },
                ],
                "conditional_diagnostic_facility_risk_available": True,
                "asset_rank_by_known_expected_fatalities_low_high": [{"tank-01": 1}, {"tank-01": 1}],
                "scenario_family_rank_by_known_expected_fatalities_low_high": [{"vessel_hole": 1}, {"vessel_hole": 1}],
                "provider_packet_promoted": False,
                "qualified_provider_packet_case_count": 0,
                "complete_facility_qra_claim": False,
                "physical_validation_claim": False,
            }
        ],
        "fresh_physics_executed": False,
        "statistical_confidence_interval": False,
        "facility_credible_interval": False,
        "conditional_diagnostic_facility_risk": "diagnostic only",
        "asset_rank_stability": {"top_id_consistent": True},
        "scenario_family_rank_stability": {"top_id_consistent": True},
        "provider_packet_promoted": False,
        "qualified_provider_packet_case_count": 0,
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
        "semantics": "explicit literature quantiles; no inference",
    }
    view = build_conditional_facility_risk_view(assessment)
    frequency = view["frequency_uncertainty"]
    assert frequency["schema_version"] == "prism.conditional_facility_frequency_trace.v1"
    assert frequency["scenario_count"] == 1
    assert frequency["frequency_inference_allowed"] is False
    assert frequency["scenarios"][0]["id"] == "published"
    assert frequency["asset_rank_stability"]["top_id_consistent"] is True
    assert frequency["provider_packet_promoted"] is False
    assert frequency["uncomputed_case_count_by_scenario"] == {"published": 2}
    assert frequency["uncomputed_case_unique_key_count_by_scenario"] == {"published": 1}
    assert frequency["uncomputed_case_duplicate_row_count_by_scenario"] == {"published": 1}
    assert frequency["uncomputed_case_union_count"] == 1
    assert frequency["scenarios"][0]["uncomputed_case_status_counts"] == {
        "EXECUTED_OPERATOR_LIMITED": 2
    }
