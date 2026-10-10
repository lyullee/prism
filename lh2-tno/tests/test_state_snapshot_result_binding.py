import pytest

from lh2_tno.state_snapshot import EquipmentStateSnapshot
from lh2_tno.state_snapshot_result_binding import bind_campaign_result_state_snapshots


def _inputs(*, include_snapshot: bool = True):
    event_id = "facility/tank/AREA_0.01%"
    component_id = "tank-01"
    result_digest = "a" * 64
    snapshot = EquipmentStateSnapshot(
        schema_version="prism.equipment_state_snapshot.v1",
        component_id=component_id,
        captured_at_s=0.0,
        origin="model_prediction",
        pressure_pa_abs=200000.0,
        temperature_k=20.0,
        mass_kg=1.0,
        phase="liquid",
    )
    request = {
        "component_id": component_id,
        "resolved_release": {"provider_result_digest": result_digest},
    }
    if include_snapshot:
        request.update(
            {
                "state_snapshot": snapshot.to_mapping(),
                "state_snapshot_digest": snapshot.digest(),
                "provider_state_snapshot_digest": snapshot.digest(),
            }
        )
    campaign = {
        "id": "campaign",
        "event_routes": [{"event_id": event_id, "branches": [{"id": "open", "request": request}]}],
    }
    identity = {
        "event_id": event_id,
        "component_id": component_id,
        "provider_result_digests": [result_digest],
    }
    result = {
        "cases": [{"event_id": event_id, "provider_packet_identity": dict(identity)}],
        "uncomputed_cases": [],
        "risk_atoms": [{"event_id": event_id, "provider_packet_identity": dict(identity)}],
    }
    audit = {
        "status": "STATE_SNAPSHOT_BOUND_AND_ECHOED",
        "rows": [
            {
                "event_id": event_id,
                "component_id": component_id,
                "provider_result_digest": result_digest,
                "declared_digest": snapshot.digest(),
                "status": "BOUND_AND_ECHOED",
            }
        ],
    }
    return campaign, result, audit, snapshot


def test_result_binding_copies_exact_audited_snapshot_into_cases_and_atoms():
    campaign, result, audit, snapshot = _inputs()

    bound, report = bind_campaign_result_state_snapshots(result, campaign, audit)

    assert report["status"] == "STATE_SNAPSHOT_RESULT_BOUND_AND_ECHOED"
    assert report["bound_case_count"] == 1
    assert report["bound_risk_atom_count"] == 1
    for row in (*bound["cases"], *bound["risk_atoms"]):
        identity = row["provider_packet_identity"]
        assert identity["state_snapshot_digest"] == snapshot.digest()
        assert identity["provider_state_snapshot_digest"] == snapshot.digest()
        assert identity["state_snapshot"]["component_id"] == "tank-01"


def test_result_binding_rejects_unbound_campaign_request():
    campaign, result, audit, _ = _inputs(include_snapshot=False)

    with pytest.raises(ValueError, match="no canonical state_snapshot"):
        bind_campaign_result_state_snapshots(result, campaign, audit)
