from __future__ import annotations

import pytest

import lh2_tno.integrated_risk as integrated_risk
from lh2_tno.integrated_risk import (
    IntegratedRiskError,
    build_hazop_facility_campaign_evaluator,
    run_hazop_integrated_risk,
)
from lh2_tno.observed_state_runtime import build_observed_state_runtime_frames


def _table():
    return {"facility_id": "facility-01"}


def _current_result():
    return {
        "status": "FACILITY_HAZOP_RUNTIME_EVALUATED",
        "components": {
            "TK-01": {
                "selection": {"operating_mode": "receiving"},
                "branches": [{"scenario_id": "TK-01-pressure"}],
            }
        },
    }


def _forecast_result():
    return {
        "status": "FORECAST_RISK_SCAN_COMPLETE",
        "scenario_entries": [
            {
                "component_id": "TK-01",
                "scenario_id": "TK-01-pressure",
                "operating_mode": "receiving",
            }
        ],
        "trigger_count": 1,
        "evaluated_count": 0,
        "withheld_count": 1,
        "policy": {"diagnostic_only": True, "facility_qra_promotion": False},
    }


def test_integrated_risk_joins_current_and_forecast_identity(monkeypatch):
    calls = {}

    def current(table, frames, **kwargs):
        calls["current"] = (table, frames, kwargs)
        return _current_result()

    def forecast(**kwargs):
        calls["forecast"] = kwargs
        return _forecast_result()

    monkeypatch.setattr(integrated_risk, "run_hazop_facility_runtime", current)
    monkeypatch.setattr(integrated_risk, "run_hazop_forecast_risk_scan", forecast)
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
    )

    assert result["status"] == "INTEGRATED_DIAGNOSTIC_PARTIAL"
    assert result["linkage"]["current_operating_modes"] == {"TK-01": "receiving"}
    assert result["linkage"]["forecast_operating_modes"] == {"TK-01": ["receiving"]}
    assert result["linkage"]["shared_scenario_ids"] == ["TK-01-pressure"]
    assert result["linkage"]["shared_component_scenario_keys"] == [
        {"component_id": "TK-01", "scenario_id": "TK-01-pressure"}
    ]
    assert result["policy"]["facility_qra_promotion"] is False
    assert result["policy"]["frequency_inference_performed"] is False
    assert calls["current"][2]["now_s"] == 10.0
    assert calls["forecast"]["expected_component_ids"] == ("TK-01",)


def test_integrated_risk_requires_explicit_forecast_tables(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    with pytest.raises(IntegratedRiskError, match="forecast_tables_by_component"):
        run_hazop_integrated_risk(
            _table(),
            {"TK-01": {"operating_mode": "receiving"}},
            now_s=10.0,
            component_bindings={"TK-01": object()},
            release_resolvers={},
            forecast_frames=[{"component_id": "TK-01"}],
        )


def test_integrated_risk_can_be_current_only(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_COMPLETE"
    assert result["forecast"]["status"] == "FORECAST_NOT_REQUESTED"


def test_integrated_risk_runs_from_observed_custom_tag_to_forecast_path():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    table = json.loads(
        (root / "examples" / "generic_hazop_operating_modes.json").read_text(
            encoding="utf-8"
        )
    )
    tables = json.loads(
        (root / "examples" / "generic_hazop_tables_by_component.json").read_text(
            encoding="utf-8"
        )
    )
    source = {
        "source_id": "synthetic-integrated-tank-01",
        "source_path": "synthetic://prism/integrated",
        "source_sha256": "b" * 64,
        "format": "json",
        "component_id": "storage-tank-01",
        "origin": "synthetic",
        "samples": [{
            "captured_at_s": 12.0,
            "operating_mode": "receiving",
            "values": {
                "tank_pressure": {
                    "quantity": "pressure",
                    "value_si": 500000.0,
                    "sensor_location": "storage-tank-01.vapour",
                }
            },
        }],
    }
    current_frame = build_observed_state_runtime_frames([source])["frames"][0]
    forecast_frame = {
        "schema_version": "prism.hazop_state_frame.v1",
        "facility_id": "generic-outdoor-lh2",
        "component_id": "storage-tank-01",
        "captured_at_s": 0.0,
        "forecast_time_s": 0.0,
        "origin": "model_prediction",
        "operating_mode": "receiving",
        "source_provenance": "synthetic integrated forecast frame",
        "values": {
            "tank_pressure": {
                "quantity": "pressure",
                "value_si": 500000.0,
                "sensor_location": "storage-tank-01.vapour",
                "quality": "valid",
            }
        },
    }
    result = run_hazop_integrated_risk(
        table,
        {"storage-tank-01": current_frame},
        now_s=12.0,
        component_bindings={"storage-tank-01": object()},
        release_resolvers={},
        forecast_frames=[forecast_frame],
        forecast_tables_by_component=tables,
        forecast_component_ids=("storage-tank-01",),
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_COMPLETE"
    assert result["current"]["status"] == "FACILITY_HAZOP_RUNTIME_EVALUATED"
    assert result["current"]["components"]["storage-tank-01"]["selection"]["operating_mode"] == "receiving"
    assert result["forecast"]["trigger_count"] == 0
    assert result["forecast"]["withheld_count"] == 0
    assert result["policy"]["facility_qra_promotion"] is False


def test_integrated_risk_can_attach_operator_limited_facility_campaign(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    campaign = {
        "schema_version": "prism.hazop_facility_campaign_handoff.v1",
        "status": "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "facility_ledger": {"status": "CONDITIONAL_DIAGNOSTIC"},
        "policy": {
            "facility_qra_promotion": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
        },
    }
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        facility_campaign_evaluator=lambda current: campaign,
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_COMPLETE"
    assert result["facility_campaign"]["status"] == "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert result["facility_campaign"]["policy"]["facility_qra_promotion"] is False


def test_integrated_risk_withholds_unsafe_facility_campaign_claim(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        facility_campaign_evaluator=lambda current: {
            "status": "READY_FOR_IJHE_SCOPE",
            "complete_facility_qra_claim": True,
            "policy": {"facility_qra_promotion": True},
        },
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_PARTIAL"
    assert result["facility_campaign"]["status"] == "WITHHELD_UNSAFE_FACILITY_CAMPAIGN_RESULT"
    assert result["facility_campaign"]["policy"]["facility_qra_promotion"] is False


def test_campaign_evaluator_factory_binds_existing_hazop_campaign(monkeypatch):
    captured = {}

    def campaign(current, **kwargs):
        captured["current"] = current
        captured.update(kwargs)
        return {"status": "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"}

    monkeypatch.setattr(integrated_risk, "build_hazop_facility_campaign_result", campaign)
    evaluator = build_hazop_facility_campaign_evaluator(
        annual_conditions=[{"id": "weather-d", "annual_probability": 1.0}],
        scenario_bindings=[{"component_id": "TK-01", "hazop_scenario_id": "s-01"}],
        expected_component_ids=("TK-01",),
    )
    result = evaluator({"facility_id": "facility-01"})
    assert result["status"] == "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert captured["annual_conditions"][0]["id"] == "weather-d"
    assert captured["scenario_bindings"][0]["hazop_scenario_id"] == "s-01"
    assert captured["expected_component_ids"] == ("TK-01",)
