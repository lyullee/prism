"""Build the v0.6.0 IJHE readiness report from existing audit ledgers.

The report is an aggregation layer for reviewers.  It does not rerun a source,
dispersion, ignition, or risk model and it never converts conditional
diagnostics into a qualified facility QRA.  Its purpose is to put equipment,
accident-family, facility, frequency, timing, and evidence gates in one
versioned record.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


READINESS_SCHEMA = "prism.v060_ijhe_readiness_report.v1"


class V060ReadinessError(ValueError):
    """Raised when a required readiness input is malformed."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise V060ReadinessError(f"{label} must be an object")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise V060ReadinessError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise V060ReadinessError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _check_row(check: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": check.get("id") or check.get("name"),
        "status": check.get("status"),
        "blocking_reason": check.get("blocking_reason"),
        "evidence_paths": list(check.get("evidence_paths", ()))
        if isinstance(check.get("evidence_paths"), Sequence)
        and not isinstance(check.get("evidence_paths"), (str, bytes))
        else [],
    }


def _component_rows(facility: Mapping[str, Any]) -> list[dict[str, Any]]:
    coverage = facility.get("conditional_diagnostic_facility_coverage")
    if not isinstance(coverage, Mapping):
        return []
    accounting = coverage.get("component_case_accounting")
    if not isinstance(accounting, Mapping):
        return []
    result: list[dict[str, Any]] = []
    for component_id, raw in sorted(accounting.items()):
        if not isinstance(raw, Mapping):
            continue
        result.append(
            {
                "component_id": str(component_id),
                "status": raw.get("status"),
                "event_count": raw.get("event_count"),
                "conditional_case_count": raw.get("conditional_case_count"),
                "conditional_executed_case_count": raw.get("conditional_executed_case_count"),
                "not_numerically_executed_case_count": raw.get("not_numerically_executed_case_count"),
                "qualified_evidence_withheld_case_count": raw.get("qualified_evidence_withheld_case_count"),
                "risk_atom_count": raw.get("risk_atom_count"),
                "strict_gate_categories": list(raw.get("strict_gate_categories", ()))
                if isinstance(raw.get("strict_gate_categories"), Sequence)
                and not isinstance(raw.get("strict_gate_categories"), (str, bytes))
                else [],
            }
        )
    return result


