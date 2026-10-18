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
import math
import time
from typing import Any

from .contracts import canonical_digest
from .facility_ledger import merge_facility_campaign_results
from .hazop import HazopTable, run_hazop_facility_runtime
from .hazop_campaign import build_hazop_facility_campaign_result
from .hazop_forecast import HazopForecastError, run_hazop_forecast_risk_scan
from .forecast_handoff import build_forecast_facility_campaign_evidence_gate


SCHEMA = "prism.hazop_integrated_risk.v1"
FORECAST_FACILITY_SCHEMA = "prism.hazop_forecast_facility_campaign.v1"


class IntegratedRiskError(ValueError):
    """Raised when the current/forecast integration contract is incomplete."""


def _facility_ledgers(campaign: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Collect direct and per-forecast facility ledgers from one campaign."""
    ledgers: list[Mapping[str, Any]] = []
    direct = campaign.get("facility_ledger")
    if isinstance(direct, Mapping):
        ledgers.append(direct)
        return ledgers

    nested = campaign.get("campaigns")
    if not isinstance(nested, Sequence) or isinstance(nested, (str, bytes)):
        return ledgers
    for item in nested:
        if not isinstance(item, Mapping):
            continue
        nested_ledger = item.get("facility_ledger")
        if isinstance(nested_ledger, Mapping):
            ledgers.append(nested_ledger)
            continue
        nested_result = item.get("result")
        if isinstance(nested_result, Mapping) and isinstance(
            nested_result.get("facility_ledger"), Mapping
        ):
            ledgers.append(nested_result["facility_ledger"])
    return ledgers


def _has_unsafe_facility_claim(campaign: Mapping[str, Any]) -> bool:
    """Return whether a supplied campaign claims a facility-QRA promotion.

    Evaluator callbacks may expose a nested facility ledger.  Checking only
    the callback's top-level policy leaves a fail-open path where a ledger can
    claim qualified QRA or provider promotion while the wrapper still labels
    the result operator-limited.  Keep numerical conditional totals visible,
    but reject qualification, provider-promotion, inference, and validation
    claims at both levels.
    """
    sources: list[Mapping[str, Any]] = [campaign, *_facility_ledgers(campaign)]
    blocked_flags = (
        "facility_qra_promotion",
        "qualified_facility_qra_available",
        "complete_facility_qra_claim",
        "provider_packet_promoted",
        "facility_qra_claim",
        "frequency_inference_performed",
        "sensor_frequency_learning_used",
        "physical_validation_claim",
    )
    return any(source.get(flag) is True for source in sources for flag in blocked_flags)


def _facility_gate_summary(campaign: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the facility promotion gates without hiding missing evidence."""
    # Forecast evaluators may retain one facility ledger per prediction time
    # under ``campaigns``.  Do not report null simply because the evaluator
    # uses that explicit nested representation.
    ledgers = _facility_ledgers(campaign)
    policy = campaign.get("policy")
    policy = policy if isinstance(policy, Mapping) else {}

    def aggregate_bool(key: str) -> bool | None:
        values = [row[key] for row in ledgers if isinstance(row.get(key), bool)]
        if not values:
            return None
        # An aggregate is available only when every nested campaign carries
        # the gate and every one of those gates is open.  This is deliberately
        # conservative for a facility-wide digital-twin summary.
        return all(values)

    def aggregate_case_count() -> int | None:
        values = [
            row["provider_release_boundary_case_count"]
            for row in ledgers
            if isinstance(row.get("provider_release_boundary_case_count"), int)
            and not isinstance(row.get("provider_release_boundary_case_count"), bool)
        ]
        return sum(values) if values else None

    def aggregate_fn_available() -> bool | None:
        if not ledgers:
            return None
        return all(
            row.get("conditional_diagnostic_facility_expected_death_fn_low_high")
            is not None
            for row in ledgers
        )

    return {
        "campaign_status": str(campaign.get("status", "")),
        "facility_ledger_present": bool(ledgers),
        "facility_ledger_count": len(ledgers),
        "provider_release_boundary_case_count": aggregate_case_count(),
        "provider_release_boundary_ready": aggregate_bool("provider_release_boundary_ready"),
        "conditional_diagnostic_facility_risk_available": aggregate_bool(
            "conditional_diagnostic_facility_risk_available"
        ),
        "conditional_diagnostic_facility_fn_available": aggregate_fn_available(),
        "facility_total_risk_available": aggregate_bool("facility_total_risk_available"),
        "qualified_facility_qra_available": aggregate_bool(
            "qualified_facility_qra_available"
        ),
        "facility_qra_promotion": policy.get("facility_qra_promotion") is True,
        "frequency_inference_performed": policy.get("frequency_inference_performed") is True,
        "physical_validation_claim": policy.get("physical_validation_claim") is True,
    }


def _forecast_trigger_key(component_id: str, scenario_id: str, forecast_time_s: float) -> str:
    """Return the JSON-safe identity for one forecast quantitative trigger."""

    return f"{component_id}|{scenario_id}|{format(float(forecast_time_s), '.17g')}"


def build_hazop_forecast_facility_campaign_result(
    forecast_scan: Mapping[str, Any],
    *,
    campaign_bindings: Mapping[str, Mapping[str, Any]],
    expected_component_ids: Sequence[str] = (),
    evidence_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Join explicit forecast-trigger campaigns into one facility ledger.

    ``run_hazop_forecast_risk_scan`` deliberately returns one quantitative
    evaluation at a time.  A digital-twin host that has an approved provider /
    SLABx-LH2 / facility calculation can place that *already evaluated* result
    in ``campaign_bindings`` under the canonical key
    ``component_id|scenario_id|forecast_time_s``.  The binding value must have
    ``component_id``, ``scenario_id``, ``forecast_time_s``, ``operating_mode``
    (the exact mode selected by HAZOP), and a complete ``campaign`` mapping.

    This function only joins reviewed campaign outputs.  It never creates a
    release, infers a frequency, substitutes a missing consequence, or marks
    a forecast facility QRA as qualified.  Missing or extra trigger bindings
    fail closed.
    """
    if not isinstance(forecast_scan, Mapping):
        raise IntegratedRiskError("forecast_scan must be a mapping")
    if forecast_scan.get("schema_version") != "prism.hazop_forecast_risk_scan.v1":
        raise IntegratedRiskError("forecast_scan has an unsupported schema_version")
    if forecast_scan.get("status") != "FORECAST_RISK_SCAN_COMPLETE":
        raise IntegratedRiskError("a completed forecast HAZOP scan is required")
    if int(forecast_scan.get("withheld_count", 0) or 0) != 0:
        raise IntegratedRiskError(
            "forecast campaign join is withheld while quantitative evaluations remain withheld"
        )
    if not isinstance(campaign_bindings, Mapping):
        raise IntegratedRiskError("campaign_bindings must be a mapping")
    evidence_gate: dict[str, Any] | None = None
    if evidence_coverage is not None:
        try:
            evidence_gate = build_forecast_facility_campaign_evidence_gate(evidence_coverage)
        except Exception as error:
            raise IntegratedRiskError(f"forecast evidence coverage gate is invalid: {error}") from error
        if evidence_gate["downstream_campaign_input_allowed"] is not True:
            raise IntegratedRiskError(
                "forecast facility campaign is withheld by incomplete quantitative evidence coverage"
            )

    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(forecast_scan.get("scenario_entries", ())):
        if not isinstance(raw, Mapping):
            raise IntegratedRiskError(f"forecast_scan.scenario_entries[{index}] must be a mapping")
        trigger_type = raw.get("trigger_type")
        if trigger_type not in {"RISK_CONDITION_REACHED", "ACTIVE_CONDITION_RECHECK"}:
            continue
        component_id = _name(raw.get("component_id"), f"scenario_entries[{index}].component_id")
        scenario_id = _name(raw.get("scenario_id"), f"scenario_entries[{index}].scenario_id")
        try:
            forecast_time_s = float(raw.get("forecast_time_s"))
        except (TypeError, ValueError) as error:
            raise IntegratedRiskError(
                f"scenario_entries[{index}].forecast_time_s must be finite and non-negative"
            ) from error
        if not math.isfinite(forecast_time_s) or forecast_time_s < 0.0:
            raise IntegratedRiskError(
                f"scenario_entries[{index}].forecast_time_s must be finite and non-negative"
            )
        key = _forecast_trigger_key(component_id, scenario_id, forecast_time_s)
        if key in {row["key"] for row in entries}:
            raise IntegratedRiskError(f"duplicate forecast quantitative trigger: {key}")
        evaluation = raw.get("evaluation")
        if not isinstance(evaluation, Mapping) or evaluation.get("status") != "EVALUATED_OPERATOR_LIMITED":
            raise IntegratedRiskError(
                f"forecast trigger {key} lacks an evaluated operator-limited result"
            )
        operating_mode = _name(
            raw.get("operating_mode"),
            f"scenario_entries[{index}].operating_mode",
        )
        entries.append(
            {
                "key": key,
                "component_id": component_id,
                "scenario_id": scenario_id,
                "forecast_time_s": forecast_time_s,
                "operating_mode": operating_mode,
                "trigger_type": trigger_type,
            }
        )

    expected_keys = {row["key"] for row in entries}
    supplied_keys = {str(key) for key in campaign_bindings}
    if supplied_keys != expected_keys:
        missing = sorted(expected_keys - supplied_keys)
        extra = sorted(supplied_keys - expected_keys)
        raise IntegratedRiskError(
            "forecast campaign bindings must cover exactly every quantitative trigger; "
            f"missing={missing}, extra={extra}"
        )
    if not entries:
        return {
            "schema_version": FORECAST_FACILITY_SCHEMA,
            "status": "FORECAST_NO_QUANTITATIVE_TRIGGERS",
            "facility_id": _name(forecast_scan.get("facility_id"), "forecast_scan.facility_id"),
            "forecast_scan_digest": canonical_digest(dict(forecast_scan)),
            "trigger_bindings": [],
            "facility_ledger": None,
            "evidence_gate": evidence_gate,
            "policy": {
                "forecast_origin": "model_prediction",
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "facility_qra_promotion": False,
                "physical_validation_claim": False,
                "missing_trigger_substituted_as_zero": False,
            },
        }

    facility_id = _name(forecast_scan.get("facility_id"), "forecast_scan.facility_id")
    normalized_campaigns: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for entry in entries:
        raw_binding = campaign_bindings[entry["key"]]
        if not isinstance(raw_binding, Mapping):
            raise IntegratedRiskError(f"campaign binding must be a mapping: {entry['key']}")
        if _name(raw_binding.get("component_id"), f"campaign_bindings[{entry['key']}].component_id") != entry["component_id"]:
            raise IntegratedRiskError(f"campaign binding component identity mismatch: {entry['key']}")
        if _name(raw_binding.get("scenario_id"), f"campaign_bindings[{entry['key']}].scenario_id") != entry["scenario_id"]:
            raise IntegratedRiskError(f"campaign binding scenario identity mismatch: {entry['key']}")
        try:
            binding_time = float(raw_binding.get("forecast_time_s"))
        except (TypeError, ValueError) as error:
            raise IntegratedRiskError(f"campaign binding forecast_time_s is invalid: {entry['key']}") from error
        if not math.isclose(binding_time, entry["forecast_time_s"], rel_tol=0.0, abs_tol=1.0e-12):
            raise IntegratedRiskError(f"campaign binding forecast time mismatch: {entry['key']}")
        binding_mode = raw_binding.get("operating_mode")
        if binding_mode != entry["operating_mode"]:
            raise IntegratedRiskError(f"campaign binding operating mode mismatch: {entry['key']}")
        campaign = raw_binding.get("campaign")
        if not isinstance(campaign, Mapping):
            raise IntegratedRiskError(f"campaign binding has no complete campaign: {entry['key']}")
        if campaign.get("facility_id") != facility_id:
            raise IntegratedRiskError(f"campaign facility identity mismatch: {entry['key']}")
        policy = campaign.get("policy")
        policy = policy if isinstance(policy, Mapping) else {}
        if _has_unsafe_facility_claim(campaign):
            raise IntegratedRiskError(f"unsafe promotion or inference claim in forecast campaign: {entry['key']}")
        event_ids = {
            str(event.get("id"))
            for event in campaign.get("events", ())
            if isinstance(event, Mapping) and event.get("id")
        }
        if seen_event_ids & event_ids:
            raise IntegratedRiskError(
                "forecast campaigns reuse an event ID across prediction times; "
                f"namespace the event IDs explicitly: {sorted(seen_event_ids & event_ids)}"
            )
        seen_event_ids.update(event_ids)
        normalized_campaigns.append(
            {
                "campaign_id": f"forecast:{entry['key']}",
                "result": copy.deepcopy(dict(campaign)),
            }
        )
        trace.append(
            {
                **entry,
                "campaign_id": f"forecast:{entry['key']}",
                "campaign_digest": canonical_digest(dict(campaign)),
                "origin": "model_prediction",
            }
        )

    components = tuple(expected_component_ids) or tuple(sorted({row["component_id"] for row in entries}))
    if len(set(components)) != len(components):
        raise IntegratedRiskError("expected_component_ids must be unique")
    ledger = merge_facility_campaign_results(
        normalized_campaigns,
        expected_component_ids=components,
    )
    return {
        "schema_version": FORECAST_FACILITY_SCHEMA,
        "status": "FORECAST_FACILITY_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "facility_id": facility_id,
        "forecast_scan_digest": canonical_digest(dict(forecast_scan)),
        "trigger_bindings": trace,
        "campaign_results": normalized_campaigns,
        "facility_ledger": ledger,
        "evidence_gate": evidence_gate,
        "policy": {
            "forecast_origin": "model_prediction",
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
            "missing_trigger_substituted_as_zero": False,
            "facility_aggregation_performed": True,
        },
    }


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
    population_binding: Any | None = None,
    facility_campaign_evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    forecast_facility_campaign_evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    forecast_campaign_bindings: Mapping[str, Mapping[str, Any]] | None = None,
    forecast_evidence_coverage: Mapping[str, Any] | None = None,
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
            population_binding=population_binding,
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
            "conditional_current_weather_expected_death_fn": {
                "status": "FORECAST_NOT_REQUESTED",
                "expected_death_fn_low_high": None,
                "frequency_sensitivity_expected_death_fn_low_high": None,
            },
            "facility_annual_ir_available": False,
            "facility_fn_available": False,
            "policy": {
                "diagnostic_only": True,
                "facility_qra_promotion": False,
                "conditional_expected_death_fn_calculated": False,
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

    forecast_evidence_gate: dict[str, Any] | None = None
    if forecast_evidence_coverage is not None:
        try:
            forecast_evidence_gate = build_forecast_facility_campaign_evidence_gate(
                forecast_evidence_coverage
            )
        except Exception as error:
            raise IntegratedRiskError(f"forecast evidence coverage gate is invalid: {error}") from error

    forecast_facility_campaign: dict[str, Any]
    if forecast_facility_campaign_evaluator is not None and forecast_campaign_bindings is not None:
        raise IntegratedRiskError(
            "supply either forecast_facility_campaign_evaluator or forecast_campaign_bindings, not both"
        )
    if forecast_campaign_bindings is not None:
        if forecast_frames is None:
            raise IntegratedRiskError(
                "forecast_campaign_bindings requires forecast_frames"
            )
        if forecast_evidence_gate is not None and not forecast_evidence_gate[
            "downstream_campaign_input_allowed"
        ]:
            forecast_facility_campaign = {
                "status": "WITHHELD_FORECAST_FACILITY_CAMPAIGN_EVIDENCE_COVERAGE",
                "reason": "forecast quantitative evidence coverage is incomplete",
                "evidence_gate": forecast_evidence_gate,
                "policy": {
                    "facility_qra_promotion": False,
                    "frequency_inference_performed": False,
                    "physical_validation_claim": False,
                },
            }
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
                forecast_facility_campaign = build_hazop_forecast_facility_campaign_result(
                    forecast,
                    campaign_bindings=forecast_campaign_bindings,
                    expected_component_ids=tuple(
                        forecast_component_ids or tuple(forecast_tables_by_component or {})
                    ),
                    evidence_coverage=forecast_evidence_coverage,
                )
            except Exception as error:
                forecast_facility_campaign = {
                    "status": "WITHHELD_FORECAST_FACILITY_CAMPAIGN_BINDING_ERROR",
                    "error_type": type(error).__name__,
                    "reason": str(error),
                    "policy": {
                        "facility_qra_promotion": False,
                        "frequency_inference_performed": False,
                        "physical_validation_claim": False,
                    },
                }
    elif forecast_facility_campaign_evaluator is None:
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
    elif forecast_evidence_gate is not None and not forecast_evidence_gate[
        "downstream_campaign_input_allowed"
    ]:
        forecast_facility_campaign = {
            "status": "WITHHELD_FORECAST_FACILITY_CAMPAIGN_EVIDENCE_COVERAGE",
            "reason": "forecast quantitative evidence coverage is incomplete",
            "evidence_gate": forecast_evidence_gate,
            "policy": {
                "facility_qra_promotion": False,
                "frequency_inference_performed": False,
                "physical_validation_claim": False,
            },
        }
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
                unsafe = _has_unsafe_facility_claim(forecast_campaign)
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
                unsafe = _has_unsafe_facility_claim(campaign)
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
        "FORECAST_NO_QUANTITATIVE_TRIGGERS",
        "FORECAST_FACILITY_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED",
        "HAZOP_BRANCH_CAMPAIGNS_BUILT_OPERATOR_LIMITED",
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
        "facility_gate_summary": {
            "current": _facility_gate_summary(facility_campaign),
            "forecast": _facility_gate_summary(forecast_facility_campaign),
        },
        "forecast_evidence_gate": forecast_evidence_gate,
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
    "FORECAST_FACILITY_SCHEMA",
    "IntegratedRiskError",
    "build_hazop_forecast_facility_campaign_result",
    "build_hazop_facility_campaign_evaluator",
    "run_hazop_integrated_risk",
]
