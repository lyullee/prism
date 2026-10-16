from __future__ import annotations

from lh2_tno.equipment_hazop_handoff import build_equipment_hazop_mode_handoff
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames


def _manifest():
    return {
        "schema_version": "1.0",
        "facility_id": "runtime-test-facility",
        "environment": "outdoor",
        "configuration_origin": "synthetic",
        "components": [
            {
                "id": "tank-01",
                "kind": "storage_tank",
                "position_enu_m": [0.0, 0.0, 1.0],
                "property_basis": {
                    "fluid": "Hydrogen",
                    "backend": "CoolProp-HEOS",
                    "energy_reference": "CoolProp-HEOS:Hydrogen:native",
                },
                "parameters_si": {"volume_m3": 10.0},
            }
        ],
        "ports": [
            {
                "id": "tank-01-out",
                "component_id": "tank-01",
                "phase": "liquid",
                "direction": "out",
            }
        ],
    }


def _source(component_id="tank-01"):
    return {
        "source_id": f"historian-{component_id}",
        "source_sha256": "a" * 64,
        "component_id": component_id,
        "origin": "historian_measured",
        "samples": [
            {
                "captured_at_s": 3.0,
                "values": {
                    "pressure": {
                        "value_si": 650000.0,
                        "sensor_location": f"{component_id}.vapour",
                    }
                },
            }
        ],
    }


def _table(component_id="tank-01"):
    return {
        "schema_version": "prism.hazop_operating_mode_selection.v1",
        "id": "runtime-test-hazop",
        "facility_id": "runtime-test-facility",
        "operating_modes": ["receiving", "supply", "standby"],
        "configuration_origin": "synthetic",
        "source_provenance": "test",
        "rows": [
            {
                "id": "high-pressure",
                "component_id": component_id,
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


def _inputs(component_id="tank-01"):
    runtime = build_observed_state_runtime_frames(
        [_source(component_id)],
        operating_mode_map={f"historian-{component_id}": "receiving"},
    )
    return runtime, {"schema_version": "prism.hazop_runtime_table_set.v1", "tables": {component_id: _table(component_id)}}


def test_equipment_hazop_handoff_binds_explicit_mode_and_component():
    runtime, tables = _inputs()
    result = build_equipment_hazop_mode_handoff(
        _manifest(), runtime, tables, now_s=4.0
    )
    assert result["status"] == "EQUIPMENT_HAZOP_MODE_HANDOFF_READY"
    assert result["component_coverage"]["exact_component_set"] is True
    assert result["hazop_runtime_audit"]["selected_scenario_count"] == 1
    assert result["policy"]["operating_mode_inferred"] is False
    assert result["policy"]["release_created"] is False


def test_equipment_hazop_handoff_blocks_unknown_runtime_component():
    runtime, tables = _inputs("other-tank")
    result = build_equipment_hazop_mode_handoff(
        _manifest(), runtime, tables, now_s=4.0
    )
    assert result["status"] == "EQUIPMENT_HAZOP_MODE_HANDOFF_BLOCKED"
    assert result["component_coverage"]["unknown_runtime_component_ids"] == ["other-tank"]
    assert result["policy"]["frequency_inference_performed"] is False


def test_equipment_hazop_handoff_keeps_incomplete_manifest_partial():
    runtime, tables = _inputs()
    manifest = _manifest()
    manifest["components"][0]["position_enu_m"] = None
    result = build_equipment_hazop_mode_handoff(
        manifest, runtime, tables, now_s=4.0
    )
    assert result["status"] == "EQUIPMENT_HAZOP_MODE_HANDOFF_PARTIAL"
    assert result["equipment_manifest_audit"]["status"] == "PARTIAL"
