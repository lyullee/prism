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
