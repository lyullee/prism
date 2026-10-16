from types import SimpleNamespace
from copy import deepcopy

import pytest

from lh2_tno.hazop import HAZOP_SCHEMA, HAZOP_STATE_SCHEMA
from lh2_tno.hazop_forecast import (
    HazopForecastError,
    build_hazop_forecast_runtime_evaluator,
    run_hazop_forecast_risk_scan,
)


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


def _component_table(component_id):
    table = deepcopy(_table())
    table["rows"][0]["component_id"] = component_id
    return table


def _component_frame(component_id, time_s, pressure, *, mode="receiving"):
    frame = deepcopy(_frame(time_s, pressure, mode=mode))
    frame["component_id"] = component_id
    frame["source_provenance"] = f"simulation://forecast/{component_id}"
    for value in frame["values"].values():
        value["component_id"] = component_id
    return frame


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
    trigger = next(row for row in result["scenario_entries"] if row["trigger_type"] == "RISK_CONDITION_REACHED")
    assert trigger["operating_mode"] == "receiving"
    cleared = next(row for row in result["scenario_entries"] if row["trigger_type"] == "RISK_CONDITION_CLEARED")
    assert cleared["operating_mode"] == "receiving"
    assert result["steps"][1]["components"][0]["scenarios"][0]["operating_mode"] == "receiving"
    assert result["policy"]["frequency_inference_performed"] is False
    assert result["policy"]["conditional_expected_death_fn_calculated"] is False
    assert result["conditional_current_weather_expected_death_fn"]["status"] == (
        "WITHHELD_FORECAST_FACILITY_AGGREGATOR_REQUIRED"
    )
    assert result["facility_annual_ir_available"] is False
    assert result["facility_fn_available"] is False
    assert result["timing"]["wall_elapsed_ms"] >= 0.0
    assert result["timing"]["quantitative_evaluation_elapsed_ms"] >= 0.0
    assert result["timing"]["fresh_physics_claim"] is False


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


def test_forecast_runtime_evaluator_reuses_existing_provider_gate():
    class Monitor:
        def update_from_runtime_frame(self, template, frame, *, now_s, release_resolver, mapping_digest=None):
            request = release_resolver(template, {"operating_mode": frame["operating_mode"]})
            return {"request": request, "now_s": now_s, "mapping_digest": mapping_digest}

    provider_request = SimpleNamespace(
        component_id="TK-01",
        resolved_release=None,
        resolved_release_set=None,
        resolved_liquid_release=SimpleNamespace(event_kind="accidental_leak"),
        source_operator="equipment_liquid_release",
        release_termination=SimpleNamespace(basis="model_pressure_equalization"),
    )
    evaluator = build_hazop_forecast_runtime_evaluator(
        tables_by_component={"TK-01": _table()},
        component_bindings={"TK-01": {"template": object(), "monitor": Monitor()}},
        release_resolvers={
            ("TK-01", "TK01-pressure-receiving:receiving:vessel_hole"): lambda template, normalized: provider_request
        },
    )
    result = run_hazop_forecast_risk_scan(
        facility_id="forecast-facility",
        tables_by_component={"TK-01": _table()},
        forecast_frames=[_frame(0.0, 650000.0)],
        expected_component_ids=("TK-01",),
        quantitative_evaluator=evaluator,
    )
    evaluation = result["steps"][0]["components"][0]["scenarios"][0]["quantitative_evaluation"]
    assert evaluation["status"] == "EVALUATED_OPERATOR_LIMITED"
    assert evaluation["result"]["status"] == "CONSEQUENCE_EVALUATED"
    assert evaluation["result"]["forecast_resolver_binding"]["key_type"] == "component_scenario"


