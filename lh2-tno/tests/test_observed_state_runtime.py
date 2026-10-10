from __future__ import annotations

import pytest

from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames
from lh2_tno.service import validate_equipment_process_state


def _source():
    return {
        "source_id": "historian-tank-01",
        "source_path": "external://center/tank.csv",
        "source_sha256": "a" * 64,
        "format": "csv",
        "component_id": "tank-01",
        "origin": "historian_measured",
        "samples": [
            {
                "captured_at_s": 0,
                "values": {
                    "pressure": {"value_si": 250000.0, "sensor_location": "PT-01"},
                    "temperature": {"value_si": 23.15, "sensor_location": "TT-01"},
                },
            },
            {
                "captured_at_s": 1,
                "values": {
                    "pressure": {"value_si": 251000.0, "sensor_location": "PT-01"},
                    "temperature": {"value_si": 23.25, "sensor_location": "TT-01"},
                },
            },
        ],
    }


def test_runtime_frame_selects_latest_state_and_matches_service_shape():
    report = build_observed_state_runtime_frames([_source()])
    assert report["schema_version"] == "prism.observed_state_runtime_frames.v1"
    assert report["status"] == "STATE_RUNTIME_FRAMES_READY"
    assert report["source_count"] == report["frame_count"] == 1
    assert report["evidence_sample_count"] == 2
    frame = report["frames"][0]
    assert frame["captured_at_s"] == 1.0
    assert frame["state_snapshot_digest"]
    assert frame["values"]["pressure"]["component_id"] == "tank-01"
    normalized = {"component_id": frame["component_id"], "values": frame["values"]}
    assert validate_equipment_process_state(normalized)["component_id"] == "tank-01"
    assert report["policy"]["release_scenario_generated"] is False
    assert report["policy"]["provider_release_required_for_consequence"] is True


def test_runtime_frame_rejects_accident_owned_fields():
    source = _source()
    source["samples"][0]["event_id"] = "accident"
    with pytest.raises(ValueError, match="accident-owned"):
        build_observed_state_runtime_frames([source])


def test_runtime_frame_rejects_duplicate_component_sources():
    source = _source()
    other = dict(_source())
    other["source_id"] = "historian-tank-02"
    with pytest.raises(ValueError, match="one source per component_id"):
        build_observed_state_runtime_frames([source, other])
