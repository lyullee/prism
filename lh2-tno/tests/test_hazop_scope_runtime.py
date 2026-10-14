from lh2_tno.hazop_scope_runtime import (
    build_full_scope_hazop_runtime_audit,
    build_full_scope_hazop_table_set,
)
from lh2_tno.contracts import canonical_digest


def _row(component_id, component_kind, mode, tag, family, release_mode, row_id):
    return {
        "id": row_id,
        "component_id": component_id,
        "component_kind": component_kind,
        "operating_modes": [mode],
        "variable_tag": tag,
        "quantity": "pressure",
        "trigger": "at_or_above",
        "threshold_high_si": 600000.0,
        "scenario_family": family,
        "release_mode": release_mode,
        "priority": "high",
        "deviation_label": "diagnostic deviation",
        "cause_summary": "synthetic test input",
        "consequence_summary": "provider remains separate",
        "safeguards": ["ESD"],
        "provenance": "synthetic test input",
    }


def _inputs():
    base = {
        "schema_version": "prism.hazop_runtime_table_set.v1",
        "facility_id": "test-facility",
        "tables": {
            "ambient-vaporizer-01": {
                "schema_version": "prism.hazop_operating_mode_selection.v1",
                "id": "ambient-table",
                "facility_id": "test-facility",
                "operating_modes": ["supply", "standby"],
                "configuration_origin": "synthetic",
                "source_provenance": "synthetic test input",
                "rows": [_row(
                    "ambient-vaporizer-01", "vaporizer", "supply", "vaporizer_pressure",
                    "inventory_depletion", "instantaneous_inventory", "ambient-base",
                )],
            },
            "reliquefier-01": {
                "schema_version": "prism.hazop_operating_mode_selection.v1",
                "id": "reliquefier-table",
                "facility_id": "test-facility",
                "operating_modes": ["standby", "supply"],
                "configuration_origin": "synthetic",
                "source_provenance": "synthetic test input",
                "rows": [_row(
                    "reliquefier-01", "reliquefier", "standby", "reliquefier_pressure",
                    "two_sided_rupture", "two_sided_rupture", "reliquefier-base",
                )],
            },
        },
    }
    frames = {
        "schema_version": "prism.observed_state_runtime_frames.v1",
        "frames": [
            {
                "source_id": "synthetic-vaporizer",
                "component_id": "ambient-vaporizer-01",
                "captured_at_s": 12.0,
                "origin": "synthetic",
                "quality": "valid",
                "operating_mode": "supply",
                "values": {"vaporizer_pressure": {"component_id": "ambient-vaporizer-01", "quantity": "pressure", "value_si": 650000.0, "quality": "valid"}},
                "state_snapshot_digest": "a" * 64,
                "source_sha256": "b" * 64,
            },
            {
                "source_id": "synthetic-reliquefier",
                "component_id": "reliquefier-01",
                "captured_at_s": 12.0,
                "origin": "synthetic",
                "quality": "valid",
                "operating_mode": "standby",
                "values": {"reliquefier_pressure": {"component_id": "reliquefier-01", "quantity": "pressure", "value_si": 650000.0, "quality": "valid"}},
                "state_snapshot_digest": "c" * 64,
                "source_sha256": "d" * 64,
            },
        ],
    }
    for frame in frames["frames"]:
        tag = next(iter(frame["values"]))
        frame["state_snapshot"] = {
            "schema_version": "prism.equipment_state_snapshot.v1",
            "component_id": frame["component_id"],
            "captured_at_s": frame["captured_at_s"],
            "origin": frame["origin"],
            "pressure_pa_abs": frame["values"][tag]["value_si"],
            "temperature_k": None,
            "mass_kg": None,
            "liquid_fraction": None,
            "phase": None,
            "position_enu_m": None,
            "measurements": {tag: frame["values"][tag]},
            "source_digest": frame["source_sha256"],
            "quality": frame["quality"],
        }
        frame["state_snapshot_digest"] = canonical_digest(frame["state_snapshot"])
        frame["frame_digest"] = canonical_digest(
            {key: value for key, value in frame.items() if key != "frame_digest"}
        )
    events = [
        ("facility/vaporizer/G1", "ambient-vaporizer-01", "supply", "inventory_depletion", "instantaneous_inventory"),
        ("facility/vaporizer/G2", "ambient-vaporizer-01", "supply", "inventory_over_600s", "inventory_over_600s"),
        ("facility/reliquefier/G4", "reliquefier-01", "standby", "two_sided_rupture", "two_sided_rupture"),
        ("facility/reliquefier/G6", "reliquefier-01", "standby", "reliquefier_hole", "hole"),
    ]
    campaign = {
        "events": [
            {
                "id": event_id,
                "model_component_id": component_id,
                "release": {"mode": release_mode},
            }
            for event_id, component_id, _mode, _family, release_mode in events
        ],
        "cases": [
            {"event_id": event_id, "scenario_families": [family]}
            for event_id, _component_id, _mode, family, _release_mode in events
        ],
    }
    bindings = {
        "schema_version": "prism.hazop_event_mode_binding.v1",
        "bindings": [
            {
                "event_id": event_id,
                "component_id": component_id,
                "operating_mode": mode,
                "release_mode": release_mode,
                "hazop_scenario_id": f"scenario/{event_id}",
            }
            for event_id, component_id, mode, _family, release_mode in events
        ],
    }
    return base, frames, campaign, bindings


def test_full_scope_rows_are_added_only_for_missing_explicit_families():
    base, _frames, campaign, bindings = _inputs()
    result = build_full_scope_hazop_table_set(base, campaign, bindings)
    assert result["scope_audit"]["status"] == "FULL_SCOPE_HAZOP_ROWS_EXPANDED"
    assert result["scope_audit"]["added_row_count"] == 2
    assert {
        row["scenario_family"] for row in result["scope_audit"]["added_rows"]
    } == {"inventory_over_600s", "reliquefier_hole"}


def test_full_scope_runtime_and_event_identity_audit_closes_all_explicit_events():
    base, frames, campaign, bindings = _inputs()
    result = build_full_scope_hazop_runtime_audit(
        base, frames, campaign, bindings, now_s=12.0
    )
    assert result["status"] == "FULL_SCOPE_HAZOP_SELECTION_EVENT_BINDING_COMPLETE"
    assert result["selected_scenario_count"] == 4
    assert result["frequency_event_count"] == 4
    assert result["bound_event_count"] == 4
    assert result["unbound_event_count"] == 0
    assert result["policy"]["frequency_assignment_performed"] is False
    assert result["policy"]["provider_release_created"] is False
