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
    assert "operating_mode" not in frame
    assert (
        report["runtime_handoff_contract"]["facility_monitor_method"]
        == "FacilityRealtimeConsequenceMonitor.update_from_runtime_frames"
    )


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


def test_runtime_frame_carries_operating_mode_with_state_values():
    source = _source()
    source["samples"][1]["operating_mode"] = "receiving"
    report = build_observed_state_runtime_frames([source])
    frame = report["frames"][0]
    assert frame["operating_mode"] == "receiving"
    normalized = service_state_from_runtime_frame(frame, now_s=2.0)
    assert normalized["operating_mode"] == "receiving"


def test_runtime_frame_binds_explicit_source_mode_map_without_inference():
    report = build_observed_state_runtime_frames(
        [_source()],
        operating_mode_map={
            "schema_version": "prism.explicit_operating_mode_input.v1",
            "source_to_mode": {"historian-tank-01": "receiving"},
        },
    )
    frame = report["frames"][0]
    assert frame["operating_mode"] == "receiving"
    assert report["operating_mode_binding"]["status"] == "EXPLICIT_MODE_INPUT_BOUND"
    assert report["operating_mode_binding"]["inference_performed"] is False
    assert report["policy"]["operating_mode_input_bound"] is True
    assert report["policy"]["operating_mode_inferred"] is False


def test_runtime_frame_rejects_incomplete_explicit_source_mode_map():
    with pytest.raises(ValueError, match="non-empty source_to_mode"):
        build_observed_state_runtime_frames(
            [_source()],
            operating_mode_map={"source_to_mode": {}},
        )


def test_runtime_frame_rejects_mode_map_conflict_with_source_mode():
    source = _source()
    source["operating_mode"] = "standby"
    with pytest.raises(ValueError, match="conflicts"):
        build_observed_state_runtime_frames(
            [source],
            operating_mode_map={"historian-tank-01": "receiving"},
        )


def test_runtime_frame_preserves_custom_hazop_tag_with_declared_quantity():
    source = _source()
    source["samples"][1]["operating_mode"] = "receiving"
    source["samples"][1]["values"] = {
        "tank_pressure": {
            "quantity": "pressure",
            "value_si": 251000.0,
            "sensor_location": "PT-01",
        }
    }
    report = build_observed_state_runtime_frames([source])
    frame = report["frames"][0]
    assert "tank_pressure" in frame["values"]
    assert frame["values"]["tank_pressure"]["quantity"] == "pressure"
    normalized = service_state_from_runtime_frame(frame, now_s=2.0)
    assert normalized["values"]["tank_pressure"]["value_si"] == 251000.0


def test_runtime_frame_rejects_custom_hazop_tag_without_declared_quantity():
    source = _source()
    source["samples"][1]["values"] = {
        "tank_pressure": {"value_si": 251000.0, "sensor_location": "PT-01"}
    }
    with pytest.raises(ValueError, match="custom state tags must include"):
        build_observed_state_runtime_frames([source])


def test_runtime_frame_rejects_blank_operating_mode():
    source = _source()
    source["operating_mode"] = "   "
    with pytest.raises(ValueError, match="operating_mode"):
        build_observed_state_runtime_frames([source])


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
    release = _release().model_copy(update={"component_id": "tank-01"})
    defaults = _defaults()
    defaults["component_id"] = "tank-01"
    provider_request = build_consequence_request_from_provider_release(
        release, defaults
    )
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
    assert resolved.state_snapshot is not None
    assert resolved.state_snapshot_digest == frame["state_snapshot_digest"]
    assert resolved.provider_state_snapshot_digest == frame["state_snapshot_digest"]
    assert "annual_frequency_per_year" not in seen["state"]


