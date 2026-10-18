from __future__ import annotations

import pytest

import lh2_tno.integrated_risk as integrated_risk
from lh2_tno.integrated_risk import (
    IntegratedRiskError,
    build_hazop_forecast_facility_campaign_result,
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


def _forecast_campaign_scan():
    return {
        "schema_version": "prism.hazop_forecast_risk_scan.v1",
        "status": "FORECAST_RISK_SCAN_COMPLETE",
        "facility_id": "facility-1",
        "withheld_count": 0,
        "evaluated_count": 1,
        "scenario_entries": [{
            "component_id": "TK-01",
            "scenario_id": "TK-01-pressure",
            "operating_mode": "receiving",
            "forecast_time_s": 12.0,
            "trigger_type": "RISK_CONDITION_REACHED",
            "evaluation": {"status": "EVALUATED_OPERATOR_LIMITED"},
        }],
    }


def _forecast_campaign():
    return {
        "facility_id": "facility-1",
        "campaign_digest": "forecast-campaign-digest",
        "events": [{
            "id": "forecast-event-tank",
            "asset_id": "tank-asset",
            "model_component_id": "TK-01",
        }],
        "annual_conditions": [{"id": "weather-1", "annual_probability": 1.0}],
        "cases": [{"event_id": "forecast-event-tank", "status": "EXECUTED"}],
        "uncomputed_cases": [],
        "risk_atoms": [{
            "event_id": "forecast-event-tank",
            "asset_id": "tank-asset",
            "annual_condition_id": "weather-1",
            "release_branch_id": "release-1",
            "ignition_branch": "direct_fire",
            "initiating_frequency_per_year": 1.0e-4,
            "conditional_weight": 1.0,
            "receptor_harm_low_high": {"worker-01": [0.1, 0.2]},
            "expected_deaths_low_high": [0.1, 0.2],
        }],
        "declared_scope_numerically_complete": False,
        "synthetic_release_horizon_present": False,
        "excluded_model_components": {},
        "physical_validation_claim": False,
        "coverage": {"by_component": [{"component_id": "TK-01"}]},
        "timing": {"campaign_elapsed_ms": 4.0},
        "policy": {
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
        },
    }


def test_forecast_facility_campaign_binds_each_trigger_without_inference(monkeypatch):
    captured = {}

    def merge(campaigns, **kwargs):
        captured["campaigns"] = campaigns
        captured["kwargs"] = kwargs
        return {"status": "FACILITY_SCOPE_PARTIAL"}

    monkeypatch.setattr(integrated_risk, "merge_facility_campaign_results", merge)
    scan = _forecast_campaign_scan()
    key = "TK-01|TK-01-pressure|12"
    result = build_hazop_forecast_facility_campaign_result(
        scan,
        campaign_bindings={key: {
            "component_id": "TK-01",
            "scenario_id": "TK-01-pressure",
            "forecast_time_s": 12.0,
            "operating_mode": "receiving",
            "campaign": _forecast_campaign(),
        }},
        expected_component_ids=("TK-01",),
    )
    assert result["status"] == "FORECAST_FACILITY_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    assert result["policy"]["frequency_inference_performed"] is False
    assert result["trigger_bindings"][0]["forecast_time_s"] == 12.0
    assert captured["kwargs"]["expected_component_ids"] == ("TK-01",)
    assert captured["campaigns"][0]["campaign_id"] == "forecast:TK-01|TK-01-pressure|12"


def test_forecast_facility_campaign_preserves_provider_release_boundary_gate():
    campaign = _forecast_campaign()
    identity = {
        "event_id": "forecast-event-tank",
        "component_id": "TK-01",
        "provider_result_digests": ["c" * 64],
        "termination_bases": ["inventory_depletion"],
        "duration_s": [1.0],
        "available_mass_kg": [10.0],
        "cumulative_mass_out_kg": [9.0],
        "provider_mass_balances": [{
            "initial_mass_kg": 10.0,
            "final_mass_kg": 1.0,
            "cumulative_mass_out_kg": 9.0,
        }],
    }
    campaign["cases"][0].update({
        "termination": {
            "basis": "inventory_depletion",
            "time_s": 1.0,
            "provenance": "forecast provider inventory ledger",
        },
        "mass_ledger": {"released_kg": 9.0, "end_to_end_residual_kg": 0.0},
        "provider_packet_identity": identity,
    })
    campaign["risk_atoms"][0]["provider_packet_identity"] = identity

    result = build_hazop_forecast_facility_campaign_result(
        _forecast_campaign_scan(),
        campaign_bindings={
            "TK-01|TK-01-pressure|12": {
                "component_id": "TK-01",
                "scenario_id": "TK-01-pressure",
                "forecast_time_s": 12.0,
                "operating_mode": "receiving",
                "campaign": campaign,
            }
        },
        expected_component_ids=("TK-01",),
    )

    ledger = result["facility_ledger"]
    assert ledger["provider_release_boundary_case_count"] == 1
    assert ledger["provider_release_boundary_ready"] is False
    assert ledger["facility_total_risk_available"] is False
    assert ledger["conditional_diagnostic_facility_risk_available"] is True
    assert any(
        "provider-backed release boundary is not closed" in reason
        for reason in ledger["blocking_reasons"]
    )


def test_forecast_facility_campaign_rejects_missing_trigger_binding():
    with pytest.raises(IntegratedRiskError, match="cover exactly every quantitative trigger"):
        build_hazop_forecast_facility_campaign_result(
            _forecast_campaign_scan(),
            campaign_bindings={},
            expected_component_ids=("TK-01",),
        )


def test_integrated_risk_can_use_strict_forecast_campaign_bindings(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_forecast_risk_scan",
        lambda **kwargs: _forecast_campaign_scan(),
    )
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
        forecast_campaign_bindings={
            "TK-01|TK-01-pressure|12": {
                "component_id": "TK-01",
                "scenario_id": "TK-01-pressure",
                "forecast_time_s": 12.0,
                "operating_mode": "receiving",
                "campaign": _forecast_campaign(),
            }
        },
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_COMPLETE"
    assert result["forecast_facility_campaign"]["status"] == (
        "FORECAST_FACILITY_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    )
    assert result["forecast_facility_campaign"]["policy"]["facility_qra_promotion"] is False


def test_integrated_risk_withholds_forecast_campaign_when_evidence_gate_is_incomplete(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_forecast_risk_scan",
        lambda **kwargs: _forecast_campaign_scan(),
    )
    coverage = {
        "schema_version": "prism.forecast_quantitative_evidence_coverage.v1",
        "facility_id": "facility-1",
        "rows": [{
            "request_id": "TK-01|TK-01-pressure|12",
            "status": "MISSING_EVIDENCE",
            "missing_fields": ["provider_release_packet.source_digest"],
            "malformed_reason": "attachment_missing",
        }],
        "extra_attachment_keys": [],
    }
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
        forecast_campaign_bindings={
            "TK-01|TK-01-pressure|12": {
                "component_id": "TK-01",
                "scenario_id": "TK-01-pressure",
                "forecast_time_s": 12.0,
                "operating_mode": "receiving",
                "campaign": _forecast_campaign(),
            }
        },
        forecast_evidence_coverage=coverage,
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_PARTIAL"
    assert result["forecast_facility_campaign"]["status"] == (
        "WITHHELD_FORECAST_FACILITY_CAMPAIGN_EVIDENCE_COVERAGE"
    )
    assert result["forecast_facility_campaign"]["evidence_gate"][
        "downstream_campaign_input_allowed"
    ] is False


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
    assert calls["current"][2]["population_binding"] is None


def test_integrated_risk_forwards_explicit_population_binding(monkeypatch):
    calls = {}

    def current(table, frames, **kwargs):
        calls["current"] = kwargs
        return _current_result()

    monkeypatch.setattr(integrated_risk, "run_hazop_facility_runtime", current)
    population = object()
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        population_binding=population,
    )

    assert result["status"] == "INTEGRATED_DIAGNOSTIC_COMPLETE"
    assert calls["current"]["population_binding"] is population


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
    assert result["forecast"]["facility_fn_available"] is False


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


def test_integrated_risk_withholds_nested_unsafe_facility_ledger_claim(monkeypatch):
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
            "status": "FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
            "facility_ledger": {"qualified_facility_qra_available": True},
            "policy": {"facility_qra_promotion": False},
        },
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_PARTIAL"
    assert result["facility_campaign"]["status"] == (
        "WITHHELD_UNSAFE_FACILITY_CAMPAIGN_RESULT"
    )
    assert result["facility_campaign"]["policy"]["facility_qra_promotion"] is False


