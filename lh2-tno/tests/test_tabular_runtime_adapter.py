from __future__ import annotations

import pytest

from lh2_tno.tabular_runtime_adapter import (
    TabularRuntimeAdapterError,
    build_runtime_frames_from_csv,
    load_csv_runtime_source,
)
from lh2_tno.telemetry import TagMapping, TelemetryNormalizer


def _normalizer() -> TelemetryNormalizer:
    return TelemetryNormalizer(
        (
            TagMapping(
                tag="pressure",
                component_id="TK-01",
                quantity="pressure",
                source_unit="bar",
                pressure_basis="absolute",
                sensor_location="TK-01.shell",
            ),
            TagMapping(
                tag="temperature",
                component_id="TK-01",
                quantity="temperature",
                source_unit="degC",
                sensor_location="TK-01.shell",
            ),
        ),
        maximum_age_s=10.0,
    )


def _write(path):
    path.write_text(
        "time_s,mode,PT1105A,TT1106\n"
        "0,receiving,6.2,-160\n"
        "1,receiving,6.5,-159.5\n",
        encoding="utf-8",
    )


def _bindings():
    return {
        "PT1105A": {"tag": "pressure", "unit": "bar", "quality": "valid"},
        "TT1106": {"tag": "temperature", "unit": "degC", "quality": "valid"},
    }


def test_csv_adapter_preserves_explicit_mode_and_si_conversion(tmp_path):
    path = tmp_path / "history.csv"
    _write(path)
    source = load_csv_runtime_source(
        path,
        source_id="historian-tk-01",
        component_id="TK-01",
        timestamp_column="time_s",
        operating_mode_column="mode",
        bindings=_bindings(),
        normalizer=_normalizer(),
    )
    assert source["schema_version"] == "prism.tabular_runtime_source.v1"
    assert source["policy"]["operating_mode_inferred"] is False
    assert source["samples"][1]["operating_mode"] == "receiving"
    frames = build_runtime_frames_from_csv(
        path,
        source_id="historian-tk-01",
        component_id="TK-01",
        timestamp_column="time_s",
        operating_mode_column="mode",
        bindings=_bindings(),
        normalizer=_normalizer(),
    )
    frame = frames["frames"][0]
    assert frame["captured_at_s"] == 1.0
    assert frame["operating_mode"] == "receiving"
    assert frame["values"]["pressure"]["value_si"] == pytest.approx(650000.0)
    assert frame["values"]["temperature"]["value_si"] == pytest.approx(113.65)


def test_csv_adapter_requires_explicit_mode(tmp_path):
    path = tmp_path / "history.csv"
    _write(path)
    with pytest.raises(TabularRuntimeAdapterError, match="operating_mode_column"):
        load_csv_runtime_source(
            path,
            source_id="historian-tk-01",
            component_id="TK-01",
            timestamp_column="time_s",
            bindings=_bindings(),
            normalizer=_normalizer(),
        )


def test_csv_adapter_rejects_nonmonotonic_time_and_unit_drift(tmp_path):
    path = tmp_path / "history.csv"
    _write(path)
    path.write_text(
        "time_s,mode,PT1105A,TT1106\n"
        "1,receiving,6.2,-160\n"
        "1,receiving,6.5,-159.5\n",
        encoding="utf-8",
    )
    with pytest.raises(TabularRuntimeAdapterError, match="strictly increasing"):
        load_csv_runtime_source(
            path,
            source_id="historian-tk-01",
            component_id="TK-01",
            timestamp_column="time_s",
            operating_mode_column="mode",
            bindings=_bindings(),
            normalizer=_normalizer(),
        )
    bad_bindings = {
        **_bindings(),
        "PT1105A": {"tag": "pressure", "unit": "kPa", "quality": "valid"},
    }
    with pytest.raises(TabularRuntimeAdapterError, match="disagrees"):
        load_csv_runtime_source(
            tmp_path / "history.csv",
            source_id="historian-tk-01",
            component_id="TK-01",
            timestamp_column="time_s",
            operating_mode_column="mode",
            bindings=bad_bindings,
            normalizer=_normalizer(),
        )


def test_csv_adapter_rejects_normalizer_component_drift(tmp_path):
    path = tmp_path / "history.csv"
    _write(path)
    with pytest.raises(TabularRuntimeAdapterError, match="maps to component"):
        load_csv_runtime_source(
            path,
            source_id="historian-tk-01",
            component_id="TK-02",
            timestamp_column="time_s",
            operating_mode_column="mode",
            bindings=_bindings(),
            normalizer=_normalizer(),
        )

