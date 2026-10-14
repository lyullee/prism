from lh2_tno.hazop_extension_mode_binding import bind_hazop_extension_modes


def _runtime():
    return {
        "schema_version": "prism.observed_hazop_runtime_audit.v1",
        "rows": [{
            "component_id": "tank-01",
            "selected_scenarios": [{
                "scenario_id": "tank|receiving|vessel_hole",
                "component_id": "tank-01",
                "operating_mode": "receiving",
                "scenario_family": "vessel_hole",
                "release_mode": "hole",
            }],
        }],
    }


def _binding():
    return {
        "schema_version": "prism.hazop_event_mode_binding.v1",
        "bindings": [{
            "event_id": "facility/tank/AREA_1%",
            "component_id": "tank-01",
            "operating_mode": "receiving",
            "hazop_scenario_id": "tank|receiving|vessel_hole",
            "scenario_family": "vessel_hole",
            "release_mode": "hole",
        }],
    }


def _campaign():
    return {
        "events": [{
            "id": "facility/tank/AREA_1%",
            "model_component_id": "tank-01",
            "scenario_families": ["vessel_hole"],
            "release": {"mode": "hole"},
        }, {
            "id": "facility/extension/AREA_1%",
            "model_component_id": "extension-pipe-01",
            "scenario_families": ["vertical_handoff"],
            "release": {"mode": "hole"},
        }],
        "cases": [{
            "event_id": "facility/extension/AREA_1%",
            "provider_packet_identity": {
                "state_snapshot_digest": "a" * 64,
            },
        }],
    }


def test_explicit_extension_mode_closes_event_identity_without_frequency_or_provider_creation():
    result = bind_hazop_extension_modes(
        _runtime(),
        _binding(),
        _campaign(),
        {
            "schema_version": "prism.hazop_extension_mode_config.v1",
            "extensions": [{
                "component_id": "extension-pipe-01",
                "event_prefix": "facility/extension/",
                "operating_mode": "receiving",
                "scenario_family": "vertical_handoff",
                "release_mode": "hole",
                "hazop_row_id": "EXT-01",
                "hazop_scenario_id": "extension|receiving|vertical_handoff",
                "table_id": "table-v1",
                "source_id": "source-01",
                "source_provenance": "explicit synthetic extension row",
            }],
        },
    )
    assert result["selection_event_audit"]["status"] == (
        "HAZOP_SELECTION_EVENT_BINDING_COMPLETE"
    )
    assert result["selection_event_audit"]["bound_event_count"] == 2
    assert result["selection_event_audit"]["unbound_event_count"] == 0
    assert result["frequency_assignment_performed"] is False
    assert result["provider_release_created"] is False
