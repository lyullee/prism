from copy import deepcopy

import pytest

from lh2_tno.hazop_campaign import (
    HazopFacilityCampaignError,
    build_hazop_facility_campaign_result,
)


def _annual_conditions():
    return [
        {
            "id": "weather-d-03",
            "annual_probability": 1.0,
            "weather": {"wind_speed_m_s": 3.0, "stability_class": "D"},
            "population": [
                {
                    "receptor_id": "worker-01",
                    "persons": 12.0,
                    "presence_probability": 1.0,
                    "provenance": "reviewed outdoor population fixture",
                }
            ],
            "provenance": "reviewed annual weather fixture",
        }
    ]


def _runtime_result(*, branch_count=1):
    probabilities = {
        "direct_fire": 0.25,
        "delayed_flash_fire": 0.35,
        "delayed_explosion": 0.10,
        "no_ignition": 0.30,
    }
    consequence = {
        "data": {
            "ignition_branch_probabilities": probabilities,
            "receptors": [
                {
                    "id": "worker-01",
                    "harm_given_observed_release_low_high": [0.2, 0.4],
                }
            ],
        },
        "equipment_release_path": {
            "status": "AVAILABLE_PROVIDER_RELEASE_PATH",
            "boundaries": [
                {
                    "event_id": "evt-tk01-hole",
                    "component_id": "TK-01",
                    "port_id": "liquid-outlet",
                    "provider_source_digest": "a" * 64,
                    "provider_result_digest": "b" * 64,
                    "provider_boundary_reference": "provider://tk01/outlet",
                    "termination_basis": "model_pressure_equalization",
                    "termination_provenance": "reviewed provider packet",
                    "event_kind": "accidental_leak",
                    "input_origin": "native_provider",
                    "duration_s": 2.0,
                    "available_mass_kg": 100.0,
                    "cumulative_mass_out_kg": 80.0,
                    "provider_mass_balance": {"status": "closed"},
                }
            ],
            "termination": {
                "basis": "model_pressure_equalization",
                "time_s": 2.0,
                "provenance": "reviewed provider packet",
            },
            "inventory": {
                "cumulative_mass_out_kg": 80.0,
                "mass_residual_kg": 20.0,
            },
        },
    }
    risk = {
        "status": "AVAILABLE_CURRENT_WEATHER_IR",
        "annual_ir_low_high": {"worker-01": [2.0e-4, 4.0e-4]},
        "risk_atom": {
            "event_id": "evt-tk01-hole",
            "asset_id": "TK-01",
            "initiating_frequency_per_year": 1.0e-3,
            "conditional_weight": 1.0,
            "annual_condition_probability": 1.0,
            "release_branch_probability": 1.0,
            "occupancy_probability": 1.0,
            "receptor_harm_low_high": {"worker-01": [0.2, 0.4]},
            "frequency_provenance": "reviewed LH2 literature fixture",
            "frequency_source_digest": "c" * 64,
            "frequency_is_not_inferred": True,
            "frequency_p05_per_year": 5.0e-4,
            "frequency_p95_per_year": 2.0e-3,
            "expected_deaths_low_high": None,
        },
    }
    branches = []
    for index in range(branch_count):
        branches.append(
            {
                "scenario_id": "TK01-high-pressure-receiving"
                if index == 0
                else f"TK01-secondary-{index}",
                "scenario_family": "vessel_hole",
                "release_mode": "hole",
                "result": {
                    "status": "CONSEQUENCE_EVALUATED",
                    "consequence": deepcopy(consequence),
                },
                "risk": deepcopy(risk),
            }
        )
    return {
        "schema_version": "prism.hazop_facility_runtime.v1",
        "facility_id": "generic-outdoor-lh2",
        "status": "FACILITY_HAZOP_RUNTIME_EVALUATED",
        "component_count": 1,
        "components": {
            "TK-01": {
                "status": "CONSEQUENCE_BRANCHES_EVALUATED",
                "component_id": "TK-01",
                "selection": {"status": "SCENARIOS_SELECTED", "state_digest": "d" * 64},
                "branches": branches,
            }
        },
        "conditional_current_weather_risk": {
            "status": "AVAILABLE_CONDITIONAL_CURRENT_WEATHER_IR",
            "annual_ir_low_high_by_receptor": {"worker-01": [2.0e-4, 4.0e-4],
            },
        },
    }


def _binding():
    return {
        "component_id": "TK-01",
        "hazop_scenario_id": "TK01-high-pressure-receiving",
        "event_id": "evt-tk01-hole",
        "asset_id": "TK-01",
        "annual_condition_id": "weather-d-03",
        "release_branch_id": "reviewed-isolation",
        "release_branch_probability": 1.0,
        "ignition_branch_probabilities": {
            "direct_fire": 0.25,
            "delayed_flash_fire": 0.35,
            "delayed_explosion": 0.10,
            "no_ignition": 0.30,
        },
        "branch_harm_low_high": {
            "worker-01": {
                "direct_fire": [2.0 / 7.0, 4.0 / 7.0],
                "delayed_flash_fire": [2.0 / 7.0, 4.0 / 7.0],
                "delayed_explosion": [2.0 / 7.0, 4.0 / 7.0],
                "no_ignition": [0.0, 0.0],
            }
        },
        "scenario_families": ["vessel_hole"],
    }


def test_hazop_runtime_can_enter_existing_facility_campaign_contract():
    result = build_hazop_facility_campaign_result(
        _runtime_result(),
        annual_conditions=_annual_conditions(),
        scenario_bindings=[_binding()],
        expected_component_ids=("TK-01",),
    )
    assert result["schema_version"] == "prism.hazop_facility_campaign_handoff.v1"
    assert result["status"] == "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert result["policy"]["hazop_scenario_id_bound"] is True
    assert result["campaign"]["status"] == "PARTIAL_DECLARED_SCOPE"
    assert len(result["campaign"]["risk_atoms"]) == 4
    assert result["campaign"]["complete_facility_qra_claim"] is False
    assert result["campaign"]["provider_packet_promoted"] is False
    assert result["facility_ledger"]["conditional_diagnostic_facility_risk_available"] is True
    assert result["facility_ledger"]["facility_total_risk_available"] is False
    assert result["facility_ledger"]["qualified_facility_qra_available"] is False


def test_hazop_bridge_rejects_unmatched_mode_specific_scenario_id():
    binding = _binding()
    binding["hazop_scenario_id"] = "wrong-mode-scenario"
    with pytest.raises(HazopFacilityCampaignError, match="does not match selected branch"):
        build_hazop_facility_campaign_result(
            _runtime_result(),
            annual_conditions=_annual_conditions(),
            scenario_bindings=[binding],
            expected_component_ids=("TK-01",),
        )


def test_hazop_bridge_rejects_multiple_active_branches_without_partition():
    with pytest.raises(HazopFacilityCampaignError, match="explicit branch probabilities"):
        build_hazop_facility_campaign_result(
            _runtime_result(branch_count=2),
            annual_conditions=_annual_conditions(),
            scenario_bindings=[_binding()],
            expected_component_ids=("TK-01",),
        )
