"""Fail-closed IJHE readiness audit for one PRISM campaign.

This module does not certify a QRA.  It collects the existing evidence ledgers
and states whether the declared scope can be presented as complete.  Missing
physical validation, missing accident families, or withheld facility risk are
blocking evidence rather than a zero-valued result.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and value == value and value not in (float("inf"), float("-inf"))


def _check(name: str, passed: bool, evidence: Any, blocking_reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if passed else "BLOCKED",
        "evidence": evidence,
        "blocking_reason": None if passed else blocking_reason,
    }


def build_ijhe_completion_audit(
    current_status: Mapping[str, Any],
    scope_matrix: Mapping[str, Any],
    campaign_result: Mapping[str, Any],
    uncertainty_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an evidence-based readiness report without promoting claims."""
    cases = campaign_result.get("cases", [])
    events = campaign_result.get("events", [])
    timing = campaign_result.get("timing", {})
    fresh_physics_cases = timing.get("fresh_physics_cases")
    executed_cases = [
        row for row in cases
        if isinstance(row, Mapping) and str(row.get("status", "")).startswith("EXECUTED")
    ]
    ledger_cases = [
        row for row in executed_cases
        if isinstance(row.get("termination"), Mapping)
        and _finite(row["termination"].get("time_s"))
        and row["termination"].get("time_s") > 0
        and isinstance(row.get("mass_ledger"), Mapping)
        and _finite(row["mass_ledger"].get("end_to_end_residual_kg"))
    ]
    checks = [
        _check(
            "equipment_state_to_release_to_consequence",
            bool(events) and bool(cases) and bool(executed_cases),
            {
                "generated_event_count": len(events),
                "case_count": len(cases),
                "executed_case_count": len(executed_cases),
            },
            "no executed release-to-consequence case is present",
        ),
        _check(
            "release_duration_isolation_inventory_ledger",
            bool(executed_cases) and len(ledger_cases) == len(executed_cases),
            {
                "executed_case_count": len(executed_cases),
                "cases_with_termination_and_mass_ledger": len(ledger_cases),
                "max_end_to_end_residual_kg": max(
                    (
                        abs(float(row["mass_ledger"]["end_to_end_residual_kg"]))
                        for row in ledger_cases
                    ),
                    default=None,
                ),
            },
            "one or more executed cases lacks a finite release termination time or mass/inventory ledger",
        ),
        _check(
            "declared_major_accident_scope",
            scope_matrix.get("matrix_complete") is True,
            {
                "matrix_status": scope_matrix.get("matrix_complete"),
                "blocking_reasons": scope_matrix.get("blocking_reasons", []),
                "required_family_count": len(scope_matrix.get("required_families", [])),
            },
            "one or more declared accident families are missing, partial, or uncomputed",
        ),
        _check(
            "facility_ir_fn_available",
            campaign_result.get("total_facility_annual_ir_low_high") is not None
            and campaign_result.get("total_facility_expected_death_fn_low_high") is not None,
            {
                "total_facility_annual_ir_low_high": campaign_result.get("total_facility_annual_ir_low_high"),
                "total_facility_expected_death_fn_low_high": campaign_result.get("total_facility_expected_death_fn_low_high"),
            },
            "facility IR/F-N is withheld because the declared facility scope is incomplete or synthetic",
        ),
        _check(
            "physical_validation_evidence",
            current_status.get("physical_validation_claim") is True,
            {
                "physical_validation_claim": current_status.get("physical_validation_claim"),
                "evidence_status": current_status.get("physical_validation_evidence_status"),
            },
            "independent end-to-end physical validation has not been established",
        ),
        _check(
            "frequency_uncertainty_reported",
            uncertainty_result is not None
            and bool(uncertainty_result.get("scenarios"))
            and uncertainty_result.get("facility_credible_interval") is True,
            {
                "uncertainty_result_present": uncertainty_result is not None,
                "scenario_count": len(uncertainty_result.get("scenarios", [])) if uncertainty_result else 0,
                "facility_credible_interval": uncertainty_result.get("facility_credible_interval") if uncertainty_result else None,
            },
            "frequency uncertainty is available only for a known contribution, not the complete facility",
        ),
        _check(
            "processing_time_evidence",
            _finite(timing.get("campaign_elapsed_ms"))
            and isinstance(fresh_physics_cases, int)
            and fresh_physics_cases > 0,
            {
                "fresh_physics_cases": fresh_physics_cases,
                "campaign_elapsed_ms": timing.get("campaign_elapsed_ms"),
                "one_hz_fresh_physics_demonstrated": current_status.get("one_hz_fresh_physics_demonstrated"),
            },
            "fresh-case timing evidence is missing",
        ),
    ]
    blocking = [check["blocking_reason"] for check in checks if check["blocking_reason"]]
    complete = not blocking
    return {
        "schema_version": "prism.ijhe_completion_audit.v1",
        "status": "READY_FOR_IJHE_SCOPE" if complete else "INCOMPLETE_EVIDENCE",
        "checks": checks,
        "blocking_reasons": blocking,
        "physical_validation_claim": False if not complete else True,
        "complete_facility_qra_claim": complete,
        "interpretation": "Readiness evidence gate; a blocked check is not treated as zero risk or as an implicit accident substitution.",
    }