def test_forecast_runtime_evaluator_reaches_real_slabx_monitor(tmp_path):
    from lh2_tno.provider_release import build_consequence_request_from_provider_release
    from lh2_tno.service import ConsequenceService, RealtimeConsequenceMonitor
    from test_consequence_service import Pipeline, request
    from test_provider_release import _defaults, _liquid_release

    release = _liquid_release().model_copy(update={"component_id": "TK-01"})
    defaults = _defaults()
    defaults.update(
        {
            "component_id": "TK-01",
            "source_operator": "equipment_liquid_release",
            "release_termination": {
                "basis": "model_pressure_equalization",
                "time_s": 0.2,
                "provenance": "forecast runtime integration test",
            },
            "source_duration_mode": "model_natural",
        }
    )
    provider_request = build_consequence_request_from_provider_release(release, defaults)
    evaluator = build_hazop_forecast_runtime_evaluator(
        tables_by_component={"TK-01": _table()},
        component_bindings={
            "TK-01": {
                "template": request().model_copy(update={"component_id": "TK-01"}),
                "monitor": RealtimeConsequenceMonitor(ConsequenceService(Pipeline(tmp_path))),
            }
        },
        release_resolvers={
            "TK01-pressure-receiving:receiving:vessel_hole": lambda template, normalized: provider_request
        },
    )
    result = run_hazop_forecast_risk_scan(
        facility_id="forecast-facility",
        tables_by_component={"TK-01": _table()},
        forecast_frames=[_frame(10.0, 650000.0)],
        expected_component_ids=("TK-01",),
        quantitative_evaluator=evaluator,
    )
    evaluation = result["steps"][0]["components"][0]["scenarios"][0]["quantitative_evaluation"]
    assert evaluation["status"] == "EVALUATED_OPERATOR_LIMITED"
    assert evaluation["result"]["status"] == "CONSEQUENCE_EVALUATED"
    assert evaluation["result"]["consequence"]["equipment_release_path"]["status"] == "AVAILABLE_PROVIDER_RELEASE_PATH"
    assert result["timing"]["quantitative_evaluation_elapsed_ms"] >= 0.0


def test_forecast_runtime_evaluator_keeps_duplicate_hazop_ids_per_component():
    class Monitor:
        def update_from_runtime_frame(self, template, frame, *, now_s, release_resolver, mapping_digest=None):
            request = release_resolver(template, {"operating_mode": frame["operating_mode"]})
            return {
                "status": "CONSEQUENCE_EVALUATED",
                "component_id": request.component_id,
                "now_s": now_s,
                "mapping_digest": mapping_digest,
            }

    scenario_id = "TK01-pressure-receiving:receiving:vessel_hole"
    requests = {
        component_id: SimpleNamespace(
            component_id=component_id,
            resolved_release=None,
            resolved_release_set=None,
            resolved_liquid_release=SimpleNamespace(event_kind="accidental_leak"),
            source_operator="equipment_liquid_release",
            release_termination=SimpleNamespace(basis="model_pressure_equalization"),
        )
        for component_id in ("TK-01", "TK-02")
    }
    evaluator = build_hazop_forecast_runtime_evaluator(
        tables_by_component={
            "TK-01": _component_table("TK-01"),
            "TK-02": _component_table("TK-02"),
        },
        component_bindings={
            "TK-01": {"template": object(), "monitor": Monitor()},
            "TK-02": {"template": object(), "monitor": Monitor()},
        },
        release_resolvers={
            ("TK-01", scenario_id): lambda template, normalized: requests["TK-01"],
            ("TK-02", scenario_id): lambda template, normalized: requests["TK-02"],
        },
    )
    result = run_hazop_forecast_risk_scan(
        facility_id="forecast-facility",
        tables_by_component={
            "TK-01": _component_table("TK-01"),
            "TK-02": _component_table("TK-02"),
        },
        forecast_frames=[
            _component_frame("TK-01", 0.0, 650000.0),
            _component_frame("TK-02", 0.0, 650000.0),
        ],
        expected_component_ids=("TK-01", "TK-02"),
        quantitative_evaluator=evaluator,
    )
    rows = result["steps"][0]["components"]
    evaluations = [row["scenarios"][0]["quantitative_evaluation"] for row in rows]
    assert evaluations[0]["result"]["consequence"]["component_id"] == "TK-01"
    assert evaluations[1]["result"]["consequence"]["component_id"] == "TK-02"
    assert {evaluation["result"]["forecast_resolver_binding"]["component_id"] for evaluation in evaluations} == {
        "TK-01",
        "TK-02",
    }
