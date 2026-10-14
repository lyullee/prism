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


def _case_key(row: Mapping[str, Any]) -> str:
    """Use the same event × branch × annual-condition grain as the ledger."""

    return "|".join(
        "" if row.get(field) is None else str(row.get(field))
        for field in ("event_id", "release_branch_id", "annual_condition_id")
    )


def _build_release_trace(
    audit: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach case-level release closure to the conditional risk envelope.

    This is a trace export only.  It carries the exact case rows produced by
    ``release_boundary_case_audit`` and adds the number of risk atoms that use
    each case.  It never turns an open or operator-limited row into zero risk
    and never changes the facility-QRA promotion gate.
    """

    rows = audit.get("rows")
    if not isinstance(rows, list):
        raise ValueError("release_boundary_case_audit.rows must be a list")
    atoms = ledger.get("risk_atoms", [])
    if not isinstance(atoms, list):
        atoms = []
    cases = ledger.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    case_timing: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        timing_fields = {
            field: case[field]
            for field in ("elapsed_ms", "stage_elapsed_ms")
            if field in case
        }
        case_timing[_case_key(case)] = timing_fields
    atom_counts: dict[str, dict[str, int]] = {}
    for atom in atoms:
        if not isinstance(atom, Mapping):
            continue
        key = _case_key(atom)
        counts = atom_counts.setdefault(
            key,
            {"risk_atom_count": 0, "nonzero_receptor_harm_atom_count": 0},
        )
        counts["risk_atom_count"] += 1
        harm = atom.get("receptor_harm_low_high")
        if isinstance(harm, Mapping) and any(
            isinstance(bounds, list)
            and any(isinstance(value, (int, float)) and value > 0 for value in bounds)
            for bounds in harm.values()
        ):
            counts["nonzero_receptor_harm_atom_count"] += 1

    selected_summary_fields = (
        "case_count",
        "strict_release_boundary_eligible_case_count",
        "strict_release_boundary_blocked_case_count",
        "numerically_closed_case_count",
        "numerically_open_case_count",
        "operator_review_required_case_count",
        "consequence_domain_truncated_case_count",
        "numerical_closure_status_counts",
        "consequence_domain_status_counts",
        "facility_ir_fn_promotion",
    )
    summary = {
        field: audit.get(field)
        for field in selected_summary_fields
        if field in audit
    }
    summary["risk_atom_count"] = len(atoms)
    trace_rows: list[dict[str, Any]] = []
    trace_fields = (
        "event_id",
        "case_key",
        "release_branch_id",
        "annual_condition_id",
        "asset_id",
        "model_component_id",
        "frequency_port_ids",
        "operating_mode",
        "hazop_scenario_id",
        "scenario_families",
        "status",
        "termination",
        "release_duration_s",
        "available_mass_kg",
        "cumulative_mass_out_kg",
        "residual_mass_kg",
        "residual_fraction",
        "isolation_status",
        "inventory_status",
        "end_to_end_residual_kg",
        "release_termination_reasons",
        "operational_execution_reasons",
        "consequence_domain_reasons",
        "numerical_release_closed",
        "numerical_closure_status",
        "consequence_domain_status",
        "provider_input_origins",
        "strict_release_boundary_eligible",
        "strict_release_boundary_status",
        "release_boundary_blocking_reasons",
        "provider_qualification_status",
        "provider_qualification_blocking_reasons",
        "facility_qra_promotion_eligible",
        "facility_qra_promotion_status",
    )
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            raise ValueError("release_boundary_case_audit.rows must contain objects")
        row = {field: raw_row[field] for field in trace_fields if field in raw_row}
        key = str(raw_row.get("case_key") or _case_key(raw_row))
        row["case_key"] = key
        row["risk_atom_accounting"] = atom_counts.get(
            key,
            {"risk_atom_count": 0, "nonzero_receptor_harm_atom_count": 0},
        )
        row["calculation_timing"] = case_timing.get(key, {})
        trace_rows.append(row)
    return {
        "schema_version": "prism.conditional_facility_release_trace.v1",
        "source_schema": audit.get("schema_version"),
        "source_status": audit.get("status"),
        "case_key_definition": audit.get(
            "case_key_definition",
            "event_id|release_branch_id|annual_condition_id",
        ),
        "summary": summary,
        "rows": trace_rows,
        "semantics": {
            "role": "case-level release-to-risk trace for digital-twin consumers",
            "duration_and_inventory": (
                "rows preserve provider release duration, initial mass, cumulative outflow, "
                "residual mass and residual fraction"
            ),
            "risk_atom_accounting": (
                "risk_atom_count counts consequence atoms using the same case key; zero "
                "means no atom was linked, not zero physical risk"
            ),
            "promotion": (
                "diagnostic trace only; strict release closure, provider qualification, "
                "physical validation and facility IR/F-N promotion remain separate gates"
            ),
        },
    }


def build_conditional_facility_risk_view(
    assessment: Mapping[str, Any],
    provider_mass_balance_audit: Mapping[str, Any] | None = None,
    release_boundary_case_audit: Mapping[str, Any] | None = None,
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
    release_audit = release_boundary_case_audit
    if release_audit is None:
        embedded = source.get("release_boundary_case_audit")
        release_audit = embedded if isinstance(embedded, Mapping) else None
    release_trace = (
        _build_release_trace(release_audit, ledger)
        if release_audit is not None
        else None
    )

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
        "timing": source.get("timing"),
        "component_contributions": dict(component_contributions),
        "component_risk_ranking": source.get("component_risk_ranking"),
        "scenario_family_contributions": dict(family_contributions),
        "scenario_branch_accounting": dict(branch_accounting),
        "release_termination_inventory_ledger": dict(release_ledger),
        "release_trace": release_trace,
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
