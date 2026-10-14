from __future__ import annotations

import pytest

import lh2_tno.integrated_risk as integrated_risk
from lh2_tno.integrated_risk import IntegratedRiskError, run_hazop_integrated_risk


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
