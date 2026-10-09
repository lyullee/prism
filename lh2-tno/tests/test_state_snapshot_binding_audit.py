from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot
from lh2_tno.state_snapshot_binding_audit import build_state_snapshot_binding_audit


def _snapshot(component_id="tank-1"):
    return EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": component_id,
        "captured_at_s": 10.0,
        "origin": "model_prediction",
        "pressure_pa_abs": 500000.0,
        "temperature_k": 20.5,
        "position_enu_m": [1.0, 2.0, 3.0],
    })


def test_canonical_snapshot_and_provider_echo_are_bound():
    snapshot = _snapshot()
    report = build_state_snapshot_binding_audit(diagnostic_records=[{
        "event_id": "event-1",
        "component_id": "tank-1",
        "request": {
            "state_snapshot": snapshot.to_mapping(),
            "state_snapshot_digest": snapshot.digest(),
        },
        "provider_response": {
            "provider_state_snapshot_digest": snapshot.digest(),
        },
    }])
    assert report["status"] == "STATE_SNAPSHOT_BOUND_AND_ECHOED"
    assert report["bound_count"] == 1
    assert report["rows"][0]["status"] == "BOUND_AND_ECHOED"


def test_digest_only_does_not_count_as_binding():
    report = build_state_snapshot_binding_audit(diagnostic_records=[{
        "event_id": "event-2",
        "component_id": "tank-1",
        "state_snapshot_digest_match": True,
    }])
    assert report["status"] == "NO_STATE_SNAPSHOT_BOUND"
    assert report["bound_count"] == 0
    assert report["declared_digest_only_count"] == 1


def test_verification_record_can_carry_snapshot_payload_at_top_level():
    snapshot = _snapshot()
    report = build_state_snapshot_binding_audit(diagnostic_records=[{
        "event_id": "event-top-level",
        "component_id": "tank-1",
        "state_snapshot": snapshot.to_mapping(),
        "state_snapshot_handoff": {
            "present": True,
            "digest": snapshot.digest(),
            "provider_echo_digest": snapshot.digest(),
        },
    }])
    assert report["bound_count"] == 1
    assert report["rows"][0]["status"] == "BOUND_AND_ECHOED"


def test_snapshot_digest_mismatch_is_fail_closed():
    snapshot = _snapshot()
    report = build_state_snapshot_binding_audit(diagnostic_records=[{
        "event_id": "event-3",
        "component_id": "tank-1",
        "request": {
            "state_snapshot": snapshot.to_mapping(),
            "state_snapshot_digest": "a" * 64,
        },
        "provider_response": {
            "provider_state_snapshot_digest": snapshot.digest(),
        },
    }])
    assert report["status"] == "STATE_SNAPSHOT_BINDING_ERROR"
    assert report["digest_mismatch_count"] == 1


def test_campaign_without_payload_is_unbound_even_when_release_exists():
    report = build_state_snapshot_binding_audit({
        "event_routes": [{
            "event_id": "event-4",
            "branches": [{
                "request": {
                    "component_id": "tank-1",
                    "resolved_liquid_release": {
                        "component_id": "tank-1",
                        "provider_result_digest": "b" * 64,
                    },
                },
            }],
        }],
    })
    assert report["status"] == "NO_STATE_SNAPSHOT_BOUND"
    assert report["unbound_count"] == 1
