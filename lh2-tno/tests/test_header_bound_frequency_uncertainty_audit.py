from __future__ import annotations

from lh2_tno.header_bound_frequency_uncertainty_audit import (
    audit_header_bound_frequency_uncertainty,
)


def _risk(*, bounded: bool) -> dict:
    risk = {"status": "AVAILABLE_CURRENT_WEATHER_IR"}
    if bounded:
        risk["frequency_sensitivity_current_weather_ir_low_high"] = {
            "p05": {"worker-01": [0.0, 0.0]},
            "published": {"worker-01": [0.0, 0.0]},
            "p95": {"worker-01": [0.0, 0.0]},
        }
    return risk


def test_audit_reconciles_partial_fail_closed_summary() -> None:
    result = {
        "components": {
            "tank": {
                "branches": [
                    {"scenario_id": "tank-case", "risk": _risk(bounded=True)},
                ]
            },
            "vent": {
                "branches": [
                    {"scenario_id": "vent-case", "risk": _risk(bounded=False)},
                ]
            },
        },
        "conditional_current_weather_frequency_uncertainty": {
            "status": "PARTIAL_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY",
            "risk_atom_count": 2,
            "frequency_bound_scenario_count": 1,
            "frequency_unbound_scenario_count": 1,
            "frequency_bound_scenario_ids": ["tank-case"],
            "frequency_unbound_scenario_ids": ["vent-case"],
            "complete": False,
            "frequency_inference_performed": False,
            "missing_bounds_imputed": False,
        },
    }
    report = audit_header_bound_frequency_uncertainty(result)
    assert report["status"] == "PASS_DIAGNOSTIC_ONLY"
    assert report["frequency_bound_scenario_count"] == 1
    assert report["frequency_unbound_scenario_count"] == 1


def test_audit_rejects_imputed_bounds() -> None:
    result = {
        "components": {
            "tank": {
                "branches": [
                    {"scenario_id": "tank-case", "risk": _risk(bounded=False)},
                ]
            }
        },
        "conditional_current_weather_frequency_uncertainty": {
            "status": "WITHHELD_CURRENT_WEATHER_FREQUENCY_UNCERTAINTY",
            "risk_atom_count": 1,
            "frequency_bound_scenario_count": 0,
            "frequency_unbound_scenario_count": 1,
            "frequency_bound_scenario_ids": [],
            "frequency_unbound_scenario_ids": ["tank-case"],
            "complete": False,
            "frequency_inference_performed": False,
            "missing_bounds_imputed": True,
        },
    }
    report = audit_header_bound_frequency_uncertainty(result)
    assert report["status"] == "BLOCKED"
    assert "summary_status_or_policy_is_not_fail_closed" in report["blocking_reasons"]

