from lh2_tno.hazop_event_selection_audit import (
    audit_hazop_selection_event_bindings,
)


def _runtime():
    return {
        "schema_version": "prism.observed_hazop_runtime_audit.v1",
        "rows": [{
            "selected_scenarios": [{
                "scenario_id": "row-1:receiving:vessel_hole",
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
            "hazop_scenario_id": "explicit-scenario-id",
            "release_mode": "hole",
        }],
    }


def _event():
    return [{
        "id": "facility/tank/AREA_1%",
        "model_component_id": "tank-01",
        "scenario_families": ["vessel_hole"],
        "release": {"mode": "hole"},
    }]


def test_selected_hazop_scenario_expands_to_explicit_event_bin():
    report = audit_hazop_selection_event_bindings(_runtime(), _binding(), _event())
    assert report["status"] == "HAZOP_SELECTION_EVENT_BINDING_COMPLETE"
    assert report["selected_scenario_count"] == 1
    assert report["bound_event_count"] == 1
    assert report["policy"]["frequency_assignment_performed"] is False


def test_event_component_or_release_mismatch_is_blocked():
    event = _event()
    event[0]["model_component_id"] = "pipe-01"
    report = audit_hazop_selection_event_bindings(_runtime(), _binding(), event)
    assert report["status"] == "HAZOP_SELECTION_EVENT_BINDING_REQUIRED"
    assert report["event_rows"][0]["checks"]["component_matches_event"] is False


def test_unselected_hazop_scenario_cannot_be_silently_ignored():
    binding = _binding()
    binding["bindings"][0]["operating_mode"] = "supply"
    report = audit_hazop_selection_event_bindings(_runtime(), binding, _event())
    assert report["status"] == "HAZOP_SELECTION_EVENT_BINDING_REQUIRED"
    assert report["selected_scenarios"][0]["status"] == "BINDING_REQUIRED"


def test_blocked_runtime_row_is_reported_as_missing_selection_instead_of_crashing():
    runtime = _runtime()
    runtime["rows"] = [{
        "component_id": "tank-01",
        "status": "HAZOP_EVALUATION_BLOCKED",
        "blocking_reasons": ["missing frame digest"],
    }]
    report = audit_hazop_selection_event_bindings(runtime, _binding(), _event())
    assert report["status"] == "HAZOP_SELECTION_EVENT_BINDING_REQUIRED"
    assert report["bound_event_count"] == 0
    assert report["unbound_event_count"] == 1


def test_extension_event_without_mode_binding_is_reported_as_unbound():
    events = _event()
    events.append({
        "id": "facility/vertical-handoff/AREA_1%",
        "model_component_id": "vertical-handoff-terminal-pipe-01",
        "scenario_families": ["vertical_handoff"],
        "release": {"mode": "hole"},
    })
    report = audit_hazop_selection_event_bindings(_runtime(), _binding(), events)
    assert report["status"] == "HAZOP_SELECTION_EVENT_BINDING_REQUIRED"
    assert report["frequency_event_count"] == 2
    assert report["bound_event_count"] == 1
    assert report["unbound_event_count"] == 1
    assert report["event_rows"][-1]["status"] == "BINDING_REQUIRED"
    assert "no explicit HAZOP mode binding" in report["errors"][-1]
