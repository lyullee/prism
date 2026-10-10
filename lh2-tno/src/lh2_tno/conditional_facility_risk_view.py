"""Build a reviewable conditional facility risk view.

The facility ledger already calculates a conditional IR/F-N sum from the risk
atoms that reached the consequence chain.  This module exposes that result in
a small, stable envelope for digital-twin consumers and reviewers.  It keeps
the qualification boundary explicit: a conditional view is never promoted to
a qualified facility QRA result merely because the numeric fields exist.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def build_conditional_facility_risk_view(
    assessment: Mapping[str, Any],
    provider_mass_balance_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the conditional facility IR/F-N envelope from an assessment.

    The function deliberately consumes an executed assessment rather than
    rerunning physics.  It requires both conditional IR and F/N outputs and
    retains the source ledger's coverage and qualification gates.  Missing
    cases are reported through the copied coverage/blocker fields; they are
    never converted to zero risk.
    """

    source = _mapping(assessment, "assessment")
    conditional_ir = source.get("conditional_diagnostic_facility_annual_ir_low_high")
    if not isinstance(conditional_ir, Mapping) or not conditional_ir:
        raise ValueError(
            "assessment has no conditional_diagnostic_facility_annual_ir_low_high"
        )
    conditional_fn = source.get("conditional_diagnostic_facility_expected_death_fn_low_high")
    if not isinstance(conditional_fn, list) or len(conditional_fn) != 2:
        raise ValueError(
            "assessment must contain two conditional expected-death F/N endpoints"
        )
    ledger = _mapping(source.get("facility_risk_ledger"), "facility_risk_ledger")
    coverage = _mapping(
        source.get("conditional_diagnostic_facility_coverage"),
        "conditional_diagnostic_facility_coverage",
    )
    component_contributions = ledger.get("component_contributions")
    if not isinstance(component_contributions, Mapping):
        raise ValueError("facility_risk_ledger.component_contributions must be an object")
    family_contributions = ledger.get("scenario_family_contributions")
    if not isinstance(family_contributions, Mapping):
        raise ValueError(
            "facility_risk_ledger.scenario_family_contributions must be an object"
        )
    branch_accounting = source.get("scenario_branch_accounting")
    if not isinstance(branch_accounting, Mapping):
        branch_accounting = ledger.get("scenario_branch_accounting")
    branch_accounting = _mapping(branch_accounting, "scenario_branch_accounting")
    release_ledger = source.get("release_termination_inventory_ledger")
    if not isinstance(release_ledger, Mapping):
        release_ledger = ledger.get("release_termination_inventory_ledger")
    release_ledger = _mapping(
        release_ledger, "release_termination_inventory_ledger"
    )
    mass_balance_audit = None
    if provider_mass_balance_audit is not None:
        mass_balance_audit = _mapping(
            provider_mass_balance_audit, "provider_mass_balance_audit"
        )

    blockers = source.get("provider_qualification_blocking_reasons")
    if not isinstance(blockers, list):
        blockers = []
    strict_release_boundary = source.get("strict_release_boundary")
    if strict_release_boundary is None:
        strict_release_boundary = ledger.get("strict_release_boundary")

    return {
        "schema_version": "prism.conditional_facility_risk_view.v1",
        "status": "CONDITIONAL_DIAGNOSTIC_FACILITY_RISK",
        "facility_id": source.get("facility_id"),
        "source_assessment_schema": source.get("schema_version"),
        "source_assessment_digest": source.get("assessment_digest"),
        "event_count": _nonnegative_int(source.get("event_count", ledger.get("event_count", 0)), "event_count"),
        "case_count": _nonnegative_int(source.get("case_count", ledger.get("case_count", 0)), "case_count"),
        "risk_atom_count": _nonnegative_int(
            coverage.get("risk_atom_count", ledger.get("risk_atom_count", 0)),
            "risk_atom_count",
        ),
        "conditional_diagnostic_facility_risk_available": bool(
            source.get("conditional_diagnostic_facility_risk_available")
        ),
        "conditional_annual_ir_low_high": dict(conditional_ir),
        "conditional_expected_death_fn_low_high": conditional_fn,
        "conditional_expected_death_fn_diagnostics": source.get(
            "conditional_diagnostic_facility_expected_death_fn_diagnostics"
        ),
        "component_contributions": dict(component_contributions),
        "component_risk_ranking": source.get("component_risk_ranking"),
        "scenario_family_contributions": dict(family_contributions),
        "scenario_branch_accounting": dict(branch_accounting),
        "release_termination_inventory_ledger": dict(release_ledger),
        "provider_mass_balance_audit": (
            {
                "schema_version": mass_balance_audit.get("schema_version"),
                "record_count": mass_balance_audit.get("record_count"),
                "status_counts": dict(mass_balance_audit.get("status_counts", {}))
                if isinstance(mass_balance_audit.get("status_counts"), Mapping)
                else {},
                "promotion_allowed": bool(mass_balance_audit.get("promotion_allowed")),
                "diagnostic_only": bool(mass_balance_audit.get("diagnostic_only")),
            }
            if mass_balance_audit is not None
            else None
        ),
        "coverage": dict(coverage),
        "strict_release_boundary": strict_release_boundary,
        "qualification": {
            "facility_total_risk_available": bool(
                source.get("facility_total_risk_available")
            ),
            "qualified_facility_qra_available": bool(
                source.get("qualified_facility_qra_available")
            ),
            "complete_facility_qra_claim": bool(
                source.get("complete_facility_qra_claim")
            ),
            "provider_packet_promoted": bool(source.get("provider_packet_promoted")),
            "provider_packet_case_count": source.get("provider_packet_case_count"),
            "qualified_provider_packet_case_count": source.get(
                "qualified_provider_packet_case_count"
            ),
            "physical_validation_claim": bool(source.get("physical_validation_claim")),
            "synthetic_release_horizon_present": bool(
                ledger.get("synthetic_release_horizon_present")
            ),
            "blocking_reasons": list(blockers),
            "promotion_allowed": False,
            "provider_mass_balance_promotion_allowed": bool(
                mass_balance_audit is not None
                and mass_balance_audit.get("promotion_allowed") is True
            ),
        },
        "semantics": {
            "risk_sum": (
                "conditional IR/F-N is the sum of the risk atoms that reached the "
                "executed consequence ledger"
            ),
            "missing_cases": (
                "missing, operator-limited, or domain-incomplete cases remain visible "
                "in coverage and are not assigned zero risk"
            ),
            "frequency": "explicit supplied literature frequencies only; no inference or learning",
            "promotion": (
                "this envelope is diagnostic-only until qualified provider coverage, "
                "strict scope, and independent physical validation gates close"
            ),
        },
    }


__all__ = ["build_conditional_facility_risk_view"]
