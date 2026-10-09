from lh2_tno.extension_state_snapshot_coverage import (
    build_extension_state_snapshot_coverage,
)
from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot


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


def test_extension_state_coverage_accepts_snapshot_carried_in_case_identity():
    event_id = "facility/vertical/AREA_1%"
    snapshot = EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id="pipe-01",
        captured_at_s=0.0,
        origin="model_prediction",
        pressure_pa_abs=101000.0,
        temperature_k=20.5,
    )
    identity = {
        "component_id": "pipe-01",
        "provider_source_digests": ["source-digest"],
        "provider_result_digests": ["result-digest"],
        "state_snapshot": snapshot.to_mapping(),
        "state_snapshot_digest": snapshot.digest(),
        "provider_state_snapshot_digest": snapshot.digest(),
    }
    result = _result(event_id)
    result["cases"][0]["provider_packet_identity"] = identity
    report = build_extension_state_snapshot_coverage(
        extension_results={"vertical_handoff": result}
    )
    assert report["status"] == "EXTENSION_STATE_SNAPSHOT_COVERAGE_COMPLETE"
    assert report["bound_event_count"] == 1
    assert report["rows"][0]["status"] == "BOUND_AND_ECHOED"


def test_extension_state_coverage_allows_explicit_namespace_component_mapping():
    event_id = "facility/vertical/AREA_1%"
    snapshot = EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id="pipe-01",
        captured_at_s=0.0,
        origin="model_prediction",
        pressure_pa_abs=101000.0,
    )
    result = _result(event_id)
    result["events"][0]["model_component_id"] = "rebound-pipe-01"
    result["campaign_namespace_rebind"] = {
        "source_component_id": "pipe-01",
        "component_id": "rebound-pipe-01",
    }
    result["cases"][0]["provider_packet_identity"].update({
        "component_id": "rebound-pipe-01",
        "state_snapshot": snapshot.to_mapping(),
        "state_snapshot_digest": snapshot.digest(),
        "provider_state_snapshot_digest": snapshot.digest(),
    })
    report = build_extension_state_snapshot_coverage(
        extension_results={"vertical_handoff": result}
    )
    assert report["status"] == "EXTENSION_STATE_SNAPSHOT_COVERAGE_COMPLETE"
