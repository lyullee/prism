from __future__ import annotations

from lh2_tno.observed_hazop_provider_binding import (
    audit_observed_hazop_provider_binding,
)


def _runtime():
    return {
        "schema_version": "prism.observed_hazop_runtime_audit.v1",
        "rows": [{
            "selected_scenarios": [{
                "scenario_id": "scenario-1",
                "hazop_row_id": "hazop-1",
                "component_id": "observed-tank",
                "operating_mode": "receiving",
                "scenario_family": "vessel_hole",
                "release_mode": "hole",
            }],
        }],
    }


def _worklist():
    return {
        "work_items": [{
            "event_id": "event-1",
            "component_id": "provider-tank",
            "accident_port_ids": ["tank-out"],
            "scenario_families": ["vessel_hole"],
            "release_mode": "hole",
            "provider_event_kind": "accidental_leak",
            "status": "UNCOMPUTED_PROVIDER_PACKET",
            "annual_frequency_per_year": 1.0e-4,
        }],
    }


def _mapping():
    return {
        "schema_version": "prism.observed_hazop_provider_event_binding_map.v1",
        "bindings": [{
            "scenario_id": "scenario-1",
            "provider_event_id": "event-1",
            "provider_component_id": "provider-tank",
            "provider_port_id": "tank-out",
        }],
    }


def test_explicit_binding_is_diagnostic_only():
    report = audit_observed_hazop_provider_binding(_runtime(), _worklist(), _mapping())
    assert report["status"] == "OBSERVED_HAZOP_PROVIDER_EVENT_BINDINGS_DIAGNOSTIC"
    assert report["selected_scenario_count"] == 1
    assert report["bound_scenario_count"] == 1
    assert report["rows"][0]["provider_release_created"] is False
    assert report["policy"]["frequency_assignment_performed"] is False
    assert report["policy"]["facility_qra_claim"] is False


def test_missing_explicit_binding_is_blocked():
    report = audit_observed_hazop_provider_binding(
        _runtime(),
        _worklist(),
        {"schema_version": "prism.observed_hazop_provider_event_binding_map.v1", "bindings": []},
    )
    assert report["status"] == "OBSERVED_HAZOP_PROVIDER_EVENT_BINDING_AUDIT_BLOCKED"
    assert report["bound_scenario_count"] == 0
    assert report["blocking_reasons"]


def test_incompatible_release_mode_is_blocked():
    mapping = _mapping()
    worklist = _worklist()
    worklist["work_items"][0]["release_mode"] = "maximum_relief_discharge"
    report = audit_observed_hazop_provider_binding(_runtime(), worklist, mapping)
    assert report["status"] == "OBSERVED_HAZOP_PROVIDER_EVENT_BINDING_AUDIT_BLOCKED"
    assert report["rows"][0]["checks"]["release_mode_compatible"] is False
