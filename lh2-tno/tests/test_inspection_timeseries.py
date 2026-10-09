import pytest

from lh2_tno.inspection_timeseries import (
    classify_signal,
    frame_from_row,
    normalise_unit_map,
    resolve_unit,
    state_snapshot_from_row,
    summarise_numeric,
)
from lh2_tno.telemetry import TagMapping, TelemetryNormalizer


def test_signal_classification_does_not_infer_units_from_tag_name():
    assert classify_signal("PT1105A") == {"category": "pressure", "basis": "tag_prefix"}
    assert classify_signal("DPT1101")["category"] == "differential_pressure"
    assert classify_signal("TT1106")["category"] == "temperature"


def test_unit_map_requires_exact_reviewed_mapping():
    unit_map = normalise_unit_map({"signal_units": {"PT1105A": "bar"}})
    assert resolve_unit("PT1105A", unit_map) == ("bar", "CONFIRMED_BY_REVIEWED_MAP")
    assert resolve_unit("PT1105B", unit_map) == (None, "MISSING_OR_UNCONFIRMED")


def test_numeric_summary_keeps_only_aggregate_values():
    assert summarise_numeric([1, 2.5, None, "3", True]) == {"numeric_count": 2, "min": 1.0, "max": 2.5}


def test_frame_from_row_requires_explicit_tag_unit_and_quality():
    frame = frame_from_row(
        {"PT1105A": 6.5, "TT1106": 20.8},
        stream_id="tank-01-historian",
        sequence=4,
        source_time_s=12.0,
        arrival_time_s=12.2,
        origin="historian_measured",
        bindings={
            "PT1105A": {"tag": "P", "unit": "bar", "quality": "valid"},
            "TT1106": {"tag": "T", "unit": "K", "quality": "valid"},
        },
    )
    assert frame.values["P"].value == pytest.approx(6.5)
    assert frame.values["P"].unit == "bar"
    assert frame.values["T"].quality == "valid"

    with pytest.raises(ValueError, match="explicit unit"):
        frame_from_row(
            {"PT1105A": 6.5},
            stream_id="tank-01-historian",
            sequence=5,
            source_time_s=13.0,
            arrival_time_s=13.2,
            origin="historian_measured",
            bindings={"PT1105A": {"tag": "P", "quality": "valid"}},
        )


def test_state_snapshot_from_row_uses_normalizer_and_remains_state_only():
    normalizer = TelemetryNormalizer(
        (
            TagMapping(
                tag="P",
                component_id="tank-01",
                quantity="pressure",
                source_unit="bar",
                pressure_basis="absolute",
                sensor_location="tank-01.shell",
            ),
            TagMapping(
                tag="T",
                component_id="tank-01",
                quantity="temperature",
                source_unit="degC",
                sensor_location="tank-01.shell",
            ),
        ),
        maximum_age_s=2.0,
    )
    snapshot = state_snapshot_from_row(
        {"PT1105A": 2.1, "TT1106": 20.0},
        stream_id="tank-01-historian",
        sequence=1,
        source_time_s=10.0,
        arrival_time_s=10.1,
        origin="historian_measured",
        bindings={
            "PT1105A": {"tag": "P", "unit": "bar", "quality": "valid"},
            "TT1106": {"tag": "T", "unit": "degC", "quality": "valid"},
        },
        normalizer=normalizer,
        now_s=10.2,
        component_id="tank-01",
        position_enu_m=(1.0, 2.0, 3.0),
    )
    assert snapshot.pressure_pa_abs == pytest.approx(210000.0)
    assert snapshot.temperature_k == pytest.approx(293.15)
    assert snapshot.origin == "historian_measured"
    assert snapshot.position_enu_m == (1.0, 2.0, 3.0)
    assert "provider_release" not in snapshot.to_mapping()