def test_runtime_frame_monitor_executes_provider_release_and_deadline(tmp_path):
    from lh2_tno.provider_release import (
        build_consequence_request_from_provider_release,
    )
    from lh2_tno.service import ConsequenceService, RealtimeConsequenceMonitor
    from test_consequence_service import Pipeline, request
    from test_provider_release import _defaults, _release

    report = build_observed_state_runtime_frames([_source()])
    frame = report["frames"][0]
    pipeline = Pipeline(tmp_path)
    monitor = RealtimeConsequenceMonitor(
        ConsequenceService(pipeline), period_s=1.0
    )
    template = request().model_copy(update={"component_id": "tank-01"})
    release = _release().model_copy(update={"component_id": "tank-01"})
    defaults = _defaults()
    defaults["component_id"] = "tank-01"
    provider_request = build_consequence_request_from_provider_release(
        release, defaults
    )
    result = monitor.update_from_runtime_frame(
        template,
        frame,
        now_s=101.0,
        release_resolver=lambda _template, _state: provider_request,
    )
    assert result["telemetry_boundary"]["equipment_release_resolved"] is True
    assert result["telemetry_boundary"]["state_snapshot_binding_status"] == "BOUND_CANONICAL_RUNTIME_STATE"
    assert result["telemetry_boundary"]["state_snapshot_digest"] == frame["state_snapshot_digest"]
    assert result["equipment_release_path"]["status"] == "AVAILABLE_PROVIDER_RELEASE_PATH"
    assert result["realtime"]["runtime_frame"] is True
    assert result["realtime"]["deadline_status"] == "MET"


def test_facility_runtime_frames_execute_each_provider_and_preserve_facility_gates(tmp_path):
    from lh2_tno.service import (
        ConsequenceService,
        FacilityRealtimeBinding,
        FacilityRealtimeConsequenceMonitor,
        RealtimeConsequenceMonitor,
    )
    from lh2_tno.provider_release import build_consequence_request_from_provider_release
    from test_consequence_service import Pipeline, request
    from test_provider_release import _defaults, _release

    first_source = _source()
    first_source["component_id"] = "tank-01"
    second_source = _source()
    second_source["source_id"] = "historian-tank-02"
    second_source["component_id"] = "tank-02"
    report = build_observed_state_runtime_frames([first_source, second_source])

    class RuntimeNormalizer:
        def normalize(self, *_args, **_kwargs):
            raise AssertionError("runtime-frame path must bypass historian normalizer")

    bindings = {}
    for component_id in ("tank-01", "tank-02"):
        component_tmp_path = tmp_path / component_id
        component_tmp_path.mkdir()
        release = _release().model_copy(update={"component_id": component_id})
        defaults = _defaults()
        defaults["component_id"] = component_id
        provider_request = build_consequence_request_from_provider_release(
            release, defaults
        )
        bindings[component_id] = FacilityRealtimeBinding(
            component_id=component_id,
            template=request().model_copy(update={"component_id": component_id}),
            monitor=RealtimeConsequenceMonitor(
                ConsequenceService(Pipeline(component_tmp_path))
            ),
            # Runtime frames bypass historian normalization but the binding
            # still carries these explicit metadata fields for compatibility.
            normalizer=RuntimeNormalizer(),
            pressure_tag="pressure",
            temperature_tag="temperature",
            release_resolver=lambda _template, _state, p=provider_request: p,
        )

    result = FacilityRealtimeConsequenceMonitor(
        bindings, facility_id="generic-outdoor-lh2"
    ).update_from_runtime_frames(
        {frame["component_id"]: frame for frame in report["frames"]},
        now_s=101.0,
    )
    assert result["status"] == "ACCEPTED"
    assert result["accepted_component_count"] == 2
    assert result["runtime_frame_batch"]["status"] == "STATE_ONLY_RUNTIME_BATCH"
    assert result["runtime_frame_batch"]["arrival_time_available"] is False
    assert result["aggregate"]["runtime_frame_batch"] is True
    assert result["aggregate"]["facility_annual_risk_available"] is False
    assert result["aggregate"]["facility_fn_available"] is False
    assert all(
        result["components"][component_id]["result"]["realtime"]["runtime_frame"]
        for component_id in ("tank-01", "tank-02")
    )
    assert result["aggregate"]["equipment_release_path_component_count"] == 2