def _family_rows(scope: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in _rows(scope.get("rows", ()), "scope.rows"):
        result.append(
            {
                "family": raw.get("family"),
                "status": raw.get("status"),
                "conditional_status": raw.get("conditional_status"),
                "generated_event_count": raw.get("generated_event_count"),
                "case_count": raw.get("case_count"),
                "conditional_executed_case_count": raw.get("conditional_executed_case_count"),
                "not_numerically_executed_case_count": raw.get("not_numerically_executed_case_count"),
                "qualified_evidence_withheld_case_count": raw.get("qualified_evidence_withheld_case_count"),
                "uncomputed_reasons": list(raw.get("uncomputed_reasons", ()))
                if isinstance(raw.get("uncomputed_reasons"), Sequence)
                and not isinstance(raw.get("uncomputed_reasons"), (str, bytes))
                else [],
            }
        )
    return result


def build_v060_readiness_report(
    *,
    objective_audit: Mapping[str, Any],
    union_verification: Mapping[str, Any],
    scope_matrix: Mapping[str, Any],
    facility_assessment: Mapping[str, Any],
    completion_audit: Mapping[str, Any],
    validation_matrix: Mapping[str, Any],
    realtime_benchmark: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate current v0.6.0 status without changing any promotion gate."""
    objective = _mapping(objective_audit, "objective_audit")
    union = _mapping(union_verification, "union_verification")
    scope = _mapping(scope_matrix, "scope_matrix")
    facility = _mapping(facility_assessment, "facility_assessment")
    completion = _mapping(completion_audit, "completion_audit")
    validation = _mapping(validation_matrix, "validation_matrix")
    realtime = _mapping(realtime_benchmark, "realtime_benchmark")

    objective_checks = {
        str(row.get("id")): _check_row(row)
        for row in _rows(objective.get("checks", ()), "objective_audit.checks")
        if row.get("id") or row.get("name")
    }
    coverage = facility.get("conditional_diagnostic_facility_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    timing = facility.get("timing")
    timing = timing if isinstance(timing, Mapping) else {}
    uncertainty = facility.get("frequency_uncertainty")
    uncertainty = uncertainty if isinstance(uncertainty, Mapping) else {}
    domains = [
        {
            "id": row.get("id"),
            "status": row.get("status"),
            "physical_validation_claim": row.get("physical_validation_claim"),
            "facility_qra_claim": row.get("facility_qra_claim"),
        }
        for row in _rows(validation.get("evidence_domains", ()), "validation_matrix.evidence_domains")
    ]

    family_rows = _family_rows(scope)
    component_rows = _component_rows(facility)
    conditional_chain_complete = objective.get("conditional_chain_complete") is True
    strict_blocked = list(objective.get("strict_blocking_check_ids", ()))
    readiness = {
        "schema_version": READINESS_SCHEMA,
        "release": "PRISM v0.6.0",
        "objective_status": objective.get("status"),
        "completion_audit_status": completion.get("status"),
        "conditional_chain_complete": conditional_chain_complete,
        "strict_blocking_check_ids": strict_blocked,
        "promotion": {
            "facility_total_risk_available": facility.get("facility_total_risk_available") is True,
            "complete_facility_qra_claim": facility.get("complete_facility_qra_claim") is True,
            "qualified_provider_packet_case_count": facility.get("qualified_provider_packet_case_count"),
            "physical_validation_claim": validation.get("physical_validation_claim") is True,
            "frequency_inference_performed": validation.get("frequency_inference_performed") is True,
            "facility_qra_claim": validation.get("facility_qra_claim") is True,
        },
        "chain": {
            "event_count": union.get("merged_event_count"),
            "case_count": union.get("merged_case_count"),
            "risk_atom_count": union.get("merged_risk_atom_count"),
            "conditional_case_count": coverage.get("conditional_case_count"),
            "conditional_executed_case_count": coverage.get("conditional_executed_case_count"),
            "not_numerically_executed_case_count": coverage.get("not_numerically_executed_case_count"),
            "qualified_evidence_withheld_case_count": coverage.get("qualified_evidence_withheld_case_count"),
            "annual_condition_count": coverage.get("annual_condition_count"),
            "scenario_branch_status": coverage.get("scenario_branch_status"),
            "conditional_ir_fn_available": facility.get("conditional_diagnostic_facility_risk_available"),
        },
        "equipment": {
            "component_rows": component_rows,
            "observed_component_count": coverage.get("observed_component_count"),
            "expected_component_count": coverage.get("expected_component_count"),
            "component_status_counts": coverage.get("component_status_counts", {}),
        },
        "accident_families": {
            "required_family_count": len(family_rows),
            "conditional_chain_complete": scope.get("conditional_chain_complete"),
            "strict_matrix_complete": scope.get("matrix_complete"),
            "rows": family_rows,
        },
        "frequency": {
            "scenario_count": uncertainty.get("scenario_count"),
            "correlation_comparison_present": uncertainty.get("correlation_comparison_present"),
            "asset_rank_stability": uncertainty.get("asset_rank_stability"),
            "scenario_family_rank_stability": uncertainty.get("scenario_family_rank_stability"),
            "frequency_inference_performed": union.get("frequency_inference_performed", False),
            "sensor_frequency_learning": False,
        },
        "timing": {
            "cache_p95_ms": realtime.get("cache_p95_ms"),
            "cache_meets_one_hz_all_samples": realtime.get("cache_meets_one_hz_all_samples"),
            "fresh_physics_elapsed_ms": realtime.get("fresh_physics_elapsed_ms"),
            "fresh_physics_meets_one_hz": realtime.get("fresh_physics_meets_one_hz"),
            "campaign_case_p95_ms": timing.get("case_p95_ms"),
            "campaign_case_p99_ms": timing.get("case_p99_ms"),
            "stage_elapsed_ms": timing.get("stage_elapsed_ms", {}),
        },
        "validation_domains": domains,
        "completion_criteria": [
            {
                "id": "A_equipment_state_and_release",
                "status": "CONDITIONAL_PASS" if objective_checks.get("equipment_state_to_native_release", {}).get("status") == "PASS" else "BLOCKED",
                "evidence": objective_checks.get("equipment_state_to_native_release", {}).get("evidence_paths", []),
                "strict_gate_open": False,
            },
            {
                "id": "B_release_to_final_damage",
                "status": "CONDITIONAL_PASS" if objective_checks.get("release_to_final_damage", {}).get("status") == "CONDITIONALLY_COMPLETE" else "BLOCKED",
                "evidence": objective_checks.get("release_to_final_damage", {}).get("evidence_paths", []),
                "strict_gate_open": False,
            },
            {
                "id": "C_facility_ir_fn_and_scope",
                "status": "CONDITIONAL_PASS" if conditional_chain_complete else "BLOCKED",
                "evidence": ["scope_matrix.json", "facility_assessment.json"],
                "strict_gate_open": "strict_facility_scope" not in strict_blocked and "strict_facility_qra" not in strict_blocked,
            },
            {
                "id": "D_literature_frequency_uncertainty",
                "status": "CONDITIONAL_PASS" if objective_checks.get("literature_frequency_uncertainty", {}).get("status") == "CONDITIONALLY_COMPLETE" else "BLOCKED",
                "evidence": objective_checks.get("literature_frequency_uncertainty", {}).get("evidence_paths", []),
                "strict_gate_open": False,
            },
            {
                "id": "E_validation_and_processing_time",
                "status": "CONDITIONAL_PASS" if objective_checks.get("realtime_processing", {}).get("status") == "CONDITIONALLY_COMPLETE" else "BLOCKED",
                "evidence": objective_checks.get("realtime_processing", {}).get("evidence_paths", []),
                "strict_gate_open": "independent_physical_validation" not in strict_blocked,
            },
        ],
        "explicit_exclusions": [
            "field_accident_frequency_collection",
            "sensor_based_frequency_learning",
            "indoor_release_and_confinement",
            "detonation_or_DDT",
            "full_domino_escalation",
        ],
        "interpretation": (
            "The v0.6.0 declared outdoor chain is numerically connected for conditional diagnostics. "
            "Operator-limited cases, missing qualified provider packets, restricted component validation, "
            "and strict facility-QRA gates remain visible and are not replaced by another scenario."
        ),
    }
    return readiness


__all__ = ["READINESS_SCHEMA", "V060ReadinessError", "build_v060_readiness_report"]
