from copy import deepcopy

from lh2_tno.equipment_hazop_campaign import build_equipment_hazop_quantitative_campaign
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames

from test_equipment_hazop_handoff import _manifest, _source
from test_hazop_campaign import _annual_conditions, _binding, _runtime_result


def _integration_inputs():
    runtime_frames = build_observed_state_runtime_frames(
        [_source("TK-01")],
        operating_mode_map={"historian-TK-01": "receiving"},
    )
    table_set = {
        "schema_version": "prism.hazop_runtime_table_set.v1",
        "tables": {
            "TK-01": {
                "schema_version": "prism.hazop_operating_mode_selection.v1",
                "id": "runtime-test-hazop",
                "facility_id": "generic-outdoor-lh2",
                "operating_modes": ["receiving", "supply", "standby"],
                "configuration_origin": "synthetic",
                "source_provenance": "test",
                "rows": [
                    {
                        "id": "high-pressure",
                        "component_id": "TK-01",
                        "component_kind": "storage_tank",
                        "operating_modes": ["receiving"],
                        "variable_tag": "pressure",
                        "quantity": "pressure",
                        "trigger": "at_or_above",
                        "threshold_high_si": 600000.0,
                        "scenario_family": "vessel_hole",
                        "release_mode": "hole",
                        "priority": "high",
                        "deviation_label": "high pressure",
                        "cause_summary": "test",
                        "consequence_summary": "provider required",
                        "provenance": "test",
                    }
                ],
            }
        },
    }
    equipment_manifest = _manifest()
    # The integration boundary permits explicit identifier translation, but
    # every occurrence must be changed consistently before the crosswalk.
    equipment_manifest = deepcopy(equipment_manifest)
    equipment_manifest["facility_id"] = "generic-outdoor-lh2"
    component = equipment_manifest["components"][0]
    component["id"] = "TK-01"
    equipment_manifest["ports"][0]["component_id"] = "TK-01"
    runtime_frames["facility_id"] = "generic-outdoor-lh2"
    return {
        "equipment_manifest": equipment_manifest,
        "runtime_frames": runtime_frames,
        "hazop_table_set": table_set,
        "runtime_result": _runtime_result(),
        "annual_conditions": _annual_conditions(),
        "scenario_bindings": [_binding()],
        "branch_probabilities": {"TK-01|TK01-high-pressure-receiving": 1.0},
        "branch_partition_groups": {"TK-01|TK01-high-pressure-receiving": "pressure-deviation"},
        "scenario_identity_crosswalk": [
            {
                "component_id": "TK-01",
                "qualitative_scenario_id": "high-pressure:receiving:vessel_hole",
                "quantitative_scenario_id": "TK01-high-pressure-receiving",
            }
        ],
        "expected_component_ids": ["TK-01"],
    }


def test_equipment_hazop_quantitative_campaign_closes_explicit_identity_boundary():
    data = _integration_inputs()
    result = build_equipment_hazop_quantitative_campaign(
        **data,
        now_s=4.0,
    )
    assert result["status"] == "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert result["scenario_identity_crosswalk"]["status"] == "SCENARIO_IDENTITY_CROSSWALK_ALIGNED"
    assert result["scenario_identity_crosswalk"]["selected_qualitative_scenario_count"] == 1
    assert len(result["campaign"]["risk_atoms"]) == 4
    assert result["policy"]["dispatch_performed"] is True
    assert result["policy"]["frequency_inference_performed"] is False
    assert result["policy"]["facility_qra_claim"] is False


def test_equipment_hazop_quantitative_campaign_blocks_identity_drift():
    data = _integration_inputs()
    data["scenario_identity_crosswalk"][0]["quantitative_scenario_id"] = "wrong-scenario"
    result = build_equipment_hazop_quantitative_campaign(**data, now_s=4.0)
    assert result["status"] == "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BLOCKED"
    assert result["policy"]["dispatch_performed"] is False
    assert "campaign" not in result
    assert any("no scenario branch" in reason for reason in result["blocking_reasons"])


def test_equipment_hazop_quantitative_campaign_blocks_qualitative_handoff():
    data = _integration_inputs()
    data["runtime_frames"]["frames"][0]["component_id"] = "unknown"
    result = build_equipment_hazop_quantitative_campaign(**data, now_s=4.0)
    assert result["status"] == "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BLOCKED"
    assert result["policy"]["dispatch_performed"] is False
    assert any("unknown" in reason for reason in result["blocking_reasons"])


