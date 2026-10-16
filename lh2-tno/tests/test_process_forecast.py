from datetime import datetime, timedelta

import pytest

from lh2_tno.hazop import HAZOP_SCHEMA, HAZOP_STATE_SCHEMA
from lh2_tno.hazop_forecast import run_hazop_forecast_risk_scan
from lh2_tno.process_forecast import ProcessForecastError, build_forecast_frames


def _mapping():
    return {
        "PT-01": {
            "source_column": "pressure_mpa",
            "quantity": "pressure",
            "unit": "MPa",
            "sensor_location": "tank-vapour",
        },
        "TT-01": {
            "source_column": "temperature_c",
            "quantity": "temperature",
            "unit": "C",
            "sensor_location": "tank-vapour",
        },
    }


def test_process_forecast_preserves_input_mode_and_converts_si():
    result = build_forecast_frames(
        [
            {"time": datetime(2026, 1, 1, 0, 0, 0), "pressure_mpa": 0.60, "temperature_c": -253.0},
            {"time": datetime(2026, 1, 1, 0, 0, 1), "pressure_mpa": 0.61, "temperature_c": -252.5},
        ],
        facility_id="facility-01",
        component_id="TK-01",
        operating_mode="receiving",
        mapping=_mapping(),
        source_id="forecast://center/receiving",
        source_provenance="test workbook",
        time_column="time",
    )

    assert result["schema_version"] == "prism.process_forecast_frame_set.v1"
    assert result["policy"]["operating_mode_taken_from_input"] is True
    assert result["policy"]["frequency_inference_performed"] is False
    assert len(result["frames"]) == 2
    assert result["frames"][0]["schema_version"] == HAZOP_STATE_SCHEMA
    assert result["frames"][0]["origin"] == "model_prediction"
    assert result["frames"][1]["forecast_time_s"] == pytest.approx(1.0)
    assert result["frames"][0]["values"]["PT-01"]["value_si"] == pytest.approx(600000.0)
    assert result["frames"][0]["values"]["TT-01"]["value_si"] == pytest.approx(20.15)


def test_process_forecast_uses_explicit_sample_period_when_no_time_column():
    result = build_forecast_frames(
        [{"pressure": 1.0}, {"pressure": 2.0}],
        facility_id="facility-01",
        component_id="TK-01",
        operating_mode="standby",
        mapping={"PT-01": {"source_column": "pressure", "quantity": "pressure", "unit": "bar"}},
        source_id="forecast://test",
        source_provenance="test rows",
        sample_period_s=2.5,
    )
    assert [frame["forecast_time_s"] for frame in result["frames"]] == [0.0, 2.5]
    assert all(frame["operating_mode"] == "standby" for frame in result["frames"])


def test_process_forecast_rejects_missing_or_unsupported_mapping():
    with pytest.raises(ProcessForecastError, match="source column"):
        build_forecast_frames(
            [{"pressure": 1.0}],
            facility_id="facility",
            component_id="component",
            operating_mode="receiving",
            mapping={"PT": {"source_column": "missing", "quantity": "pressure", "unit": "bar"}},
            source_id="source",
            source_provenance="rows",
        )
    with pytest.raises(ProcessForecastError, match="unsupported unit"):
        build_forecast_frames(
            [{"pressure": 1.0}],
            facility_id="facility",
            component_id="component",
            operating_mode="receiving",
            mapping={"PT": {"source_column": "pressure", "quantity": "pressure", "unit": "psi"}},
            source_id="source",
            source_provenance="rows",
        )


def test_process_forecast_rejects_non_monotonic_time():
    with pytest.raises(ProcessForecastError, match="strictly increasing"):
        build_forecast_frames(
            [{"time": 0.0, "pressure": 1.0}, {"time": 0.0, "pressure": 1.1}],
            facility_id="facility",
            component_id="component",
            operating_mode="receiving",
            mapping={"PT": {"source_column": "pressure", "quantity": "pressure", "unit": "bar"}},
            source_id="source",
            source_provenance="rows",
            time_column="time",
        )


def test_process_forecast_frames_enter_the_existing_hazop_forecast_scanner():
    record = build_forecast_frames(
        [{"pressure": 0.50}, {"pressure": 0.65}],
        facility_id="facility",
        component_id="TK-01",
        operating_mode="receiving",
        mapping={"PT-01": {"source_column": "pressure", "quantity": "pressure", "unit": "MPa"}},
        source_id="forecast://test",
        source_provenance="test rows",
    )
    table = {
        "schema_version": HAZOP_SCHEMA,
        "id": "table",
        "facility_id": "facility",
        "operating_modes": ["receiving"],
        "configuration_origin": "synthetic",
        "source_provenance": "test table",
        "rows": [{
            "id": "TK01-high-pressure",
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
            "cause_summary": "forecast excursion",
            "consequence_summary": "provider release required",
            "provenance": "test table",
        }],
    }
    result = run_hazop_forecast_risk_scan(
        facility_id="facility",
        tables_by_component={"TK-01": table},
        forecast_frames=record["frames"],
        expected_component_ids=("TK-01",),
    )
    assert result["forecast_origin"] == "model_prediction"
    assert result["trigger_count"] == 1
    assert result["steps"][1]["components"][0]["scenarios"][0]["quantitative_evaluation"]["status"] == (
        "WITHHELD_NO_QUANTITATIVE_EVALUATOR"
    )
