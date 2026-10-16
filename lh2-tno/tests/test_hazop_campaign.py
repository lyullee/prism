from copy import deepcopy

import pytest

from lh2_tno.hazop_campaign import (
    HazopFacilityCampaignError,
    build_hazop_facility_campaign_branches,
    build_hazop_facility_campaign_branches_from_manifest,
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
        branch_consequence = deepcopy(consequence)
        branch_risk = deepcopy(risk)
        if index:
            event_id = f"evt-tk01-hole-{index}"
            branch_consequence["equipment_release_path"]["boundaries"][0]["event_id"] = event_id
            branch_risk["risk_atom"]["event_id"] = event_id
        branches.append(
            {
                "scenario_id": "TK01-high-pressure-receiving"
                if index == 0
                else f"TK01-secondary-{index}",
                "scenario_family": "vessel_hole",
                "release_mode": "hole",
                "result": {
                    "status": "CONSEQUENCE_EVALUATED",
                    "consequence": branch_consequence,
                },
                "risk": branch_risk,
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
                "selection": {
                    "status": "SCENARIOS_SELECTED",
                    "state_digest": "d" * 64,
                    "operating_mode": "receiving",
                },
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
        "operating_mode": "receiving",
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
    assert result["snapshot"]["components"]["TK-01"]["selected_operating_mode"] == "receiving"
    assert result["campaign"]["cases"][0]["operating_mode"] == "receiving"
    assert result["campaign"]["cases"][0]["hazop_scenario_id"] == "TK01-high-pressure-receiving"
    assert result["campaign"]["events"][0]["hazop_scenario_id"] == "TK01-high-pressure-receiving"
    assert all(
        atom["hazop_scenario_id"] == "TK01-high-pressure-receiving"
        for atom in result["campaign"]["risk_atoms"]
    )
    assert all(atom["operating_mode"] == "receiving" for atom in result["campaign"]["risk_atoms"])
    assert result["facility_ledger"]["conditional_diagnostic_facility_risk_available"] is True
    assert result["facility_ledger"]["facility_total_risk_available"] is False
    assert result["facility_ledger"]["qualified_facility_qra_available"] is False
    assert result["hazop_scenario_trace_audit"]["status"] == "HAZOP_SCENARIO_TRACE_COMPLETE"
    assert result["equipment_state_release_audit"]["status"] == "PARTIAL_EQUIPMENT_STATE_RELEASE_CHAIN"
    assert result["risk_atom_chain_audit"]["status"] == "PARTIAL_RISK_ATOM_CHAIN"


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


def test_hazop_bridge_rejects_operating_mode_drift():
    binding = _binding()
    binding["operating_mode"] = "supply"
    with pytest.raises(HazopFacilityCampaignError, match="operating_mode does not match"):
        build_hazop_facility_campaign_result(
            _runtime_result(),
            annual_conditions=_annual_conditions(),
            scenario_bindings=[binding],
            expected_component_ids=("TK-01",),
        )


def test_hazop_bridge_rejects_event_identity_drift():
    binding = _binding()
    binding["event_id"] = "different-provider-event"
    with pytest.raises(HazopFacilityCampaignError, match="event_id does not match"):
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


def test_hazop_branch_bridge_uses_explicit_partition_for_facility_ledger():
    second = _binding()
    second.update(
        hazop_scenario_id="TK01-secondary-1",
        event_id="evt-tk01-hole-1",
    )
    result = build_hazop_facility_campaign_branches(
        _runtime_result(branch_count=2),
        annual_conditions=_annual_conditions(),
        scenario_bindings=[_binding(), second],
        branch_probabilities={
            "TK01-high-pressure-receiving": 0.6,
            "TK01-secondary-1": 0.4,
        },
        branch_partition_groups={
            "TK01-high-pressure-receiving": "pressure-deviation",
            "TK01-secondary-1": "pressure-deviation",
        },
        expected_component_ids=("TK-01",),
    )
    assert result["status"] == "HAZOP_BRANCH_CAMPAIGNS_BUILT_OPERATOR_LIMITED"
    assert result["policy"]["branch_partition_explicit"] is True
    assert len(result["campaign"]["risk_atoms"]) == 8
    assert result["facility_ledger"]["conditional_diagnostic_facility_risk_available"] is True
    assert result["facility_ledger"]["facility_total_risk_available"] is False
    assert result["hazop_scenario_trace_audit"]["status"] == "HAZOP_SCENARIO_TRACE_COMPLETE"
    assert result["equipment_state_release_audit"]["status"] == "PARTIAL_EQUIPMENT_STATE_RELEASE_CHAIN"
    assert result["risk_atom_chain_audit"]["status"] == "PARTIAL_RISK_ATOM_CHAIN"


def test_hazop_branch_bridge_rejects_open_partition():
    second = _binding()
    second.update(
        hazop_scenario_id="TK01-secondary-1",
        event_id="evt-tk01-hole-1",
    )
    with pytest.raises(HazopFacilityCampaignError, match="partition group must close"):
        build_hazop_facility_campaign_branches(
            _runtime_result(branch_count=2),
            annual_conditions=_annual_conditions(),
            scenario_bindings=[_binding(), second],
            branch_probabilities={
                "TK01-high-pressure-receiving": 0.6,
                "TK01-secondary-1": 0.3,
            },
            branch_partition_groups={
                "TK01-high-pressure-receiving": "pressure-deviation",
                "TK01-secondary-1": "pressure-deviation",
            },
            expected_component_ids=("TK-01",),
        )


def test_hazop_branch_bridge_keeps_reused_scenario_ids_separate_by_component():
    runtime = _runtime_result()
    second_component = deepcopy(runtime["components"]["TK-01"])
    second_component["component_id"] = "TK-02"
    branch = second_component["branches"][0]
    branch["result"]["consequence"]["equipment_release_path"]["boundaries"][0].update(
        {
            "event_id": "evt-tk02-hole",
            "component_id": "TK-02",
        }
    )
    branch["risk"]["risk_atom"].update(
        {
            "event_id": "evt-tk02-hole",
            "asset_id": "TK-02",
        }
    )
    runtime["components"]["TK-02"] = second_component
    runtime["component_count"] = 2
    second_binding = _binding()
    second_binding.update(
        component_id="TK-02",
        event_id="evt-tk02-hole",
        asset_id="TK-02",
    )
    result = build_hazop_facility_campaign_branches(
        runtime,
        annual_conditions=_annual_conditions(),
        scenario_bindings=[_binding(), second_binding],
        branch_probabilities={
            "TK-01|TK01-high-pressure-receiving": 0.5,
            "TK-02|TK01-high-pressure-receiving": 0.5,
        },
        branch_partition_groups={
            "TK-01|TK01-high-pressure-receiving": "shared-deviation",
            "TK-02|TK01-high-pressure-receiving": "shared-deviation",
        },
        expected_component_ids=("TK-01", "TK-02"),
    )
    assert result["status"] == "HAZOP_BRANCH_CAMPAIGNS_BUILT_OPERATOR_LIMITED"
    assert result["branch_probabilities"] == {
        "TK-01|TK01-high-pressure-receiving": 0.5,
        "TK-02|TK01-high-pressure-receiving": 0.5,
    }
    assert len(result["campaign"]["risk_atoms"]) == 8


def test_hazop_branch_manifest_replays_the_same_facility_campaign():
    second = _binding()
    second.update(
        hazop_scenario_id="TK01-secondary-1",
        event_id="evt-tk01-hole-1",
    )
    manifest = {
        "schema_version": "prism.hazop_facility_campaign_manifest.v1",
        "runtime_result": _runtime_result(branch_count=2),
        "annual_conditions": _annual_conditions(),
        "scenario_bindings": [_binding(), second],
        "branch_probabilities": {
            "TK-01|TK01-high-pressure-receiving": 0.6,
            "TK-01|TK01-secondary-1": 0.4,
        },
        "branch_partition_groups": {
            "TK-01|TK01-high-pressure-receiving": "pressure-deviation",
            "TK-01|TK01-secondary-1": "pressure-deviation",
        },
        "expected_component_ids": ["TK-01"],
    }
    result = build_hazop_facility_campaign_branches_from_manifest(manifest)
    assert result["manifest"]["branch_identity_key"] == "component_id|hazop_scenario_id"
    assert result["branch_probabilities"]["TK-01|TK01-secondary-1"] == 0.4
    assert len(result["campaign"]["risk_atoms"]) == 8


def test_hazop_branch_manifest_fails_closed_when_input_is_missing():
    manifest = {
        "runtime_result": _runtime_result(),
        "annual_conditions": _annual_conditions(),
        "scenario_bindings": [_binding()],
        "branch_probabilities": {"TK-01|TK01-high-pressure-receiving": 1.0},
    }
    with pytest.raises(HazopFacilityCampaignError, match="branch_partition_groups"):
        build_hazop_facility_campaign_branches_from_manifest(manifest)
