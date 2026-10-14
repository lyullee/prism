"""Forecast-state HAZOP scanning for the PRISM digital-twin handoff.

The realtime HAZOP adapter evaluates the state that exists now.  A simulator
produces a sequence of future state frames, however, and a risk calculation is
needed when a predicted frame first reaches a declared HAZOP deviation.  This
module owns that orchestration boundary:

* every forecast frame carries an explicit ``model_prediction`` origin and
  ``forecast_time_s``;
* the operating mode is passed unchanged to the HAZOP selector;
* a quantitative evaluator is called only on a new selected scenario (or when
  the caller asks for every step);
* the evaluator is responsible for the provider release, literature frequency,
  SLABx-LH2 consequence and facility risk calculation; and
* missing or failed evaluators remain withheld and never become zero risk.

This is a diagnostic orchestration contract.  It does not learn frequencies
from sensor or simulation data and it does not promote facility QRA claims.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import copy
import math
import time
from typing import Any

from .contracts import canonical_digest
from .hazop import evaluate_hazop, run_hazop_runtime_consequence
from .state_snapshot import EquipmentStateSnapshot


SCHEMA = "prism.hazop_forecast_risk_scan.v1"
_ORIGIN = "model_prediction"


class HazopForecastError(ValueError):
    """Raised when a forecast scan cannot satisfy its explicit input contract."""


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HazopForecastError(f"{field} must be a non-empty string")
    return value.strip()


def _time(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise HazopForecastError(f"{field} must be finite and non-negative") from error
    if not math.isfinite(number) or number < 0.0:
        raise HazopForecastError(f"{field} must be finite and non-negative")
    return number


def _frames(
    forecast_frames: Sequence[Mapping[str, Any]],
    *,
    expected_component_ids: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(forecast_frames, Sequence) or isinstance(forecast_frames, (str, bytes)):
        raise HazopForecastError("forecast_frames must be a non-empty sequence")
    if not forecast_frames:
        raise HazopForecastError("forecast_frames must be non-empty")
    expected = tuple(sorted(_name(value, "expected_component_ids[]") for value in expected_component_ids))
    if not expected:
        raise HazopForecastError("expected_component_ids must be non-empty")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()
    for index, raw in enumerate(forecast_frames):
        if not isinstance(raw, Mapping):
            raise HazopForecastError(f"forecast_frames[{index}] must be a mapping")
        component_id = _name(raw.get("component_id"), f"forecast_frames[{index}].component_id")
        if component_id not in expected:
            raise HazopForecastError(
                f"forecast_frames[{index}] references an unexpected component: {component_id}"
            )
        forecast_time_s = _time(raw.get("forecast_time_s"), f"forecast_frames[{index}].forecast_time_s")
        key = (forecast_time_s, component_id)
        if key in seen:
            raise HazopForecastError(
                f"duplicate forecast frame for {component_id} at {forecast_time_s} s"
            )
        seen.add(key)
        origin = raw.get("origin", raw.get("input_origin"))
        if origin != _ORIGIN:
            raise HazopForecastError(
                f"forecast_frames[{index}] must declare origin='model_prediction'"
            )
        frame = dict(raw)
        frame["forecast_time_s"] = forecast_time_s
        frame["origin"] = _ORIGIN
        rows.append(frame)
    rows.sort(key=lambda row: (float(row["forecast_time_s"]), str(row["component_id"])))
    times = sorted({float(row["forecast_time_s"]) for row in rows})
    for forecast_time_s in times:
        component_ids = {
            str(row["component_id"])
            for row in rows
            if float(row["forecast_time_s"]) == forecast_time_s
        }
        if component_ids != set(expected):
            missing = sorted(set(expected) - component_ids)
            extra = sorted(component_ids - set(expected))
            raise HazopForecastError(
                f"forecast time {forecast_time_s} s must contain every expected component; "
                f"missing={missing}, extra={extra}"
            )
    return rows


def _step_groups(frames: Sequence[Mapping[str, Any]]) -> list[tuple[float, list[dict[str, Any]]]]:
    grouped: dict[float, list[dict[str, Any]]] = {}
    for frame in frames:
        grouped.setdefault(float(frame["forecast_time_s"]), []).append(dict(frame))
    return [(time_s, sorted(rows, key=lambda row: str(row["component_id"]))) for time_s, rows in sorted(grouped.items())]


def _hazop_selection_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Remove forecast envelope fields before strict HAZOP state validation."""
    state = {
        key: copy.deepcopy(value)
        for key, value in frame.items()
        if key not in {"forecast_time_s", "origin", "input_origin"}
    }
    values = state.get("values")
    if isinstance(values, Mapping):
        state["values"] = [
            (tag, {
                key: copy.deepcopy(value)
                for key, value in raw.items()
                if key != "component_id"
            } if isinstance(raw, Mapping) else raw)
            for tag, raw in values.items()
        ]
        state["values"] = dict(state["values"])
    return state


