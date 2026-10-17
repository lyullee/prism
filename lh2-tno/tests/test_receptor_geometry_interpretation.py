from __future__ import annotations

from lh2_tno.receptor_geometry_interpretation import (
    build_facility_receptor_geometry,
    build_receptor_geometry_interpretation,
)


def _manifest(facility_id: str, receptor_position: list[float]) -> dict:
    return {
        "facility_id": facility_id,
        "components": [{"id": "source-01", "position_enu_m": [0.0, 0.0, 1.0]}],
        "receptors": [{"id": "worker-01", "position_enu_m": receptor_position}],
    }


def _full() -> dict:
    return {
        "facility_id": "full",
        "conditional_diagnostic_facility_annual_ir_low_high": {"worker-01": [0.0, 0.0]},
        "conditional_diagnostic_facility_expected_death_fn_low_high": [[], []],
        "conditional_diagnostic_facility_coverage": {"event_count": 34, "case_count": 44, "risk_atom_count": 176},
        "complete_facility_qra_claim": False,
        "facility_total_risk_available": False,
        "physical_validation_claim": False,
    }


def _near() -> dict:
    return {
        "facility_id": "near",
        "conditional_diagnostic_facility_annual_ir_low_high": {"worker-01": [4.68e-5, 4.68e-5]},
        "conditional_diagnostic_facility_expected_death_fn_low_high": [
            {"expected_deaths": [1.0], "cumulative_frequency_per_year": [4.68e-5]},
            {"expected_deaths": [1.0], "cumulative_frequency_per_year": [4.68e-5]},
        ],
        "frequency_event_count": 24,
        "campaign_case_count": 24,
        "risk_atom_count": 96,
        "harm_diagnostic": {"positive_receptor_harm_atom_count": 1},
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }


def test_geometry_comparison_passes_and_keeps_records_separate() -> None:
    result = build_receptor_geometry_interpretation(
        _full(), _near(), _manifest("full", [20.0, 0.0, 1.0]), _manifest("near", [0.5, 0.0, 1.0])
    )
    assert result["status"] == "PASS_DIAGNOSTIC_ONLY"
    assert result["full_scope"]["nearest_component_distance_m"] == 20.0
    assert result["near_receptor"]["nearest_component_distance_m"] == 0.5
    assert result["promotion_boundary"]["facility_total_risk_claim"] is False
    assert all(item["status"] == "PASS" for item in result["checks"])


def test_geometry_comparison_blocks_manifest_identity_drift() -> None:
    full = _full()
    full["facility_id"] = "wrong"
    result = build_receptor_geometry_interpretation(
        full, _near(), _manifest("full", [20.0, 0.0, 1.0]), _manifest("near", [0.5, 0.0, 1.0])
    )
    assert result["status"] == "BLOCKED_METADATA"
    assert any(item["id"] == "full_scope_manifest_identity" and item["status"] == "BLOCKED" for item in result["checks"])


def test_geometry_comparison_does_not_accept_zero_near_receptor() -> None:
    near = _near()
    near["conditional_diagnostic_facility_annual_ir_low_high"] = {"worker-01": [0.0, 0.0]}
    near["harm_diagnostic"] = {"positive_receptor_harm_atom_count": 0}
    result = build_receptor_geometry_interpretation(
        _full(), near, _manifest("full", [20.0, 0.0, 1.0]), _manifest("near", [0.5, 0.0, 1.0])
    )
    assert result["status"] == "BLOCKED_METADATA"
    assert any(item["id"] == "near_receptor_diagnostic_is_nonzero" and item["status"] == "BLOCKED" for item in result["checks"])


def test_facility_geometry_contract_closes_multiple_receptors_and_population() -> None:
    facility = {
        "id": "facility-multi",
        "environment": "outdoor",
        "components": [
            {"id": "tank", "kind": "storage_tank", "position_enu_m": [0.0, 0.0, 1.0]},
            {"id": "boundary", "kind": "boundary", "position_enu_m": [0.1, 0.0, 1.0]},
        ],
        "receptors": [
            {"id": "near", "position_enu_m": [1.0, 0.0, 1.0]},
            {"id": "public", "position_enu_m": [20.0, 0.0, 1.0]},
        ],
    }
    geometry = build_facility_receptor_geometry(
        facility,
        annual_conditions=[
            {
                "id": "weather-1",
                "annual_probability": 1.0,
                "provenance": "reviewed population fixture",
                "population": [
                    {"receptor_id": "near", "persons": 2.0, "presence_probability": 1.0},
                    {"receptor_id": "public", "persons": 0.0, "presence_probability": 1.0},
                ],
            }
        ],
    )
    assert geometry["schema_version"] == "prism.facility_receptor_geometry.v1"
    assert geometry["receptor_count"] == 2
    assert geometry["receptors"][0]["nearest_component_id"] == "tank"
    assert geometry["population_contract"]["status"] == "EXPLICIT_RECEPTOR_POPULATION_CLOSED"
    assert geometry["population_contract"]["zero_population_rows_must_be_explicit"] is True


def test_facility_geometry_contract_blocks_population_set_drift() -> None:
    facility = {
        "id": "facility-multi",
        "environment": "outdoor",
        "components": [{"id": "tank", "kind": "storage_tank", "position_enu_m": [0.0, 0.0, 1.0]}],
        "receptors": [{"id": "near", "position_enu_m": [1.0, 0.0, 1.0]}],
    }
    geometry = build_facility_receptor_geometry(
        facility,
        annual_conditions=[
            {"id": "weather-1", "population": [], "annual_probability": 1.0}
        ],
    )
    assert geometry["population_contract"]["status"] == "RECEPTOR_POPULATION_REVIEW_REQUIRED"
    assert geometry["population_contract"]["mismatched_condition_ids"]
