"""Build an explicit quantitative handoff from a forecast HAZOP scan.

The handoff is a worklist, not a risk result. It turns each reached
component/scenario/time condition into a stable request for a reviewed
provider release, literature frequency binding, SLABx-LH2 consequence and
facility campaign. Missing evaluations remain pending; no zero risk,
frequency, release or facility IR/F-N value is inferred.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA = "prism.forecast_quantitative_handoff.v1"


class ForecastHandoffError(ValueError):
    """Raised when a forecast scan cannot satisfy the handoff contract."""


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForecastHandoffError(f"{field} must be a non-empty string")
    return value.strip()


def _time(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ForecastHandoffError(f"{field} must be finite") from error
    if not number == number or number in {float("inf"), float("-inf")}:
        raise ForecastHandoffError(f"{field} must be finite")
    return number


def build_forecast_quantitative_handoff(scan: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a complete forecast scan into an auditable request worklist."""
    if not isinstance(scan, Mapping):
        raise ForecastHandoffError("scan must be a mapping")
    if scan.get("status") != "FORECAST_RISK_SCAN_COMPLETE":
        raise ForecastHandoffError("scan must have status FORECAST_RISK_SCAN_COMPLETE")
    facility_id = _name(scan.get("facility_id"), "facility_id")
    steps = scan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ForecastHandoffError("scan.steps must be a non-empty list")
    requests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step_index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise ForecastHandoffError(f"scan.steps[{step_index}] must be a mapping")
        forecast_time_s = _time(step.get("forecast_time_s"), f"scan.steps[{step_index}].forecast_time_s")
        components = step.get("components")
        if not isinstance(components, list):
            raise ForecastHandoffError(f"scan.steps[{step_index}].components must be a list")
        for component_index, component in enumerate(components):
            if not isinstance(component, Mapping):
                raise ForecastHandoffError(
                    f"scan.steps[{step_index}].components[{component_index}] must be a mapping"
                )
            component_id = _name(
                component.get("component_id"),
                f"scan.steps[{step_index}].components[{component_index}].component_id",
            )
            for scenario_index, scenario_row in enumerate(component.get("scenarios", ())):
                if not isinstance(scenario_row, Mapping):
                    raise ForecastHandoffError("scenario rows must be mappings")
                # A scan may retain an active condition at every subsequent
                # time step. Only rows that requested a quantitative
                # evaluation become new work items; active-condition rows are
                # already represented by their original trigger.
                if scenario_row.get("status") != "QUANTITATIVE_EVALUATION_REQUESTED":
                    continue
                scenario_id = _name(scenario_row.get("scenario_id"), "scenario_id")
                scenario = scenario_row.get("scenario")
                if not isinstance(scenario, Mapping):
                    raise ForecastHandoffError(f"scenario {scenario_id} must include its selection")
                operating_mode = _name(scenario.get("operating_mode"), "scenario.operating_mode")
                key = f"{component_id}|{scenario_id}|{forecast_time_s:g}"
                if key in seen:
                    raise ForecastHandoffError(f"duplicate forecast quantitative trigger: {key}")
                seen.add(key)
                evaluation = scenario_row.get("quantitative_evaluation")
                evaluation_status = (
                    evaluation.get("status") if isinstance(evaluation, Mapping) else None
                )
                requests.append({
                    "request_id": key,
                    "facility_id": facility_id,
                    "component_id": component_id,
                    "scenario_id": scenario_id,
                    "forecast_time_s": forecast_time_s,
                    "operating_mode": operating_mode,
                    "scenario_family": scenario.get("scenario_family"),
                    "release_mode": scenario.get("release_mode"),
                    "source_trigger_type": "RISK_CONDITION_REACHED",
                    "current_evaluation_status": evaluation_status,
                    "required_inputs": [
                        "qualified_provider_release_packet",
                        "reviewed_literature_frequency_binding",
                        "SLABx-LH2_consequence_result",
                        "facility_annual_condition_population_ignition_binding",
                    ],
                    "status": (
                        "READY_FOR_QUANTITATIVE_EVALUATION"
                        if evaluation_status == "WITHHELD_NO_QUANTITATIVE_EVALUATOR"
                        else "REVIEW_REQUIRED"
                    ),
                })
    return {
        "schema_version": SCHEMA,
        "status": "FORECAST_QUANTITATIVE_HANDOFF_READY",
        "facility_id": facility_id,
        "requests": requests,
        "timing": {
            "source_scan_timing": dict(scan.get("timing", {}))
            if isinstance(scan.get("timing"), Mapping)
            else None,
            "measurement_policy": (
                "Copied from the forecast scan invocation; it is a diagnostic wall-clock "
                "measurement and does not claim a 1 Hz operating guarantee."
            ),
        },
        "summary": {
            "request_count": len(requests),
            "ready_for_quantitative_evaluation_count": sum(
                item["status"] == "READY_FOR_QUANTITATIVE_EVALUATION" for item in requests
            ),
            "review_required_count": sum(
                item["status"] == "REVIEW_REQUIRED" for item in requests
            ),
        },
        "policy": {
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "slabx_lh2_calculated": False,
            "facility_ir_fn_calculated": False,
            "facility_qra_promotion": False,
            "missing_requests_assigned_zero": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Each predicted HAZOP condition is an explicit quantitative work item. "
            "The handoff requests reviewed provider, frequency, SLABx-LH2 and "
            "facility bindings but creates none of them."
        ),
    }


__all__ = ["SCHEMA", "ForecastHandoffError", "build_forecast_quantitative_handoff"]
