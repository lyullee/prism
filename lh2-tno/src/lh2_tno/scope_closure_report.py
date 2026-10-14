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
        "policy": {
            "missing_accidents_are_not_inferred": True,
            "operator_limited_cases_are_not_qualified": True,
            "frequency_inference_performed": False,
            "provider_packet_promoted": False,
            "physical_validation_claim": bool(
                facility_assessment.get("physical_validation_claim", False)
            ),
            "facility_qra_claim": bool(facility_assessment.get("complete_facility_qra_claim", False)),
        },
        "interpretation": (
            "This report makes the declared outdoor accident scope and all strict-withheld rows visible. "
            "It is a scope/accounting diagnostic and does not promote a partial campaign to a facility QRA."
        ),
    }
