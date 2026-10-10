import json
from pathlib import Path

from lh2_tno.external_equipment_model_audit import audit_external_equipment_model


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_external_equipment_audit_separates_state_readiness_from_release(tmp_path):
    assets = _write(tmp_path / "assets.json", {
        "schema_version": "0.1",
        "assets": [
            {"asset_id": "TK-1", "component_model": "homogeneous_tank", "status": "ready"},
            {"asset_id": "TK-2", "component_model": "homogeneous_tank", "status": "ready"},
        ],
    })
    private = _write(tmp_path / "private.json", {
        "schema_version": "0.1",
        "audits": [
            {"asset_id": "TK-1", "ready": True, "issues": []},
            {"asset_id": "TK-2", "ready": True, "issues": []},
        ],
    })
    events = _write(tmp_path / "events.json", {
        "schema_version": "0.1",
        "physical_time_status": "unassigned",
        "official_promotion_allowed": False,
        "fitting": False,
        "valve_events": [{"physical_time_s": None, "event_feedback_channel": None}],
        "dead_volume": {"actual_installed_route_length_m": None},
    })
    observations = _write(tmp_path / "observations.json", {
        "schema_version": "0.1",
        "time_alignment": {"command_timestamp_available": False},
        "source_provenance": {
            "verified_raw_historian_session_count": 0,
            "explicit_reconstructed_session_count": 2,
        },
        "calibration": {"final_accuracy_use_allowed": False},
        "release_policy": {"official_94_percent_accuracy_decision_allowed": False},
    })
    report = audit_external_equipment_model(assets, private, events, observations)
    assert report["status"] == "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED"
    assert report["state_model_ready_asset_count"] == 2
    assert report["promotion_gates"]["state_model_input_allowed"] is True
    assert report["promotion_gates"]["accident_release_packet_allowed"] is False
    assert report["frequency_inference_performed"] is False
    assert "procedure_events_are_not_accident_release_packets" in report["blocking_reasons"]
