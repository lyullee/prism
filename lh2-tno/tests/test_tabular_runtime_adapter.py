from __future__ import annotations

import pytest

from lh2_tno.tabular_runtime_adapter import (
    TabularRuntimeAdapterError,
    build_runtime_frames_from_csv,
    build_runtime_frames_from_xlsx,
    load_csv_runtime_source,
    load_xlsx_runtime_source,
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


def test_xlsx_adapter_preserves_explicit_sheet_and_mode(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "history.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Receiving"
    worksheet.append(["time_s", "mode", "PT1105A", "TT1106"])
    worksheet.append([0, "receiving", 6.2, -160])
    worksheet.append([1, "receiving", 6.5, -159.5])
    workbook.save(path)
    workbook.close()

    source = load_xlsx_runtime_source(
        path,
        source_id="xlsx-tk-01",
        component_id="TK-01",
        timestamp_column="time_s",
        timestamp_base="2026-01-21T13:00:00",
        operating_mode_column="mode",
        sheet="Receiving",
        bindings=_bindings(),
        normalizer=_normalizer(),
    )
    assert source["format"] == "xlsx"
    assert source["tabular_binding"]["sheet"] == "Receiving"
    assert source["samples"][1]["operating_mode"] == "receiving"
    frames = build_runtime_frames_from_xlsx(
        path,
        source_id="xlsx-tk-01",
        component_id="TK-01",
        timestamp_column="time_s",
        timestamp_base="2026-01-21T13:00:00",
        operating_mode_column="mode",
        sheet="Receiving",
        bindings=_bindings(),
        normalizer=_normalizer(),
    )
    assert frames["frames"][0]["captured_at_s"] == 1.0
    assert frames["frames"][0]["values"]["pressure"]["value_si"] == pytest.approx(650000.0)


def test_xlsx_adapter_requires_base_for_datetime_timestamps(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from datetime import datetime

    path = tmp_path / "datetime.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["captured_at", "mode", "PT1105A", "TT1106"])
    worksheet.append([datetime(2026, 1, 21, 13, 0), "receiving", 6.2, -160])
    workbook.save(path)
    workbook.close()
    with pytest.raises(TabularRuntimeAdapterError, match="timestamp_base"):
        load_xlsx_runtime_source(
            path,
            source_id="xlsx-tk-01",
            component_id="TK-01",
            timestamp_column="captured_at",
            operating_mode_column="mode",
            bindings=_bindings(),
            normalizer=_normalizer(),
        )
    source = load_xlsx_runtime_source(
        path,
        source_id="xlsx-tk-01",
        component_id="TK-01",
        timestamp_column="captured_at",
        operating_mode_column="mode",
        timestamp_base="2026-01-21T13:00:00",
        bindings=_bindings(),
        normalizer=_normalizer(),
    )
    assert source["samples"][0]["captured_at_s"] == 0.0


def test_xlsx_adapter_rejects_duplicate_headers(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "bad.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["time_s", "PT1105A", "PT1105A"])
    worksheet.append([0, 6.2, 6.2])
    workbook.save(path)
    workbook.close()
    with pytest.raises(TabularRuntimeAdapterError, match="duplicate"):
        load_xlsx_runtime_source(
            path,
            source_id="xlsx-tk-01",
            component_id="TK-01",
            timestamp_column="time_s",
            operating_mode="receiving",
            bindings=_bindings(),
            normalizer=_normalizer(),
        )

