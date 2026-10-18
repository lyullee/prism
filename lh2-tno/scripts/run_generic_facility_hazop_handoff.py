"""Run the generic outdoor-LH2 forecast HAZOP-to-quantitative handoff.

This is a facility-neutral digital-twin seam.  Each forecast frame carries an
explicit component and operating mode; the reviewed HAZOP table selects a
scenario when a declared deviation is reached.  The resulting worklist names
the provider-release, literature-frequency, SLABx-LH2, and facility-condition
inputs required for quantitative evaluation.  It deliberately does not
invent a release, learn a frequency, run consequence physics, or promote a
facility IR/F-N result.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.forecast_handoff import build_forecast_quantitative_handoff  # noqa: E402
from lh2_tno.hazop import evaluate_hazop  # noqa: E402
from lh2_tno.hazop_forecast import run_hazop_forecast_risk_scan  # noqa: E402


SCHEMA = "prism.generic_outdoor_facility_hazop_handoff.v1"

_REQUIRED_CONTRACT = {
    "provider_release_packet": [
        "source_digest", "release_start_s", "release_end_s", "duration_s",
        "termination_basis", "isolation_time_s", "post_isolation_observation_s",
        "inventory_initial_kg", "inventory_out_kg", "mass_residual_kg",
    ],
    "frequency_binding": [
        "literature_event_id", "annual_frequency", "annual_frequency_low",
        "annual_frequency_high", "source_provenance",
    ],
    "slabx_lh2_consequence": [
        "result_digest", "weather_condition_id", "ignition_branch_id",
        "receptor_damage_or_harm_outputs", "processing_time_ms",
    ],
    "facility_condition_binding": [
        "population_condition_id", "weather_condition_id", "ignition_branch_id",
        "facility_port_or_endpoint_id",
    ],
}

_REQUIRED_EVIDENCE_BLOCKS = tuple(_REQUIRED_CONTRACT)
_RELEASE_RESIDUAL_TOLERANCE_KG = 1.0e-8


def _load(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def _frames(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        value = value.get("frames")
    if not isinstance(value, list) or not value or not all(isinstance(row, Mapping) for row in value):
        raise ValueError("forecast input must be a non-empty array of frame objects")
    return list(value)


def _current_quantitative_handoff(
    frames: Any,
    tables: Mapping[str, Any],
    *,
    expected_component_ids: list[str],
) -> dict[str, Any]:
    """Select current-state scenarios and turn them into explicit work items."""
    rows = _frames(frames)
    seen_components: set[str] = set()
    requests: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    for index, frame in enumerate(rows):
        component_id = str(frame.get("component_id") or "")
        if component_id not in expected_component_ids:
            raise ValueError(f"current frame {index} references an unexpected component: {component_id}")
        if component_id in seen_components:
            raise ValueError(f"current frames must contain one frame per component: {component_id}")
        seen_components.add(component_id)
        if frame.get("origin") == "model_prediction" or frame.get("input_origin") == "model_prediction":
            raise ValueError("current frames must not use origin='model_prediction'")
        # Runtime envelopes may carry origin and component identity inside a
        # measurement.  The strict HAZOP state contract keeps those fields at
        # the frame level, so remove only the envelope metadata before the
        # qualitative selector runs.
        state = {
            key: value
            for key, value in frame.items()
            if key not in {"origin", "input_origin", "forecast_time_s"}
        }
        if isinstance(state.get("values"), Mapping):
            state["values"] = {
                tag: {
                    key: value
                    for key, value in raw.items()
                    if key != "component_id"
                }
                if isinstance(raw, Mapping) else raw
                for tag, raw in state["values"].items()
            }
        selection = evaluate_hazop(tables[component_id], state)
        selections.append(selection)
        for scenario in selection.get("selected_scenarios", ()):
            scenario_id = str(scenario["scenario_id"])
            captured_at_s = float(frame["captured_at_s"])
            request_id = f"current|{component_id}|{scenario_id}|{captured_at_s:g}"
            requests.append({
                "request_id": request_id,
                "facility_id": selection["facility_id"],
                "component_id": component_id,
                "scenario_id": scenario_id,
                "captured_at_s": captured_at_s,
                "operating_mode": scenario["operating_mode"],
                "scenario_family": scenario["scenario_family"],
                "release_mode": scenario["release_mode"],
                "source_trigger_type": "CURRENT_HAZOP_DEVIATION",
                "current_evaluation_status": "WITHHELD_NO_QUANTITATIVE_EVALUATOR",
                "required_inputs": [
                    "qualified_provider_release_packet",
                    "reviewed_literature_frequency_binding",
                    "SLABx-LH2_consequence_result",
                    "facility_annual_condition_population_ignition_binding",
                ],
                "required_contract": _REQUIRED_CONTRACT,
                "status": "READY_FOR_QUANTITATIVE_EVALUATION",
            })
    missing = sorted(set(expected_component_ids) - seen_components)
    if missing:
        raise ValueError(f"current frames are missing components: {missing}")
    return {
        "status": "CURRENT_HAZOP_SELECTION_COMPLETE",
        "component_count": len(expected_component_ids),
        "selected_scenario_count": len(requests),
        "selections": selections,
        "requests": requests,
        "summary": {
            "request_count": len(requests),
            "ready_for_quantitative_evaluation_count": len(requests),
            "review_required_count": 0,
        },
        "policy": {
            "operating_mode_taken_from_input": True,
            "operating_mode_inferred": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "slabx_lh2_calculated": False,
            "facility_ir_fn_calculated": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
    }


def _evidence_coverage(
    requests: list[Mapping[str, Any]],
    attachments: Any | None = None,
) -> dict[str, Any]:
    """Audit exact-keyed quantitative evidence for either state path."""
    if attachments is None:
        attachments = {}
    if not isinstance(attachments, Mapping):
        raise ValueError("quantitative evidence attachments must be a mapping")
    expected: set[str] = set()
    rows: list[dict[str, Any]] = []
    for request in requests:
        request_id = str(request.get("request_id") or "")
        if not request_id or request_id in expected:
            raise ValueError("quantitative requests require unique non-empty request_id values")
        expected.add(request_id)
        contract = request.get("required_contract")
        if not isinstance(contract, Mapping):
            raise ValueError(f"request {request_id} is missing required_contract")
        attachment = attachments.get(request_id)
        missing: list[str] = []
        malformed: str | None = None
        if attachment is None:
            missing = [
                f"{block}.{field}"
                for block in _REQUIRED_EVIDENCE_BLOCKS
                for field in contract.get(block, ())
            ]
            malformed = "attachment_missing"
        elif not isinstance(attachment, Mapping):
            malformed = "attachment_not_mapping"
        else:
            evidence = attachment.get("evidence")
            if not isinstance(evidence, Mapping):
                malformed = "evidence_not_mapping"
            else:
                for block in _REQUIRED_EVIDENCE_BLOCKS:
                    value = evidence.get(block)
                    if not isinstance(value, Mapping):
                        missing.extend(
                            f"{block}.{field}" for field in contract.get(block, ())
                        )
                        continue
                    if not isinstance(value.get("status"), str) or not value["status"].strip():
                        missing.append(f"{block}.status")
                    missing.extend(
                        f"{block}.{field}"
                        for field in contract.get(block, ())
                        if field not in value
                    )
        rows.append({
            "request_id": request_id,
            "component_id": request.get("component_id"),
            "scenario_id": request.get("scenario_id"),
            "operating_mode": request.get("operating_mode"),
            "forecast_time_s": request.get("forecast_time_s"),
            "captured_at_s": request.get("captured_at_s"),
            "status": (
                "EVIDENCE_COMPLETE"
                if not missing and malformed is None
                else "MISSING_EVIDENCE"
            ),
            "missing_fields": sorted(set(missing)),
            "malformed_reason": malformed,
        })
    extra = sorted(set(attachments) - expected)
    complete_count = sum(row["status"] == "EVIDENCE_COMPLETE" for row in rows)
    return {
        "schema_version": "prism.generic_quantitative_evidence_coverage.v1",
        "status": (
            "QUANTITATIVE_EVIDENCE_COVERAGE_COMPLETE"
            if rows and complete_count == len(rows) and not extra
            else "WITHHELD_QUANTITATIVE_EVIDENCE_MISSING"
        ),
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
            "slabx_lh2_calculated": False,
            "facility_ir_fn_calculated": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
    }


def _provider_release_boundary_audit(provider: Any) -> dict[str, Any]:
    """Check the explicit release clock and termination evidence.

    The generic attachment contains a provider-owned release summary rather
    than the full strict release packet.  This audit therefore only checks
    fields that are present; it never turns a residual inventory into zero or
    infers pressure-equalization evidence from a short history.
    """

    if not isinstance(provider, Mapping):
        return {
            "status": "MISSING_PROVIDER_RELEASE_BOUNDARY",
            "valid": False,
            "blocking_reasons": ["provider_release_packet is missing"],
        }
    reasons: list[str] = []

    def finite(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    start = finite(provider.get("release_start_s"))
    end = finite(provider.get("release_end_s"))
    duration = finite(provider.get("duration_s"))
    if start is None or end is None or duration is None or duration <= 0.0:
        reasons.append("release start/end/duration fields are incomplete or invalid")
    elif not math.isclose(end - start, duration, rel_tol=0.0, abs_tol=1.0e-9):
        reasons.append("release_end_s does not equal release_start_s + duration_s")

    basis = provider.get("termination_basis")
    if basis == "inventory_depletion":
        inventory_status = provider.get("inventory_status")
        if inventory_status != "INVENTORY_CLOSED":
            reasons.append(
                "inventory_depletion is declared but inventory_status is not INVENTORY_CLOSED"
            )
        residual = finite(provider.get("mass_residual_kg"))
        if residual is not None and abs(residual) > _RELEASE_RESIDUAL_TOLERANCE_KG:
            reasons.append(
                "inventory_depletion is declared but mass_residual_kg remains above tolerance"
            )
    elif basis == "reviewed_isolation_success":
        isolation = finite(provider.get("isolation_time_s"))
        if isolation is None:
            reasons.append("reviewed_isolation_success requires isolation_time_s")
        elif duration is not None and isolation > duration + 1.0e-9:
            reasons.append("isolation_time_s exceeds the provider release duration")
    elif basis == "model_pressure_equalization":
        reasons.append(
            "model_pressure_equalization requires the explicit pressure-equalization observation set"
        )
    elif not isinstance(basis, str) or not basis.strip():
        reasons.append("termination_basis is missing")

    return {
        "status": "VALID_DIAGNOSTIC_BOUNDARY" if not reasons else "BOUNDARY_EVIDENCE_WITHHELD",
        "valid": not reasons,
        "blocking_reasons": list(dict.fromkeys(reasons)),
    }


def _diagnostic_quantitative_evaluation(
    requests: list[Mapping[str, Any]],
    attachments: Any | None,
    *,
    path: str,
) -> dict[str, Any]:
    """Expose exact attached consequence results at the generic facility seam.

    This is an evidence-bound handoff, not a new physics calculation.  The
    provider and consequence records are copied only after the same request
    key has passed the four-block coverage contract.  A missing literature
    rate remains visible; it is never replaced with a value inferred from a
    sensor or from a neighbouring event.
    """
    attachments = attachments if isinstance(attachments, Mapping) else {}
    rows: list[dict[str, Any]] = []
    for request in requests:
        request_id = str(request.get("request_id") or "")
        attachment = attachments.get(request_id)
        evidence = attachment.get("evidence") if isinstance(attachment, Mapping) else None
        provider = evidence.get("provider_release_packet") if isinstance(evidence, Mapping) else None
        frequency = evidence.get("frequency_binding") if isinstance(evidence, Mapping) else None
        consequence = evidence.get("slabx_lh2_consequence") if isinstance(evidence, Mapping) else None
        facility = evidence.get("facility_condition_binding") if isinstance(evidence, Mapping) else None
        outputs = consequence.get("receptor_damage_or_harm_outputs") if isinstance(consequence, Mapping) else None
        complete = (
            isinstance(provider, Mapping)
            and isinstance(frequency, Mapping)
            and isinstance(consequence, Mapping)
            and isinstance(facility, Mapping)
            and isinstance(outputs, Mapping)
        )
        chain_executed = bool(outputs.get("full_chain_executed")) if isinstance(outputs, Mapping) else False
        provider_boundary_audit = _provider_release_boundary_audit(provider)
        annual_frequency = frequency.get("annual_frequency") if isinstance(frequency, Mapping) else None
        frequency_bound = isinstance(annual_frequency, (int, float)) and not isinstance(annual_frequency, bool)
        if not complete:
            status = "WITHHELD_QUANTITATIVE_EVIDENCE_MISSING"
        elif not chain_executed:
            status = "WITHHELD_CONSEQUENCE_CHAIN_NOT_EXECUTED"
        elif not frequency_bound:
            status = "CONDITIONAL_CHAIN_ATTACHED_FREQUENCY_VALUE_WITHHELD"
        else:
            status = "CONDITIONAL_QUANTITATIVE_RISK_ATTACHED"
        rows.append({
            "path": path,
            "request_id": request_id,
            "component_id": request.get("component_id"),
            "scenario_id": request.get("scenario_id"),
            "operating_mode": request.get("operating_mode"),
            "scenario_family": request.get("scenario_family"),
            "status": status,
            "provider_source_digest": provider.get("source_digest") if isinstance(provider, Mapping) else None,
            "provider_release_boundary": {
                key: provider.get(key)
                for key in (
                    "release_start_s", "release_end_s", "duration_s",
                    "termination_basis", "isolation_time_s",
                    "inventory_initial_kg", "inventory_out_kg", "mass_residual_kg",
                    "inventory_status",
                )
            } if isinstance(provider, Mapping) else None,
            "provider_release_boundary_status": provider_boundary_audit["status"],
            "provider_release_boundary_valid": provider_boundary_audit["valid"],
            "provider_release_boundary_blocking_reasons": provider_boundary_audit[
                "blocking_reasons"
            ],
            "literature_event_id": frequency.get("literature_event_id") if isinstance(frequency, Mapping) else None,
            "annual_frequency": annual_frequency,
            "frequency_source_provenance": frequency.get("source_provenance") if isinstance(frequency, Mapping) else None,
            "frequency_inference_performed": bool(frequency.get("frequency_inference_performed")) if isinstance(frequency, Mapping) else False,
            "slabx_lh2_result_digest": consequence.get("result_digest") if isinstance(consequence, Mapping) else None,
            "weather_condition_id": consequence.get("weather_condition_id") if isinstance(consequence, Mapping) else None,
            "ignition_branch_id": consequence.get("ignition_branch_id") if isinstance(consequence, Mapping) else None,
            "chain_stages": list(outputs.get("stages", ())) if isinstance(outputs, Mapping) else [],
            "processing_time_ms": consequence.get("processing_time_ms") if isinstance(consequence, Mapping) else None,
            "facility_ir_fn_available": bool(facility.get("facility_ir_fn_available")) if isinstance(facility, Mapping) else False,
            "facility_qra_promotion": bool(facility.get("facility_qra_promotion")) if isinstance(facility, Mapping) else False,
            "physical_validation_claim": bool(outputs.get("physical_validation_claim")) if isinstance(outputs, Mapping) else False,
            "diagnostic_only": True,
        })
    status_counts = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    attached_count = sum(
        row["status"] in {
            "CONDITIONAL_QUANTITATIVE_RISK_ATTACHED",
            "CONDITIONAL_CHAIN_ATTACHED_FREQUENCY_VALUE_WITHHELD",
        }
        for row in rows
    )
    return {
        "schema_version": "prism.generic_diagnostic_quantitative_evaluation.v1",
        "path": path,
        "status": (
            "CONDITIONAL_DIAGNOSTIC_EVALUATION_AVAILABLE"
            if attached_count
            else "WITHHELD_QUANTITATIVE_EVALUATION"
        ),
        "rows": rows,
        "summary": {
            "request_count": len(rows),
            "diagnostic_chain_attached_count": attached_count,
            "frequency_bound_count": sum(row["status"] == "CONDITIONAL_QUANTITATIVE_RISK_ATTACHED" for row in rows),
            "frequency_value_withheld_count": sum(row["status"] == "CONDITIONAL_CHAIN_ATTACHED_FREQUENCY_VALUE_WITHHELD" for row in rows),
            "release_boundary_valid_count": sum(
                row["provider_release_boundary_valid"] for row in rows
            ),
            "release_boundary_withheld_count": sum(
                not row["provider_release_boundary_valid"] for row in rows
            ),
            "status_counts": status_counts,
        },
        "policy": {
            "evidence_reused_without_new_physics": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_ir_fn_calculated": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
            "diagnostic_only": True,
        },
    }


def build_handoff(
    frames: Any,
    tables: Mapping[str, Any],
    current_frames: Any | None = None,
    current_attachments: Any | None = None,
    forecast_attachments: Any | None = None,
) -> dict[str, Any]:
    """Build a generic multi-component HAZOP scan and quantitative worklist."""
    rows = _frames(frames)
    if not isinstance(tables, Mapping) or not tables:
        raise ValueError("tables must be a non-empty component-keyed object")
    component_ids = sorted(str(row.get("component_id") or "") for row in rows)
    component_ids = sorted(set(component_ids))
    if not component_ids or any(not value for value in component_ids):
        raise ValueError("every forecast frame requires component_id")
    if set(tables) != set(component_ids):
        raise ValueError(
            "tables must cover exactly the forecast components; "
            f"expected={component_ids}, actual={sorted(tables)}"
        )
    facility_ids = {str(row.get("facility_id") or "") for row in rows}
    if len(facility_ids) != 1 or not next(iter(facility_ids)):
        raise ValueError("all forecast frames must use one non-empty facility_id")
    facility_id = next(iter(facility_ids))
    scan = run_hazop_forecast_risk_scan(
        facility_id=facility_id,
        tables_by_component={component_id: tables[component_id] for component_id in component_ids},
        forecast_frames=rows,
        expected_component_ids=component_ids,
    )
    handoff = build_forecast_quantitative_handoff(scan)
    current_handoff = (
        _current_quantitative_handoff(
            current_frames,
            tables,
            expected_component_ids=component_ids,
        )
        if current_frames is not None
        else {
            "status": "CURRENT_HAZOP_INPUT_NOT_SUPPLIED",
            "component_count": 0,
            "selected_scenario_count": 0,
            "selections": [],
            "requests": [],
            "summary": {
                "request_count": 0,
                "ready_for_quantitative_evaluation_count": 0,
                "review_required_count": 0,
            },
            "policy": {
                "operating_mode_taken_from_input": False,
                "operating_mode_inferred": False,
                "frequency_inference_performed": False,
                "sensor_frequency_learning_used": False,
                "provider_release_created": False,
                "slabx_lh2_calculated": False,
                "facility_ir_fn_calculated": False,
                "facility_qra_promotion": False,
                "diagnostic_only": True,
            },
        }
    )
    current_coverage = _evidence_coverage(
        current_handoff["requests"], current_attachments
    )
    forecast_coverage = _evidence_coverage(
        handoff["requests"], forecast_attachments
    )
    current_diagnostic_evaluation = _diagnostic_quantitative_evaluation(
        current_handoff["requests"], current_attachments, path="current"
    )
    forecast_diagnostic_evaluation = _diagnostic_quantitative_evaluation(
        handoff["requests"], forecast_attachments, path="forecast"
    )
    return {
        "schema_version": SCHEMA,
        "facility_id": facility_id,
        "component_ids": component_ids,
        "operating_modes": sorted({str(row.get("operating_mode")) for row in rows}),
        "forecast_time_grid_s": sorted({float(row["forecast_time_s"]) for row in rows}),
        "scan": scan,
        "quantitative_handoff": handoff,
        "current_state_handoff": current_handoff,
        "current_evidence_coverage": current_coverage,
        "forecast_evidence_coverage": forecast_coverage,
        "current_diagnostic_evaluation": current_diagnostic_evaluation,
        "forecast_diagnostic_evaluation": forecast_diagnostic_evaluation,
        "policy": {
            "operating_mode_taken_from_forecast_input": True,
            "operating_mode_inferred": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "slabx_lh2_calculated": False,
            "facility_ir_fn_calculated": False,
            "diagnostic_quantitative_evidence_reused": bool(
                current_diagnostic_evaluation["summary"]["diagnostic_chain_attached_count"]
                or forecast_diagnostic_evaluation["summary"]["diagnostic_chain_attached_count"]
            ),
            "physical_validation_claim": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "This record proves the generic facility state -> operating-mode -> "
            "HAZOP scenario -> quantitative request connection. Each request "
            "remains withheld until reviewed provider, frequency, SLABx-LH2 and "
            "facility-condition evidence is supplied."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument(
        "--current-frames",
        type=Path,
        help="optional historian/runtime state frames; one explicit frame per component",
    )
    parser.add_argument("--current-attachments", type=Path)
    parser.add_argument("--forecast-attachments", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_handoff(
        _load(args.frames),
        _load(args.tables),
        _load(args.current_frames) if args.current_frames is not None else None,
        _load(args.current_attachments) if args.current_attachments is not None else None,
        _load(args.forecast_attachments) if args.forecast_attachments is not None else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scan = result["scan"]
    handoff = result["quantitative_handoff"]
    print(json.dumps({
        "status": result["schema_version"],
        "facility_id": result["facility_id"],
        "component_count": len(result["component_ids"]),
        "trigger_count": scan["trigger_count"],
        "withheld_count": scan["withheld_count"],
        "quantitative_request_count": handoff["summary"]["request_count"],
        "current_quantitative_request_count": result["current_state_handoff"]["summary"]["request_count"],
        "current_evidence_status": result["current_evidence_coverage"]["status"],
        "forecast_evidence_status": result["forecast_evidence_coverage"]["status"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
