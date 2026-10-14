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

from collections.abc import Mapping, Sequence
import time
from typing import Any

from .hazop import HazopTable, run_hazop_facility_runtime
from .hazop_forecast import HazopForecastError, run_hazop_forecast_risk_scan


SCHEMA = "prism.hazop_integrated_risk.v1"


class IntegratedRiskError(ValueError):
    """Raised when the current/forecast integration contract is incomplete."""


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


def _forecast_scenarios(result: Mapping[str, Any]) -> set[str]:
    scenario_ids: set[str] = set()
    for entry in result.get("scenario_entries", ()):
        if isinstance(entry, Mapping) and isinstance(entry.get("scenario_id"), str):
            scenario_ids.add(entry["scenario_id"])
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
    mapping_digest: str | None = None,
) -> dict[str, Any]:
    """Run current and optional forecast HAZOP risk paths as one ledger.

    ``current_frames`` contains measured runtime state and operating mode.  If
    ``forecast_frames`` is supplied, the caller must also supply a table per
    forecast component; every forecast frame is then checked by
    :func:`run_hazop_forecast_risk_scan`.  No forecast result is silently
    substituted for a missing quantitative evaluator.
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

    current_status = str(current.get("status", ""))
    current_ok = current_status == "FACILITY_HAZOP_RUNTIME_EVALUATED"
    forecast_status = str(forecast.get("status", ""))
    forecast_ok = forecast_status == "FORECAST_NOT_REQUESTED" or (
        forecast_status == "FORECAST_RISK_SCAN_COMPLETE"
        and int(forecast.get("withheld_count", 0) or 0) == 0
    )
    current_modes = _current_modes(current)
    forecast_modes = _forecast_modes(forecast)
    current_scenarios = {
        str(branch.get("scenario_id"))
        for component in current.get("components", {}).values()
        if isinstance(component, Mapping)
        for branch in component.get("branches", ())
        if isinstance(branch, Mapping) and isinstance(branch.get("scenario_id"), str)
    }
    forecast_scenarios = _forecast_scenarios(forecast)
    return {
        "schema_version": SCHEMA,
        "facility_id": facility_id,
        "status": "INTEGRATED_DIAGNOSTIC_COMPLETE" if current_ok and forecast_ok else "INTEGRATED_DIAGNOSTIC_PARTIAL",
        "current": current,
        "forecast": forecast,
        "linkage": {
            "current_component_ids": sorted(current_frames),
            "forecast_component_ids": sorted(forecast_tables_by_component or {}),
            "current_operating_modes": current_modes,
            "forecast_operating_modes": forecast_modes,
            "shared_scenario_ids": sorted(current_scenarios & forecast_scenarios),
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


__all__ = ["SCHEMA", "IntegratedRiskError", "run_hazop_integrated_risk"]
