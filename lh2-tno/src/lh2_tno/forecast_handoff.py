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
EVIDENCE_COVERAGE_SCHEMA = "prism.forecast_quantitative_evidence_coverage.v1"
FACILITY_CAMPAIGN_GATE_SCHEMA = "prism.forecast_facility_campaign_evidence_gate.v1"


class ForecastHandoffError(ValueError):
    """Raised when a forecast scan cannot satisfy the handoff contract."""


_REQUIRED_EVIDENCE = (
    "provider_release_packet",
    "frequency_binding",
    "slabx_lh2_consequence",
    "facility_condition_binding",
)


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
                    "required_contract": {
                        "provider_release_packet": [
                            "source_digest",
                            "release_start_s",
                            "release_end_s",
                            "duration_s",
                            "termination_basis",
                            "isolation_time_s",
                            "post_isolation_observation_s",
                            "inventory_initial_kg",
                            "inventory_out_kg",
                            "mass_residual_kg",
                        ],
                        "frequency_binding": [
                            "literature_event_id",
                            "annual_frequency",
                            "annual_frequency_low",
                            "annual_frequency_high",
                            "source_provenance",
                        ],
                        "slabx_lh2_consequence": [
                            "result_digest",
                            "weather_condition_id",
                            "ignition_branch_id",
                            "receptor_damage_or_harm_outputs",
                            "processing_time_ms",
                        ],
                        "facility_condition_binding": [
                            "population_condition_id",
                            "weather_condition_id",
                            "ignition_branch_id",
                            "facility_port_or_endpoint_id",
                        ],
                    },
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


