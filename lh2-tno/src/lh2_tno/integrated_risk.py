"""Unified current/forecast HAZOP risk orchestration for PRISM.

The current-state and forecast-state adapters deliberately remain separate:
the former consumes measured runtime frames and the latter consumes explicit
``model_prediction`` frames.  This module is the small integration boundary
that a digital-twin host can call once for both paths.  It does not create a
release, infer a frequency, run physics, or promote a facility QRA claim.
Those responsibilities remain with the supplied runtime monitor,
quantitative evaluator, and facility campaign layers.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import copy
import time
from typing import Any

from .hazop import HazopTable, run_hazop_facility_runtime
from .hazop_campaign import build_hazop_facility_campaign_result
from .hazop_forecast import HazopForecastError, run_hazop_forecast_risk_scan


SCHEMA = "prism.hazop_integrated_risk.v1"


class IntegratedRiskError(ValueError):
    """Raised when the current/forecast integration contract is incomplete."""


def build_hazop_facility_campaign_evaluator(
    *,
    annual_conditions: Sequence[Mapping[str, Any]],
    scenario_bindings: Sequence[Mapping[str, Any]],
    expected_component_ids: Sequence[str] = (),
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Bind the existing annual facility handoff as an integration callback.

    The returned evaluator only supplies the reviewed annual-condition and
    scenario-binding inputs to :func:`build_hazop_facility_campaign_result`.
    It does not create missing provider releases, frequencies, weather,
    population, ignition, or validation evidence.
    """
    conditions = tuple(copy.deepcopy(dict(row)) for row in annual_conditions)
    bindings = tuple(copy.deepcopy(dict(row)) for row in scenario_bindings)
    components = tuple(str(value) for value in expected_component_ids)

    def evaluate(current_result: Mapping[str, Any]) -> Mapping[str, Any]:
        return build_hazop_facility_campaign_result(
            current_result,
            annual_conditions=copy.deepcopy(conditions),
            scenario_bindings=copy.deepcopy(bindings),
            expected_component_ids=components,
        )

    return evaluate


def _facility_id(table: HazopTable | Mapping[str, Any]) -> str:
    if isinstance(table, HazopTable):
        value = table.facility_id
    elif isinstance(table, Mapping):
        value = table.get("facility_id")
    else:
        value = None
    if not isinstance(value, str) or not value.strip():
        raise IntegratedRiskError("table must provide a non-empty facility_id")
    return value.strip()


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntegratedRiskError(f"{field} must be a non-empty string")
    return value.strip()


def _current_modes(result: Mapping[str, Any]) -> dict[str, str]:
    modes: dict[str, str] = {}
    components = result.get("components")
    if not isinstance(components, Mapping):
        return modes
    for component_id, component in components.items():
        if not isinstance(component, Mapping):
            continue
        selection = component.get("selection")
        mode = selection.get("operating_mode") if isinstance(selection, Mapping) else None
        if isinstance(mode, str) and mode.strip():
            modes[str(component_id)] = mode.strip()
    return modes


def _forecast_modes(result: Mapping[str, Any]) -> dict[str, list[str]]:
    modes: dict[str, set[str]] = {}
    for entry in result.get("scenario_entries", ()):
        if not isinstance(entry, Mapping):
            continue
        component_id = entry.get("component_id")
        mode = entry.get("operating_mode")
        if isinstance(component_id, str) and isinstance(mode, str) and mode.strip():
            modes.setdefault(component_id, set()).add(mode.strip())
    return {component_id: sorted(values) for component_id, values in sorted(modes.items())}


def _forecast_scenarios(result: Mapping[str, Any]) -> set[tuple[str, str]]:
    scenario_ids: set[tuple[str, str]] = set()
    for entry in result.get("scenario_entries", ()):
        if (
            isinstance(entry, Mapping)
            and isinstance(entry.get("component_id"), str)
            and isinstance(entry.get("scenario_id"), str)
        ):
            scenario_ids.add((entry["component_id"], entry["scenario_id"]))
    return scenario_ids


