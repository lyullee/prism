"""Build an explicit outdoor accident-scope closure report.

The facility assessment already keeps conditional numbers and strict-QRA gates
separate.  This helper turns those ledgers into a compact, auditable table so a
reviewer can see which equipment/family rows are complete, operator-limited,
excluded, or still withheld.  It never infers a missing accident or changes a
risk value.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _family_closure(row: Mapping[str, Any]) -> str:
    applicability = row.get("applicability")
    if applicability in {"NOT_APPLICABLE", "EXCLUDED"} or row.get("status") == "EXCLUDED":
        return "EXCLUDED_OR_NOT_APPLICABLE"
    if _as_int(row.get("case_count", row.get("generated_event_count"))) == 0:
        return "NO_GENERATED_CASES"
    if _as_int(row.get("uncomputed_case_count")) > 0 or _as_int(
        row.get("qualified_evidence_withheld_case_count")
    ) > 0:
        return "PARTIAL_STRICT_CASES_WITHHELD"
    if _as_int(row.get("failed_case_count")) > 0 or _as_int(
        row.get("event_without_case_count")
    ) > 0:
        return "BLOCKED_CASE_GAP"
    if _as_int(row.get("fully_validated_case_count")) == _as_int(row.get("case_count")):
        return "CLOSED_DIAGNOSTIC_CASES"
    return "DECLARED_WITHOUT_CLOSURE"


def _component_closure(row: Mapping[str, Any]) -> str:
    status = row.get("status")
    if status == "EXCLUDED":
        return "EXCLUDED_OR_NOT_APPLICABLE"
    if _as_int(row.get("strict_uncomputed_case_count")) > 0 or _as_int(
        row.get("qualified_evidence_withheld_case_count")
    ) > 0:
        return "PARTIAL_STRICT_CASES_WITHHELD"
    if _as_int(row.get("failed_case_count")) > 0:
        return "BLOCKED_CASE_FAILURE"
    if status == "EXECUTED" and _as_int(row.get("strict_uncomputed_case_count")) == 0:
        return "CLOSED_DIAGNOSTIC_CASES"
    return "DECLARED_WITHOUT_CLOSURE"


def build_scope_closure_report(
    scope_matrix: Mapping[str, Any],
    facility_assessment: Mapping[str, Any],
    frequency_scenarios_record: Mapping[str, Any] | None = None,
    hazop_mode_binding_record: Mapping[str, Any] | None = None,
    hazop_selection_event_binding_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact, fail-closed scope/family/component ledger."""
    matrix_rows = scope_matrix.get("rows")
    matrix_rows = matrix_rows if isinstance(matrix_rows, list) else []
    coverage = facility_assessment.get("conditional_diagnostic_facility_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    component_rows_raw = coverage.get("component_case_accounting")
    component_rows_raw = component_rows_raw if isinstance(component_rows_raw, Mapping) else {}
    risk_ledger = facility_assessment.get("facility_risk_ledger")
    risk_ledger = risk_ledger if isinstance(risk_ledger, Mapping) else {}
    uncomputed_rows = risk_ledger.get("uncomputed_cases")
    uncomputed_rows = uncomputed_rows if isinstance(uncomputed_rows, list) else []
    uncomputed_ids = [
        row.get("event_id")
        for row in uncomputed_rows
        if isinstance(row, Mapping) and isinstance(row.get("event_id"), str)
    ]

    family_rows: list[dict[str, Any]] = []
    for row in matrix_rows:
        if not isinstance(row, Mapping):
            continue
        family_rows.append(
            {
                "family": row.get("family"),
                "applicability": row.get("applicability"),
                "status": row.get("status"),
                "conditional_status": row.get("conditional_status"),
                "closure_status": _family_closure(row),
                "event_count": _as_int(row.get("event_count", row.get("generated_event_count"))),
                "case_count": _as_int(row.get("case_count")),
                "executed_case_count": _as_int(row.get("executed_case_count")),
                "fully_validated_case_count": _as_int(row.get("fully_validated_case_count")),
                "strict_uncomputed_case_count": _as_int(row.get("uncomputed_case_count")),
                "operator_limited_case_count": _as_int(row.get("operator_limited_case_count")),
                "domain_incomplete_case_count": _as_int(row.get("domain_incomplete_case_count")),
                "qualified_evidence_withheld_case_count": _as_int(
                    row.get("qualified_evidence_withheld_case_count")
                ),
                "event_ids": list(row.get("event_ids", []))
                if isinstance(row.get("event_ids"), list)
                else [],
                "uncomputed_reasons": list(row.get("uncomputed_reasons", []))
                if isinstance(row.get("uncomputed_reasons"), list)
                else [],
                "strict_gate_categories": list(row.get("strict_gate_categories", []))
                if isinstance(row.get("strict_gate_categories"), list)
                else [],
            }
        )

    component_rows: list[dict[str, Any]] = []
    for component_id, row in sorted(component_rows_raw.items()):
        if not isinstance(row, Mapping):
            continue
        component_rows.append(
            {
                "component_id": component_id,
                "status": row.get("status"),
                "closure_status": _component_closure(row),
                "event_count": _as_int(row.get("event_count")),
                "case_count": _as_int(row.get("conditional_case_count")),
                "numerically_executed_case_count": _as_int(
                    row.get("numerically_executed_case_count")
                ),
                "strict_uncomputed_case_count": _as_int(
                    row.get("strict_uncomputed_case_count")
                ),
                "operator_limited_case_count": _as_int(row.get("operator_limited_case_count")),
                "domain_incomplete_case_count": _as_int(
                    row.get("domain_incomplete_case_count")
                ),
                "qualified_evidence_withheld_case_count": _as_int(
                    row.get("qualified_evidence_withheld_case_count")
                ),
                "strict_gate_categories": list(row.get("strict_gate_categories", []))
                if isinstance(row.get("strict_gate_categories"), list)
                else [],
                "event_ids": list(row.get("event_ids", []))
                if isinstance(row.get("event_ids"), list)
                else [],
            }
        )

    family_status_counts: dict[str, int] = {}
    for row in family_rows:
        status = row["closure_status"]
        family_status_counts[status] = family_status_counts.get(status, 0) + 1
    component_status_counts: dict[str, int] = {}
    for row in component_rows:
        status = row["closure_status"]
        component_status_counts[status] = component_status_counts.get(status, 0) + 1

    strict_boundary = facility_assessment.get("strict_release_boundary")
    strict_boundary = strict_boundary if isinstance(strict_boundary, Mapping) else {}
    frequency_uncertainty = facility_assessment.get("frequency_uncertainty")
    frequency_uncertainty = (
        frequency_uncertainty if isinstance(frequency_uncertainty, Mapping) else {}
    )
    if isinstance(frequency_scenarios_record, Mapping):
        frequency_scenarios = frequency_scenarios_record.get("scenarios")
        frequency_inference_performed = frequency_scenarios_record.get(
            "frequency_inference_performed"
        )
        facility_credible_interval = frequency_scenarios_record.get(
            "facility_credible_interval"
        )
    else:
        frequency_scenarios = frequency_uncertainty.get("scenarios")
        frequency_inference_performed = frequency_uncertainty.get(
            "frequency_inference_performed"
        )
        facility_credible_interval = frequency_uncertainty.get(
            "facility_credible_interval"
        )
    frequency_scenarios = frequency_scenarios if isinstance(frequency_scenarios, list) else []
    timing = facility_assessment.get("timing")
    timing = timing if isinstance(timing, Mapping) else {}
    fresh_physics_cases = timing.get("fresh_physics_cases")
    timing_ready = (
        isinstance(fresh_physics_cases, int)
        and fresh_physics_cases >= 0
        and isinstance(timing.get("campaign_elapsed_ms"), (int, float))
        and timing.get("campaign_elapsed_ms") >= 0
    )
    physical_validation_claim = facility_assessment.get("physical_validation_claim") is True
    provider_blockers = facility_assessment.get("provider_qualification_blocking_reasons")
    provider_blockers = provider_blockers if isinstance(provider_blockers, list) else []
    frequency_uncertainty_ready = bool(frequency_scenarios) and (
        frequency_inference_performed is not True
    )
    evidence_gates = {
        "frequency_uncertainty": {
            "status": "REPORTED" if frequency_uncertainty_ready else "MISSING",
            "scenario_count": len(frequency_scenarios),
            "frequency_inference_performed": frequency_inference_performed,
            "facility_credible_interval": facility_credible_interval,
        },
        "processing_time": {
            "status": "REPORTED" if timing_ready else "MISSING",
            "fresh_physics_cases": fresh_physics_cases,
            "case_median_ms": timing.get("case_median_ms"),
            "case_p95_ms": timing.get("case_p95_ms"),
            "campaign_elapsed_ms": timing.get("campaign_elapsed_ms"),
            "one_hz_claim": False,
        },
        "physical_validation": {
            "status": "CLAIMED" if physical_validation_claim else "WITHHELD",
            "physical_validation_claim": physical_validation_claim,
            "reason": (
                "independent physical-validation evidence is not present"
                if not physical_validation_claim
                else None
            ),
        },
        "release_boundary": {
            "status": "CLOSED" if strict_boundary.get("strict_release_boundary_ready") else "WITHHELD",
            "withheld_case_count": strict_boundary.get("withheld_case_count"),
            "blocking_reasons": list(strict_boundary.get("blocking_reasons", [])),
        },
        "provider_qualification": {
            "status": "QUALIFIED" if facility_assessment.get("provider_packet_promoted") else "WITHHELD",
            "qualified_provider_packet_case_count": facility_assessment.get(
                "qualified_provider_packet_case_count"
            ),
            "blocking_reasons": provider_blockers,
        },
        "hazop_mode_binding": {
            "status": (
                "REPORTED"
                if isinstance(hazop_mode_binding_record, Mapping)
                and hazop_mode_binding_record.get("status")
                == "HAZOP_EVENT_MODE_BINDING_COMPLETE"
                and hazop_mode_binding_record.get("mode_required_event_count") == 0
                and hazop_mode_binding_record.get("scenario_id_required_event_count") == 0
                and hazop_mode_binding_record.get("mode_conflict_event_count") == 0
                and not hazop_mode_binding_record.get("errors")
                else "MISSING"
            ),
            "event_count": (
                hazop_mode_binding_record.get("event_count")
                if isinstance(hazop_mode_binding_record, Mapping)
                else None
            ),
            "mode_bound_event_count": (
                hazop_mode_binding_record.get("mode_bound_event_count")
                if isinstance(hazop_mode_binding_record, Mapping)
                else None
            ),
            "mode_required_event_count": (
                hazop_mode_binding_record.get("mode_required_event_count")
                if isinstance(hazop_mode_binding_record, Mapping)
                else None
            ),
            "scenario_id_required_event_count": (
                hazop_mode_binding_record.get("scenario_id_required_event_count")
                if isinstance(hazop_mode_binding_record, Mapping)
                else None
            ),
            "mode_conflict_event_count": (
                hazop_mode_binding_record.get("mode_conflict_event_count")
                if isinstance(hazop_mode_binding_record, Mapping)
                else None
            ),
            "errors": (
                list(hazop_mode_binding_record.get("errors", []))
                if isinstance(hazop_mode_binding_record, Mapping)
                and isinstance(hazop_mode_binding_record.get("errors", []), list)
                else []
            ),
            "mode_inference_performed": False,
            "scenario_inference_performed": False,
        },
        "hazop_selection_event_binding": {
            "status": (
                "REPORTED"
                if isinstance(hazop_selection_event_binding_record, Mapping)
                and hazop_selection_event_binding_record.get("status")
                == "HAZOP_SELECTION_EVENT_BINDING_COMPLETE"
                and hazop_selection_event_binding_record.get("unbound_event_count") == 0
                and not hazop_selection_event_binding_record.get("errors")
                else "MISSING"
            ),
            "selected_scenario_count": (
                hazop_selection_event_binding_record.get("selected_scenario_count")
                if isinstance(hazop_selection_event_binding_record, Mapping)
                else None
            ),
            "frequency_event_count": (
                hazop_selection_event_binding_record.get("frequency_event_count")
                if isinstance(hazop_selection_event_binding_record, Mapping)
                else None
            ),
            "bound_event_count": (
                hazop_selection_event_binding_record.get("bound_event_count")
                if isinstance(hazop_selection_event_binding_record, Mapping)
                else None
            ),
            "unbound_event_count": (
                hazop_selection_event_binding_record.get("unbound_event_count")
                if isinstance(hazop_selection_event_binding_record, Mapping)
                else None
            ),
            "errors": (
                list(hazop_selection_event_binding_record.get("errors", []))
                if isinstance(hazop_selection_event_binding_record, Mapping)
                and isinstance(hazop_selection_event_binding_record.get("errors", []), list)
                else []
            ),
            "scenario_family_inference_performed": False,
            "frequency_assignment_performed": False,
        },
    }
    return {
        "schema_version": "prism.outdoor_scope_closure_report.v1",
        "facility_id": facility_assessment.get("facility_id"),
        "environment": scope_matrix.get("environment"),
        "scope": scope_matrix.get("scope"),
        "status": (
            "SCOPE_CLOSURE_DIAGNOSTIC_PARTIAL"
            if family_status_counts.get("PARTIAL_STRICT_CASES_WITHHELD", 0)
            or component_status_counts.get("PARTIAL_STRICT_CASES_WITHHELD", 0)
            or not strict_boundary.get("strict_release_boundary_ready", False)
            else "SCOPE_CLOSURE_DIAGNOSTIC_CLOSED"
        ),
        "required_families": list(scope_matrix.get("required_families", [])),
        "declared_family_count": len(family_rows),
        "declared_event_count": _as_int(coverage.get("event_count")),
        "numerically_executed_case_count": _as_int(coverage.get("conditional_executed_case_count")),
        "strict_uncomputed_case_count": _as_int(coverage.get("strict_uncomputed_case_count")),
        "qualified_evidence_withheld_case_count": _as_int(
            coverage.get("qualified_evidence_withheld_case_count")
        ),
        "uncomputed_event_ids": sorted(set(uncomputed_ids)),
        "family_status_counts": family_status_counts,
        "component_status_counts": component_status_counts,
        "family_rows": family_rows,
        "component_rows": component_rows,
        "strict_release_boundary": {
            "ready": strict_boundary.get("strict_release_boundary_ready"),
            "case_count": strict_boundary.get("case_count"),
            "withheld_case_count": strict_boundary.get("withheld_case_count"),
            "blocking_reasons": list(strict_boundary.get("blocking_reasons", [])),
        },
        "evidence_gates": evidence_gates,
        "timing": dict(timing),
        "frequency_uncertainty": {
            "scenario_count": len(frequency_scenarios),
            "scenarios": frequency_scenarios,
            "frequency_inference_performed": frequency_inference_performed,
            "facility_credible_interval": facility_credible_interval,
        },
        "physical_validation": {
            "claim": physical_validation_claim,
            "evidence": facility_assessment.get("physical_validation_evidence"),
        },
        "hazop_mode_binding": (
            dict(hazop_mode_binding_record)
            if isinstance(hazop_mode_binding_record, Mapping)
            else None
        ),
        "hazop_selection_event_binding": (
            dict(hazop_selection_event_binding_record)
            if isinstance(hazop_selection_event_binding_record, Mapping)
            else None
        ),
        "policy": {
            "missing_accidents_are_not_inferred": True,
            "operator_limited_cases_are_not_qualified": True,
            "frequency_inference_performed": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": physical_validation_claim,
            "facility_qra_claim": bool(facility_assessment.get("complete_facility_qra_claim", False)),
            "hazop_mode_inference_performed": False,
            "hazop_scenario_inference_performed": False,
            "hazop_selection_event_family_inference_performed": False,
            "hazop_selection_event_frequency_assignment_performed": False,
        },
        "interpretation": (
            "This report makes the declared outdoor accident scope and all strict-withheld rows visible. "
            "It is a scope/accounting diagnostic and does not promote a partial campaign to a facility QRA."
        ),
    }
