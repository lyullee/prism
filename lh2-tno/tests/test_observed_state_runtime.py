from __future__ import annotations

import pytest

from lh2_tno.observed_state_runtime import (
    build_observed_state_runtime_frames,
    request_from_observed_state_runtime_frame,
    service_state_from_runtime_frame,
)
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


def test_runtime_frame_converts_to_service_state_input_without_accident_fields():
    report = build_observed_state_runtime_frames([_source()])
    frame = report["frames"][0]
    normalized = service_state_from_runtime_frame(frame, now_s=101.0)
    assert normalized["values"]["pressure"]["value_si"] == 251000.0
    assert normalized["data_age_s"] == 100.0
    assert normalized["independent_measurement_claim"] is True
    assert "release_termination" not in normalized


def test_runtime_frame_rejects_tampering_and_accident_owned_fields():
    report = build_observed_state_runtime_frames([_source()])
    frame = dict(report["frames"][0])
    frame["values"] = dict(frame["values"])
    frame["values"]["pressure"] = dict(frame["values"]["pressure"])
    frame["values"]["pressure"]["value_si"] = 252000.0
    with pytest.raises(ValueError, match="frame_digest"):
        service_state_from_runtime_frame(frame, now_s=101.0)
    frame = dict(report["frames"][0])
    frame["duration_s"] = 1.0
    with pytest.raises(ValueError, match="accident-owned"):
        service_state_from_runtime_frame(frame, now_s=101.0)


def test_runtime_frame_provider_resolver_seam_is_explicit():
    from lh2_tno.consequences import ConsequenceRequest
    from lh2_tno.provider_release import (
        build_consequence_request_from_provider_release,
    )
    from test_consequence_service import request
    from test_provider_release import _defaults, _release

    report = build_observed_state_runtime_frames([_source()])
    frame = report["frames"][0]
    template = request().model_copy(update={"component_id": "tank-01"})
    provider_request = build_consequence_request_from_provider_release(
        _release(), _defaults()
    ).model_copy(update={"component_id": "tank-01"})
    seen = {}

    def resolver(_template, state):
        seen["state"] = state
        return provider_request

    resolved = request_from_observed_state_runtime_frame(
        template,
        frame,
        now_s=101.0,
        release_resolver=resolver,
    )
    assert isinstance(resolved, ConsequenceRequest)
    assert resolved.source_input is None
    assert resolved.resolved_release is not None
    assert "annual_frequency_per_year" not in seen["state"]