def _safe_result(result: Any) -> tuple[str, Any, str | None]:
    if not isinstance(result, Mapping):
        return "WITHHELD_INVALID_EVALUATOR_RESULT", None, "quantitative evaluator must return a mapping"
    policy = result.get("policy")
    if isinstance(policy, Mapping) and (
        policy.get("frequency_inference_performed") is True
        or policy.get("sensor_frequency_learning_used") is True
        or policy.get("facility_qra_promotion") is True
    ):
        return (
            "WITHHELD_UNSAFE_EVALUATOR_RESULT",
            None,
            "quantitative evaluator returned an unsafe inference or promotion claim",
        )
    if result.get("frequency_inference_performed") is True or result.get("facility_qra_claim") is True:
        return (
            "WITHHELD_UNSAFE_EVALUATOR_RESULT",
            None,
            "quantitative evaluator returned an unsafe inference or promotion claim",
        )
    return "EVALUATED_OPERATOR_LIMITED", copy.deepcopy(dict(result)), None


QuantitativeEvaluator = Callable[[str, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]


def _runtime_frame_from_forecast(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Create the existing state-runtime envelope for a predicted frame."""
    component_id = _name(frame.get("component_id"), "forecast frame component_id")
    values = frame.get("values")
    if not isinstance(values, Mapping) or not values:
        raise HazopForecastError("forecast frame values must be a non-empty mapping")
    normalized_values: dict[str, dict[str, Any]] = {}
    for tag, raw in values.items():
        if not isinstance(raw, Mapping):
            raise HazopForecastError(f"forecast frame value {tag} must be a mapping")
        quality = raw.get("quality", "valid")
        if quality != "valid":
            raise HazopForecastError(f"forecast frame value {tag} must have valid quality")
        normalized_values[str(tag)] = {
            "component_id": component_id,
            "quantity": raw.get("quantity"),
            "value_si": raw.get("value_si"),
            "sensor_location": raw.get("sensor_location"),
            "quality": quality,
        }
    snapshot = frame.get("state_snapshot")
    if not isinstance(snapshot, Mapping):
        snapshot_measurements = {
            tag: {
                "quantity": raw["quantity"],
                "value_si": raw["value_si"],
                "sensor_location": raw.get("sensor_location"),
                "quality": raw["quality"],
            }
            for tag, raw in normalized_values.items()
        }
        snapshot = {
            "schema_version": "prism.equipment_state_snapshot.v1",
            "component_id": component_id,
            "captured_at_s": float(frame.get("captured_at_s", frame["forecast_time_s"])),
            "origin": _ORIGIN,
            "measurements": snapshot_measurements,
        }
    snapshot_model = EquipmentStateSnapshot.from_mapping(copy.deepcopy(dict(snapshot)))
    snapshot = snapshot_model.to_mapping()
    body = {
        key: copy.deepcopy(value)
        for key, value in frame.items()
        if key not in {"forecast_time_s", "frame_digest", "state_snapshot_digest", "state_snapshot"}
    }
    body["component_id"] = component_id
    body["origin"] = _ORIGIN
    body["source_id"] = str(frame.get("source_id") or f"forecast://{component_id}/{frame['forecast_time_s']}")
    body["values"] = normalized_values
    body["state_snapshot"] = snapshot
    body["state_snapshot_digest"] = snapshot_model.digest()
    body["frame_digest"] = canonical_digest(body)
    return body


def _binding_value(binding: Any, field: str) -> Any:
    if isinstance(binding, Mapping):
        return binding.get(field)
    return getattr(binding, field, None)


def build_hazop_forecast_runtime_evaluator(
    *,
    tables_by_component: Mapping[str, Mapping[str, Any]],
    component_bindings: Mapping[str, Any],
    release_resolvers: Mapping[Any, Any],
    mapping_digest: str | None = None,
) -> QuantitativeEvaluator:
    """Build a forecast callback backed by the existing runtime consequence gate.

    The returned callback turns one predicted frame into a strict runtime frame,
    narrows the HAZOP table to the selected row, and calls
    :func:`run_hazop_runtime_consequence`.  Provider release, termination,
    isolation, inventory and SLABx-LH2 remain owned by the existing monitor and
    resolver; this helper does not create any of them.  A resolver may be keyed
    by ``(component_id, scenario_id)`` for facility-wide uniqueness, or by the
    legacy ``scenario_id`` key for single-component integrations.  The scoped
    key is checked first so a duplicated row ID cannot silently cross equipment
    boundaries.
    """
    if not isinstance(tables_by_component, Mapping) or not tables_by_component:
        raise HazopForecastError("tables_by_component must be non-empty")
    if not isinstance(component_bindings, Mapping):
        raise HazopForecastError("component_bindings must be a mapping")
    if not isinstance(release_resolvers, Mapping):
        raise HazopForecastError("release_resolvers must be a mapping")

    def evaluate(
        component_id: str,
        scenario: Mapping[str, Any],
        frame: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        table = tables_by_component.get(component_id)
        binding = component_bindings.get(component_id)
        if not isinstance(table, Mapping) or binding is None:
            raise HazopForecastError(f"forecast runtime binding is missing for component {component_id}")
        row_id = _name(scenario.get("hazop_row_id"), "forecast scenario hazop_row_id")
        rows = [row for row in table.get("rows", ()) if isinstance(row, Mapping) and row.get("id") == row_id]
        if len(rows) != 1:
            raise HazopForecastError(
                f"forecast HAZOP table must contain exactly one selected row: {component_id}/{row_id}"
            )
        scenario_id = _name(scenario.get("scenario_id"), "forecast scenario_id")
        resolver = release_resolvers.get((component_id, scenario_id))
        resolver_key = "component_scenario"
        if resolver is None:
            resolver = release_resolvers.get(scenario_id)
            resolver_key = "scenario"
        if resolver is None:
            raise HazopForecastError(
                "no release resolver is bound for forecast scenario "
                f"{component_id}/{scenario_id}"
            )
        template = _binding_value(binding, "template")
        monitor = _binding_value(binding, "monitor")
        if template is None or monitor is None:
            raise HazopForecastError(f"component binding lacks template or monitor: {component_id}")
        narrowed_table = dict(table)
        narrowed_table["rows"] = [copy.deepcopy(dict(rows[0]))]
        runtime_frame = _runtime_frame_from_forecast(frame)
        forecast_time_s = _time(context.get("forecast_time_s"), "forecast context forecast_time_s")
        now_s = max(float(runtime_frame["captured_at_s"]), forecast_time_s)
        result = run_hazop_runtime_consequence(
            narrowed_table,
            runtime_frame,
            now_s=now_s,
            template=template,
            monitor=monitor,
            release_resolver=resolver,
            mapping_digest=mapping_digest,
        )
        if isinstance(result, Mapping):
            result = copy.deepcopy(dict(result))
            result["forecast_resolver_binding"] = {
                "key_type": resolver_key,
                "component_id": component_id,
                "scenario_id": scenario_id,
            }
        return result

    return evaluate


def run_hazop_forecast_risk_scan(
    *,
    facility_id: str,
    tables_by_component: Mapping[str, Mapping[str, Any]],
    forecast_frames: Sequence[Mapping[str, Any]],
    expected_component_ids: Sequence[str],
    quantitative_evaluator: QuantitativeEvaluator | None = None,
    evaluate_on: str = "entry",
) -> dict[str, Any]:
    """Scan predicted states and trigger explicit quantitative evaluations.

    ``quantitative_evaluator`` receives ``(component_id, selection,
    forecast_frame, step_context)``.  It may call the existing provider,
    SLABx-LH2 and facility ledger layers, but this function never invents a
    release, a frequency, or a result when it is absent.  ``evaluate_on`` is
    ``entry`` (one evaluation per continuous HAZOP condition) or ``each_step``
    (re-evaluate every predicted frame while the condition is active).
    """
    facility_id = _name(facility_id, "facility_id")
    if evaluate_on not in {"entry", "each_step"}:
        raise HazopForecastError("evaluate_on must be 'entry' or 'each_step'")
    component_ids = tuple(sorted(_name(value, "expected_component_ids[]") for value in expected_component_ids))
    if len(set(component_ids)) != len(component_ids):
        raise HazopForecastError("expected_component_ids must be unique")
    if set(tables_by_component) != set(component_ids):
        raise HazopForecastError(
            "tables_by_component must cover exactly expected_component_ids"
        )
    frames = _frames(forecast_frames, expected_component_ids=component_ids)
    grouped = _step_groups(frames)
    active_keys: set[tuple[str, str]] = set()
    steps: list[dict[str, Any]] = []
    trigger_count = 0
    evaluated_count = 0
    withheld_count = 0
    scenario_entries: list[dict[str, Any]] = []
    scan_started = time.perf_counter()
    quantitative_elapsed_ms = 0.0

    for step_index, (forecast_time_s, rows) in enumerate(grouped):
        step_rows: list[dict[str, Any]] = []
        current_keys: set[tuple[str, str]] = set()
        for frame in rows:
            component_id = str(frame["component_id"])
            try:
                selection = evaluate_hazop(
                    tables_by_component[component_id],
                    _hazop_selection_frame(frame),
                )
            except Exception as error:
                step_rows.append(
                    {
                        "component_id": component_id,
                        "status": "WITHHELD_INVALID_HAZOP_FRAME",
                        "forecast_time_s": forecast_time_s,
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "selection": None,
                        "quantitative_evaluation": None,
                    }
                )
                withheld_count += 1
                continue
            selected = selection.get("selected_scenarios", [])
            component_rows: list[dict[str, Any]] = []
            if not selected:
                step_rows.append(
                    {
                        "component_id": component_id,
                        "status": "NO_RISK_TRIGGER",
                        "forecast_time_s": forecast_time_s,
                        "selection_status": selection.get("status"),
                        "selection": selection,
                        "quantitative_evaluation": None,
                    }
                )
                continue
            for scenario in selected:
                scenario_id = _name(scenario.get("scenario_id"), "selected scenario_id")
                key = (component_id, scenario_id)
                current_keys.add(key)
                should_evaluate = evaluate_on == "each_step" or key not in active_keys
                evaluation: dict[str, Any] | None = None
                if should_evaluate:
                    trigger_count += 1
                    trigger = {
                        "component_id": component_id,
                        "scenario_id": scenario_id,
                        "forecast_time_s": forecast_time_s,
                        "trigger_type": "RISK_CONDITION_REACHED" if key not in active_keys else "ACTIVE_CONDITION_RECHECK",
                    }
                    if quantitative_evaluator is None:
                        evaluation = {
                            "status": "WITHHELD_NO_QUANTITATIVE_EVALUATOR",
                            "reason": "an explicit provider/SLABx-LH2/facility evaluator is required",
                            "facility_qra_claim": False,
                            "frequency_inference_performed": False,
                            "elapsed_ms": 0.0,
                        }
                        withheld_count += 1
                    else:
                        evaluator_started = time.perf_counter()
                        try:
                            raw_result = quantitative_evaluator(
                                component_id,
                                copy.deepcopy(scenario),
                                copy.deepcopy(frame),
                                {
                                    "facility_id": facility_id,
                                    "step_index": step_index,
                                    "forecast_time_s": forecast_time_s,
                                    "trigger": trigger,
                                },
                            )
                            status, safe_result, reason = _safe_result(raw_result)
                            evaluation = {
                                "status": status,
                                "result": safe_result,
                                "reason": reason,
                                "facility_qra_claim": False,
                                "frequency_inference_performed": False,
                                "elapsed_ms": (time.perf_counter() - evaluator_started) * 1000.0,
                            }
                            quantitative_elapsed_ms += evaluation["elapsed_ms"]
                            if status == "EVALUATED_OPERATOR_LIMITED":
                                evaluated_count += 1
                            else:
                                withheld_count += 1
                        except Exception as error:
                            evaluation = {
                                "status": "WITHHELD_QUANTITATIVE_EVALUATOR_ERROR",
                                "reason": str(error),
                                "error_type": type(error).__name__,
                                "facility_qra_claim": False,
                                "frequency_inference_performed": False,
                                "elapsed_ms": (time.perf_counter() - evaluator_started) * 1000.0,
                            }
                            quantitative_elapsed_ms += evaluation["elapsed_ms"]
                            withheld_count += 1
                    trigger["evaluation"] = evaluation
                    scenario_entries.append(trigger)
                else:
                    evaluation = {
                        "status": "ACTIVE_CONDITION_NO_REEVALUATION",
                        "reason": "evaluate_on='entry' and the scenario remains active",
                    }
                component_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "status": "QUANTITATIVE_EVALUATION_REQUESTED" if should_evaluate else "ACTIVE_CONDITION",
                        "scenario": scenario,
                        "quantitative_evaluation": evaluation,
                    }
                )
            step_rows.append(
                {
                    "component_id": component_id,
                    "status": "RISK_TRIGGERED",
                    "forecast_time_s": forecast_time_s,
                    "selection_status": selection.get("status"),
                    "selection": selection,
                    "scenarios": component_rows,
                }
            )
        exited = sorted(active_keys - current_keys)
        if exited:
            for component_id, scenario_id in exited:
                scenario_entries.append(
                    {
                        "component_id": component_id,
                        "scenario_id": scenario_id,
                        "forecast_time_s": forecast_time_s,
                        "trigger_type": "RISK_CONDITION_CLEARED",
                        "evaluation": None,
                    }
                )
        active_keys = current_keys
        steps.append(
            {
                "step_index": step_index,
                "forecast_time_s": forecast_time_s,
                "components": step_rows,
                "active_scenario_count": len(current_keys),
                "risk_condition_reached": bool(current_keys),
            }
        )

    return {
        "schema_version": SCHEMA,
        "status": "FORECAST_RISK_SCAN_COMPLETE",
        "facility_id": facility_id,
        "forecast_origin": _ORIGIN,
        "evaluate_on": evaluate_on,
        "steps": steps,
        "scenario_entries": scenario_entries,
        "trigger_count": trigger_count,
        "evaluated_count": evaluated_count,
        "withheld_count": withheld_count,
        "timing": {
            "wall_elapsed_ms": (time.perf_counter() - scan_started) * 1000.0,
            "quantitative_evaluation_elapsed_ms": quantitative_elapsed_ms,
            "trigger_count": trigger_count,
            "evaluated_count": evaluated_count,
            "withheld_count": withheld_count,
            "fresh_physics_claim": False,
            "interpretation": "Measured for this scan invocation; not an operating 1 Hz guarantee.",
        },
        "policy": {
            "operating_mode_taken_from_forecast_input": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "release_packet_created_by_scan": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Predicted process states were evaluated at explicit forecast times. "
            "Quantitative analysis is requested only when a HAZOP condition is reached; "
            "provider, SLABx-LH2, literature frequency and facility-ledger evidence remain "
            "owned by the supplied evaluator."
        ),
    }


__all__ = [
    "SCHEMA",
    "HazopForecastError",
    "QuantitativeEvaluator",
    "build_hazop_forecast_runtime_evaluator",
    "run_hazop_forecast_risk_scan",
]
