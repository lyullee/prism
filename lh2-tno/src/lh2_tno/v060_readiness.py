"""Build the v0.6.0 IJHE readiness report from existing audit ledgers.

The report is an aggregation layer for reviewers.  It does not rerun a source,
dispersion, ignition, or risk model and it never converts conditional
diagnostics into a qualified facility QRA.  Its purpose is to put equipment,
accident-family, facility, frequency, timing, and evidence gates in one
versioned record.
"""
from __future__ import annotations

from collections import Counter
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


def _scenario_evidence_summary(audit: Mapping[str, Any]) -> dict[str, Any]:
    """Keep scenario-register evidence visible without promoting it to QRA input.

    Both the full ``prism.scenario_evidence_audit.v1`` record and the small,
    tracked screening summary are accepted.  The summary deliberately carries
    only counts and policy flags; it never contains a release rate or a
    frequency inferred from an operating trace.
    """
    files = audit.get("files") if isinstance(audit.get("files"), Mapping) else {}
    summary = audit.get("summary") if isinstance(audit.get("summary"), Mapping) else audit
    candidate_counts = audit.get("candidate_accident_family_counts")
    if not isinstance(candidate_counts, Mapping):
        candidate_counts = summary.get("family_candidate_counts")
    if not isinstance(candidate_counts, Mapping):
        candidate_counts = summary.get("candidate_family_counts")
    candidate_counts = candidate_counts if isinstance(candidate_counts, Mapping) else {}
    signal_counts = audit.get("candidate_monitoring_signal_counts")
    if not isinstance(signal_counts, Mapping):
        signal_counts = summary.get("candidate_monitoring_signal_counts")
    signal_counts = signal_counts if isinstance(signal_counts, Mapping) else {}
    scope_counts = audit.get("scope_status_counts")
    if not isinstance(scope_counts, Mapping):
        scope_counts = summary.get("scope_status_counts")
    scope_counts = scope_counts if isinstance(scope_counts, Mapping) else {}
    policy = audit.get("promotion_policy")
    policy = policy if isinstance(policy, Mapping) else {}
    provider = audit.get("provider_promotion")
    provider = provider if isinstance(provider, Mapping) else {}
    scenario_count = files.get("scenario_rows")
    if scenario_count is None:
        scenario_count = summary.get("record_count")
    if scenario_count is None and isinstance(audit.get("scenario_records"), Sequence):
        scenario_count = len(audit["scenario_records"])
    blocking_reasons = audit.get("blocking_reasons")
    if not isinstance(blocking_reasons, Sequence) or isinstance(blocking_reasons, (str, bytes)):
        blocking_reasons = list(audit.get("limitations", ()))
    qualified_count = provider.get("qualified_packet_count", 0)
    frequency_assigned = provider.get("frequency_assigned")
    if frequency_assigned is None:
        frequency_assigned = policy.get("frequency_applied", False)
    sensor_learning = policy.get("sensor_frequency_learning_used", False)
    facility_claim = policy.get("facility_qra_claim", False)
    return {
        "schema": audit.get("schema") or audit.get("schema_version"),
        "status": audit.get("status"),
        "scenario_row_count": scenario_count,
        "candidate_accident_family_counts": dict(sorted(candidate_counts.items())),
        "candidate_monitoring_signal_counts": dict(sorted(signal_counts.items())),
        "scope_status_counts": dict(sorted(scope_counts.items())),
        "csv_count": files.get("csv_count", audit.get("source_file_count")),
        "workbook_count": files.get("workbook_count"),
        "telemetry_candidate_sheet_count": files.get("telemetry_candidate_sheet_count"),
        "telemetry_metadata_incomplete_sheet_count": files.get("telemetry_metadata_incomplete_sheet_count"),
        "qualified_provider_packet_count": qualified_count,
        "frequency_assigned": frequency_assigned,
        "sensor_frequency_learning_used": sensor_learning,
        "facility_qra_claim": facility_claim,
        "candidate_only": True,
        "blocking_reasons": list(blocking_reasons),
    }


def _release_boundary_summary(facility: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize duration, isolation, inventory, and domain closure evidence.

    This is an accounting view of the already-built facility ledger.  It does
    not infer a termination time or convert a synthetic horizon into a valid
    isolation event.  The explicit status is carried into the readiness report
    so a reviewer can see the release boundary before considering facility
    IR/F-N promotion.
    """
    ledger = facility.get("release_termination_inventory_ledger")
    if not isinstance(ledger, Mapping):
        return {
            "schema": None,
            "status": "NOT_REPORTED",
            "case_count": 0,
            "termination_basis_counts": {},
            "isolation_status_counts": {},
            "inventory_status_counts": {},
            "strict_release_boundary_ready": False,
            "blocking_reasons": [
                "release termination/inventory ledger is not present"
            ],
        }
    rows = ledger.get("rows", ())
    rows = rows if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)) else ()
    summary = ledger.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}

    def _count(field: str) -> dict[str, int]:
        def _value(row: Mapping[str, Any]) -> str:
            if field == "termination_basis":
                termination = row.get("termination")
                if isinstance(termination, Mapping):
                    return str(termination.get("basis", "not_declared"))
            return str(row.get(field, "not_declared"))

        return dict(sorted(Counter(
            _value(row)
            for row in rows
            if isinstance(row, Mapping)
        ).items()))

    termination_counts = _count("termination_basis")
    if not termination_counts:
        termination_counts = dict(summary.get("termination_basis_counts", {}))
    isolation_counts = _count("isolation_status")
    inventory_counts = _count("inventory_status")
    case_count = summary.get("case_count", len(rows))
    try:
        case_count = max(0, int(case_count or 0))
    except (TypeError, ValueError):
        case_count = len(rows)
    withheld = summary.get(
        "withheld_case_count",
        summary.get("operator_limited_or_domain_incomplete_row_count", 0),
    )
    uncomputed = summary.get("uncomputed_row_count", 0)
    synthetic_horizon_count = termination_counts.get("synthetic_diagnostic_horizon", 0)
    not_declared_isolation_count = isolation_counts.get("not_declared", 0)
    blocking: list[str] = []
    if uncomputed:
        blocking.append(f"{uncomputed} release case(s) have no numerical result")
    if withheld:
        blocking.append(f"{withheld} release case(s) are operator/domain limited")
    if synthetic_horizon_count:
        blocking.append(
            f"{synthetic_horizon_count} release case(s) end at a synthetic diagnostic horizon"
        )
    if not_declared_isolation_count:
        blocking.append(
            f"{not_declared_isolation_count} release case(s) have no reviewed isolation status"
        )
    # New facility ledgers expose the gate at the assessment root.  Accept a
    # nested copy as well so older saved ledgers can still be audited without
    # silently rebuilding a different release-boundary policy.
    declared_gate = facility.get("strict_release_boundary")
    if not isinstance(declared_gate, Mapping):
        declared_gate = ledger.get("strict_release_boundary")
    declared_gate = declared_gate if isinstance(declared_gate, Mapping) else None
    if declared_gate is not None:
        gate_blocking = declared_gate.get("blocking_reasons", ())
        if isinstance(gate_blocking, Sequence) and not isinstance(gate_blocking, (str, bytes)):
            blocking.extend(str(reason) for reason in gate_blocking if reason)
    blocking = list(dict.fromkeys(blocking))
    strict_ready = (
        bool(case_count)
        and not blocking
        and (declared_gate is None or declared_gate.get("strict_release_boundary_ready") is True)
    )
    return {
        "schema": ledger.get("schema_version"),
        "facility_gate_schema": (
            declared_gate.get("schema_version") if declared_gate is not None else None
        ),
        "status": (
            "COMPLETE_RELEASE_BOUNDARY_COVERAGE"
            if strict_ready
            else "PARTIAL_RELEASE_BOUNDARY_COVERAGE"
        ),
        "case_count": case_count,
        "provider_packet_consumed_case_count": summary.get(
            "provider_packet_consumed_row_count", 0
        ),
        "complete_row_count": summary.get("complete_row_count", 0),
        "withheld_case_count": withheld,
        "uncomputed_case_count": uncomputed,
        "termination_basis_counts": termination_counts,
        "isolation_status_counts": isolation_counts,
        "inventory_status_counts": inventory_counts,
        "synthetic_horizon_case_count": synthetic_horizon_count,
        "strict_release_boundary_ready": strict_ready,
        "blocking_reasons": blocking,
        "facility_gate_checks": (
            declared_gate.get("checks") if declared_gate is not None else None
        ),
        "promotion_policy": {
            "duration_is_not_inferred": True,
            "isolation_is_not_inferred": True,
            "inventory_depletion_is_not_inferred": True,
            "facility_ir_fn_promotion": "independent qualification and physical-validation gates remain required",
        },
    }


def _release_closure_worklist_summary(
    worklist: Mapping[str, Any],
) -> dict[str, Any]:
    """Copy the case-level release closure worklist into the readiness chain.

    The worklist is intentionally summarized rather than embedded in the
    readiness report.  Its case-level JSON remains the actionable evidence
    request, while this block makes the open closure gates visible to a
    reviewer of the v0.6.0 report.
    """
    summary = worklist.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    def _counts(name: str) -> dict[str, Any]:
        value = summary.get(name, {})
        return dict(sorted(value.items())) if isinstance(value, Mapping) else {}
    return {
        "schema": worklist.get("schema_version"),
        "status": worklist.get("status"),
        "case_count": worklist.get("case_count"),
        "open_case_count": worklist.get("open_case_count"),
        "closure_status_counts": _counts("closure_status_counts"),
        "closure_gap_counts": _counts("closure_gap_counts"),
        "termination_basis_counts": _counts("termination_basis_counts"),
        "isolation_status_counts": _counts("isolation_status_counts"),
        "inventory_status_counts": _counts("inventory_status_counts"),
        "provider_packet_required_case_count": summary.get(
            "provider_packet_required_case_count"
        ),
        "mass_closure_open_case_count": summary.get("mass_closure_open_case_count"),
        "isolation_open_case_count": summary.get("isolation_open_case_count"),
        "termination_open_case_count": summary.get("termination_open_case_count"),
        "inventory_closure_open_case_count": summary.get(
            "inventory_closure_open_case_count"
        ),
        "release_boundary_promotion_allowed": False,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "physical_validation_claim": False,
        "diagnostic_only": True,
    }


def _frequency_port_binding_summary(
    facility: Mapping[str, Any],
    evidence_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose the reviewed accident-port trace in the readiness report.

    The public facility assessment mirrors the nested ledger field.  Readiness
    consumers should see both copies and whether they agree, while preserving
    legacy ledgers as explicitly unaudited.  This helper only summarizes the
    trace; it never supplies a port, reallocates a frequency, or opens QRA.
    """
    root = facility.get("frequency_port_binding")
    ledger = facility.get("facility_risk_ledger")
    nested = ledger.get("frequency_port_binding") if isinstance(ledger, Mapping) else None
    selected = root if isinstance(root, Mapping) else nested
    source = "facility_assessment" if isinstance(selected, Mapping) else None
    if not isinstance(selected, Mapping) and isinstance(evidence_request, Mapping):
        request_binding = evidence_request.get("frequency_port_binding")
        if isinstance(request_binding, Mapping):
            # A legacy facility assessment may predate the port-binding field.
            # The evidence request is allowed to expose its observed
            # provider-only/reviewed-port split, but it can never repair the
            # assessment or promote facility QRA.
            selected = request_binding
            source = "facility_evidence_request"
    if not isinstance(selected, Mapping):
        return {
            "schema": None,
            "status": "NOT_REPORTED",
            "port_scoped_event_count": None,
            "port_unbound_event_count": None,
            "all_events_port_scoped": None,
            "case_port_binding_mismatch_count": None,
            "risk_atom_port_binding_mismatch_count": None,
            "mismatch_count": None,
            "assessment_nested_mirror_match": None,
            "source": None,
            "diagnostic_only": True,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
        }
    mirror_match = (
        None
        if source == "facility_evidence_request"
        else (root is None or nested is None or root == nested)
    )
    def _count(name: str) -> Any:
        value = selected.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) else value
    return {
        "schema": selected.get("schema_version"),
        "status": selected.get("status"),
        "port_scoped_event_count": _count("port_scoped_event_count"),
        "port_unbound_event_count": _count("port_unbound_event_count"),
        "all_events_port_scoped": selected.get("all_events_port_scoped"),
        "case_port_binding_mismatch_count": _count("case_port_binding_mismatch_count"),
        "risk_atom_port_binding_mismatch_count": _count("risk_atom_port_binding_mismatch_count"),
        "mismatch_count": _count("mismatch_count"),
        "assessment_nested_mirror_match": mirror_match,
        "source": source,
        "diagnostic_only": True,
        "frequency_inference_allowed": False,
        # Readiness itself never opens facility QRA.  Keep the lower-level
        # port-completeness result separately so a fully reviewed port map can
        # be visible without being mistaken for provider/validation closure.
        "facility_qra_allowed": False,
        "port_binding_facility_qra_allowed": selected.get("facility_qra_allowed") is True,
        "reviewed_frequency_port_case_count": selected.get(
            "reviewed_frequency_port_case_count"
        ),
        "provider_packet_only_case_count": selected.get(
            "provider_packet_only_case_count"
        ),
        "port_binding_mismatch_case_count": selected.get(
            "port_binding_mismatch_case_count"
        ),
        "port_binding_withheld_case_count": selected.get(
            "port_binding_withheld_case_count"
        ),
        "reviewed_frequency_ports_complete": selected.get(
            "reviewed_frequency_ports_complete"
        ),
    }