def run_hazop_integrated_risk(
    table: HazopTable | Mapping[str, Any],
    current_frames: Mapping[str, Mapping[str, Any]],
    *,
    now_s: float,
    component_bindings: Mapping[str, Any],
    release_resolvers: Mapping[Any, Any],
    forecast_frames: Sequence[Mapping[str, Any]] | None = None,
    forecast_tables_by_component: Mapping[str, Mapping[str, Any]] | None = None,
    forecast_component_ids: Sequence[str] | None = None,
    forecast_quantitative_evaluator: Any = None,
    forecast_evaluate_on: str = "entry",
    facility_campaign_evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    forecast_facility_campaign_evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    mapping_digest: str | None = None,
) -> dict[str, Any]:
    """Run current and optional forecast HAZOP risk paths as one ledger.

    ``current_frames`` contains measured runtime state and operating mode.  If
    ``forecast_frames`` is supplied, the caller must also supply a table per
    forecast component; every forecast frame is then checked by
    :func:`run_hazop_forecast_risk_scan`.  No forecast result is silently
    substituted for a missing quantitative evaluator.  An optional
    ``facility_campaign_evaluator`` may receive the current runtime ledger and
    attach the existing annual-condition/facility-ledger handoff.  A separate
    ``forecast_facility_campaign_evaluator`` receives the completed forecast
    scan, including trigger evaluations, so future-state facility aggregation
    is explicit rather than being confused with the current snapshot.  Both
    results are copied only after unsafe frequency, physical-validation, or
    facility-QRA claims are rejected.
    """
    facility_id = _facility_id(table)
    if not isinstance(current_frames, Mapping) or not current_frames:
        raise IntegratedRiskError("current_frames must be a non-empty mapping")
    if not isinstance(component_bindings, Mapping) or not component_bindings:
        raise IntegratedRiskError("component_bindings must be a non-empty mapping")
    started = time.perf_counter()
    try:
        current = run_hazop_facility_runtime(
            table,
            current_frames,
            now_s=now_s,
            component_bindings=component_bindings,
            release_resolvers=release_resolvers,
            mapping_digest=mapping_digest,
        )
    except Exception as error:
        raise IntegratedRiskError(f"current-state HAZOP execution failed: {error}") from error

    forecast: dict[str, Any]
    if forecast_frames is None:
        forecast = {
            "status": "FORECAST_NOT_REQUESTED",
            "facility_id": facility_id,
            "scenario_entries": [],
            "trigger_count": 0,
            "evaluated_count": 0,
            "withheld_count": 0,
            "policy": {
                "diagnostic_only": True,
                "facility_qra_promotion": False,
            },
        }
    else:
        if not isinstance(forecast_tables_by_component, Mapping) or not forecast_tables_by_component:
            raise IntegratedRiskError(
                "forecast_tables_by_component is required when forecast_frames are supplied"
            )
        expected = tuple(
            _name(value, "forecast_component_ids[]")
            for value in (forecast_component_ids or tuple(forecast_tables_by_component))
        )
        if not expected or len(set(expected)) != len(expected):
            raise IntegratedRiskError("forecast_component_ids must be non-empty and unique")
        try:
            forecast = run_hazop_forecast_risk_scan(
                facility_id=facility_id,
                tables_by_component=forecast_tables_by_component,
                forecast_frames=forecast_frames,
                expected_component_ids=expected,
                quantitative_evaluator=forecast_quantitative_evaluator,
                evaluate_on=forecast_evaluate_on,
            )
        except (HazopForecastError, ValueError, TypeError) as error:
            raise IntegratedRiskError(f"forecast-state HAZOP execution failed: {error}") from error

    forecast_facility_campaign: dict[str, Any]
    if forecast_facility_campaign_evaluator is None:
        forecast_facility_campaign = {
            "status": "FORECAST_FACILITY_CAMPAIGN_NOT_REQUESTED",
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        }
    elif not callable(forecast_facility_campaign_evaluator):
        raise IntegratedRiskError(
            "forecast_facility_campaign_evaluator must be callable when supplied"
        )
    elif forecast.get("status") != "FORECAST_RISK_SCAN_COMPLETE":
        forecast_facility_campaign = {
            "status": "WITHHELD_FORECAST_FACILITY_CAMPAIGN_SCAN_PARTIAL",
            "reason": "forecast facility campaign requires a completed forecast HAZOP scan",
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        }
    elif int(forecast.get("withheld_count", 0) or 0) > 0:
        forecast_facility_campaign = {
            "status": "WITHHELD_FORECAST_FACILITY_CAMPAIGN_SCAN_WITHHELD",
            "reason": "forecast HAZOP scan contains withheld quantitative evaluations",
            "withheld_count": int(forecast.get("withheld_count", 0) or 0),
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        }
    else:
        try:
            raw_forecast_campaign = forecast_facility_campaign_evaluator(
                copy.deepcopy(forecast)
            )
        except Exception as error:
            forecast_facility_campaign = {
                "status": "WITHHELD_FORECAST_FACILITY_CAMPAIGN_EVALUATOR_ERROR",
                "error_type": type(error).__name__,
                "reason": str(error),
                "policy": {
                    "facility_qra_promotion": False,
                    "frequency_inference_performed": False,
                    "physical_validation_claim": False,
                },
            }
        else:
            if not isinstance(raw_forecast_campaign, Mapping):
                forecast_facility_campaign = {
                    "status": "WITHHELD_INVALID_FORECAST_FACILITY_CAMPAIGN_RESULT",
                    "reason": "forecast facility campaign evaluator must return a mapping",
                    "policy": {
                        "facility_qra_promotion": False,
                        "frequency_inference_performed": False,
                        "physical_validation_claim": False,
                    },
                }
            else:
                forecast_campaign = copy.deepcopy(dict(raw_forecast_campaign))
                forecast_campaign_policy = forecast_campaign.get("policy")
                forecast_campaign_policy = (
                    forecast_campaign_policy
                    if isinstance(forecast_campaign_policy, Mapping)
                    else {}
                )
                unsafe = (
                    forecast_campaign_policy.get("facility_qra_promotion") is True
                    or forecast_campaign_policy.get("frequency_inference_performed") is True
                    or forecast_campaign_policy.get("physical_validation_claim") is True
                    or forecast_campaign.get("complete_facility_qra_claim") is True
                )
                if unsafe:
                    forecast_facility_campaign = {
                        "status": "WITHHELD_UNSAFE_FORECAST_FACILITY_CAMPAIGN_RESULT",
                        "reason": "forecast facility campaign evaluator returned an unsafe promotion or inference claim",
                        "policy": {
                            "facility_qra_promotion": False,
                            "frequency_inference_performed": False,
                            "physical_validation_claim": False,
                        },
                    }
                else:
                    forecast_campaign["status"] = str(
                        forecast_campaign.get("status")
                        or "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED"
                    )
                    forecast_campaign["policy"] = {
                        **dict(forecast_campaign_policy),
                        "facility_qra_promotion": False,
                        "frequency_inference_performed": False,
                        "physical_validation_claim": False,
                    }
                    forecast_facility_campaign = forecast_campaign

    facility_campaign: dict[str, Any]
    if facility_campaign_evaluator is None:
        facility_campaign = {
            "status": "FACILITY_CAMPAIGN_NOT_REQUESTED",
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        }
    elif not callable(facility_campaign_evaluator):
        raise IntegratedRiskError("facility_campaign_evaluator must be callable when supplied")
    elif current.get("status") != "FACILITY_HAZOP_RUNTIME_EVALUATED":
        facility_campaign = {
            "status": "WITHHELD_FACILITY_CAMPAIGN_CURRENT_RUNTIME_PARTIAL",
            "reason": "facility campaign requires a fully evaluated current HAZOP runtime result",
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        }
    else:
        try:
            raw_campaign = facility_campaign_evaluator(copy.deepcopy(current))
        except Exception as error:
            facility_campaign = {
                "status": "WITHHELD_FACILITY_CAMPAIGN_EVALUATOR_ERROR",
                "error_type": type(error).__name__,
                "reason": str(error),
                "policy": {
                    "facility_qra_promotion": False,
                    "frequency_inference_performed": False,
                    "physical_validation_claim": False,
                },
            }
        else:
            if not isinstance(raw_campaign, Mapping):
                facility_campaign = {
                    "status": "WITHHELD_INVALID_FACILITY_CAMPAIGN_RESULT",
                    "reason": "facility campaign evaluator must return a mapping",
                    "policy": {
                        "facility_qra_promotion": False,
                        "frequency_inference_performed": False,
                        "physical_validation_claim": False,
                    },
                }
            else:
                campaign = copy.deepcopy(dict(raw_campaign))
                campaign_policy = campaign.get("policy")
                campaign_policy = campaign_policy if isinstance(campaign_policy, Mapping) else {}
                unsafe = (
                    campaign_policy.get("facility_qra_promotion") is True
                    or campaign_policy.get("frequency_inference_performed") is True
                    or campaign_policy.get("physical_validation_claim") is True
                    or campaign.get("complete_facility_qra_claim") is True
                )
                if unsafe:
                    facility_campaign = {
                        "status": "WITHHELD_UNSAFE_FACILITY_CAMPAIGN_RESULT",
                        "reason": "facility campaign evaluator returned an unsafe promotion or inference claim",
                        "policy": {
                            "facility_qra_promotion": False,
                            "frequency_inference_performed": False,
                            "physical_validation_claim": False,
                        },
                    }
                else:
                    campaign["status"] = str(
                        campaign.get("status") or "FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED"
                    )
                    campaign["policy"] = {
                        **dict(campaign_policy),
                        "facility_qra_promotion": False,
                        "frequency_inference_performed": False,
                        "physical_validation_claim": False,
                    }
                    facility_campaign = campaign

    current_status = str(current.get("status", ""))
    current_ok = current_status == "FACILITY_HAZOP_RUNTIME_EVALUATED"
    forecast_status = str(forecast.get("status", ""))
    forecast_ok = forecast_status == "FORECAST_NOT_REQUESTED" or (
        forecast_status == "FORECAST_RISK_SCAN_COMPLETE"
        and int(forecast.get("withheld_count", 0) or 0) == 0
    )
    facility_campaign_status = str(facility_campaign.get("status", ""))
    facility_campaign_ok = facility_campaign_status in {
        "FACILITY_CAMPAIGN_NOT_REQUESTED",
        "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
    }
    forecast_facility_campaign_status = str(forecast_facility_campaign.get("status", ""))
    forecast_facility_campaign_ok = forecast_facility_campaign_status in {
        "FORECAST_FACILITY_CAMPAIGN_NOT_REQUESTED",
        "FORECAST_FACILITY_CAMPAIGN_EVALUATED_OPERATOR_LIMITED",
    }
    current_modes = _current_modes(current)
    forecast_modes = _forecast_modes(forecast)
    current_scenarios = {
        (str(component_id), str(branch.get("scenario_id")))
        for component_id, component in current.get("components", {}).items()
        if isinstance(component, Mapping)
        for branch in component.get("branches", ())
        if isinstance(branch, Mapping) and isinstance(branch.get("scenario_id"), str)
    }
    forecast_scenarios = _forecast_scenarios(forecast)
    return {
        "schema_version": SCHEMA,
        "facility_id": facility_id,
        "status": "INTEGRATED_DIAGNOSTIC_COMPLETE"
        if current_ok and forecast_ok and facility_campaign_ok and forecast_facility_campaign_ok
        else "INTEGRATED_DIAGNOSTIC_PARTIAL",
        "current": current,
        "forecast": forecast,
        "facility_campaign": facility_campaign,
        "forecast_facility_campaign": forecast_facility_campaign,
        "linkage": {
            "current_component_ids": sorted(current_frames),
            "forecast_component_ids": sorted(forecast_tables_by_component or {}),
            "current_operating_modes": current_modes,
            "forecast_operating_modes": forecast_modes,
            "shared_scenario_ids": sorted({scenario_id for _, scenario_id in current_scenarios & forecast_scenarios}),
            "shared_component_scenario_keys": [
                {"component_id": component_id, "scenario_id": scenario_id}
                for component_id, scenario_id in sorted(current_scenarios & forecast_scenarios)
            ],
            "mode_and_scenario_identity_preserved": True,
        },
        "timing": {
            "wall_elapsed_ms": (time.perf_counter() - started) * 1000.0,
            "interpretation": "Measured for this invocation; not an operating 1 Hz guarantee.",
        },
        "policy": {
            "operating_mode_taken_from_input": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created_by_integration": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
    }


__all__ = [
    "SCHEMA",
    "IntegratedRiskError",
    "build_hazop_facility_campaign_evaluator",
    "run_hazop_integrated_risk",
]