def test_equipment_hazop_quantitative_campaign_keeps_two_equipment_paths_separate():
    """Each equipment keeps its own mode, scenario, provider event and asset."""

    data = _integration_inputs()
    manifest = deepcopy(data["equipment_manifest"])
    manifest["components"].append(
        {
            "id": "VAP-01",
            "kind": "vaporizer",
            "position_enu_m": [12.0, 0.0, 1.0],
            "property_basis": {
                "fluid": "Hydrogen",
                "backend": "CoolProp-HEOS",
                "energy_reference": "CoolProp-HEOS:Hydrogen:native",
            },
            "parameters_si": {"volume_m3": 1.0},
        }
    )
    manifest["ports"].append(
        {
            "id": "vap-01-out",
            "component_id": "VAP-01",
            "phase": "vapour",
            "direction": "out",
        }
    )
    data["equipment_manifest"] = manifest
    data["runtime_frames"] = build_observed_state_runtime_frames(
        [_source("TK-01"), _source("VAP-01")],
        operating_mode_map={
            "historian-TK-01": "receiving",
            "historian-VAP-01": "supply",
        },
    )
    data["runtime_frames"]["facility_id"] = "generic-outdoor-lh2"

    vaporizer_table = deepcopy(data["hazop_table_set"]["tables"]["TK-01"])
    vaporizer_table["id"] = "runtime-test-vaporizer-hazop"
    vaporizer_table["operating_modes"] = ["supply"]
    vaporizer_row = deepcopy(vaporizer_table["rows"][0])
    vaporizer_row.update(
        {
            "id": "high-pressure-vaporizer",
            "component_id": "VAP-01",
            "component_kind": "vaporizer",
            "operating_modes": ["supply"],
            "scenario_family": "vaporizer_hole",
        }
    )
    vaporizer_table["rows"] = [vaporizer_row]
    data["hazop_table_set"]["tables"]["VAP-01"] = vaporizer_table

    runtime_result = deepcopy(data["runtime_result"])
    tank_component = runtime_result["components"]["TK-01"]
    vaporizer_component = deepcopy(tank_component)
    vaporizer_component["component_id"] = "VAP-01"
    vaporizer_component["selection"]["operating_mode"] = "supply"
    vaporizer_component["selection"]["state_digest"] = "e" * 64
    vaporizer_branch = vaporizer_component["branches"][0]
    vaporizer_branch["scenario_id"] = "VAP01-high-pressure-supply"
    vaporizer_branch["scenario_family"] = "vaporizer_hole"
    vaporizer_consequence = vaporizer_branch["result"]["consequence"]
    vaporizer_boundary = vaporizer_consequence["equipment_release_path"]["boundaries"][0]
    vaporizer_boundary.update(
        {
            "event_id": "evt-vap01-hole",
            "component_id": "VAP-01",
            "port_id": "vap-01-out",
            "provider_source_digest": "c" * 64,
            "provider_result_digest": "d" * 64,
            "provider_boundary_reference": "provider://vap01/outlet",
        }
    )
    vaporizer_risk_atom = vaporizer_branch["risk"]["risk_atom"]
    vaporizer_risk_atom.update(
        {"event_id": "evt-vap01-hole", "asset_id": "VAP-01"}
    )
    runtime_result["components"]["VAP-01"] = vaporizer_component
    runtime_result["component_count"] = 2
    data["runtime_result"] = runtime_result

    vaporizer_binding = deepcopy(_binding())
    vaporizer_binding.update(
        {
            "component_id": "VAP-01",
            "operating_mode": "supply",
            "hazop_scenario_id": "VAP01-high-pressure-supply",
            "event_id": "evt-vap01-hole",
            "asset_id": "VAP-01",
            "release_branch_id": "reviewed-vaporizer-isolation",
            "scenario_families": ["vaporizer_hole"],
        }
    )
    data["scenario_bindings"] = [data["scenario_bindings"][0], vaporizer_binding]
    data["branch_probabilities"]["VAP-01|VAP01-high-pressure-supply"] = 1.0
    data["branch_partition_groups"]["VAP-01|VAP01-high-pressure-supply"] = "pressure-deviation-vaporizer"
    data["scenario_identity_crosswalk"].append(
        {
            "component_id": "VAP-01",
            "qualitative_scenario_id": "high-pressure-vaporizer:supply:vaporizer_hole",
            "quantitative_scenario_id": "VAP01-high-pressure-supply",
        }
    )
    data["expected_component_ids"] = ["TK-01", "VAP-01"]

    result = build_equipment_hazop_quantitative_campaign(**data, now_s=4.0)

    assert result["status"] == "EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert result["scenario_identity_crosswalk"]["selected_qualitative_scenario_count"] == 2
    assert len(result["campaign"]["cases"]) == 2
    assert len(result["campaign"]["risk_atoms"]) == 8
    cases_by_component = {row["component_id"]: row for row in result["campaign"]["cases"]}
    assert cases_by_component["TK-01"]["operating_mode"] == "receiving"
    assert cases_by_component["VAP-01"]["operating_mode"] == "supply"
    assert {row["asset_id"] for row in result["campaign"]["risk_atoms"]} == {"TK-01", "VAP-01"}
    assert {row["hazop_scenario_id"] for row in result["campaign"]["risk_atoms"]} == {
        "TK01-high-pressure-receiving",
        "VAP01-high-pressure-supply",
    }
    assert result["policy"]["facility_qra_claim"] is False
