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
        "provider_termination_evidence_status",
        "provider_termination_evidence_used",
        "provider_termination_evidence_basis",
        "provider_termination_evidence_digest",
        "provider_termination_evidence_checks",
        "provider_termination_evidence_blocking_reasons",
        "residual_closure_basis",
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


def _build_frequency_trace(
    frequency_uncertainty: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose literature-frequency scenarios without copying the full ledger.

    The facility assessment stores a large scenario object containing branch
    accounting and every event row.  A digital-twin consumer needs the
    scenario identity, quantile provenance, conditional IR/F-N result and
    rank-stability evidence; this helper exports those fields while keeping
    the no-inference and no-promotion claims explicit.
    """

    raw_scenarios = frequency_uncertainty.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("frequency_uncertainty.scenarios must be a non-empty list")
    scenarios: list[dict[str, Any]] = []
    uncomputed_case_count_by_scenario: dict[str, int] = {}
    uncomputed_case_keys_by_scenario: dict[str, list[str]] = {}
    uncomputed_case_unique_key_count_by_scenario: dict[str, int] = {}
    uncomputed_case_duplicate_row_count_by_scenario: dict[str, int] = {}
    uncomputed_case_status_counts_by_scenario: dict[str, dict[str, int]] = {}
    for raw in raw_scenarios:
        if not isinstance(raw, Mapping):
            raise ValueError("frequency_uncertainty.scenarios must contain objects")
        definition = raw.get("scenario")
        if not isinstance(definition, Mapping):
            raise ValueError("frequency uncertainty scenario definition is missing")
        scenario_id = definition.get("id")
        raw_uncomputed_cases = raw.get("uncomputed_cases")
        uncomputed_cases = (
            raw_uncomputed_cases if isinstance(raw_uncomputed_cases, list) else []
        )
        uncomputed_case_keys: list[str] = []
        status_counts: dict[str, int] = {}
        for raw_case in uncomputed_cases:
            if not isinstance(raw_case, Mapping):
                continue
            case_key = raw_case.get("case_key")
            if not isinstance(case_key, str) or not case_key:
                case_key = _case_key(raw_case)
            uncomputed_case_keys.append(case_key)
            status = raw_case.get("status")
            status_name = str(status) if status is not None else "UNSPECIFIED"
            status_counts[status_name] = status_counts.get(status_name, 0) + 1
        uncomputed_case_count_by_scenario[str(scenario_id)] = len(uncomputed_cases)
        uncomputed_case_keys_by_scenario[str(scenario_id)] = uncomputed_case_keys
        unique_key_count = len(set(uncomputed_case_keys))
        uncomputed_case_unique_key_count_by_scenario[str(scenario_id)] = (
            unique_key_count
        )
        uncomputed_case_duplicate_row_count_by_scenario[str(scenario_id)] = (
            len(uncomputed_case_keys) - unique_key_count
        )
        uncomputed_case_status_counts_by_scenario[str(scenario_id)] = status_counts
        scenario = {
            "id": scenario_id,
            "asset_quantiles": dict(definition.get("asset_quantiles", {}))
            if isinstance(definition.get("asset_quantiles"), Mapping)
            else {},
            "event_quantiles": dict(definition.get("event_quantiles", {}))
            if isinstance(definition.get("event_quantiles"), Mapping)
            else {},
            "provenance": definition.get("provenance"),
            "correlation_assumption": definition.get("correlation_assumption"),
            "conditional_diagnostic_facility_annual_ir_low_high": raw.get(
                "conditional_diagnostic_facility_annual_ir_low_high"
            ),
            "conditional_diagnostic_facility_expected_death_fn_low_high": raw.get(
                "conditional_diagnostic_facility_expected_death_fn_low_high"
            ),
            "conditional_diagnostic_facility_expected_death_fn_diagnostics": raw.get(
                "conditional_diagnostic_facility_expected_death_fn_diagnostics"
            ),
            "conditional_diagnostic_facility_risk_available": raw.get(
                "conditional_diagnostic_facility_risk_available"
            ),
            "asset_known_annual_expected_fatalities_low_high": raw.get(
                "asset_known_annual_expected_fatalities_low_high"
            ),
            "asset_rank_by_known_expected_fatalities_low_high": raw.get(
                "asset_rank_by_known_expected_fatalities_low_high"
            ),
            "scenario_family_known_expected_fatalities_low_high": raw.get(
                "scenario_family_known_expected_fatalities_low_high"
            ),
            "scenario_family_rank_by_known_expected_fatalities_low_high": raw.get(
                "scenario_family_rank_by_known_expected_fatalities_low_high"
            ),
            "event_frequency_per_year": raw.get("event_frequency_per_year"),
            "uncomputed_cases": raw_uncomputed_cases,
            "uncomputed_case_count": len(uncomputed_cases),
            "uncomputed_case_keys": uncomputed_case_keys,
            "uncomputed_case_status_counts": status_counts,
            "provider_packet_promoted": raw.get("provider_packet_promoted"),
            "qualified_provider_packet_case_count": raw.get(
                "qualified_provider_packet_case_count"
            ),
            "complete_facility_qra_claim": raw.get("complete_facility_qra_claim"),
            "physical_validation_claim": raw.get("physical_validation_claim"),
        }
        scenarios.append(scenario)
    frequency_port_binding = frequency_uncertainty.get("frequency_port_binding")
    uncomputed_case_union = {
        case_key
        for case_keys in uncomputed_case_keys_by_scenario.values()
        for case_key in case_keys
    }
    return {
        "schema_version": "prism.conditional_facility_frequency_trace.v1",
        "campaign_digest": frequency_uncertainty.get("campaign_digest"),
        "physical_risk_atoms_digest": frequency_uncertainty.get(
            "physical_risk_atoms_digest"
        ),
        "scenario_count": len(scenarios),
        "scenario_ids": [scenario.get("id") for scenario in scenarios],
        "uncomputed_case_count_by_scenario": uncomputed_case_count_by_scenario,
        "uncomputed_case_unique_key_count_by_scenario": (
            uncomputed_case_unique_key_count_by_scenario
        ),
        "uncomputed_case_duplicate_row_count_by_scenario": (
            uncomputed_case_duplicate_row_count_by_scenario
        ),
        "uncomputed_case_union_count": len(uncomputed_case_union),
        "uncomputed_case_status_counts_by_scenario": (
            uncomputed_case_status_counts_by_scenario
        ),
        "uncomputed_case_policy": (
            "facility-assessment uncomputed_cases are copied with explicit status; "
            "duplicate rows are preserved, no unsupported accident family is substituted, "
            "and no missing case is assigned zero risk"
        ),
        "fresh_physics_executed": frequency_uncertainty.get("fresh_physics_executed"),
        "statistical_confidence_interval": frequency_uncertainty.get(
            "statistical_confidence_interval"
        ),
        "facility_credible_interval": frequency_uncertainty.get(
            "facility_credible_interval"
        ),
        "frequency_port_binding": (
            dict(frequency_port_binding)
            if isinstance(frequency_port_binding, Mapping)
            else None
        ),
        "conditional_diagnostic_facility_risk": frequency_uncertainty.get(
            "conditional_diagnostic_facility_risk"
        ),
        "frequency_inference_allowed": (
            frequency_port_binding.get("frequency_inference_allowed")
            if isinstance(frequency_port_binding, Mapping)
            else None
        ),
        "asset_rank_stability": frequency_uncertainty.get("asset_rank_stability"),
        "scenario_family_rank_stability": frequency_uncertainty.get(
            "scenario_family_rank_stability"
        ),
        "provider_packet_promoted": frequency_uncertainty.get(
            "provider_packet_promoted"
        ),
        "qualified_provider_packet_case_count": frequency_uncertainty.get(
            "qualified_provider_packet_case_count"
        ),
        "complete_facility_qra_claim": frequency_uncertainty.get(
            "complete_facility_qra_claim"
        ),
        "physical_validation_claim": frequency_uncertainty.get(
            "physical_validation_claim"
        ),
        "scenarios": scenarios,
        "semantics": frequency_uncertainty.get("semantics"),
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
    frequency_uncertainty = source.get("frequency_uncertainty")
    if isinstance(frequency_uncertainty, Mapping):
        frequency_uncertainty = dict(frequency_uncertainty)
        frequency_uncertainty["frequency_port_binding"] = source.get(
            "frequency_port_binding", ledger.get("frequency_port_binding")
        )
    frequency_trace = (
        _build_frequency_trace(frequency_uncertainty)
        if isinstance(frequency_uncertainty, Mapping)
        else None
    )
    release_summary = (
        release_trace.get("summary")
        if isinstance(release_trace, Mapping)
        and isinstance(release_trace.get("summary"), Mapping)
        else {}
    )
    strict_release_eligible = release_summary.get(
        "strict_release_boundary_eligible_case_count"
    )
    strict_release_blocked = release_summary.get(
        "strict_release_boundary_blocked_case_count"
    )
    release_gate_closed = (
        isinstance(strict_release_blocked, int) and strict_release_blocked == 0
    )
    if isinstance(release_audit, Mapping) and isinstance(release_summary, Mapping):
        # The facility assessment may predate a later case-level termination
        # evidence reconciliation.  Keep its original gate for provenance,
        # but expose the authoritative external audit counts and reasons so a
        # digital-twin consumer cannot see stale residual blockers.
        source_gate = dict(strict_release_boundary) if isinstance(
            strict_release_boundary, Mapping
        ) else {}
        case_audit_reasons = sorted({
            str(reason)
            for row in release_audit.get("rows", [])
            if isinstance(row, Mapping)
            for reason in row.get("release_boundary_blocking_reasons", [])
            if reason is not None
        })
        strict_release_boundary = dict(source_gate)
        strict_release_boundary.update({
            "source_assessment_gate": source_gate,
            "case_audit_status": release_audit.get("status"),
            "case_count": release_summary.get("case_count"),
            "withheld_case_count": release_summary.get(
                "strict_release_boundary_blocked_case_count"
            ),
            "strict_release_boundary_ready": release_gate_closed,
            "numerically_closed_case_count": release_summary.get(
                "numerically_closed_case_count"
            ),
            "numerically_open_case_count": release_summary.get(
                "numerically_open_case_count"
            ),
            "operator_review_required_case_count": release_summary.get(
                "operator_review_required_case_count"
            ),
            "numerical_closure_status_counts": release_summary.get(
                "numerical_closure_status_counts"
            ),
            "provider_termination_evidence_status_counts": release_audit.get(
                "provider_termination_evidence_status_counts"
            ),
            "provider_termination_evidence_used_case_count": release_audit.get(
                "provider_termination_evidence_used_case_count"
            ),
            "blocking_reasons": case_audit_reasons,
            "provider_qualification_evaluated": False,
            "independent_physical_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_ir_fn_promotion": False,
        })
    provider_case_count = source.get("provider_packet_case_count")
    qualified_provider_case_count = source.get(
        "qualified_provider_packet_case_count"
    )
    provider_gate_closed = (
        source.get("provider_packet_promoted") is True
        and isinstance(provider_case_count, int)
        and provider_case_count > 0
        and qualified_provider_case_count == provider_case_count
    )
    physical_validation_gate_closed = source.get("physical_validation_claim") is True
    facility_ir_fn_gate_closed = (
        source.get("facility_total_risk_available") is True
        and source.get("qualified_facility_qra_available") is True
        and source.get("complete_facility_qra_claim") is True
    )
    promotion_gates = {
        "release_boundary": {
            "status": "PASS_DIAGNOSTIC_ONLY"
            if release_gate_closed
            else "BLOCKED",
            "strict_eligible_case_count": strict_release_eligible,
            "strict_blocked_case_count": strict_release_blocked,
            "promotion_allowed": False,
        },
        "provider_qualification": {
            "status": "PASS_DIAGNOSTIC_ONLY"
            if provider_gate_closed
            else "BLOCKED",
            "provider_packet_case_count": provider_case_count,
            "qualified_provider_packet_case_count": qualified_provider_case_count,
            "provider_packet_promoted": bool(
                source.get("provider_packet_promoted")
            ),
            "promotion_allowed": False,
        },
        "independent_physical_validation": {
            "status": "PASS_DIAGNOSTIC_ONLY"
            if physical_validation_gate_closed
            else "BLOCKED",
            "physical_validation_claim": bool(
                source.get("physical_validation_claim")
            ),
            "promotion_allowed": False,
        },
        "facility_ir_fn": {
            "status": "PASS_DIAGNOSTIC_ONLY"
            if facility_ir_fn_gate_closed
            else "BLOCKED",
            "facility_total_risk_available": bool(
                source.get("facility_total_risk_available")
            ),
            "qualified_facility_qra_available": bool(
                source.get("qualified_facility_qra_available")
            ),
            "complete_facility_qra_claim": bool(
                source.get("complete_facility_qra_claim")
            ),
            "promotion_allowed": False,
        },
        "all_gates_closed": all(
            (
                release_gate_closed,
                provider_gate_closed,
                physical_validation_gate_closed,
                facility_ir_fn_gate_closed,
            )
        ),
        "promotion_allowed": False,
    }

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
        "source_campaign_physics": source.get("source_campaign_physics"),
        "component_contributions": dict(component_contributions),
        "component_risk_ranking": source.get("component_risk_ranking"),
        "scenario_family_contributions": dict(family_contributions),
        "scenario_branch_accounting": dict(branch_accounting),
        "release_termination_inventory_ledger": dict(release_ledger),
        "release_trace": release_trace,
        "frequency_uncertainty": frequency_trace,
        "promotion_gates": promotion_gates,
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