def _runtime_profile(
    realtime: Mapping[str, Any], timing: Mapping[str, Any]
) -> dict[str, Any]:
    """Describe which execution mode can support a one-hertz diagnostic loop.

    The benchmark contains three different operations that must not be merged:
    reading a saved consequence result, running fresh consequence physics, and
    running the complete multi-case campaign.  The profile makes that boundary
    explicit for digital-twin integrators and keeps the QRA promotion claim
    closed regardless of the measured latency.
    """
    cache_p95 = realtime.get("cache_p95_ms")
    fresh_elapsed = realtime.get("fresh_physics_elapsed_ms")
    cache_ready = realtime.get("cache_meets_one_hz_all_samples") is True
    fresh_ready = realtime.get("fresh_physics_meets_one_hz") is True
    campaign_p95 = timing.get("case_p95_ms")
    campaign_p99 = timing.get("case_p99_ms")
    if cache_ready:
        recommended = "cached_diagnostic_1hz"
    elif fresh_ready:
        recommended = "fresh_physics_1hz"
    else:
        recommended = "offline_campaign"
    return {
        "recommended_mode": recommended,
        "cache_mode": {
            "p95_ms": cache_p95,
            "one_hz_ready": cache_ready,
            "purpose": "reuse a validated consequence result for diagnostic monitoring",
        },
        "fresh_physics_mode": {
            "elapsed_ms": fresh_elapsed,
            "one_hz_ready": fresh_ready,
            "purpose": "recalculate SLABx-LH2 consequence from a new equipment state",
        },
        "campaign_mode": {
            "p95_ms": campaign_p95,
            "p99_ms": campaign_p99,
            "online_one_hz_ready": False,
            "purpose": "offline multi-case risk and sensitivity assessment",
        },
        "facility_qra_realtime_claim": False,
        "interpretation": (
            "One-hertz service is a cache-mode diagnostic claim only; fresh physics "
            "and the full campaign remain slower measured paths and do not imply "
            "qualified facility QRA."
        ),
    }


