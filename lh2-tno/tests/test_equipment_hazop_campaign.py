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
