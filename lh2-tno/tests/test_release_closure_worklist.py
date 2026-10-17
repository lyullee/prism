from __future__ import annotations

import pytest

from lh2_tno.release_closure_worklist import build_release_closure_worklist


def _assessment(*, status: str = "EXECUTED", isolation: str = "reviewed_success") -> dict:
    return {
        "facility_id": "facility",
        "release_termination_inventory_ledger": {
            "rows": [{
                "event_id": "facility/tank/hole",
                "asset_id": "tank",
                "release_branch_id": "branch-1",
                "annual_condition_id": "west-3ms",
                "status": status,
                "isolation_status": isolation,
                "inventory_status": "provider_declared_inventory_depletion",
                "termination": {
                    "basis": "inventory_depletion",
                    "time_s": 4.0,
                    "provenance": "provider-clock",
                },
                "domain_assessment": {
                    "domain_truncated": False,
                    "inventory_outside_domain": False,
                },
                "mass_ledger": {"end_to_end_residual_kg": 0.0},
                "provider": {
                    "packet_consumed": True,
                    "component_id": "tank-01",
                    "available_mass_kg": [1.0],
                    "cumulative_mass_out_kg": [1.0],
                    "residual_mass_kg": [0.0],
                },
            }],
        },
    }


def test_worklist_separates_open_isolation_from_mass_closed_case():
    report = build_release_closure_worklist(_assessment(isolation="not_declared"), {
        "case_requests": [{
            "request_id": "request-1",
            "event_id": "facility/tank/hole",
            "release_branch_id": "branch-1",
            "annual_condition_id": "west-3ms",
            "scenario_families": ["vessel_hole"],
            "qualification_required": True,
            "required_provider_evidence": ["qualified packet"],
            "blocking_reasons": ["qualification withheld"],
        }],
    })
    row = report["cases"][0]
    assert report["status"] == "OPEN_RELEASE_CLOSURE_WORKLIST"
    assert row["closure_status"] == "ISOLATION_OPEN"
    assert "ISOLATION_OPEN" in row["closure_gaps"]
    assert "PROVIDER_QUALIFICATION_OPEN" in row["closure_gaps"]
    assert "qualified packet" in row["required_provider_evidence"]
    assert row["release_boundary"]["end_to_end_residual_kg"] == 0.0
    assert report["promotion_gates"]["facility_qra_allowed"] is False


def test_synthetic_horizon_and_mass_residual_are_fail_closed():
    assessment = _assessment()
    row = assessment["release_termination_inventory_ledger"]["rows"][0]
    row["termination"]["basis"] = "synthetic_diagnostic_horizon"
    row["mass_ledger"]["end_to_end_residual_kg"] = 1.0
    report = build_release_closure_worklist(assessment)
    result = report["cases"][0]
    assert result["closure_status"] == "MASS_CLOSURE_OPEN"
    assert "TERMINATION_OPEN" in result["closure_gaps"]
    assert "MASS_CLOSURE_OPEN" in result["closure_gaps"]
    assert report["summary"]["mass_closure_open_case_count"] == 1


def test_missing_ledger_is_rejected():
    with pytest.raises(ValueError, match="release_termination_inventory_ledger"):
        build_release_closure_worklist({"facility_id": "facility"})


def test_optional_boundary_audit_join_exposes_numerical_and_strict_counts():
    boundary = {
        "schema_version": "prism.release_boundary_case_audit.v1",
        "_record_path": "release-boundary.json",
        "rows": [{
            "event_id": "facility/tank/hole",
            "release_branch_id": "branch-1",
            "annual_condition_id": "west-3ms",
            "numerical_release_closed": True,
            "numerical_closure_status": "NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED",
            "provider_termination_evidence_status": "VALID",
            "strict_release_boundary_eligible": False,
            "strict_release_boundary_status": "PROMOTION_BLOCKED",
            "release_boundary_blocking_reasons": ["status_executed_operator_limited"],
        }],
    }
    report = build_release_closure_worklist(_assessment(), release_boundary_case_audit=boundary)
    row = report["cases"][0]["boundary_audit_join"]
    assert row["matched"] is True
    assert row["numerical_closure_status"] == "NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED"
    assert report["summary"]["boundary_audit_join_case_count"] == 1
    assert report["summary"]["numerically_closed_case_count"] == 1
    assert report["summary"]["numerically_open_case_count"] == 0
    assert report["summary"]["operator_review_required_case_count"] == 1
    assert report["summary"]["strict_release_boundary_eligible_case_count"] == 0
    assert report["summary"]["provider_termination_evidence_status_counts"] == {"VALID": 1}
    assert report["boundary_audit_record"] == "release-boundary.json"
