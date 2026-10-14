import pytest

from lh2_tno.hazop import (
    HAZOP_SCHEMA,
    HAZOP_STATE_SCHEMA,
    HazopSelectionError,
    HazopStateFrame,
    HazopTable,
    evaluate_hazop,
    evaluate_hazop_runtime_frame,
    hazop_state_from_runtime_frame,
)
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames


def table_payload():
    return {
        "schema_version": HAZOP_SCHEMA,
        "id": "generic-intake-hazop-v1",
        "facility_id": "generic-outdoor-lh2",
        "operating_modes": ["receiving", "supply", "standby"],
        "configuration_origin": "synthetic",
        "source_provenance": "generic test HAZOP table; replace with reviewed P&ID HAZOP",
        "rows": [
            {
                "id": "TK01-high-pressure-receiving",
                "component_id": "TK-01",
                "component_kind": "storage_tank",
                "operating_modes": ["receiving"],
                "variable_tag": "PT-01",
                "quantity": "pressure",
                "trigger": "at_or_above",
                "threshold_high_si": 600000.0,
                "scenario_family": "vessel_hole",
                "release_mode": "hole",
                "priority": "high",
                "deviation_label": "high pressure",
                "cause_summary": "receiving pressure rises above design criterion",
                "consequence_summary": "tank wall release scenario requires provider packet",
                "safeguards": ["PSV-01", "ESD-01"],
                "provenance": "synthetic HAZOP row",
            },
            {
                "id": "TK01-low-temperature-supply",
                "component_id": "TK-01",
                "component_kind": "storage_tank",
                "operating_modes": ["supply"],
                "variable_tag": "TT-01",
                "quantity": "temperature",
                "trigger": "below",
                "threshold_low_si": 18.0,
                "scenario_family": "liquid_two_phase",
                "release_mode": "hole",
                "priority": "medium",
                "deviation_label": "low temperature",
                "cause_summary": "supply temperature falls",
                "consequence_summary": "two phase release candidate",
                "provenance": "synthetic HAZOP row",
            },
        ],
    }


def state(mode="receiving", pressure=650000.0, temperature=20.0):
    return {
        "schema_version": HAZOP_STATE_SCHEMA,
        "facility_id": "generic-outdoor-lh2",
        "component_id": "TK-01",
        "operating_mode": mode,
        "captured_at_s": 10.0,
        "source_provenance": "historian://intake/TK-01",
        "values": {
            "PT-01": {
                "quantity": "pressure", "value_si": pressure,
                "quality": "valid", "sensor_location": "tank-vapour",
            },
            "TT-01": {
                "quantity": "temperature", "value_si": temperature,
                "quality": "valid", "sensor_location": "tank-vapour",
            },
        },
    }


def test_mode_and_field_value_select_scenario_without_creating_release_or_frequency():
    result = evaluate_hazop(table_payload(), state())
    assert result["status"] == "SCENARIOS_SELECTED"
    assert result["operating_mode"] == "receiving"
    assert result["selected_scenario_count"] == 1
    selected = result["selected_scenarios"][0]
    assert selected["scenario_family"] == "vessel_hole"
    assert selected["provider_release_required"] is True
    assert selected["provider_release_status"] == "REQUIRED_NOT_CREATED"
    assert result["policy"]["frequency_inference_performed"] is False
    assert result["policy"]["release_packet_created"] is False


def test_nonmatching_operating_mode_does_not_reuse_receiving_row():
    result = evaluate_hazop(table_payload(), state(mode="standby"))
    assert result["status"] == "NO_APPLICABLE_MODE_ROW"
    assert result["selected_scenarios"] == []


def test_normal_value_produces_no_deviation():
    result = evaluate_hazop(table_payload(), state(pressure=500000.0))
    assert result["status"] == "NO_DEVIATION"
    assert result["active_deviation_count"] == 0


def test_missing_signal_is_open_and_not_treated_as_safe():
    payload = state()
    payload["values"].pop("PT-01")
    result = evaluate_hazop(table_payload(), payload)
    assert result["status"] == "BLOCKED_OPEN_INPUTS"
    assert result["selected_scenarios"] == []
    assert result["checks"][0]["status"] == "MISSING_SIGNAL"


def test_wrong_quantity_is_open():
    payload = state()
    payload["values"]["PT-01"]["quantity"] = "temperature"
    result = evaluate_hazop(table_payload(), payload)
    assert result["status"] == "BLOCKED_OPEN_INPUTS"
    assert "quantity mismatch" in result["blocking_reasons"][0]


def test_table_rejects_family_release_mode_mismatch():
    payload = table_payload()
    payload["rows"][0]["release_mode"] = "maximum_relief_discharge"
    with pytest.raises(Exception, match="does not support"):
        evaluate_hazop(payload, state())


def test_state_facility_mismatch_fails_closed():
    payload = state()
    payload["facility_id"] = "other-facility"
    with pytest.raises(HazopSelectionError, match="facility_id"):
        evaluate_hazop(table_payload(), payload)


def test_outside_range_uses_both_bounds():
    payload = table_payload()
    payload["rows"][0].update({
        "trigger": "outside_range", "threshold_low_si": 400000.0,
        "threshold_high_si": 600000.0,
    })
    assert evaluate_hazop(payload, state(pressure=450000.0))["status"] == "NO_DEVIATION"
    assert evaluate_hazop(payload, state(pressure=650000.0))["selected_scenario_count"] == 1


def test_state_frame_rejects_missing_mode_and_bad_digest():
    payload = state()
    payload.pop("operating_mode")
    with pytest.raises(Exception):
        HazopStateFrame.model_validate(payload)


def test_verified_runtime_frame_carries_mode_into_hazop_selection():
    source = {
        "source_id": "historian-tank-01",
        "source_sha256": "a" * 64,
        "component_id": "TK-01",
        "origin": "historian_measured",
        "operating_mode": "receiving",
        "samples": [{
            "captured_at_s": 3.0,
            "values": {"pressure": {"value_si": 650000.0, "sensor_location": "vapour"}},
        }],
    }
    frame = build_observed_state_runtime_frames([source])["frames"][0]
    table = table_payload()
    table["rows"][0]["component_id"] = "TK-01"
    table["rows"][0]["variable_tag"] = "pressure"
    result = evaluate_hazop_runtime_frame(table, frame, now_s=3.2)
    assert result["status"] == "SCENARIOS_SELECTED"
    assert result["operating_mode"] == "receiving"
    assert result["state_digest"] == hazop_state_from_runtime_frame(
        frame, facility_id="generic-outdoor-lh2", now_s=3.2
    ).digest()


def test_runtime_frame_without_mode_is_withheld_from_hazop():
    source = {
        "source_id": "historian-tank-01",
        "source_sha256": "a" * 64,
        "component_id": "TK-01",
        "origin": "historian_measured",
        "samples": [{"captured_at_s": 3.0, "values": {"pressure": 650000.0}}],
    }
    frame = build_observed_state_runtime_frames([source])["frames"][0]
    with pytest.raises(HazopSelectionError, match="operating_mode"):
        evaluate_hazop_runtime_frame(table_payload(), frame, now_s=3.2)
    payload = state()
    payload["state_snapshot_digest"] = "z" * 64
    with pytest.raises(Exception):
        HazopStateFrame.model_validate(payload)
