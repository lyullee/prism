from lh2_tno.hazop_extension_evidence_request import (
    build_hazop_extension_mode_binding_request,
)


def _audit(rows):
    return {
        "schema_version": "prism.hazop_event_selection_binding_audit.v1",
        "status": "HAZOP_SELECTION_EVENT_BINDING_REQUIRED",
        "frequency_event_count": len(rows),
        "bound_event_count": sum(row["status"] == "BOUND" for row in rows),
        "unbound_event_count": sum(row["status"] != "BOUND" for row in rows),
        "event_rows": rows,
    }


def test_extension_request_preserves_unbound_identity_without_inference():
    record = build_hazop_extension_mode_binding_request(_audit([
        {
            "event_id": "facility/vertical-handoff/AREA_1%",
            "status": "BINDING_REQUIRED",
            "frequency_event_component_id": "vertical-handoff-terminal-pipe-01",
            "frequency_event_release_mode": "hole",
            "scenario_families": ["vertical_handoff"],
        }
    ]))
    assert record["status"] == "OPEN_HAZOP_EXTENSION_MODE_EVIDENCE"
    assert record["request_count"] == 1
    assert record["requests"][0]["event_id"].endswith("AREA_1%")
    assert record["requests"][0]["policy"]["operating_mode_inferred"] is False


def test_extension_request_closes_when_no_unbound_events_exist():
    record = build_hazop_extension_mode_binding_request(_audit([
        {
            "event_id": "facility/tank/AREA_1%",
            "status": "BOUND",
            "frequency_event_component_id": "tank-01",
            "frequency_event_release_mode": "hole",
            "scenario_families": ["vessel_hole"],
        }
    ]))
    assert record["status"] == "NO_HAZOP_EXTENSION_MODE_GAP"
    assert record["request_count"] == 0
