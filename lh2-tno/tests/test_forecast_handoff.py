from __future__ import annotations

import json

import pytest

from lh2_tno.forecast_handoff import (
    ForecastHandoffError,
    attach_forecast_quantitative_evidence,
    build_forecast_quantitative_handoff,
)


def _scan():
    return {
        "status": "FORECAST_RISK_SCAN_COMPLETE",
        "facility_id": "facility",
        "timing": {
            "wall_elapsed_ms": 2.5,
            "quantitative_evaluation_elapsed_ms": 0.0,
        },
        "steps": [{
            "forecast_time_s": 12.0,
            "components": [{
                "component_id": "tank-01",
                "scenarios": [{
                    "scenario_id": "tank-pressure",
                    "status": "QUANTITATIVE_EVALUATION_REQUESTED",
                    "scenario": {
                        "scenario_id": "tank-pressure",
                        "operating_mode": "receiving",
                        "scenario_family": "vessel_hole",
                        "release_mode": "hole",
                    },
                    "quantitative_evaluation": {
                        "status": "WITHHELD_NO_QUANTITATIVE_EVALUATOR",
                    },
                }],
            }],
        }],
    }


def test_forecast_quantitative_handoff_creates_explicit_request_without_risk():
    result = build_forecast_quantitative_handoff(_scan())

    assert result["schema_version"] == "prism.forecast_quantitative_handoff.v1"
    assert result["status"] == "FORECAST_QUANTITATIVE_HANDOFF_READY"
    assert result["summary"] == {
        "request_count": 1,
        "ready_for_quantitative_evaluation_count": 1,
        "review_required_count": 0,
    }
    request = result["requests"][0]
    assert request["request_id"] == "tank-01|tank-pressure|12"
    assert request["operating_mode"] == "receiving"
    assert "qualified_provider_release_packet" in request["required_inputs"]
    assert result["policy"]["provider_release_created"] is False
    assert result["policy"]["facility_ir_fn_calculated"] is False
    assert result["policy"]["missing_requests_assigned_zero"] is False
    assert result["timing"]["source_scan_timing"]["wall_elapsed_ms"] == 2.5
    assert "does not claim a 1 Hz" in result["timing"]["measurement_policy"]


def test_forecast_quantitative_handoff_rejects_incomplete_scan_and_duplicate_trigger():
    with pytest.raises(ForecastHandoffError, match="FORECAST_RISK_SCAN_COMPLETE"):
        build_forecast_quantitative_handoff({"status": "FORECAST_RISK_SCAN_PARTIAL"})
    scan = _scan()
    scan["steps"].append(scan["steps"][0])
    with pytest.raises(ForecastHandoffError, match="duplicate forecast quantitative trigger"):
        build_forecast_quantitative_handoff(scan)


def test_saved_facility_scan_builds_two_provider_requests():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scan = json.loads(
        (root / "results/20261115/inspection_center_facility_forecast_hazop_scan.json").read_text(
            encoding="utf-8"
        )
    )
    result = build_forecast_quantitative_handoff(scan)
    assert result["summary"]["request_count"] == 2
    assert result["summary"]["ready_for_quantitative_evaluation_count"] == 2
    assert {request["operating_mode"] for request in result["requests"]} == {"receiving", "supply"}


def test_quantitative_evidence_attachment_requires_exact_keys_and_all_blocks():
    handoff = build_forecast_quantitative_handoff(_scan())
    key = handoff["requests"][0]["request_id"]
    attachment = {
        key: {
            "status": "REVIEWED_INPUTS_ATTACHED",
            "evidence": {
                "provider_release_packet": {"status": "provided", "digest": "a" * 64},
                "frequency_binding": {"status": "literature_bound", "digest": "b" * 64},
                "slabx_lh2_consequence": {"status": "provided", "digest": "c" * 64},
                "facility_condition_binding": {"status": "provided", "digest": "d" * 64},
            },
        }
    }
    result = attach_forecast_quantitative_evidence(handoff, attachment)
    assert result["status"] == "FORECAST_QUANTITATIVE_EVIDENCE_ATTACHED_OPERATOR_LIMITED"
    assert result["summary"]["evidence_attached_count"] == 1
    assert result["policy"]["facility_qra_promotion"] is False

    with pytest.raises(ForecastHandoffError, match="exactly match"):
        attach_forecast_quantitative_evidence(handoff, {"other": attachment[key]})
    incomplete = {key: {"evidence": {"provider_release_packet": {}}}}
    with pytest.raises(ForecastHandoffError, match="missing evidence blocks"):
        attach_forecast_quantitative_evidence(handoff, incomplete)
