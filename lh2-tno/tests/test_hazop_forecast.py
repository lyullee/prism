import pytest

from lh2_tno.hazop import HAZOP_SCHEMA, HAZOP_STATE_SCHEMA
from lh2_tno.hazop_forecast import HazopForecastError, run_hazop_forecast_risk_scan


def _table():
    return {
        "schema_version": HAZOP_SCHEMA,
        "id": "forecast-hazop-v1",
        "facility_id": "forecast-facility",
        "operating_modes": ["receiving", "standby"],
        "configuration_origin": "synthetic",
        "source_provenance": "forecast test table",
        "rows": [
            {
                "id": "TK01-pressure-receiving",
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
                "cause_summary": "forecast pressure rises",
                "consequence_summary": "provider release required",
                "provenance": "forecast test row",
            }
        ],
    }


def _frame(time_s, pressure, *, mode="receiving"):
    return {
        "schema_version": HAZOP_STATE_SCHEMA,
        "facility_id": "forecast-facility",
        "component_id": "TK-01",
        "operating_mode": mode,
        "captured_at_s": time_s,
        "forecast_time_s": time_s,
        "origin": "model_prediction",
        "source_provenance": "simulation://forecast/TK-01",
        "values": {
            "PT-01": {
                "component_id": "TK-01",
                "quantity": "pressure",
                "value_si": pressure,
                "quality": "valid",
                "sensor_location": "tank-vapour",
            }
        },
    }


def test_forecast_scan_triggers_quantitative_evaluation_on_first_risk_entry():
    calls = []

    def evaluate(component_id, scenario, frame, context):
        calls.append((component_id, scenario["scenario_id"], frame["forecast_time_s"], context["trigger"]["trigger_type"]))
        return {
            "status": "CONSEQUENCE_EVALUATED",
            "risk": {"conditional_ir_low_high": {"worker-01": [1e-5, 2e-5]}},
            "policy": {
                "frequency_inference_performed": False,
                "facility_qra_promotion": False,
            },
        }

    result = run_hazop_forecast_risk_scan(
        facility_id="forecast-facility",
        tables_by_component={"TK-01": _table()},
        forecast_frames=[
            _frame(0.0, 500000.0),
            _frame(10.0, 650000.0),
            _frame(20.0, 700000.0),
            _frame(30.0, 500000.0),
        ],
        expected_component_ids=("TK-01",),
        quantitative_evaluator=evaluate,
    )

    assert result["schema_version"] == "prism.hazop_forecast_risk_scan.v1"
    assert result["trigger_count"] == 1
    assert result["evaluated_count"] == 1
    assert result["withheld_count"] == 0
    assert calls == [("TK-01", "TK01-pressure-receiving:receiving:vessel_hole", 10.0, "RISK_CONDITION_REACHED")]
    assert any(row["trigger_type"] == "RISK_CONDITION_CLEARED" for row in result["scenario_entries"])
    assert result["policy"]["frequency_inference_performed"] is False


def test_forecast_scan_withholds_trigger_when_evaluator_is_missing():
    result = run_hazop_forecast_risk_scan(
        facility_id="forecast-facility",
        tables_by_component={"TK-01": _table()},
        forecast_frames=[_frame(0.0, 650000.0)],
        expected_component_ids=("TK-01",),
    )

    evaluation = result["steps"][0]["components"][0]["scenarios"][0]["quantitative_evaluation"]
    assert evaluation["status"] == "WITHHELD_NO_QUANTITATIVE_EVALUATOR"
    assert result["evaluated_count"] == 0
    assert result["withheld_count"] == 1


def test_forecast_scan_rejects_non_prediction_origin_and_partial_time():
    bad = _frame(0.0, 650000.0)
    bad["origin"] = "historian_measured"
    with pytest.raises(HazopForecastError, match="model_prediction"):
        run_hazop_forecast_risk_scan(
            facility_id="forecast-facility",
            tables_by_component={"TK-01": _table()},
            forecast_frames=[bad],
            expected_component_ids=("TK-01",),
        )

    with pytest.raises(HazopForecastError, match="every expected component"):
        run_hazop_forecast_risk_scan(
            facility_id="forecast-facility",
            tables_by_component={"TK-01": _table(), "TK-02": _table()},
            forecast_frames=[_frame(0.0, 650000.0)],
            expected_component_ids=("TK-01", "TK-02"),
        )


def test_forecast_scan_rejects_unsafe_evaluator_claim():
    result = run_hazop_forecast_risk_scan(
        facility_id="forecast-facility",
        tables_by_component={"TK-01": _table()},
        forecast_frames=[_frame(0.0, 650000.0)],
        expected_component_ids=("TK-01",),
        quantitative_evaluator=lambda *_: {
            "risk": {},
            "policy": {"frequency_inference_performed": True},
        },
    )
    evaluation = result["steps"][0]["components"][0]["scenarios"][0]["quantitative_evaluation"]
    assert evaluation["status"] == "WITHHELD_UNSAFE_EVALUATOR_RESULT"
    assert result["evaluated_count"] == 0
