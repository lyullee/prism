import copy

from lh2_tno.facility_component_contribution_audit import (
    build_facility_component_contribution_audit,
)


def _campaign():
    atom = {
        "event_id": "event-1",
        "initiating_frequency_per_year": 0.1,
        "conditional_weight": 0.5,
        "provider_packet_identity": {"component_id": "tank-01"},
        "receptor_harm_low_high": {"worker": [1.0, 1.0]},
        "expected_deaths_low_high": [1.0, 1.0],
    }
    campaign = {"facility_id": "facility-1", "risk_atoms": [atom]}
    campaign["component_contributions"] = {
        "tank-01": {
            "event_count": 1,
            "risk_atom_count": 1,
            "annual_ir_low_high": {"worker": [0.05, 0.05]},
            "expected_death_fn_low_high": [
                {"expected_deaths": [1.0], "cumulative_frequency_per_year": [0.05]},
                {"expected_deaths": [1.0], "cumulative_frequency_per_year": [0.05]},
            ],
            "frequency_is_not_reallocated": True,
        }
    }
    campaign["component_risk_ranking"] = {
        "rows": [{"component_id": "tank-01", "rank": 1}],
        "frequency_reallocation_performed": False,
        "facility_ir_fn_promotion": False,
    }
    return campaign


def test_component_contribution_audit_closes_from_risk_atoms():
    result = build_facility_component_contribution_audit(_campaign())
    assert result["status"] == "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
    assert result["component_count"] == 1
    assert result["risk_atom_count"] == 1
    assert result["mismatch_count"] == 0


def test_component_contribution_audit_detects_stale_component_ir():
    campaign = _campaign()
    campaign["component_contributions"]["tank-01"]["annual_ir_low_high"]["worker"][1] = 0.2
    result = build_facility_component_contribution_audit(campaign)
    assert result["status"] == "BLOCKED_FACILITY_COMPONENT_CONTRIBUTION_AUDIT"
    assert result["mismatch_count"] > 0


def test_component_contribution_audit_requires_component_identity():
    campaign = _campaign()
    campaign["risk_atoms"] = [copy.deepcopy(campaign["risk_atoms"][0])]
    campaign["risk_atoms"][0]["provider_packet_identity"] = {}
    try:
        build_facility_component_contribution_audit(campaign)
    except ValueError as error:
        assert "component_id" in str(error)
    else:
        raise AssertionError("missing equipment identity must fail closed")


def test_component_contribution_audit_allows_withheld_event_bins_in_partial_scope():
    campaign = _campaign()
    campaign["status"] = "PARTIAL_DECLARED_SCOPE"
    campaign["uncomputed_cases"] = [{"event_id": "event-2", "status": "UNCOMPUTED"}]
    campaign["component_contributions"]["tank-01"]["event_count"] = 2

    result = build_facility_component_contribution_audit(campaign)

    assert result["status"] == "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
    assert result["partial_scope"] is True
    assert result["mismatch_count"] == 0