def build_v060_readiness_report(
    *,
    objective_audit: Mapping[str, Any],
    union_verification: Mapping[str, Any],
    scope_matrix: Mapping[str, Any],
    facility_assessment: Mapping[str, Any],
    completion_audit: Mapping[str, Any],
    validation_matrix: Mapping[str, Any],
    realtime_benchmark: Mapping[str, Any],
    facility_evidence_request: Mapping[str, Any] | None = None,
    scenario_evidence_audit: Mapping[str, Any] | None = None,
    risk_atom_chain_audit: Mapping[str, Any] | None = None,
    equipment_state_release_audit: Mapping[str, Any] | None = None,
    facility_aggregate_closure_audit: Mapping[str, Any] | None = None,
    facility_component_contribution_audit: Mapping[str, Any] | None = None,
    facility_frequency_uncertainty_audit: Mapping[str, Any] | None = None,
    external_equipment_model_audit: Mapping[str, Any] | None = None,
    equipment_scenario_coverage_audit: Mapping[str, Any] | None = None,
    equipment_frequency_binding_audit: Mapping[str, Any] | None = None,
    generic_equipment_scenario_coverage_audit: Mapping[str, Any] | None = None,
    generic_equipment_frequency_binding_audit: Mapping[str, Any] | None = None,
    generic_diagnostic_campaign_binding: Mapping[str, Any] | None = None,
    generic_chain_closure_audit: Mapping[str, Any] | None = None,
    generic_provider_closure_audit: Mapping[str, Any] | None = None,
    generic_provider_evidence_requests: Mapping[str, Any] | None = None,
    generic_provider_evidence_audit: Mapping[str, Any] | None = None,
    isolation_union_extension_verification: Mapping[str, Any] | None = None,
    release_closure_worklist: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate current v0.6.0 status without changing any promotion gate."""
    objective = _mapping(objective_audit, "objective_audit")
    union = _mapping(union_verification, "union_verification")
    scope = _mapping(scope_matrix, "scope_matrix")
    facility = _mapping(facility_assessment, "facility_assessment")
    completion = _mapping(completion_audit, "completion_audit")
    validation = _mapping(validation_matrix, "validation_matrix")
    realtime = _mapping(realtime_benchmark, "realtime_benchmark")
    evidence_request = None
    if facility_evidence_request is not None:
        evidence_request = _mapping(
            facility_evidence_request, "facility_evidence_request"
        )
    scenario_evidence = None
    if scenario_evidence_audit is not None:
        scenario_evidence = _scenario_evidence_summary(
            _mapping(scenario_evidence_audit, "scenario_evidence_audit")
        )
    atom_chain = None
    if risk_atom_chain_audit is not None:
        atom_chain = _mapping(risk_atom_chain_audit, "risk_atom_chain_audit")
    equipment_chain = None
    if equipment_state_release_audit is not None:
        equipment_chain = _mapping(
            equipment_state_release_audit, "equipment_state_release_audit"
        )
    aggregate_chain = None
    if facility_aggregate_closure_audit is not None:
        aggregate_chain = _mapping(
            facility_aggregate_closure_audit, "facility_aggregate_closure_audit"
        )
    component_contribution_chain = None
    if facility_component_contribution_audit is not None:
        component_contribution_chain = _mapping(
            facility_component_contribution_audit,
            "facility_component_contribution_audit",
        )
    frequency_uncertainty_chain = None
    if facility_frequency_uncertainty_audit is not None:
        frequency_uncertainty_chain = _mapping(
            facility_frequency_uncertainty_audit,
            "facility_frequency_uncertainty_audit",
        )
    external_equipment_chain = None
    if external_equipment_model_audit is not None:
        external_equipment_chain = _mapping(
            external_equipment_model_audit,
            "external_equipment_model_audit",
        )
    equipment_scenario_chain = None
    if equipment_scenario_coverage_audit is not None:
        equipment_scenario_chain = _mapping(
            equipment_scenario_coverage_audit,
            "equipment_scenario_coverage_audit",
        )
    equipment_frequency_chain = None
    if equipment_frequency_binding_audit is not None:
        equipment_frequency_chain = _mapping(
            equipment_frequency_binding_audit,
            "equipment_frequency_binding_audit",
        )
    generic_scenario_chain = None
    if generic_equipment_scenario_coverage_audit is not None:
        generic_scenario_chain = _mapping(
            generic_equipment_scenario_coverage_audit,
            "generic_equipment_scenario_coverage_audit",
        )
    generic_frequency_chain = None
    if generic_equipment_frequency_binding_audit is not None:
        generic_frequency_chain = _mapping(
            generic_equipment_frequency_binding_audit,
            "generic_equipment_frequency_binding_audit",
        )
    generic_diagnostic_chain = None
    if generic_diagnostic_campaign_binding is not None:
        generic_diagnostic_chain = _mapping(
            generic_diagnostic_campaign_binding,
            "generic_diagnostic_campaign_binding",
        )
    generic_chain_closure = None
    if generic_chain_closure_audit is not None:
        generic_chain_closure = _mapping(
            generic_chain_closure_audit,
            "generic_chain_closure_audit",
        )
    generic_provider_closure = None
    if generic_provider_closure_audit is not None:
        generic_provider_closure = _mapping(
            generic_provider_closure_audit,
            "generic_provider_closure_audit",
        )
    generic_provider_evidence = None
    if generic_provider_evidence_requests is not None:
        generic_provider_evidence = _mapping(
            generic_provider_evidence_requests,
            "generic_provider_evidence_requests",
        )
    generic_provider_evidence_result = None
    if generic_provider_evidence_audit is not None:
        generic_provider_evidence_result = _mapping(
            generic_provider_evidence_audit,
            "generic_provider_evidence_audit",
        )
    generic_frequency_port_binding = (
        generic_frequency_chain.get("frequency_port_binding")
        if isinstance(generic_frequency_chain, Mapping)
        else None
    )
    isolation_extension = None
    if isolation_union_extension_verification is not None:
        isolation_extension = _mapping(
            isolation_union_extension_verification,
            "isolation_union_extension_verification",
        )
    release_closure = None
    if release_closure_worklist is not None:
        release_closure = _mapping(release_closure_worklist, "release_closure_worklist")
    evidence_promotion_gate = (
        evidence_request.get("promotion_gate")
        if isinstance(evidence_request, Mapping)
        and isinstance(evidence_request.get("promotion_gate"), Mapping)
        else {}
    )
    evidence_promotion_allowed = evidence_promotion_gate.get(
        "facility_promotion_allowed_now"
    )
    if evidence_promotion_allowed is None and evidence_promotion_gate.get(
        "facility_ir_fn_remains_withheld_until_all_true"
    ) is True:
        evidence_promotion_allowed = False

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
    release_boundary = _release_boundary_summary(facility)
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
            "release_boundary": release_boundary,
            "release_closure_worklist": (
                _release_closure_worklist_summary(release_closure)
                if release_closure is not None
                else None
            ),
            "frequency_port_binding": _frequency_port_binding_summary(
                facility, facility_evidence_request
            ),
            "risk_atom_chain_closure": (
                {
                    "status": atom_chain.get("status"),
                    "case_count": atom_chain.get("case_count"),
                    "complete_case_count": atom_chain.get("complete_case_count"),
                    "incomplete_case_count": atom_chain.get("incomplete_case_count"),
                    "risk_atom_count": atom_chain.get("risk_atom_count"),
                    "operator_limited_case_count": atom_chain.get(
                        "operator_limited_case_count"
                    ),
                    "blocking_reason_count": len(atom_chain.get("blocking_reasons", ()))
                    if isinstance(atom_chain.get("blocking_reasons"), Sequence)
                    else None,
                    "diagnostic_only": atom_chain.get("diagnostic_only"),
                    "facility_qra_claim": atom_chain.get("facility_qra_claim"),
                }
                if atom_chain is not None
                else None
            ),
            "equipment_state_release_chain": (
                {
                    "status": equipment_chain.get("status"),
                    "case_count": equipment_chain.get("case_count"),
                    "complete_case_count": equipment_chain.get("complete_case_count"),
                    "incomplete_case_count": equipment_chain.get("incomplete_case_count"),
                    "component_count": equipment_chain.get("component_count"),
                    "operator_limited_case_count": equipment_chain.get(
                        "operator_limited_case_count"
                    ),
                    "blocking_reason_count": len(equipment_chain.get("blocking_reasons", ()))
                    if isinstance(equipment_chain.get("blocking_reasons"), Sequence)
                    else None,
                    "diagnostic_only": equipment_chain.get("diagnostic_only"),
                    "facility_qra_claim": equipment_chain.get("facility_qra_claim"),
                }
                if equipment_chain is not None
                else None
            ),
            "facility_ir_fn_aggregate_closure": (
                {
                    "status": aggregate_chain.get("status"),
                    "risk_atom_count": aggregate_chain.get("risk_atom_count"),
                    "ir_mismatch_count": aggregate_chain.get("ir_mismatch_count"),
                    "fn_mismatch_count": aggregate_chain.get("fn_mismatch_count"),
                    "blocking_reason_count": len(aggregate_chain.get("blocking_reasons", ()))
                    if isinstance(aggregate_chain.get("blocking_reasons"), Sequence)
                    else None,
                    "diagnostic_only": aggregate_chain.get("diagnostic_only"),
                    "facility_qra_claim": aggregate_chain.get("facility_qra_claim"),
                }
                if aggregate_chain is not None
                else None
            ),
            "facility_component_contribution_closure": (
                {
                    "status": component_contribution_chain.get("status"),
                    "risk_atom_count": component_contribution_chain.get("risk_atom_count"),
                    "component_count": component_contribution_chain.get("component_count"),
                    "mismatch_count": component_contribution_chain.get("mismatch_count"),
                    "blocking_reason_count": len(component_contribution_chain.get("blocking_reasons", ()))
                    if isinstance(component_contribution_chain.get("blocking_reasons"), Sequence)
                    else None,
                    "diagnostic_only": component_contribution_chain.get("diagnostic_only"),
                    "facility_qra_claim": component_contribution_chain.get("facility_qra_claim"),
                }
                if component_contribution_chain is not None
                else None
            ),
            "facility_frequency_uncertainty_closure": (
                {
                    "status": frequency_uncertainty_chain.get("status"),
                    "scenario_count": frequency_uncertainty_chain.get("scenario_count"),
                    "risk_atom_count": frequency_uncertainty_chain.get("risk_atom_count"),
                    "mismatch_count": frequency_uncertainty_chain.get("mismatch_count"),
                    "blocking_reason_count": len(frequency_uncertainty_chain.get("blocking_reasons", ()))
                    if isinstance(frequency_uncertainty_chain.get("blocking_reasons"), Sequence)
                    else None,
                    "frequency_inference_performed": frequency_uncertainty_chain.get(
                        "frequency_inference_performed"
                    ),
                    "facility_credible_interval": frequency_uncertainty_chain.get(
                        "facility_credible_interval"
                    ),
                    "fresh_physics_executed": frequency_uncertainty_chain.get(
                        "fresh_physics_executed"
                    ),
                    "diagnostic_only": frequency_uncertainty_chain.get("diagnostic_only"),
                    "facility_qra_claim": frequency_uncertainty_chain.get("facility_qra_claim"),
                }
                if frequency_uncertainty_chain is not None
                else None
            ),
            "external_equipment_model_readiness": (
                {
                    "status": external_equipment_chain.get("status"),
                    "asset_count": external_equipment_chain.get("asset_count"),
                    "state_model_ready_asset_count": external_equipment_chain.get(
                        "state_model_ready_asset_count"
                    ),
                    "physical_time_assigned_event_count": (
                        external_equipment_chain.get("event_register", {}).get(
                            "physical_time_assigned_event_count"
                        )
                        if isinstance(external_equipment_chain.get("event_register"), Mapping)
                        else None
                    ),
                    "pid_identity_evidence": (
                        {
                            "exact_asset_id_overlap_count": external_equipment_chain.get(
                                "pid_identity_evidence", {}
                            ).get("exact_asset_id_overlap_count"),
                            "source_backed_overlap_count": external_equipment_chain.get(
                                "pid_identity_evidence", {}
                            ).get("source_backed_overlap_count"),
                            "unmatched_external_asset_count": len(
                                external_equipment_chain.get("pid_identity_evidence", {}).get(
                                    "unmatched_external_asset_ids", []
                                )
                                if isinstance(
                                    external_equipment_chain.get("pid_identity_evidence", {}).get(
                                        "unmatched_external_asset_ids", []
                                    ),
                                    list,
                                )
                                else []
                            ),
                            "general_facility_identity_resolved": external_equipment_chain.get(
                                "pid_identity_evidence", {}
                            ).get("identity_is_general_facility_resolved"),
                        }
                        if isinstance(external_equipment_chain.get("pid_identity_evidence"), Mapping)
                        else None
                    ),
                    "pid_port_evidence": (
                        {
                            "confirmed_port_mapping_count": external_equipment_chain.get(
                                "pid_port_evidence", {}
                            ).get("confirmed_port_mapping_count"),
                            "candidate_port_mapping_count": external_equipment_chain.get(
                                "pid_port_evidence", {}
                            ).get("candidate_port_mapping_count"),
                            "promotion_allowed": external_equipment_chain.get(
                                "pid_port_evidence", {}
                            ).get("port_crosswalk_promotion_allowed"),
                        }
                        if isinstance(external_equipment_chain.get("pid_port_evidence"), Mapping)
                        else None
                    ),
                    "component_binding_evidence": (
                        {
                            "enabled_edge_count": external_equipment_chain.get(
                                "component_binding_evidence", {}
                            ).get("enabled_edge_count"),
                            "unresolved_edge_count": external_equipment_chain.get(
                                "component_binding_evidence", {}
                            ).get("unresolved_edge_count"),
                            "promotion_allowed": external_equipment_chain.get(
                                "component_binding_evidence", {}
                            ).get("numerical_topology_promotion_allowed"),
                        }
                        if isinstance(
                            external_equipment_chain.get("component_binding_evidence"),
                            Mapping,
                        )
                        else None
                    ),
                    "accident_release_packet_allowed": (
                        external_equipment_chain.get("promotion_gates", {}).get(
                            "accident_release_packet_allowed"
                        )
                        if isinstance(external_equipment_chain.get("promotion_gates"), Mapping)
                        else None
                    ),
                    "frequency_inference_allowed": (
                        external_equipment_chain.get("promotion_gates", {}).get(
                            "frequency_inference_allowed"
                        )
                        if isinstance(external_equipment_chain.get("promotion_gates"), Mapping)
                        else None
                    ),
                    "facility_qra_claim": external_equipment_chain.get("facility_qra_claim"),
                    "diagnostic_only": True,
                }
                if external_equipment_chain is not None
                else None
            ),
            "equipment_scenario_coverage": (
                {
                    "status": equipment_scenario_chain.get("status"),
                    "asset_count": equipment_scenario_chain.get("asset_count"),
                    "mapped_asset_count": equipment_scenario_chain.get("mapped_asset_count"),
                    "resolved_asset_count": equipment_scenario_chain.get("resolved_asset_count"),
                    "scenario_family_count": equipment_scenario_chain.get("scenario_family_count"),
                    "accident_release_packet_allowed": equipment_scenario_chain.get(
                        "promotion_gates", {}
                    ).get("accident_release_packet_allowed")
                    if isinstance(equipment_scenario_chain.get("promotion_gates"), Mapping)
                    else None,
                    "frequency_inference_allowed": equipment_scenario_chain.get(
                        "promotion_gates", {}
                    ).get("frequency_inference_allowed")
                    if isinstance(equipment_scenario_chain.get("promotion_gates"), Mapping)
                    else None,
                    "facility_qra_allowed": equipment_scenario_chain.get(
                        "promotion_gates", {}
                    ).get("facility_qra_allowed")
                    if isinstance(equipment_scenario_chain.get("promotion_gates"), Mapping)
                    else None,
                    "diagnostic_only": True,
                }
                if equipment_scenario_chain is not None
                else None
            ),
            "equipment_frequency_binding": (
                {
                    "status": equipment_frequency_chain.get("status"),
                    "resolved_asset_count": equipment_frequency_chain.get("resolved_asset_count"),
                    "frequency_event_count": equipment_frequency_chain.get("frequency_event_count"),
                    "valid_frequency_event_count": equipment_frequency_chain.get(
                        "valid_frequency_event_count"
                    ),
                    "uncomputed_family_count": equipment_frequency_chain.get(
                        "uncomputed_family_count"
                    ),
                    "provider_release_required": equipment_frequency_chain.get(
                        "promotion_gates", {}
                    ).get("provider_release_required")
                    if isinstance(equipment_frequency_chain.get("promotion_gates"), Mapping)
                    else None,
                    "frequency_inference_allowed": equipment_frequency_chain.get(
                        "promotion_gates", {}
                    ).get("frequency_inference_allowed")
                    if isinstance(equipment_frequency_chain.get("promotion_gates"), Mapping)
                    else None,
                    "facility_qra_allowed": equipment_frequency_chain.get(
                        "promotion_gates", {}
                    ).get("facility_qra_allowed")
                    if isinstance(equipment_frequency_chain.get("promotion_gates"), Mapping)
                    else None,
                    "diagnostic_only": True,
                }
                if equipment_frequency_chain is not None
                else None
            ),
            "generic_equipment_scenario_coverage": (
                {
                    "status": generic_scenario_chain.get("status"),
                    "asset_count": generic_scenario_chain.get("asset_count"),
                    "mapped_asset_count": generic_scenario_chain.get("mapped_asset_count"),
                    "resolved_asset_count": generic_scenario_chain.get("resolved_asset_count"),
                    "scenario_family_count": generic_scenario_chain.get("scenario_family_count"),
                    "accident_release_packet_allowed": generic_scenario_chain.get(
                        "promotion_gates", {}
                    ).get("accident_release_packet_allowed")
                    if isinstance(generic_scenario_chain.get("promotion_gates"), Mapping)
                    else None,
                    "frequency_inference_allowed": generic_scenario_chain.get(
                        "promotion_gates", {}
                    ).get("frequency_inference_allowed")
                    if isinstance(generic_scenario_chain.get("promotion_gates"), Mapping)
                    else None,
                    "facility_qra_allowed": generic_scenario_chain.get(
                        "promotion_gates", {}
                    ).get("facility_qra_allowed")
                    if isinstance(generic_scenario_chain.get("promotion_gates"), Mapping)
                    else None,
                    "diagnostic_only": True,
                }
                if generic_scenario_chain is not None
                else None
            ),
            "generic_equipment_frequency_binding": (
                {
                    "status": generic_frequency_chain.get("status"),
                    "resolved_asset_count": generic_frequency_chain.get("resolved_asset_count"),
                    "frequency_event_count": generic_frequency_chain.get("frequency_event_count"),
                    "valid_frequency_event_count": generic_frequency_chain.get(
                        "valid_frequency_event_count"
                    ),
                    "uncomputed_family_count": generic_frequency_chain.get(
                        "uncomputed_family_count"
                    ),
                    "frequency_port_binding": (
                        {
                            "schema": generic_frequency_port_binding.get("schema_version"),
                            "reviewed_port_bound_event_count": generic_frequency_port_binding.get(
                                "reviewed_port_bound_event_count"
                            ),
                            "port_unbound_event_count": generic_frequency_port_binding.get(
                                "port_unbound_event_count"
                            ),
                            "port_binding_withheld_event_count": generic_frequency_port_binding.get(
                                "port_binding_withheld_event_count"
                            ),
                            "all_supplied_port_scopes_valid": generic_frequency_port_binding.get(
                                "all_supplied_port_scopes_valid"
                            ),
                            "strict_facility_qra_gate": generic_frequency_port_binding.get(
                                "strict_facility_qra_gate"
                            ),
                        }
                        if isinstance(generic_frequency_port_binding, Mapping)
                        else None
                    ),
                    "provider_release_required": generic_frequency_chain.get(
                        "promotion_gates", {}
                    ).get("provider_release_required")
                    if isinstance(generic_frequency_chain.get("promotion_gates"), Mapping)
                    else None,
                    "frequency_inference_allowed": generic_frequency_chain.get(
                        "promotion_gates", {}
                    ).get("frequency_inference_allowed")
                    if isinstance(generic_frequency_chain.get("promotion_gates"), Mapping)
                    else None,
                    "facility_qra_allowed": generic_frequency_chain.get(
                        "promotion_gates", {}
                    ).get("facility_qra_allowed")
                    if isinstance(generic_frequency_chain.get("promotion_gates"), Mapping)
                    else None,
                    "diagnostic_only": True,
                }
                if generic_frequency_chain is not None
                else None
            ),
            "generic_diagnostic_campaign_binding": (
                {
                    "schema_version": generic_diagnostic_chain.get("schema_version"),
                    "status": generic_diagnostic_chain.get("status"),
                    "packet_event_count": generic_diagnostic_chain.get("packet_event_count"),
                    "campaign_event_count": generic_diagnostic_chain.get("campaign_event_count"),
                    "campaign_case_count": generic_diagnostic_chain.get("campaign_case_count"),
                    "campaign_risk_atom_count": generic_diagnostic_chain.get("campaign_risk_atom_count"),
                    "structural_binding_complete": generic_diagnostic_chain.get("structural_binding_complete"),
                    "packet_identity_consumed": generic_diagnostic_chain.get("packet_identity_consumed"),
                    "packet_digest_checked_event_count": generic_diagnostic_chain.get("packet_digest_checked_event_count"),
                    "packet_digest_match_event_count": generic_diagnostic_chain.get("packet_digest_match_event_count"),
                    "packet_value_checked_event_count": generic_diagnostic_chain.get("packet_value_checked_event_count"),
                    "packet_value_consumed_event_count": generic_diagnostic_chain.get("packet_value_consumed_event_count"),
                    "packet_subset_value_consumed": generic_diagnostic_chain.get("packet_subset_value_consumed"),
                    "qualified_provider_packet_count": generic_diagnostic_chain.get("qualified_provider_packet_count"),
                    "facility_qra_claim": generic_diagnostic_chain.get("facility_qra_claim"),
                    "physical_validation_claim": generic_diagnostic_chain.get("physical_validation_claim"),
                    "frequency_from_provider_packet": generic_diagnostic_chain.get("frequency_from_provider_packet"),
                    "packet_claims_preserved": generic_diagnostic_chain.get("packet_claims_preserved"),
                    "diagnostic_only": True,
                }
                if generic_diagnostic_chain is not None
                else None
            ),
            "generic_release_to_final_damage_closure": (
                {
                    "schema_version": generic_chain_closure.get("schema_version"),
                    "status": generic_chain_closure.get("status"),
                    "campaign_event_count": generic_chain_closure.get("campaign_event_count"),
                    "campaign_case_count": generic_chain_closure.get("campaign_case_count"),
                    "campaign_risk_atom_count": generic_chain_closure.get("campaign_risk_atom_count"),
                    "packet_event_count": generic_chain_closure.get("packet_event_count"),
                    "packet_chain_closed_event_count": generic_chain_closure.get("packet_chain_closed_event_count"),
                    "packet_chain_mismatch_event_count": generic_chain_closure.get("packet_chain_mismatch_event_count"),
                    "campaign_events_without_packet_count": generic_chain_closure.get("campaign_events_without_packet_count"),
                    "facility_ir_aggregate_closed": generic_chain_closure.get("facility_ir_aggregate_closed"),
                    "facility_fn_aggregate_closed": generic_chain_closure.get("facility_fn_aggregate_closed"),
                    "facility_total_risk_available": generic_chain_closure.get("facility_total_risk_available"),
                    "complete_facility_qra_claim": generic_chain_closure.get("complete_facility_qra_claim"),
                    "qualified_provider_packet_count": generic_chain_closure.get("qualified_provider_packet_count"),
                    "frequency_from_provider_packet": generic_chain_closure.get("frequency_from_provider_packet"),
                    "physical_validation_claim": generic_chain_closure.get("physical_validation_claim"),
                    "facility_qra_claim": generic_chain_closure.get("facility_qra_claim"),
                    "diagnostic_only": True,
                }
                if generic_chain_closure is not None
                else None
            ),
            "generic_provider_release_closure": (
                {
                    "schema_version": generic_provider_closure.get("schema_version"),
                    "status": generic_provider_closure.get("status"),
                    "event_count": generic_provider_closure.get("event_count"),
                    "closure_ready_event_count": generic_provider_closure.get(
                        "closure_ready_event_count"
                    ),
                    "closure_open_event_count": generic_provider_closure.get(
                        "closure_open_event_count"
                    ),
                    "packet_path_count": generic_provider_closure.get(
                        "packet_path_count"
                    ),
                    "provider_packet_count": generic_provider_closure.get(
                        "provider_packet_count"
                    ),
                    "closure_ready_packet_path_count": generic_provider_closure.get(
                        "closure_ready_packet_path_count"
                    ),
                    "closure_ready_provider_packet_count": generic_provider_closure.get(
                        "closure_ready_provider_packet_count"
                    ),
                    "closure_gap_counts": generic_provider_closure.get(
                        "closure_gap_counts", {}
                    ),
                    "qualified_provider_packet_count": generic_provider_closure.get(
                        "qualified_provider_packet_count"
                    ),
                    "frequency_from_provider_packet": generic_provider_closure.get(
                        "frequency_from_provider_packet"
                    ),
                    "physical_validation_claim": generic_provider_closure.get(
                        "physical_validation_claim"
                    ),
                    "facility_qra_claim": generic_provider_closure.get(
                        "facility_qra_claim"
                    ),
                    "diagnostic_only": True,
                }
                if generic_provider_closure is not None
                else None
            ),
            "generic_provider_evidence_requests": (
                {
                    "schema_version": generic_provider_evidence.get("schema_version"),
                    "status": generic_provider_evidence.get("status"),
                    "source_status": generic_provider_evidence.get("source_status"),
                    "event_count": generic_provider_evidence.get("event_count"),
                    "packet_path_count": generic_provider_evidence.get("packet_path_count"),
                    "packet_count": generic_provider_evidence.get("packet_count"),
                    "request_count": generic_provider_evidence.get("request_count"),
                    "closure_open_request_count": generic_provider_evidence.get(
                        "closure_open_request_count"
                    ),
                    "qualification_open_request_count": generic_provider_evidence.get(
                        "qualification_open_request_count"
                    ),
                    "qualified_provider_packet_count": generic_provider_evidence.get(
                        "qualified_provider_packet_count"
                    ),
                    "frequency_inference_allowed": generic_provider_evidence.get(
                        "frequency_inference_allowed"
                    ),
                    "facility_qra_allowed": generic_provider_evidence.get(
                        "facility_qra_allowed"
                    ),
                    "diagnostic_only": generic_provider_evidence.get("diagnostic_only"),
                }
                if generic_provider_evidence is not None
                else None
            ),
            "generic_provider_evidence_audit": (
                {
                    "schema_version": generic_provider_evidence_result.get("schema_version"),
                    "status": generic_provider_evidence_result.get("status"),
                    "request_count": generic_provider_evidence_result.get("request_count"),
                    "packet_count": generic_provider_evidence_result.get("packet_count"),
                    "qualification_sidecar_present_count": generic_provider_evidence_result.get(
                        "qualification_sidecar_present_count"
                    ),
                    "exact_match_count": generic_provider_evidence_result.get("exact_match_count"),
                    "qualified_provider_packet_count": generic_provider_evidence_result.get(
                        "qualified_provider_packet_count"
                    ),
                    "frequency_inference_allowed": generic_provider_evidence_result.get(
                        "frequency_inference_allowed"
                    ),
                    "facility_qra_allowed": generic_provider_evidence_result.get(
                        "facility_qra_allowed"
                    ),
                    "diagnostic_only": generic_provider_evidence_result.get("diagnostic_only"),
                }
                if generic_provider_evidence_result is not None
                else None
            ),
            "isolation_union_extension": (
                {
                    "schema": isolation_extension.get("schema"),
                    "status": isolation_extension.get("status"),
                    "base_counts": isolation_extension.get("base_counts"),
                    "isolation_counts": isolation_extension.get("isolation_counts"),
                    "merged_counts": isolation_extension.get("merged_counts"),
                    "risk_atom_chain_status": isolation_extension.get(
                        "risk_atom_chain_status"
                    ),
                    "equipment_state_release_status": isolation_extension.get(
                        "equipment_state_release_status"
                    ),
                    "facility_aggregate_closure_status": isolation_extension.get(
                        "facility_aggregate_closure_status"
                    ),
                    "facility_component_contribution_status": isolation_extension.get(
                        "facility_component_contribution_status"
                    ),
                    "provider_response_consumed": (
                        isolation_extension.get("isolation_counts", {}).get(
                            "provider_response_consumed"
                        )
                        if isinstance(isolation_extension.get("isolation_counts"), Mapping)
                        else None
                    ),
                    "state_snapshot_bound_cases": (
                        isolation_extension.get("isolation_counts", {}).get(
                            "state_snapshot_bound_cases"
                        )
                        if isinstance(isolation_extension.get("isolation_counts"), Mapping)
                        else None
                    ),
                    "qualified_provider_packet_case_count": isolation_extension.get(
                        "qualified_provider_packet_case_count"
                    ),
                    "facility_qra_claim": isolation_extension.get(
                        "complete_facility_qra_claim"
                    ),
                    "diagnostic_only": True,
                }
                if isolation_extension is not None
                else None
            ),
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
            "runtime_profile": _runtime_profile(realtime, timing),
        },
        "validation_domains": domains,
        "evidence_request": (
            {
                "status": evidence_request.get("status"),
                "provider_export_schema_required": evidence_request.get(
                    "provider_export_schema_required"
                ),
                "case_request_count": evidence_request.get("case_request_count"),
                "family_request_count": len(evidence_request.get("family_requests", ()))
                if isinstance(evidence_request.get("family_requests"), Sequence)
                and not isinstance(evidence_request.get("family_requests"), (str, bytes))
                else None,
                "component_request_count": len(evidence_request.get("component_requests", ()))
                if isinstance(evidence_request.get("component_requests"), Sequence)
                and not isinstance(evidence_request.get("component_requests"), (str, bytes))
                else None,
                "blocking_reasons": list(evidence_request.get("blocking_reasons", ()))
                if isinstance(evidence_request.get("blocking_reasons"), Sequence)
                and not isinstance(evidence_request.get("blocking_reasons"), (str, bytes))
                else [],
                "strict_gate_categories": list(
                    evidence_request.get("current_assessment", {}).get(
                        "strict_gate_categories", ()
                    )
                )
                if isinstance(evidence_request.get("current_assessment"), Mapping)
                and isinstance(
                    evidence_request.get("current_assessment", {}).get(
                        "strict_gate_categories", ()
                    ),
                    Sequence,
                )
                and not isinstance(
                    evidence_request.get("current_assessment", {}).get(
                        "strict_gate_categories", ()
                    ),
                    (str, bytes),
                )
                else [],
                "facility_promotion_allowed_now": evidence_promotion_allowed,
            }
            if evidence_request is not None
            else None
        ),
        "scenario_evidence": scenario_evidence,
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


def _nonnegative_int(value: Any, label: str, errors: list[str]) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        errors.append(f"{label} must be a nonnegative integer")


def validate_v060_readiness_report(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate cross-section invariants in a generated v0.6.0 report.

    This is an accounting validator, not a physical-model validator.  It
    catches stale or hand-edited readiness ledgers before they are cited in an
    IJHE record, while preserving the fail-closed rule for qualified facility
    QRA claims.
    """
    value = _mapping(report, "readiness_report")
    errors: list[str] = []
    if value.get("schema_version") != READINESS_SCHEMA:
        errors.append("unexpected readiness report schema_version")

    chain = value.get("chain")
    chain = chain if isinstance(chain, Mapping) else {}
    for field in (
        "event_count",
        "case_count",
        "risk_atom_count",
        "conditional_case_count",
        "conditional_executed_case_count",
        "not_numerically_executed_case_count",
        "qualified_evidence_withheld_case_count",
        "annual_condition_count",
    ):
        if field in chain and chain.get(field) is not None:
            _nonnegative_int(chain.get(field), f"chain.{field}", errors)
    conditional_cases = chain.get("conditional_case_count")
    executed_cases = chain.get("conditional_executed_case_count")
    unexecuted_cases = chain.get("not_numerically_executed_case_count")
    if all(isinstance(item, int) and not isinstance(item, bool)
           for item in (conditional_cases, executed_cases, unexecuted_cases)):
        if executed_cases + unexecuted_cases != conditional_cases:
            errors.append(
                "chain conditional cases do not equal executed plus not-numerically-executed cases"
            )
    if chain.get("conditional_ir_fn_available") is True:
        if value.get("promotion", {}).get("facility_total_risk_available") is True:
            errors.append(
                "conditional IR/F-N availability cannot promote facility_total_risk_available"
            )

    atom_chain = chain.get("risk_atom_chain_closure")
    if atom_chain is not None:
        if not isinstance(atom_chain, Mapping):
            errors.append("chain.risk_atom_chain_closure must be an object")
        else:
            for field in (
                "case_count",
                "complete_case_count",
                "incomplete_case_count",
                "risk_atom_count",
                "operator_limited_case_count",
                "blocking_reason_count",
            ):
                if atom_chain.get(field) is not None:
                    _nonnegative_int(
                        atom_chain.get(field),
                        f"chain.risk_atom_chain_closure.{field}",
                        errors,
                    )
            if atom_chain.get("status") == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC":
                if atom_chain.get("case_count") != atom_chain.get("complete_case_count"):
                    errors.append(
                        "risk atom chain closure is full but complete case count differs"
                    )
                if atom_chain.get("incomplete_case_count") != 0:
                    errors.append(
                        "risk atom chain closure is full but incomplete cases remain"
                    )
                if atom_chain.get("blocking_reason_count") != 0:
                    errors.append(
                        "risk atom chain closure is full but blocking reasons remain"
                    )
            if atom_chain.get("diagnostic_only") is not True:
                errors.append("risk atom chain closure must remain diagnostic_only")
            if atom_chain.get("facility_qra_claim") is True:
                errors.append("risk atom chain closure cannot claim facility QRA")

    equipment_chain = chain.get("equipment_state_release_chain")
    if equipment_chain is not None:
        if not isinstance(equipment_chain, Mapping):
            errors.append("chain.equipment_state_release_chain must be an object")
        else:
            for field in (
                "case_count",
                "complete_case_count",
                "incomplete_case_count",
                "component_count",
                "operator_limited_case_count",
                "blocking_reason_count",
            ):
                if equipment_chain.get(field) is not None:
                    _nonnegative_int(
                        equipment_chain.get(field),
                        f"chain.equipment_state_release_chain.{field}",
                        errors,
                    )
            if equipment_chain.get("status") == "FULL_EQUIPMENT_STATE_RELEASE_CHAIN_DIAGNOSTIC":
                if equipment_chain.get("case_count") != equipment_chain.get("complete_case_count"):
                    errors.append(
                        "equipment state release chain is full but complete case count differs"
                    )
                if equipment_chain.get("incomplete_case_count") != 0:
                    errors.append(
                        "equipment state release chain is full but incomplete cases remain"
                    )
                if equipment_chain.get("blocking_reason_count") != 0:
                    errors.append(
                        "equipment state release chain is full but blocking reasons remain"
                    )
            if equipment_chain.get("diagnostic_only") is not True:
                errors.append("equipment state release chain must remain diagnostic_only")
            if equipment_chain.get("facility_qra_claim") is True:
                errors.append("equipment state release chain cannot claim facility QRA")

    aggregate_chain = chain.get("facility_ir_fn_aggregate_closure")
    if aggregate_chain is not None:
        if not isinstance(aggregate_chain, Mapping):
            errors.append("chain.facility_ir_fn_aggregate_closure must be an object")
        else:
            for field in (
                "risk_atom_count",
                "ir_mismatch_count",
                "fn_mismatch_count",
                "blocking_reason_count",
            ):
                if aggregate_chain.get(field) is not None:
                    _nonnegative_int(
                        aggregate_chain.get(field),
                        f"chain.facility_ir_fn_aggregate_closure.{field}",
                        errors,
                    )
            if aggregate_chain.get("status") == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC":
                if aggregate_chain.get("risk_atom_count", 0) <= 0:
                    errors.append("facility IR/F-N aggregate closure has no risk atoms")
                if aggregate_chain.get("ir_mismatch_count") != 0:
                    errors.append("facility IR/F-N aggregate closure has IR mismatches")
                if aggregate_chain.get("fn_mismatch_count") != 0:
                    errors.append("facility IR/F-N aggregate closure has F/N mismatches")
                if aggregate_chain.get("blocking_reason_count") != 0:
                    errors.append("facility IR/F-N aggregate closure has blocking reasons")
            if aggregate_chain.get("diagnostic_only") is not True:
                errors.append("facility IR/F-N aggregate closure must remain diagnostic_only")
            if aggregate_chain.get("facility_qra_claim") is True:
                errors.append("facility IR/F-N aggregate closure cannot claim facility QRA")

    component_contribution_chain = chain.get("facility_component_contribution_closure")
    if component_contribution_chain is not None:
        if not isinstance(component_contribution_chain, Mapping):
            errors.append(
                "chain.facility_component_contribution_closure must be an object"
            )
        else:
            for field in (
                "risk_atom_count",
                "component_count",
                "mismatch_count",
                "blocking_reason_count",
            ):
                if component_contribution_chain.get(field) is not None:
                    _nonnegative_int(
                        component_contribution_chain.get(field),
                        f"chain.facility_component_contribution_closure.{field}",
                        errors,
                    )
            if component_contribution_chain.get("status") == (
                "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
            ):
                if component_contribution_chain.get("risk_atom_count", 0) <= 0:
                    errors.append(
                        "facility component contribution closure has no risk atoms"
                    )
                if component_contribution_chain.get("component_count", 0) <= 0:
                    errors.append(
                        "facility component contribution closure has no components"
                    )
                if component_contribution_chain.get("mismatch_count") != 0:
                    errors.append(
                        "facility component contribution closure has mismatches"
                    )
                if component_contribution_chain.get("blocking_reason_count") != 0:
                    errors.append(
                        "facility component contribution closure has blocking reasons"
                    )
            if component_contribution_chain.get("diagnostic_only") is not True:
                errors.append(
                    "facility component contribution closure must remain diagnostic_only"
                )
            if component_contribution_chain.get("facility_qra_claim") is True:
                errors.append(
                    "facility component contribution closure cannot claim facility QRA"
                )

    frequency_uncertainty_chain = chain.get("facility_frequency_uncertainty_closure")
    if frequency_uncertainty_chain is not None:
        if not isinstance(frequency_uncertainty_chain, Mapping):
            errors.append(
                "chain.facility_frequency_uncertainty_closure must be an object"
            )
        else:
            for field in (
                "scenario_count",
                "risk_atom_count",
                "mismatch_count",
                "blocking_reason_count",
            ):
                if frequency_uncertainty_chain.get(field) is not None:
                    _nonnegative_int(
                        frequency_uncertainty_chain.get(field),
                        f"chain.facility_frequency_uncertainty_closure.{field}",
                        errors,
                    )
            if frequency_uncertainty_chain.get("status") == (
                "FACILITY_FREQUENCY_UNCERTAINTY_CLOSED_DIAGNOSTIC"
            ):
                if frequency_uncertainty_chain.get("scenario_count", 0) <= 0:
                    errors.append(
                        "facility frequency uncertainty closure has no scenarios"
                    )
                if frequency_uncertainty_chain.get("risk_atom_count", 0) <= 0:
                    errors.append(
                        "facility frequency uncertainty closure has no risk atoms"
                    )
                if frequency_uncertainty_chain.get("mismatch_count") != 0:
                    errors.append(
                        "facility frequency uncertainty closure has mismatches"
                    )
                if frequency_uncertainty_chain.get("blocking_reason_count") != 0:
                    errors.append(
                        "facility frequency uncertainty closure has blocking reasons"
                    )
            if frequency_uncertainty_chain.get("frequency_inference_performed") is not False:
                errors.append(
                    "facility frequency uncertainty closure cannot infer frequency"
                )
            if frequency_uncertainty_chain.get("facility_credible_interval") is not False:
                errors.append(
                    "facility frequency uncertainty closure cannot claim a credible interval"
                )
            if frequency_uncertainty_chain.get("fresh_physics_executed") is not False:
                errors.append(
                    "facility frequency uncertainty closure cannot run fresh physics"
                )
            if frequency_uncertainty_chain.get("diagnostic_only") is not True:
                errors.append(
                    "facility frequency uncertainty closure must remain diagnostic_only"
                )
            if frequency_uncertainty_chain.get("facility_qra_claim") is True:
                errors.append(
                    "facility frequency uncertainty closure cannot claim facility QRA"
                )

    release_boundary = chain.get("release_boundary")
    if release_boundary is not None:
        if not isinstance(release_boundary, Mapping):
            errors.append("chain.release_boundary must be an object")
        else:
            _nonnegative_int(
                release_boundary.get("case_count", 0),
                "chain.release_boundary.case_count",
                errors,
            )
            for field in (
                "termination_basis_counts",
                "isolation_status_counts",
                "inventory_status_counts",
            ):
                counts = release_boundary.get(field)
                if not isinstance(counts, Mapping):
                    errors.append(f"chain.release_boundary.{field} must be an object")
                    continue
                for key, count in counts.items():
                    _nonnegative_int(
                        count,
                        f"chain.release_boundary.{field}.{key}",
                        errors,
                    )
            if release_boundary.get("strict_release_boundary_ready") is True and release_boundary.get(
                "blocking_reasons"
            ):
                errors.append(
                    "strict release boundary cannot be ready while blocking reasons remain"
                )
            facility_gate_schema = release_boundary.get("facility_gate_schema")
            if facility_gate_schema is not None:
                if facility_gate_schema != "prism.facility_release_boundary_gate.v1":
                    errors.append(
                        "chain.release_boundary.facility_gate_schema is unsupported"
                    )
                gate_checks = release_boundary.get("facility_gate_checks")
                if not isinstance(gate_checks, Mapping):
                    errors.append(
                        "chain.release_boundary.facility_gate_checks must be an object"
                    )
                if release_boundary.get("strict_release_boundary_ready") is True and release_boundary.get(
                    "facility_gate_checks"
                ) is not None and isinstance(gate_checks, Mapping) and gate_checks.get(
                    "all_mass_residuals_closed"
                ) is False:
                    errors.append(
                        "facility release boundary cannot be ready with open mass residuals"
                    )

    release_closure = chain.get("release_closure_worklist")
    if release_closure is not None:
        if not isinstance(release_closure, Mapping):
            errors.append("chain.release_closure_worklist must be an object")
        else:
            if release_closure.get("schema") != "prism.release_closure_worklist.v1":
                errors.append("chain.release_closure_worklist.schema is unsupported")
            for field in ("case_count", "open_case_count"):
                if release_closure.get(field) is not None:
                    _nonnegative_int(
                        release_closure.get(field),
                        f"chain.release_closure_worklist.{field}",
                        errors,
                    )
            for field in (
                "closure_status_counts",
                "closure_gap_counts",
                "termination_basis_counts",
                "isolation_status_counts",
                "inventory_status_counts",
            ):
                counts = release_closure.get(field)
                if not isinstance(counts, Mapping):
                    errors.append(
                        f"chain.release_closure_worklist.{field} must be an object"
                    )
                    continue
                for key, count in counts.items():
                    _nonnegative_int(
                        count,
                        f"chain.release_closure_worklist.{field}.{key}",
                        errors,
                    )
            status_counts = release_closure.get("closure_status_counts")
            if isinstance(status_counts, Mapping):
                status_total = sum(
                    int(count) for count in status_counts.values()
                    if isinstance(count, int) and not isinstance(count, bool)
                )
                if (
                    release_closure.get("case_count") is not None
                    and status_total != release_closure.get("case_count")
                ):
                    errors.append(
                        "release closure worklist status counts must equal case count"
                    )
                ready_count = status_counts.get("READY_FOR_STRICT_REVIEW", 0)
                if (
                    release_closure.get("case_count") is not None
                    and release_closure.get("open_case_count") is not None
                    and isinstance(ready_count, int)
                    and not isinstance(ready_count, bool)
                    and release_closure.get("open_case_count")
                    != release_closure.get("case_count") - ready_count
                ):
                    errors.append(
                        "release closure worklist open cases must equal non-ready status counts"
                    )
            gap_counts = release_closure.get("closure_gap_counts")
            if isinstance(gap_counts, Mapping):
                summary_field_to_gap = {
                    "provider_packet_required_case_count": "PROVIDER_QUALIFICATION_OPEN",
                    "mass_closure_open_case_count": "MASS_CLOSURE_OPEN",
                    "isolation_open_case_count": "ISOLATION_OPEN",
                    "termination_open_case_count": "TERMINATION_OPEN",
                    "inventory_closure_open_case_count": "INVENTORY_CLOSURE_OPEN",
                }
                for field, gap_name in summary_field_to_gap.items():
                    summary_count = release_closure.get(field)
                    gap_count = gap_counts.get(gap_name, 0)
                    if (
                        isinstance(summary_count, int)
                        and not isinstance(summary_count, bool)
                        and isinstance(gap_count, int)
                        and not isinstance(gap_count, bool)
                        and summary_count != gap_count
                    ):
                        errors.append(
                            f"release closure worklist {field} must equal closure gap count {gap_name}"
                        )
            if (
                release_closure.get("case_count") is not None
                and chain.get("case_count") is not None
                and release_closure.get("case_count") != chain.get("case_count")
            ):
                errors.append(
                    "release closure worklist case count must equal primary chain case count"
                )
            for field in (
                "provider_packet_required_case_count",
                "mass_closure_open_case_count",
                "isolation_open_case_count",
                "termination_open_case_count",
                "inventory_closure_open_case_count",
            ):
                if release_closure.get(field) is not None:
                    _nonnegative_int(
                        release_closure.get(field),
                        f"chain.release_closure_worklist.{field}",
                        errors,
                    )
            for field in (
                "release_boundary_promotion_allowed",
                "frequency_inference_allowed",
                "facility_qra_allowed",
                "physical_validation_claim",
            ):
                if release_closure.get(field) is True:
                    errors.append(
                        f"chain.release_closure_worklist.{field} cannot be true"
                    )
            if release_closure.get("diagnostic_only") is not True:
                errors.append(
                    "release closure worklist must remain diagnostic_only"
                )
            if (
                release_closure.get("case_count") is not None
                and release_closure.get("open_case_count") is not None
                and release_closure.get("open_case_count")
                > release_closure.get("case_count")
            ):
                errors.append(
                    "release closure worklist open cases cannot exceed case count"
                )

    frequency_port_binding = chain.get("frequency_port_binding")
    if frequency_port_binding is not None:
        if not isinstance(frequency_port_binding, Mapping):
            errors.append("chain.frequency_port_binding must be an object")
        else:
            if frequency_port_binding.get("schema") not in {
                None,
                "prism.frequency_port_binding.v1",
            }:
                errors.append("chain.frequency_port_binding.schema is unsupported")
            for field in (
                "port_scoped_event_count",
                "port_unbound_event_count",
                "case_port_binding_mismatch_count",
                "risk_atom_port_binding_mismatch_count",
                "mismatch_count",
            ):
                if frequency_port_binding.get(field) is not None:
                    _nonnegative_int(
                        frequency_port_binding.get(field),
                        f"chain.frequency_port_binding.{field}",
                        errors,
                    )
            status = frequency_port_binding.get("status")
            if status == "ALIGNED" and frequency_port_binding.get("mismatch_count") not in {
                None,
                0,
            }:
                errors.append(
                    "aligned frequency port binding cannot contain mismatches"
                )
            if frequency_port_binding.get("assessment_nested_mirror_match") is False:
                errors.append(
                    "facility assessment and nested ledger frequency port bindings differ"
                )
            if frequency_port_binding.get("diagnostic_only") is not True:
                errors.append(
                    "frequency port binding must remain diagnostic_only"
                )
            for field in ("frequency_inference_allowed", "facility_qra_allowed"):
                if frequency_port_binding.get(field) is True:
                    errors.append(
                        f"chain.frequency_port_binding.{field} cannot be true"
                    )

    # External equipment/P&ID and frequency ledgers are readiness evidence.
    # They are intentionally copied into the v0.6.0 report without opening a
    # release, frequency-inference, or facility-QRA gate.
    external_equipment = chain.get("external_equipment_model_readiness")
    if external_equipment is not None:
        if not isinstance(external_equipment, Mapping):
            errors.append("chain.external_equipment_model_readiness must be an object")
        else:
            for field in (
                "asset_count",
                "state_model_ready_asset_count",
                "physical_time_assigned_event_count",
            ):
                if external_equipment.get(field) is not None:
                    _nonnegative_int(
                        external_equipment.get(field),
                        f"chain.external_equipment_model_readiness.{field}",
                        errors,
                    )
            if external_equipment.get("diagnostic_only") is not True:
                errors.append(
                    "external equipment readiness must remain diagnostic_only"
                )
            if external_equipment.get("facility_qra_claim") is True:
                errors.append(
                    "external equipment readiness cannot claim facility QRA"
                )
            if external_equipment.get("accident_release_packet_allowed") is True:
                errors.append(
                    "external equipment readiness cannot open accident release"
                )
            if external_equipment.get("frequency_inference_allowed") is True:
                errors.append(
                    "external equipment readiness cannot allow frequency inference"
                )
            for evidence_name in (
                "pid_identity_evidence",
                "pid_port_evidence",
                "component_binding_evidence",
            ):
                evidence = external_equipment.get(evidence_name)
                if evidence is None:
                    continue
                if not isinstance(evidence, Mapping):
                    errors.append(
                        f"chain.external_equipment_model_readiness.{evidence_name} must be an object"
                    )
                    continue
                for field, count in evidence.items():
                    if field.endswith("_count") and count is not None:
                        _nonnegative_int(
                            count,
                            f"chain.external_equipment_model_readiness.{evidence_name}.{field}",
                            errors,
                        )
                if evidence.get("promotion_allowed") is True:
                    errors.append(
                        f"external equipment {evidence_name} cannot allow promotion"
                    )
                if evidence.get("general_facility_identity_resolved") is True:
                    errors.append(
                        "external equipment P&ID identity cannot claim general-facility resolution"
                    )

    scenario_coverage = chain.get("equipment_scenario_coverage")
    if scenario_coverage is not None:
        if not isinstance(scenario_coverage, Mapping):
            errors.append("chain.equipment_scenario_coverage must be an object")
        else:
            for field in (
                "asset_count",
                "mapped_asset_count",
                "resolved_asset_count",
                "scenario_family_count",
            ):
                if scenario_coverage.get(field) is not None:
                    _nonnegative_int(
                        scenario_coverage.get(field),
                        f"chain.equipment_scenario_coverage.{field}",
                        errors,
                    )
            if scenario_coverage.get("diagnostic_only") is not True:
                errors.append("equipment scenario coverage must remain diagnostic_only")
            for field in (
                "accident_release_packet_allowed",
                "frequency_inference_allowed",
                "facility_qra_allowed",
            ):
                if scenario_coverage.get(field) is True:
                    errors.append(
                        f"chain.equipment_scenario_coverage.{field} cannot be true"
                    )

    frequency_binding = chain.get("equipment_frequency_binding")
    if frequency_binding is not None:
        if not isinstance(frequency_binding, Mapping):
            errors.append("chain.equipment_frequency_binding must be an object")
        else:
            for field in (
                "resolved_asset_count",
                "frequency_event_count",
                "valid_frequency_event_count",
                "uncomputed_family_count",
            ):
                if frequency_binding.get(field) is not None:
                    _nonnegative_int(
                        frequency_binding.get(field),
                        f"chain.equipment_frequency_binding.{field}",
                        errors,
                    )
            if frequency_binding.get("diagnostic_only") is not True:
                errors.append("equipment frequency binding must remain diagnostic_only")
            if frequency_binding.get("provider_release_required") is not True:
                errors.append(
                    "equipment frequency binding must require provider release"
                )
            for field in ("frequency_inference_allowed", "facility_qra_allowed"):
                if frequency_binding.get(field) is True:
                    errors.append(
                        f"chain.equipment_frequency_binding.{field} cannot be true"
                    )

    generic_scenario_coverage = chain.get("generic_equipment_scenario_coverage")
    if generic_scenario_coverage is not None:
        if not isinstance(generic_scenario_coverage, Mapping):
            errors.append(
                "chain.generic_equipment_scenario_coverage must be an object"
            )
        else:
            for field in (
                "asset_count",
                "mapped_asset_count",
                "resolved_asset_count",
                "scenario_family_count",
            ):
                if generic_scenario_coverage.get(field) is not None:
                    _nonnegative_int(
                        generic_scenario_coverage.get(field),
                        f"chain.generic_equipment_scenario_coverage.{field}",
                        errors,
                    )
            if generic_scenario_coverage.get("diagnostic_only") is not True:
                errors.append(
                    "generic equipment scenario coverage must remain diagnostic_only"
                )
            for field in (
                "accident_release_packet_allowed",
                "frequency_inference_allowed",
                "facility_qra_allowed",
            ):
                if generic_scenario_coverage.get(field) is True:
                    errors.append(
                        f"chain.generic_equipment_scenario_coverage.{field} cannot be true"
                    )

    generic_frequency_binding = chain.get("generic_equipment_frequency_binding")
    if generic_frequency_binding is not None:
        if not isinstance(generic_frequency_binding, Mapping):
            errors.append(
                "chain.generic_equipment_frequency_binding must be an object"
            )
        else:
            for field in (
                "resolved_asset_count",
                "frequency_event_count",
                "valid_frequency_event_count",
                "uncomputed_family_count",
            ):
                if generic_frequency_binding.get(field) is not None:
                    _nonnegative_int(
                        generic_frequency_binding.get(field),
                        f"chain.generic_equipment_frequency_binding.{field}",
                        errors,
                    )
            port_binding = generic_frequency_binding.get("frequency_port_binding")
            if port_binding is not None:
                if not isinstance(port_binding, Mapping):
                    errors.append(
                        "chain.generic_equipment_frequency_binding.frequency_port_binding must be an object"
                    )
                else:
                    if port_binding.get("schema") != "prism.frequency_port_binding.v1":
                        errors.append(
                            "chain.generic_equipment_frequency_binding.frequency_port_binding.schema is unsupported"
                        )
                    for field in (
                        "reviewed_port_bound_event_count",
                        "port_unbound_event_count",
                        "port_binding_withheld_event_count",
                    ):
                        if port_binding.get(field) is not None:
                            _nonnegative_int(
                                port_binding.get(field),
                                f"chain.generic_equipment_frequency_binding.frequency_port_binding.{field}",
                                errors,
                            )
                    if port_binding.get("strict_facility_qra_gate") is True:
                        errors.append(
                            "chain.generic_equipment_frequency_binding.frequency_port_binding.strict_facility_qra_gate cannot be true"
                        )
            if generic_frequency_binding.get("diagnostic_only") is not True:
                errors.append(
                    "generic equipment frequency binding must remain diagnostic_only"
                )
            if generic_frequency_binding.get("provider_release_required") is not True:
                errors.append(
                    "generic equipment frequency binding must require provider release"
                )
            for field in ("frequency_inference_allowed", "facility_qra_allowed"):
                if generic_frequency_binding.get(field) is True:
                    errors.append(
                        f"chain.generic_equipment_frequency_binding.{field} cannot be true"
                    )

    generic_diagnostic_binding = chain.get("generic_diagnostic_campaign_binding")
    if generic_diagnostic_binding is not None:
        if not isinstance(generic_diagnostic_binding, Mapping):
            errors.append(
                "chain.generic_diagnostic_campaign_binding must be an object"
            )
        else:
            if generic_diagnostic_binding.get("schema_version") != "prism.diagnostic_campaign_binding.v1":
                errors.append(
                    "chain.generic_diagnostic_campaign_binding.schema_version is unsupported"
                )
            for field in (
                "packet_event_count",
                "campaign_event_count",
                "campaign_case_count",
                "campaign_risk_atom_count",
                "packet_digest_checked_event_count",
                "packet_digest_match_event_count",
                "packet_value_checked_event_count",
                "packet_value_consumed_event_count",
                "qualified_provider_packet_count",
            ):
                if generic_diagnostic_binding.get(field) is not None:
                    _nonnegative_int(
                        generic_diagnostic_binding.get(field),
                        f"chain.generic_diagnostic_campaign_binding.{field}",
                        errors,
                    )
            if generic_diagnostic_binding.get("diagnostic_only") is not True:
                errors.append(
                    "generic diagnostic campaign binding must remain diagnostic_only"
                )
            for field in (
                "frequency_from_provider_packet",
                "facility_qra_claim",
                "physical_validation_claim",
            ):
                if generic_diagnostic_binding.get(field) is True:
                    errors.append(
                        f"chain.generic_diagnostic_campaign_binding.{field} cannot be true"
                    )
            if generic_diagnostic_binding.get("packet_claims_preserved") is not True:
                errors.append(
                    "generic diagnostic campaign binding must preserve packet claims"
                )

    generic_chain_closure = chain.get("generic_release_to_final_damage_closure")
    if generic_chain_closure is not None:
        if not isinstance(generic_chain_closure, Mapping):
            errors.append(
                "chain.generic_release_to_final_damage_closure must be an object"
            )
        else:
            if generic_chain_closure.get("schema_version") != "prism.facility_chain_closure_audit.v1":
                errors.append(
                    "chain.generic_release_to_final_damage_closure.schema_version is unsupported"
                )
            for field in (
                "campaign_event_count",
                "campaign_case_count",
                "campaign_risk_atom_count",
                "packet_event_count",
                "packet_chain_closed_event_count",
                "packet_chain_mismatch_event_count",
                "campaign_events_without_packet_count",
                "qualified_provider_packet_count",
            ):
                if generic_chain_closure.get(field) is not None:
                    _nonnegative_int(
                        generic_chain_closure.get(field),
                        f"chain.generic_release_to_final_damage_closure.{field}",
                        errors,
                    )
            if generic_chain_closure.get("diagnostic_only") is not True:
                errors.append(
                    "generic release-to-final-damage closure must remain diagnostic_only"
                )
            for field in (
                "facility_total_risk_available",
                "complete_facility_qra_claim",
                "frequency_from_provider_packet",
                "physical_validation_claim",
                "facility_qra_claim",
            ):
                if generic_chain_closure.get(field) is True:
                    errors.append(
                        f"chain.generic_release_to_final_damage_closure.{field} cannot be true"
                    )
            for field in (
                "facility_ir_aggregate_closed",
                "facility_fn_aggregate_closed",
            ):
                if generic_chain_closure.get(field) is not True:
                    errors.append(
                        f"chain.generic_release_to_final_damage_closure.{field} must be true"
                    )

    generic_provider_closure = chain.get("generic_provider_release_closure")
    if generic_provider_closure is not None:
        if not isinstance(generic_provider_closure, Mapping):
            errors.append(
                "chain.generic_provider_release_closure must be an object"
            )
        else:
            if generic_provider_closure.get("schema_version") != (
                "prism.generic_provider_release_closure_audit.v1"
            ):
                errors.append(
                    "chain.generic_provider_release_closure.schema_version is unsupported"
                )
            for field in (
                "event_count",
                "closure_ready_event_count",
                "closure_open_event_count",
                "packet_path_count",
                "provider_packet_count",
                "closure_ready_packet_path_count",
                "closure_ready_provider_packet_count",
                "qualified_provider_packet_count",
            ):
                if generic_provider_closure.get(field) is not None:
                    _nonnegative_int(
                        generic_provider_closure.get(field),
                        f"chain.generic_provider_release_closure.{field}",
                        errors,
                    )
            for field in (
                "frequency_from_provider_packet",
                "physical_validation_claim",
                "facility_qra_claim",
            ):
                if generic_provider_closure.get(field) is True:
                    errors.append(
                        f"chain.generic_provider_release_closure.{field} cannot be true"
                    )
            if generic_provider_closure.get("diagnostic_only") is not True:
                errors.append(
                    "generic provider release closure must remain diagnostic_only"
                )
            ready = generic_provider_closure.get("closure_ready_event_count")
            opened = generic_provider_closure.get("closure_open_event_count")
            total = generic_provider_closure.get("event_count")
            if all(isinstance(value, int) and not isinstance(value, bool)
                   for value in (ready, opened, total)) and ready + opened != total:
                errors.append(
                    "generic provider release closure event counts must close over event_count"
                )

    generic_provider_evidence = chain.get("generic_provider_evidence_requests")
    if generic_provider_evidence is not None:
        if not isinstance(generic_provider_evidence, Mapping):
            errors.append(
                "chain.generic_provider_evidence_requests must be an object"
            )
        else:
            if generic_provider_evidence.get("schema_version") != (
                "prism.generic_provider_evidence_requests.v1"
            ):
                errors.append(
                    "chain.generic_provider_evidence_requests.schema_version is unsupported"
                )
            for field in (
                "event_count",
                "packet_path_count",
                "packet_count",
                "request_count",
                "closure_open_request_count",
                "qualification_open_request_count",
                "qualified_provider_packet_count",
            ):
                if generic_provider_evidence.get(field) is not None:
                    _nonnegative_int(
                        generic_provider_evidence.get(field),
                        f"chain.generic_provider_evidence_requests.{field}",
                        errors,
                    )
            for field in (
                "frequency_inference_allowed",
                "facility_qra_allowed",
            ):
                if generic_provider_evidence.get(field) is True:
                    errors.append(
                        f"chain.generic_provider_evidence_requests.{field} cannot be true"
                    )
            if generic_provider_evidence.get("diagnostic_only") is not True:
                errors.append(
                    "generic provider evidence requests must remain diagnostic_only"
                )
            packet_count = generic_provider_evidence.get("packet_count")
            request_count = generic_provider_evidence.get("request_count")
            closure_open = generic_provider_evidence.get("closure_open_request_count")
            qualification_open = generic_provider_evidence.get(
                "qualification_open_request_count"
            )
            if all(
                isinstance(item, int) and not isinstance(item, bool)
                for item in (packet_count, request_count, closure_open, qualification_open)
            ):
                if request_count != packet_count:
                    errors.append(
                        "generic provider evidence request count must equal provider packet count"
                    )
                if closure_open + qualification_open != request_count:
                    errors.append(
                        "generic provider evidence request kinds must close over request_count"
                    )
            if generic_provider_evidence.get("qualified_provider_packet_count") not in (0, None):
                errors.append(
                    "generic provider evidence requests cannot report a qualified provider packet"
                )
            if isinstance(generic_provider_closure, Mapping):
                closure_packets = generic_provider_closure.get("provider_packet_count")
                if (
                    isinstance(closure_packets, int)
                    and isinstance(packet_count, int)
                    and closure_packets != packet_count
                ):
                    errors.append(
                        "generic provider evidence request packet count disagrees with closure audit"
                    )

    generic_provider_evidence_audit = chain.get("generic_provider_evidence_audit")
    if generic_provider_evidence_audit is not None:
        if not isinstance(generic_provider_evidence_audit, Mapping):
            errors.append("chain.generic_provider_evidence_audit must be an object")
        else:
            if generic_provider_evidence_audit.get("schema_version") != (
                "prism.generic_provider_evidence_audit.v1"
            ):
                errors.append(
                    "chain.generic_provider_evidence_audit.schema_version is unsupported"
                )
            for field in (
                "request_count",
                "packet_count",
                "qualification_sidecar_present_count",
                "exact_match_count",
                "qualified_provider_packet_count",
            ):
                if generic_provider_evidence_audit.get(field) is not None:
                    _nonnegative_int(
                        generic_provider_evidence_audit.get(field),
                        f"chain.generic_provider_evidence_audit.{field}",
                        errors,
                    )
            for field in ("frequency_inference_allowed", "facility_qra_allowed"):
                if generic_provider_evidence_audit.get(field) is True:
                    errors.append(
                        f"chain.generic_provider_evidence_audit.{field} cannot be true"
                    )
            if generic_provider_evidence_audit.get("diagnostic_only") is not True:
                errors.append("generic provider evidence audit must remain diagnostic_only")
            if (
                isinstance(generic_provider_evidence, Mapping)
                and generic_provider_evidence_audit.get("request_count")
                != generic_provider_evidence.get("request_count")
            ):
                errors.append(
                    "generic provider evidence audit request count disagrees with evidence catalog"
                )
            if (
                isinstance(generic_provider_evidence, Mapping)
                and generic_provider_evidence_audit.get("packet_count")
                != generic_provider_evidence.get("packet_count")
            ):
                errors.append(
                    "generic provider evidence audit packet count disagrees with evidence catalog"
                )
            audit_qualified = generic_provider_evidence_audit.get(
                "qualified_provider_packet_count"
            )
            audit_exact = generic_provider_evidence_audit.get("exact_match_count")
            audit_requests = generic_provider_evidence_audit.get("request_count")
            if (
                isinstance(audit_qualified, int)
                and isinstance(audit_exact, int)
                and audit_qualified > audit_exact
            ):
                errors.append(
                    "generic provider evidence audit qualified count cannot exceed exact sidecar matches"
                )
            if (
                isinstance(audit_qualified, int)
                and isinstance(audit_requests, int)
                and audit_qualified > audit_requests
            ):
                errors.append(
                    "generic provider evidence audit qualified count cannot exceed request count"
                )

    isolation_extension = chain.get("isolation_union_extension")
    if isolation_extension is not None:
        if not isinstance(isolation_extension, Mapping):
            errors.append("chain.isolation_union_extension must be an object")
        else:
            if isolation_extension.get("schema") != "prism.isolation_union_extension_verification.v1":
                errors.append(
                    "chain.isolation_union_extension.schema is unsupported"
                )
            if isolation_extension.get("status") != "ISOLATION_UNION_EXTENSION_DIAGNOSTIC":
                errors.append(
                    "chain.isolation_union_extension must remain diagnostic"
                )
            for counts_name in ("base_counts", "isolation_counts", "merged_counts"):
                counts = isolation_extension.get(counts_name)
                if not isinstance(counts, Mapping):
                    errors.append(
                        f"chain.isolation_union_extension.{counts_name} must be an object"
                    )
                    continue
                for field in ("events", "cases", "risk_atoms"):
                    if counts.get(field) is not None:
                        _nonnegative_int(
                            counts.get(field),
                            f"chain.isolation_union_extension.{counts_name}.{field}",
                            errors,
                        )
            base_counts = isolation_extension.get("base_counts")
            isolation_counts = isolation_extension.get("isolation_counts")
            merged_counts = isolation_extension.get("merged_counts")
            if (
                isinstance(base_counts, Mapping)
                and isinstance(isolation_counts, Mapping)
                and isinstance(merged_counts, Mapping)
            ):
                for field in ("events", "cases", "risk_atoms"):
                    if (
                        base_counts.get(field) is not None
                        and isolation_counts.get(field) is not None
                        and merged_counts.get(field) is not None
                        and merged_counts.get(field)
                        != base_counts.get(field) + isolation_counts.get(field)
                    ):
                        errors.append(
                            f"chain.isolation_union_extension.{field} counts do not add"
                        )
                if (
                    base_counts.get("events") != chain.get("event_count")
                    or base_counts.get("cases") != chain.get("case_count")
                    or base_counts.get("risk_atoms") != chain.get("risk_atom_count")
                ):
                    errors.append(
                        "chain.isolation_union_extension base counts differ from primary chain"
                    )
            for field in (
                "success_cases",
                "failure_cases",
                "state_snapshot_bound_cases",
                "provider_response_consumed",
                "qualified_provider_packet_case_count",
            ):
                if field in isolation_extension:
                    value_for_field = isolation_extension.get(field)
                    if field == "provider_response_consumed":
                        if value_for_field is not True:
                            errors.append(
                                "isolation extension must record provider response consumption"
                            )
                    elif value_for_field is not None:
                        _nonnegative_int(
                            value_for_field,
                            f"chain.isolation_union_extension.{field}",
                            errors,
                        )
            # The flattened readiness block stores the two branch counters in
            # isolation_counts; require balanced diagnostic branches there.
            if isinstance(isolation_counts, Mapping):
                success_cases = isolation_counts.get("success_cases")
                failure_cases = isolation_counts.get("failure_cases")
                if success_cases != failure_cases:
                    errors.append(
                        "isolation extension success/failure branch counts must balance"
                    )
                if isolation_counts.get("provider_response_consumed") is not True:
                    errors.append(
                        "isolation extension provider response must be consumed"
                    )
                if (
                    isolation_counts.get("state_snapshot_bound_cases")
                    != isolation_counts.get("cases")
                ):
                    errors.append(
                        "isolation extension state snapshots must cover all cases"
                    )
            if isolation_extension.get("diagnostic_only") is not True:
                errors.append("isolation extension must remain diagnostic_only")
            if isolation_extension.get("facility_qra_claim") is True:
                errors.append("isolation extension cannot claim facility QRA")

    equipment = value.get("equipment")
    equipment = equipment if isinstance(equipment, Mapping) else {}
    components = equipment.get("component_rows")
    if not isinstance(components, list):
        errors.append("equipment.component_rows must be an array")
        components = []
    observed = equipment.get("observed_component_count")
    expected = equipment.get("expected_component_count")
    if observed is not None:
        _nonnegative_int(observed, "equipment.observed_component_count", errors)
    if expected is not None:
        _nonnegative_int(expected, "equipment.expected_component_count", errors)
    if (
        isinstance(observed, int)
        and not isinstance(observed, bool)
        and isinstance(expected, int)
        and not isinstance(expected, bool)
        and observed > expected
    ):
        errors.append("equipment observed component count exceeds expected count")

    families = value.get("accident_families")
    families = families if isinstance(families, Mapping) else {}
    family_rows = families.get("rows")
    if not isinstance(family_rows, list):
        errors.append("accident_families.rows must be an array")
        family_rows = []
    required_count = families.get("required_family_count")
    if required_count != len(family_rows):
        errors.append("accident family count does not match accident family rows")
    for index, row in enumerate(family_rows):
        if not isinstance(row, Mapping):
            errors.append(f"accident_families.rows[{index}] must be an object")
            continue
        for field in (
            "case_count",
            "conditional_executed_case_count",
            "not_numerically_executed_case_count",
            "qualified_evidence_withheld_case_count",
        ):
            if row.get(field) is not None:
                _nonnegative_int(row.get(field), f"accident_families.rows[{index}].{field}", errors)
        if (
            row.get("conditional_status") == "EXECUTED"
            and row.get("not_numerically_executed_case_count") not in (0, None)
        ):
            errors.append(
                f"accident family row {index} is conditionally EXECUTED but has numerically unexecuted cases"
            )

    exclusion_set = set(value.get("explicit_exclusions", ()))
    required_exclusions = {
        "field_accident_frequency_collection",
        "sensor_based_frequency_learning",
        "indoor_release_and_confinement",
        "detonation_or_DDT",
        "full_domino_escalation",
    }
    if not required_exclusions.issubset(exclusion_set):
        errors.append("required v0.6.0 exclusion declarations are incomplete")
    frequency = value.get("frequency")
    frequency = frequency if isinstance(frequency, Mapping) else {}
    if frequency.get("sensor_frequency_learning") is not False:
        errors.append("sensor_frequency_learning must remain false")

    timing = value.get("timing")
    timing = timing if isinstance(timing, Mapping) else {}
    runtime_profile = timing.get("runtime_profile")
    if runtime_profile is not None:
        if not isinstance(runtime_profile, Mapping):
            errors.append("timing.runtime_profile must be an object")
        else:
            allowed_modes = {
                "cached_diagnostic_1hz",
                "fresh_physics_1hz",
                "offline_campaign",
            }
            if runtime_profile.get("recommended_mode") not in allowed_modes:
                errors.append("timing.runtime_profile.recommended_mode is unsupported")
            if runtime_profile.get("facility_qra_realtime_claim") is not False:
                errors.append(
                    "timing.runtime_profile cannot claim real-time facility QRA"
                )
            for mode in ("cache_mode", "fresh_physics_mode", "campaign_mode"):
                block = runtime_profile.get(mode)
                if not isinstance(block, Mapping):
                    errors.append(f"timing.runtime_profile.{mode} must be an object")
            cache_mode = runtime_profile.get("cache_mode")
            if isinstance(cache_mode, Mapping) and cache_mode.get("one_hz_ready") is not None:
                if not isinstance(cache_mode.get("one_hz_ready"), bool):
                    errors.append(
                        "timing.runtime_profile.cache_mode.one_hz_ready must be boolean"
                    )
            fresh_mode = runtime_profile.get("fresh_physics_mode")
            if isinstance(fresh_mode, Mapping) and fresh_mode.get("one_hz_ready") is not None:
                if not isinstance(fresh_mode.get("one_hz_ready"), bool):
                    errors.append(
                        "timing.runtime_profile.fresh_physics_mode.one_hz_ready must be boolean"
                    )
            campaign_mode = runtime_profile.get("campaign_mode")
            if isinstance(campaign_mode, Mapping) and campaign_mode.get(
                "online_one_hz_ready"
            ) is not False:
                errors.append(
                    "timing.runtime_profile.campaign_mode must remain offline"
                )

    promotion = value.get("promotion")
    promotion = promotion if isinstance(promotion, Mapping) else {}
    strict_blockers = value.get("strict_blocking_check_ids")
    if not isinstance(strict_blockers, list):
        errors.append("strict_blocking_check_ids must be an array")
        strict_blockers = []
    if strict_blockers:
        for field in (
            "facility_total_risk_available",
            "complete_facility_qra_claim",
            "physical_validation_claim",
            "facility_qra_claim",
        ):
            if promotion.get(field) is True:
                errors.append(
                    f"promotion.{field}=true while strict blockers remain"
                )
    if promotion.get("complete_facility_qra_claim") is True:
        for field in (
            "facility_total_risk_available",
            "physical_validation_claim",
            "facility_qra_claim",
        ):
            if promotion.get(field) is not True:
                errors.append(
                    f"complete facility QRA claim requires promotion.{field}=true"
                )
        if strict_blockers:
            errors.append("complete facility QRA claim requires zero strict blockers")
    if value.get("conditional_chain_complete") is True and not family_rows:
        errors.append("conditional chain cannot be complete without accident family rows")

    source_artifacts = value.get("source_artifacts")
    if source_artifacts is not None:
        if not isinstance(source_artifacts, Mapping):
            errors.append("source_artifacts must be an object when present")
        else:
            required_sources = {
                "objective_audit",
                "union_verification",
                "scope_matrix",
                "facility_assessment",
                "completion_audit",
                "validation_matrix",
                "realtime_benchmark",
            }
            if not required_sources.issubset(source_artifacts):
                errors.append("source_artifacts is missing one or more required inputs")
            for source_id, source in source_artifacts.items():
                if not isinstance(source, Mapping):
                    errors.append(f"source_artifacts.{source_id} must be an object")
                    continue
                digest = source.get("sha256")
                if not isinstance(digest, str) or len(digest) != 64:
                    errors.append(f"source_artifacts.{source_id}.sha256 must be a SHA-256 digest")
                if not isinstance(source.get("path"), str) or not source.get("path"):
                    errors.append(f"source_artifacts.{source_id}.path must be nonempty")

    evidence_request = value.get("evidence_request")
    if evidence_request is not None:
        if not isinstance(evidence_request, Mapping):
            errors.append("evidence_request must be an object when present")
        else:
            for field in (
                "case_request_count",
                "family_request_count",
                "component_request_count",
            ):
                if evidence_request.get(field) is not None:
                    _nonnegative_int(
                        evidence_request.get(field),
                        f"evidence_request.{field}",
                        errors,
                    )
            if evidence_request.get("provider_export_schema_required") != "prism.external_accident_history.v1":
                errors.append(
                    "evidence_request.provider_export_schema_required must be prism.external_accident_history.v1"
                )
            if not isinstance(evidence_request.get("blocking_reasons"), list):
                errors.append("evidence_request.blocking_reasons must be an array")
            if not isinstance(evidence_request.get("strict_gate_categories"), list):
                errors.append("evidence_request.strict_gate_categories must be an array")
            if evidence_request.get("facility_promotion_allowed_now") is True:
                errors.append(
                    "evidence_request cannot allow facility promotion in a readiness ledger"
                )

    scenario_evidence = value.get("scenario_evidence")
    if scenario_evidence is not None:
        if not isinstance(scenario_evidence, Mapping):
            errors.append("scenario_evidence must be an object when present")
        else:
            allowed_schemas = {
                "prism.scenario_evidence_audit.v1",
                "prism.external_scenario_evidence.v1",
                "prism.inspection_center_screening_summary.v1",
            }
            if scenario_evidence.get("schema") not in allowed_schemas:
                errors.append("scenario_evidence.schema is not a supported screening schema")
            for field in (
                "scenario_row_count",
                "csv_count",
                "workbook_count",
                "telemetry_candidate_sheet_count",
                "telemetry_metadata_incomplete_sheet_count",
                "qualified_provider_packet_count",
            ):
                if scenario_evidence.get(field) is not None:
                    _nonnegative_int(
                        scenario_evidence.get(field),
                        f"scenario_evidence.{field}",
                        errors,
                    )
            for field in (
                "candidate_accident_family_counts",
                "candidate_monitoring_signal_counts",
                "scope_status_counts",
            ):
                counts = scenario_evidence.get(field)
                if not isinstance(counts, Mapping):
                    errors.append(f"scenario_evidence.{field} must be an object")
                    continue
                for key, count in counts.items():
                    _nonnegative_int(count, f"scenario_evidence.{field}.{key}", errors)
            for field in (
                "frequency_assigned",
                "sensor_frequency_learning_used",
                "facility_qra_claim",
                "candidate_only",
            ):
                if scenario_evidence.get(field) is not False and field != "candidate_only":
                    errors.append(f"scenario_evidence.{field} must remain false")
            if scenario_evidence.get("candidate_only") is not True:
                errors.append("scenario_evidence.candidate_only must remain true")
            if not isinstance(scenario_evidence.get("blocking_reasons"), list):
                errors.append("scenario_evidence.blocking_reasons must be an array")
            if scenario_evidence.get("qualified_provider_packet_count") not in (0, None):
                errors.append("scenario evidence cannot report a qualified provider packet")

    if errors:
        raise V060ReadinessError("; ".join(errors))
    return {
        "schema_version": READINESS_SCHEMA,
        "status": "VALID",
        "strict_blocking_check_count": len(strict_blockers),
        "component_row_count": len(components),
        "accident_family_row_count": len(family_rows),
        "invariant_count": 13,
    }


__all__ = [
    "READINESS_SCHEMA",
    "V060ReadinessError",
    "build_v060_readiness_report",
    "validate_v060_readiness_report",
]