def test_integrated_risk_attaches_forecast_facility_campaign(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_forecast_risk_scan",
        lambda **kwargs: {
            **_forecast_result(),
            "withheld_count": 0,
            "evaluated_count": 1,
        },
    )
    seen = {}

    def evaluate(forecast):
        seen["status"] = forecast["status"]
        seen["entry_count"] = len(forecast["scenario_entries"])
        return {
            "status": "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
            "facility_ledger": {
                "status": "CONDITIONAL_DIAGNOSTIC",
                "provider_release_boundary_case_count": 1,
                "provider_release_boundary_ready": False,
                "conditional_diagnostic_facility_risk_available": True,
                "conditional_diagnostic_facility_expected_death_fn_low_high": [0.1, 0.2],
                "facility_total_risk_available": False,
                "qualified_facility_qra_available": False,
            },
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
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
        forecast_facility_campaign_evaluator=evaluate,
    )

    assert result["status"] == "INTEGRATED_DIAGNOSTIC_COMPLETE"
    assert seen == {"status": "FORECAST_RISK_SCAN_COMPLETE", "entry_count": 1}
    assert result["forecast_facility_campaign"]["status"] == (
        "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED"
    )
    assert result["forecast_facility_campaign"]["policy"]["facility_qra_promotion"] is False
    summary = result["facility_gate_summary"]["forecast"]
    assert summary["provider_release_boundary_case_count"] == 1
    assert summary["provider_release_boundary_ready"] is False
    assert summary["conditional_diagnostic_facility_risk_available"] is True
    assert summary["conditional_diagnostic_facility_fn_available"] is True
    assert summary["facility_total_risk_available"] is False
    assert summary["qualified_facility_qra_available"] is False