def attach_forecast_quantitative_evidence(
    handoff: Mapping[str, Any],
    attachments: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach exact-keyed downstream evidence without promoting facility QRA.

    ``attachments`` is keyed by the request IDs emitted by
    :func:`build_forecast_quantitative_handoff`. Each value must contain an
    ``evidence`` mapping with all four required evidence blocks. The blocks are
    preserved verbatim for the qualified provider/facility owner; this helper
    does not run physics, infer frequency, or decide qualification.
    """
    if not isinstance(handoff, Mapping) or handoff.get("schema_version") != SCHEMA:
        raise ForecastHandoffError("handoff has an unsupported schema_version")
    requests = handoff.get("requests")
    if not isinstance(requests, list) or not requests:
        raise ForecastHandoffError("handoff.requests must be a non-empty list")
    if not isinstance(attachments, Mapping):
        raise ForecastHandoffError("attachments must be a mapping keyed by request_id")
    expected = {request.get("request_id") for request in requests if isinstance(request, Mapping)}
    if len(expected) != len(requests) or None in expected:
        raise ForecastHandoffError("handoff requests must contain unique request_id values")
    actual = set(attachments)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ForecastHandoffError(
            f"attachment keys must exactly match handoff requests; missing={missing}, extra={extra}"
        )
    attached: list[dict[str, Any]] = []
    for request in requests:
        request_id = str(request["request_id"])
        attachment = attachments[request_id]
        if not isinstance(attachment, Mapping):
            raise ForecastHandoffError(f"attachment {request_id} must be a mapping")
        evidence = attachment.get("evidence")
        if not isinstance(evidence, Mapping):
            raise ForecastHandoffError(f"attachment {request_id}.evidence must be a mapping")
        missing_evidence = [name for name in _REQUIRED_EVIDENCE if name not in evidence]
        if missing_evidence:
            raise ForecastHandoffError(
                f"attachment {request_id} is missing evidence blocks: {missing_evidence}"
            )
        contract = request.get("required_contract")
        if not isinstance(contract, Mapping):
            raise ForecastHandoffError(f"request {request_id} is missing required_contract")
        for block_name in _REQUIRED_EVIDENCE:
            block = evidence[block_name]
            if not isinstance(block, Mapping):
                raise ForecastHandoffError(
                    f"attachment {request_id}.{block_name} must be a mapping"
                )
            if not isinstance(block.get("status"), str) or not block["status"].strip():
                raise ForecastHandoffError(
                    f"attachment {request_id}.{block_name}.status is required"
                )
            required_fields = contract.get(block_name)
            if not isinstance(required_fields, list):
                raise ForecastHandoffError(
                    f"request {request_id}.required_contract.{block_name} must be a list"
                )
            missing_fields = [field for field in required_fields if field not in block]
            if missing_fields:
                raise ForecastHandoffError(
                    f"attachment {request_id}.{block_name} is missing fields: {missing_fields}"
                )
        attached.append({
            "request": dict(request),
            "attachment": dict(attachment),
            "evidence_block_names": list(_REQUIRED_EVIDENCE),
            "status": "EVIDENCE_ATTACHED_OPERATOR_LIMITED",
        })
    return {
        "schema_version": "prism.forecast_quantitative_evidence_attachment.v1",
        "status": "FORECAST_QUANTITATIVE_EVIDENCE_ATTACHED_OPERATOR_LIMITED",
        "facility_id": handoff.get("facility_id"),
        "requests": attached,
        "summary": {
            "request_count": len(attached),
            "evidence_attached_count": len(attached),
            "evidence_withheld_count": 0,
        },
        "policy": {
            "exact_request_key_match_required": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "slabx_lh2_calculated": False,
            "facility_ir_fn_calculated": False,
            "provider_qualification_claim": False,
            "independent_physical_validation_claim": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Exact-keyed downstream evidence blocks were attached for every forecast "
            "request. The attachment preserves operator review and does not itself "
            "qualify a provider, run SLABx-LH2, infer frequency or promote facility QRA."
        ),
    }


def audit_forecast_quantitative_evidence_coverage(
    handoff: Mapping[str, Any],
    attachments: Mapping[str, Any],
) -> dict[str, Any]:
    """Report request-by-request evidence gaps without assigning zero risk."""
    if not isinstance(handoff, Mapping) or handoff.get("schema_version") != SCHEMA:
        raise ForecastHandoffError("handoff has an unsupported schema_version")
    requests = handoff.get("requests")
    if not isinstance(requests, list) or not requests:
        raise ForecastHandoffError("handoff.requests must be a non-empty list")
    if not isinstance(attachments, Mapping):
        raise ForecastHandoffError("attachments must be a mapping keyed by request_id")
    rows: list[dict[str, Any]] = []
    expected: set[str] = set()
    for request in requests:
        if not isinstance(request, Mapping):
            raise ForecastHandoffError("handoff requests must be mappings")
        request_id = _name(request.get("request_id"), "request_id")
        if request_id in expected:
            raise ForecastHandoffError(f"duplicate request_id: {request_id}")
        expected.add(request_id)
        contract = request.get("required_contract")
        if not isinstance(contract, Mapping):
            raise ForecastHandoffError(f"request {request_id} is missing required_contract")
        attachment = attachments.get(request_id)
        missing: list[str] = []
        malformed: str | None = None
        if attachment is None:
            missing = [f"{block}.{field}" for block in _REQUIRED_EVIDENCE for field in contract.get(block, ())]
            malformed = "attachment_missing"
        elif not isinstance(attachment, Mapping):
            malformed = "attachment_not_mapping"
        else:
            evidence = attachment.get("evidence")
            if not isinstance(evidence, Mapping):
                malformed = "evidence_not_mapping"
            else:
                for block in _REQUIRED_EVIDENCE:
                    value = evidence.get(block)
                    if not isinstance(value, Mapping):
                        missing.extend(f"{block}.{field}" for field in contract.get(block, ()))
                        continue
                    if not isinstance(value.get("status"), str) or not value["status"].strip():
                        missing.append(f"{block}.status")
                    missing.extend(
                        f"{block}.{field}" for field in contract.get(block, ()) if field not in value
                    )
        rows.append({
            "request_id": request_id,
            "component_id": request.get("component_id"),
            "scenario_id": request.get("scenario_id"),
            "forecast_time_s": request.get("forecast_time_s"),
            "operating_mode": request.get("operating_mode"),
            "status": "EVIDENCE_COMPLETE" if not missing and malformed is None else "MISSING_EVIDENCE",
            "missing_fields": sorted(set(missing)),
            "malformed_reason": malformed,
        })
    extra = sorted(set(attachments) - expected)
    complete_count = sum(row["status"] == "EVIDENCE_COMPLETE" for row in rows)
    return {
        "schema_version": EVIDENCE_COVERAGE_SCHEMA,
        "status": "FORECAST_QUANTITATIVE_EVIDENCE_COVERAGE_AUDITED",
        "facility_id": handoff.get("facility_id"),
        "rows": rows,
        "extra_attachment_keys": extra,
        "summary": {
            "request_count": len(rows),
            "evidence_complete_count": complete_count,
            "evidence_missing_count": len(rows) - complete_count,
            "extra_attachment_key_count": len(extra),
        },
        "policy": {
            "missing_cases_assigned_zero": False,
            "frequency_inference_performed": False,
            "provider_release_created": False,
            "facility_ir_fn_calculated": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Coverage is reported at the exact forecast request key. Missing or "
            "malformed evidence remains an explicit uncomputed case and is not "
            "reallocated or assigned zero risk."
        ),
    }


def build_forecast_facility_campaign_evidence_gate(
    coverage: Mapping[str, Any],
) -> dict[str, Any]:
    """Turn exact-request evidence coverage into a downstream campaign gate.

    The coverage audit is intentionally descriptive.  This gate is the small
    control boundary used by an integrated risk runner: every quantitative
    forecast request must have all provider, frequency, SLABx-LH2 and facility
    condition fields before a forecast campaign binding may enter the facility
    ledger.  It never calculates a consequence or assigns zero risk.
    """
    if not isinstance(coverage, Mapping):
        raise ForecastHandoffError("coverage must be a mapping")
    if coverage.get("schema_version") != EVIDENCE_COVERAGE_SCHEMA:
        raise ForecastHandoffError("coverage has an unsupported schema_version")
    rows = coverage.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ForecastHandoffError("coverage.rows must be a non-empty list")
    extra = coverage.get("extra_attachment_keys")
    if not isinstance(extra, list) or any(not isinstance(value, str) for value in extra):
        raise ForecastHandoffError("coverage.extra_attachment_keys must be a string list")
    request_ids: set[str] = set()
    missing_request_ids: list[str] = []
    complete_count = 0
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ForecastHandoffError(f"coverage.rows[{index}] must be a mapping")
        request_id = _name(row.get("request_id"), f"coverage.rows[{index}].request_id")
        if request_id in request_ids:
            raise ForecastHandoffError(f"duplicate coverage request_id: {request_id}")
        request_ids.add(request_id)
        status = row.get("status")
        if status == "EVIDENCE_COMPLETE" and not row.get("missing_fields") and row.get("malformed_reason") is None:
            complete_count += 1
        else:
            missing_request_ids.append(request_id)
    request_count = len(rows)
    missing_count = request_count - complete_count
    ready = missing_count == 0 and not extra
    return {
        "schema_version": FACILITY_CAMPAIGN_GATE_SCHEMA,
        "status": (
            "FORECAST_FACILITY_CAMPAIGN_READY_FOR_DOWNSTREAM_BINDING"
            if ready
            else "WITHHELD_FORECAST_FACILITY_CAMPAIGN_MISSING_QUANTITATIVE_EVIDENCE"
        ),
        "facility_id": coverage.get("facility_id"),
        "coverage_schema_version": EVIDENCE_COVERAGE_SCHEMA,
        "summary": {
            "request_count": request_count,
            "evidence_complete_count": complete_count,
            "evidence_missing_count": missing_count,
            "extra_attachment_key_count": len(extra),
        },
        "missing_request_ids": sorted(missing_request_ids),
        "extra_attachment_keys": sorted(extra),
        "downstream_campaign_input_allowed": ready,
        "policy": {
            "missing_cases_assigned_zero": False,
            "frequency_inference_performed": False,
            "provider_release_created": False,
            "slabx_lh2_calculated": False,
            "facility_ir_fn_calculated": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "A forecast facility campaign may consume downstream bindings only "
            "when every exact request has complete evidence. Missing evidence "
            "remains withheld and is never replaced by zero risk or another case."
        ),
    }


__all__ = [
    "SCHEMA",
    "EVIDENCE_COVERAGE_SCHEMA",
    "FACILITY_CAMPAIGN_GATE_SCHEMA",
    "ForecastHandoffError",
    "build_forecast_quantitative_handoff",
    "attach_forecast_quantitative_evidence",
    "audit_forecast_quantitative_evidence_coverage",
    "build_forecast_facility_campaign_evidence_gate",
]
