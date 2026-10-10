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


def test_external_equipment_audit_records_pid_evidence_without_promotion(tmp_path):
    assets = _write(tmp_path / "assets.json", {
        "schema_version": "0.1",
        "assets": [{"asset_id": "TK-1", "component_model": "homogeneous_tank"}],
    })
    private = _write(tmp_path / "private.json", {
        "schema_version": "0.1",
        "audits": [{"asset_id": "TK-1", "ready": False, "issues": ["geometry"]}],
    })
    events = _write(tmp_path / "events.json", {
        "schema_version": "0.1", "physical_time_status": "unassigned",
        "official_promotion_allowed": False, "fitting": False,
        "valve_events": [], "dead_volume": {},
    })
    observations = _write(tmp_path / "observations.json", {
        "schema_version": "0.1",
        "time_alignment": {"command_timestamp_available": False},
        "source_provenance": {"verified_raw_historian_session_count": 0},
        "release_policy": {"official_94_percent_accuracy_decision_allowed": False},
    })
    pid = _write(tmp_path / "pid.json", {
        "schema_version": "0.1",
        "equipment": [{"equipment_id": "TK-1", "source_ids": ["P-1"], "status": "observed_not_model_ready"}],
    })
    ports = _write(tmp_path / "ports.json", {
        "schema_version": "0.1",
        "mappings": [
            {"equipment_id": "TK-1", "port_id": "TK-1:A", "status": "confirmed"},
            {"equipment_id": "TK-1", "port_id": "TK-1:G", "status": "candidate_mapping"},
        ],
    })
    components = _write(tmp_path / "components.json", {
        "schema_version": "0.1", "node_bindings": [{"node_id": "TK-1"}],
        "edge_bindings": [{"edge_id": "E1", "enabled": False}],
    })
    flow = _write(tmp_path / "flow.json", {
        "schema_version": "0.1", "rows": [{"flow_tag": "XV1"}],
        "unresolved_flow_tags": ["XV2"],
    })
    report = audit_external_equipment_model(
        assets, private, events, observations,
        pid_evidence_path=pid,
        port_mappings_path=ports,
        component_bindings_path=components,
        flow_crosswalk_path=flow,
    )
    assert report["pid_identity_evidence"]["exact_asset_id_overlap_count"] == 1
    assert report["pid_port_evidence"]["status_counts"] == {"confirmed": 1, "candidate_mapping": 1}
    assert report["component_binding_evidence"]["unresolved_edge_count"] == 1
    assert report["flow_crosswalk_evidence"]["unresolved_flow_tag_count"] == 1
    assert report["pid_identity_evidence"]["identity_is_general_facility_resolved"] is False
    assert report["promotion_gates"]["accident_release_packet_allowed"] is False
    assert len(report["sources"]) == 8