def test_facility_gate_summary_aggregates_nested_forecast_ledgers():
    summary = integrated_risk._facility_gate_summary(
        {
            "status": "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
            "campaigns": [
                {
                    "facility_ledger": {
                        "provider_release_boundary_case_count": 1,
                        "provider_release_boundary_ready": False,
                        "conditional_diagnostic_facility_risk_available": True,
                        "conditional_diagnostic_facility_expected_death_fn_low_high": [
                            0.0,
                            0.1,
                        ],
                        "facility_total_risk_available": False,
                        "qualified_facility_qra_available": False,
                    }
                },
                {
                    "facility_ledger": {
                        "provider_release_boundary_case_count": 2,
                        "provider_release_boundary_ready": False,
                        "conditional_diagnostic_facility_risk_available": True,
                        "conditional_diagnostic_facility_expected_death_fn_low_high": [
                            0.0,
                            0.2,
                        ],
                        "facility_total_risk_available": False,
                        "qualified_facility_qra_available": False,
                    }
                },
            ],
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        }
    )

    assert summary["facility_ledger_present"] is True
    assert summary["facility_ledger_count"] == 2
    assert summary["provider_release_boundary_case_count"] == 3
    assert summary["provider_release_boundary_ready"] is False
    assert summary["conditional_diagnostic_facility_risk_available"] is True
    assert summary["conditional_diagnostic_facility_fn_available"] is True
    assert summary["facility_total_risk_available"] is False
    assert summary["qualified_facility_qra_available"] is False


def test_integrated_risk_withholds_forecast_facility_campaign_when_scan_is_partial(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_forecast_risk_scan",
        lambda **kwargs: _forecast_result(),
    )
    called = []
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
        forecast_facility_campaign_evaluator=lambda *_: called.append(True),
    )
    assert called == []
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_PARTIAL"
    assert result["forecast_facility_campaign"]["status"] == (
        "WITHHELD_FORECAST_FACILITY_CAMPAIGN_SCAN_WITHHELD"
    )
    assert result["forecast_facility_campaign"]["policy"]["facility_qra_promotion"] is False


def test_integrated_risk_withholds_unsafe_forecast_facility_campaign(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_forecast_risk_scan",
        lambda **kwargs: {**_forecast_result(), "withheld_count": 0},
    )
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
        forecast_facility_campaign_evaluator=lambda *_: {
            "status": "READY_FOR_IJHE_SCOPE",
            "complete_facility_qra_claim": True,
            "policy": {"facility_qra_promotion": True},
        },
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_PARTIAL"
    assert result["forecast_facility_campaign"]["status"] == (
        "WITHHELD_UNSAFE_FORECAST_FACILITY_CAMPAIGN_RESULT"
    )
    assert result["forecast_facility_campaign"]["policy"]["facility_qra_promotion"] is False


def test_integrated_risk_withholds_nested_unsafe_forecast_facility_ledger_claim(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_forecast_risk_scan",
        lambda **kwargs: {**_forecast_result(), "withheld_count": 0},
    )
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
        forecast_facility_campaign_evaluator=lambda forecast: {
            "status": "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
            "facility_ledger": {"provider_packet_promoted": True},
            "policy": {"facility_qra_promotion": False},
        },
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_PARTIAL"
    assert result["forecast_facility_campaign"]["status"] == (
        "WITHHELD_UNSAFE_FORECAST_FACILITY_CAMPAIGN_RESULT"
    )
    assert result["forecast_facility_campaign"]["policy"]["facility_qra_promotion"] is False


def test_integrated_risk_accepts_existing_hazop_campaign_status_for_forecast(monkeypatch):
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_facility_runtime",
        lambda *args, **kwargs: _current_result(),
    )
    monkeypatch.setattr(
        integrated_risk,
        "run_hazop_forecast_risk_scan",
        lambda **kwargs: {**_forecast_result(), "withheld_count": 0},
    )
    result = run_hazop_integrated_risk(
        _table(),
        {"TK-01": {"operating_mode": "receiving"}},
        now_s=10.0,
        component_bindings={"TK-01": object()},
        release_resolvers={},
        forecast_frames=[{"component_id": "TK-01", "origin": "model_prediction"}],
        forecast_tables_by_component={"TK-01": {"rows": []}},
        forecast_facility_campaign_evaluator=lambda *_: {
            "status": "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        },
    )
    assert result["status"] == "INTEGRATED_DIAGNOSTIC_COMPLETE"
    assert result["forecast_facility_campaign"]["status"] == (
        "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED"
    )


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
