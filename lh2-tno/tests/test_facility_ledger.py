import pytest

from lh2_tno.facility_ledger import (
    FacilityLedgerError,
    merge_facility_campaign_results,
)


def _result(
    *,
    event_id: str,
    asset_id: str,
    component_id: str,
    frequency: float,
    conditional_weight: float = 1.0,
    incomplete: bool = False,
):
    atom = {
        "event_id": event_id,
        "asset_id": asset_id,
        "annual_condition_id": "weather-1",
        "release_branch_id": "release-1",
        "ignition_branch": "direct_fire",
        "initiating_frequency_per_year": frequency,
        "conditional_weight": conditional_weight,
        "receptor_harm_low_high": {
            "receptor-a": [0.7, 0.8],
            "receptor-b": [0.5, 0.6],
        },
        "expected_deaths_low_high": [1.2, 1.4],
    }
    return {
        "facility_id": "facility-1",
        "campaign_digest": f"digest-{event_id}",
        "events": [{
            "id": event_id,
            "asset_id": asset_id,
            "model_component_id": component_id,
        }],
        "cases": [{"event_id": event_id, "status": "EXECUTED"}],
        "uncomputed_cases": ([{"event_id": event_id, "status": "UNCOMPUTED"}] if incomplete else []),
        "risk_atoms": [atom],
        "declared_scope_numerically_complete": not incomplete,
        "synthetic_release_horizon_present": False,
        "excluded_model_components": {},
        "physical_validation_claim": False,
        "coverage": {
            "by_component": [{
                "component_id": component_id,
                "scope_status": "PARTIAL" if incomplete else "EXECUTED",
            }],
        },
        "timing": {"campaign_elapsed_ms": 10.0},
    }


def test_facility_ledger_sums_disjoint_equipment_atoms_once():
    result = merge_facility_campaign_results(
        [
            {"campaign_id": "tank-campaign", "result": _result(
                event_id="event-tank", asset_id="tank-asset", component_id="tank-01",
                frequency=1e-3,
            )},
            {"campaign_id": "pipe-campaign", "result": _result(
                event_id="event-pipe", asset_id="pipe-asset", component_id="pipe-01",
                frequency=2e-3, conditional_weight=0.5,
            )},
        ],
        expected_component_ids=("tank-01", "pipe-01"),
    )

    assert result["status"] == "FACILITY_SCOPE_EXECUTED"
    assert result["facility_total_risk_available"] is True
    assert result["known_contribution_annual_ir_low_high"]["receptor-a"] == pytest.approx(
        [0.0014, 0.0016]
    )
    assert result["total_facility_annual_ir_low_high"] == result[
        "known_contribution_annual_ir_low_high"
    ]
    assert result["timing"]["campaign_count"] == 2
    assert result["timing"]["campaign_elapsed_ms_p95"] == pytest.approx(10.0)
    assert result["risk_atoms_digest"]


def test_facility_ledger_rejects_duplicate_event_or_atom():
    first = _result(
        event_id="event-duplicate", asset_id="asset-1", component_id="component-1", frequency=1e-3
    )
    second = _result(
        event_id="event-duplicate", asset_id="asset-2", component_id="component-2", frequency=2e-3
    )
    with pytest.raises(FacilityLedgerError, match="duplicate event ID"):
        merge_facility_campaign_results([
            {"campaign_id": "first", "result": first},
            {"campaign_id": "second", "result": second},
        ])

    duplicate_atom = _result(
        event_id="event-one", asset_id="asset-1", component_id="component-1", frequency=1e-3
    )
    duplicate_atom["risk_atoms"].append(dict(duplicate_atom["risk_atoms"][0]))
    with pytest.raises(FacilityLedgerError, match="duplicate risk atom"):
        merge_facility_campaign_results([duplicate_atom])


def test_facility_ledger_withholds_total_for_missing_component_and_family():
    result = merge_facility_campaign_results(
        [_result(
            event_id="event-tank", asset_id="tank-asset", component_id="tank-01",
            frequency=1e-3, incomplete=True,
        )],
        expected_component_ids=("tank-01", "pipe-01"),
        scope_matrices=[{
            "rows": [{"family": "vessel_hole", "status": "EXECUTED"}],
        }],
        required_accident_families=("vessel_hole", "pipe_hole"),
    )

    assert result["status"] == "PARTIAL_FACILITY_SCOPE"
    assert result["total_facility_annual_ir_low_high"] is None
    assert result["known_contribution_annual_ir_low_high"]["receptor-a"][0] == pytest.approx(0.0007)
    assert "missing expected components: pipe-01" in result["blocking_reasons"]
    assert "accident family pipe_hole: missing scope matrix" in result["blocking_reasons"]
    assert result["component_statuses"]["tank-01"] == "PARTIAL"
