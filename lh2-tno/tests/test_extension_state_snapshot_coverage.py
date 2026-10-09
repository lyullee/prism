from lh2_tno.extension_state_snapshot_coverage import (
    build_extension_state_snapshot_coverage,
)


def _result(event_id: str, *, identity: bool = True) -> dict:
    case = {"event_id": event_id}
    if identity:
        case["provider_packet_identity"] = {
            "component_id": "pipe-01",
            "provider_source_digests": ["source-digest"],
            "provider_result_digests": ["result-digest"],
        }
    return {
        "_record_path": "extension-result.json",
        "events": [{"id": event_id, "model_component_id": "pipe-01"}],
        "cases": [case],
    }


def test_extension_state_coverage_fails_closed_without_canonical_snapshot():
    report = build_extension_state_snapshot_coverage(
        extension_results={
            "vertical_handoff": _result("facility/vertical/AREA_1%"),
            "inventory_depletion": _result("facility/inventory/AREA_1%", identity=False),
        }
    )
    assert report["status"] == "EXTENSION_STATE_SNAPSHOT_COVERAGE_INCOMPLETE"
    assert report["event_count"] == 2
    assert report["bound_event_count"] == 0
    assert report["unbound_event_count"] == 2
    assert report["provider_identity_missing_event_ids"] == ["facility/inventory/AREA_1%"]
    assert "not used to reconstruct equipment state" in report["rows"][0]["reason"]


def test_extension_state_coverage_accepts_explicit_bound_audit_row():
    event_id = "facility/vertical/AREA_1%"
    report = build_extension_state_snapshot_coverage(
        extension_results={"vertical_handoff": _result(event_id)},
        state_snapshot_audit={
            "_record_path": "extension-state-audit.json",
            "rows": [{
                "event_id": event_id,
                "status": "BOUND_AND_ECHOED",
                "reason": "canonical snapshot echoed",
                "record": "state-record.json",
            }],
        },
    )
    assert report["status"] == "EXTENSION_STATE_SNAPSHOT_COVERAGE_COMPLETE"
    assert report["bound_event_count"] == 1
    assert report["rows"][0]["snapshot_bound"] is True
