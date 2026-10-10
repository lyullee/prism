"""Build a fail-closed request for the evidence still needed by a facility QRA.

The facility assessment already records which accident families and components
were executed.  This module turns that accounting into an actionable, generic
request for provider evidence.  It never invents a frequency, fills a missing
case, or promotes a diagnostic packet.  The output is deliberately suitable
for handing to any LH2 digital-twin provider, not just the inspection-centre
model.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.facility_evidence_request.v1"
PROVIDER_SCHEMA = "prism.external_accident_history.v1"

_COMMON_REQUIREMENTS = (
    "qualified_actual provider status with provider source/result SHA-256 digests and evidence identifier",
    "exact component_id, accident port, event_id, opening geometry, position and direction",
    "provider-owned time history with start/end clock and explicit termination basis",
    "provider mass and energy closure with residuals and initial/final inventory",
    "prism.provider_release_closure_audit.v1 with termination, isolation and inventory checks closed",
    "independent physical validation or a declared validation gap for the release boundary",
)

_FAMILY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "vessel_hole": ("tank pressure, phase inventory and vessel opening history",),
    "pipe_hole": ("pipe upstream/downstream state and isolation response history",),
    "valve_hole": ("valve opening command, travel/closure history and upstream state",),
    "vent_hole": ("relief/vent set point, capacity and discharge termination history",),
    "pump_hole": ("pump trip/seal failure state and connected inventory history",),
    "vaporizer_hole": ("vaporizer process-side state, failure mode and boundary history",),
    "reliquefier_hole": ("reliquefier failure mode, connected inventory and outlet history",),
    "liquid_two_phase": ("flash quality, gas/liquid/ground partition and droplet treatment",),
    "inventory_depletion": ("positive inventory threshold, depletion clock and final residual mass",),
    "inventory_over_600s": ("complete 600 s provider history and end-of-horizon inventory",),
    "two_sided_rupture": (
        "both provider outlets, endpoint geometry and same-event coupling",
        "paired plume/pressure/inventory interaction output or an explicit provider unresolved-interaction declaration",
    ),
    "vertical_handoff": ("provider-owned vertical-to-horizontal handoff state and boundary",),
}

_GATE_REQUIREMENTS: dict[str, str] = {
    "MISSING_PROVIDER_CASES": "one exact qualified provider packet for every strict uncomputed case",
    "OPERATOR_LIMITED_INPUT": "replace synthetic, screening or operator-limited boundary inputs with provider-owned facility evidence",
    "DOMAIN_INCOMPLETE": "close the declared model-domain boundary and provide the missing consequence handoff evidence",
    "FAILED_PROVIDER_CASE": "repeat the failed provider case with a reproducible error-free release ledger",
    "FAMILY_SCOPE_PARTIAL": "complete the family-specific accident branch and termination coverage",
}

_CASE_STATUS_RANK = {
    "EXECUTED": 0,
    "EXECUTED_OPERATOR_LIMITED": 1,
    "EXECUTED_DOMAIN_INCOMPLETE": 2,
    "UNCOMPUTED": 3,
    "FAILED": 4,
}


def _gate_categories(row: Mapping[str, Any], status: str, strict_uncomputed_case_count: Any) -> list[str]:
    """Classify why strict promotion is withheld without inferring a cause."""
    categories: list[str] = []
    try:
        strict_count = max(0, int(strict_uncomputed_case_count or 0))
    except (TypeError, ValueError):
        strict_count = 0
    try:
        operator_count = max(0, int(row.get("operator_limited_case_count", 0) or 0))
    except (TypeError, ValueError):
        operator_count = 0
    try:
        domain_count = max(0, int(row.get("domain_incomplete_case_count", 0) or 0))
    except (TypeError, ValueError):
        domain_count = 0
    try:
        failed_count = max(0, int(row.get("failed_case_count", 0) or 0))
    except (TypeError, ValueError):
        failed_count = 0
    if strict_count:
        categories.append("MISSING_PROVIDER_CASES")
    if operator_count:
        categories.append("OPERATOR_LIMITED_INPUT")
    if domain_count:
        categories.append("DOMAIN_INCOMPLETE")
    if failed_count:
        categories.append("FAILED_PROVIDER_CASE")
    if status not in {"EXECUTED", "NOT_APPLICABLE"} and not categories:
        categories.append("FAMILY_SCOPE_PARTIAL")
    return categories


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    result = []
    for index, row in enumerate(value):
        result.append(_mapping(row, f"{label}[{index}]"))
    return result


def _status(row: Mapping[str, Any]) -> str:
    value = row.get("status")
    return value.strip() if isinstance(value, str) and value.strip() else "UNSPECIFIED"


def _case_identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return the stable facility case key used to collapse ledger duplicates."""
    return (
        str(row.get("event_id", "")),
        str(row.get("annual_condition_id", "")),
        str(row.get("release_branch_id", "")),
    )


def _case_status_rank(value: Any) -> int:
    return _CASE_STATUS_RANK.get(str(value), 5)


def _case_required_families(row: Mapping[str, Any]) -> list[str]:
    families = row.get("scenario_families", ())
    if not isinstance(families, Sequence) or isinstance(families, (str, bytes)):
        return []
    return sorted({str(family) for family in families if str(family).strip()})


def _port_ids(value: Any) -> list[str] | None:
    """Normalize an explicit port list while preserving an absent list."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    return [str(item) for item in value if str(item).strip()]


def _case_gap_class(
    status: str,
    *,
    identity: Mapping[str, Any],
    qualification_gap: bool,
) -> str:
    """Classify the closure state of one requested facility case.

    The classification is accounting metadata only.  It deliberately keeps a
    numerically missing case separate from a computed case whose provider
    qualification or exact packet identity is still unavailable.
    """
    if status in {"UNCOMPUTED", "FAILED"}:
        return "NUMERICAL_CASE_MISSING"
    if status.startswith("EXECUTED") or qualification_gap or not identity:
        return "QUALIFICATION_EVIDENCE_WITHHELD"
    return "FAMILY_SCOPE_PARTIAL"


def _release_boundary_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the current release-boundary evidence without recalculating it."""
    termination = row.get("termination")
    termination = termination if isinstance(termination, Mapping) else {}
    domain = row.get("domain_assessment")
    domain = domain if isinstance(domain, Mapping) else {}
    mass = row.get("mass_ledger")
    mass = mass if isinstance(mass, Mapping) else {}
    return {
        "termination_basis": termination.get("basis"),
        "termination_time_s": termination.get("time_s"),
        "termination_provenance": termination.get("provenance"),
        "domain_truncated": domain.get("domain_truncated"),
        "inventory_outside_domain": domain.get("inventory_outside_domain"),
        "outside_domain_h2_kg_at_ignition": domain.get(
            "outside_domain_h2_kg_at_ignition"
        ),
        "end_to_end_residual_kg": mass.get("end_to_end_residual_kg"),
    }


def _release_boundary_gaps(
    row: Mapping[str, Any],
    *,
    status: str,
) -> list[str]:
    """List observable release-boundary limitations for the evidence request."""
    summary = _release_boundary_summary(row)
    gaps: list[str] = []
    if summary["termination_basis"] is None:
        gaps.append("current case has no explicit release termination record")
    elif summary["termination_basis"] == "synthetic_diagnostic_horizon":
        gaps.append("current release ends at a synthetic diagnostic horizon")
    if summary["domain_truncated"] is True:
        gaps.append("current consequence domain is truncated")
    if summary["inventory_outside_domain"] is True:
        gaps.append("current inventory remains outside the consequence domain")
    if summary["end_to_end_residual_kg"] is None:
        gaps.append("current case has no end-to-end mass-closure residual")
    if status in {"EXECUTED_OPERATOR_LIMITED", "EXECUTED_DOMAIN_INCOMPLETE"}:
        reason = row.get("reason")
        if isinstance(reason, str) and reason.strip():
            gaps.append(f"provider qualification withheld: {reason.strip()}")
    return list(dict.fromkeys(gaps))


def _build_case_requests(
    ledger: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build exact provider requests from facility cases without inventing inputs.

    The merged ledger historically contains a case in both ``cases`` and
    ``uncomputed_cases`` when a consequence run exposed a second limitation.
    We collapse those rows by event/condition/branch and retain the most
    restrictive status plus all declared reasons.  A request is emitted when
    the case is not fully executed or when the facility has no qualified
    provider packet coverage.  This makes the request actionable while keeping
    the promotion gate fail-closed.
    """
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for source_name in ("cases", "uncomputed_cases"):
        source = ledger.get(source_name, ())
        if not isinstance(source, Sequence) or isinstance(source, (str, bytes)):
            continue
        for raw in source:
            if not isinstance(raw, Mapping):
                continue
            key = _case_identity(raw)
            current = rows.get(key)
            if current is None:
                current = dict(raw)
                current["_reasons"] = []
                rows[key] = current
            # A consequence ledger can expose the same case once as an
            # executed row and once as an uncomputed/limitation row.  The
            # provider identity is sometimes present on only one of those
            # rows.  Preserve it instead of letting source-list order decide
            # whether the exact packet request is useful.
            current_identity = current.get("provider_packet_identity")
            candidate_identity = raw.get("provider_packet_identity")
            if isinstance(candidate_identity, Mapping):
                if not isinstance(current_identity, Mapping) or not current_identity:
                    current["provider_packet_identity"] = dict(candidate_identity)
                elif dict(current_identity) != dict(candidate_identity):
                    # Keep the first identity for traceability, but make the
                    # ambiguity explicit so a later promotion cannot silently
                    # select one of two conflicting packets.
                    current["_reasons"].append(
                        "duplicate ledger rows carry conflicting provider packet identities"
                    )
            current_families = _case_required_families(current)
            candidate_families = _case_required_families(raw)
            if candidate_families:
                current["scenario_families"] = sorted(
                    set(current_families).union(candidate_families)
                )
            for field in ("asset_id", "component_id"):
                if not current.get(field) and raw.get(field):
                    current[field] = raw[field]
            current_frequency_ports = _port_ids(current.get("frequency_port_ids"))
            candidate_frequency_ports = _port_ids(raw.get("frequency_port_ids"))
            if candidate_frequency_ports is not None:
                if current_frequency_ports is None:
                    current["frequency_port_ids"] = candidate_frequency_ports
                elif current_frequency_ports != candidate_frequency_ports:
                    current["_reasons"].append(
                        "duplicate ledger rows carry conflicting reviewed frequency port IDs"
                    )
            current_status = str(current.get("status", "UNSPECIFIED"))
            candidate_status = str(raw.get("status", "UNSPECIFIED"))
            if _case_status_rank(candidate_status) > _case_status_rank(current_status):
                current["status"] = candidate_status
            for field in ("reason", "uncomputed_reason"):
                reason = raw.get(field)
                if isinstance(reason, str) and reason.strip() and reason.strip() not in current["_reasons"]:
                    current["_reasons"].append(reason.strip())

    try:
        case_count = max(0, int(ledger.get("case_count", len(rows)) or 0))
    except (TypeError, ValueError):
        case_count = len(rows)
    try:
        qualified_count = max(0, int(ledger.get("qualified_provider_packet_case_count", 0) or 0))
    except (TypeError, ValueError):
        qualified_count = 0
    qualification_gap = qualified_count < case_count

    requests: list[dict[str, Any]] = []
    for key in sorted(rows):
        row = rows[key]
        status = str(row.get("status", "UNSPECIFIED"))
        identity = row.get("provider_packet_identity")
        if not isinstance(identity, Mapping):
            identity = {}
        families = _case_required_families(row)
        family_requirements: list[str] = []
        for family in families:
            family_requirements.extend(_FAMILY_REQUIREMENTS.get(
                family,
                ("provider-specific accident history for the declared family",),
            ))
        reasons = list(row.get("_reasons", ()))
        if status != "EXECUTED":
            reasons.append(f"current case status is {status}")
        if not identity:
            reasons.append("provider packet identity is absent from the facility case")
        if qualification_gap:
            reasons.append(
                f"qualified provider packet coverage is {qualified_count}/{case_count} cases"
            )
        if not reasons:
            continue
        port_ids = identity.get("port_ids")
        reviewed_frequency_port_ids = _port_ids(row.get("frequency_port_ids"))
        provider_packet_port_ids = _port_ids(port_ids)
        if reviewed_frequency_port_ids is not None and provider_packet_port_ids is not None:
            if reviewed_frequency_port_ids != provider_packet_port_ids:
                reasons.append(
                    "provider packet port IDs differ from reviewed frequency port IDs"
                )
        requested_port_ids = (
            reviewed_frequency_port_ids
            if reviewed_frequency_port_ids is not None
            else provider_packet_port_ids
        )
        port_binding_status = (
            "PORT_BINDING_MISMATCH"
            if reviewed_frequency_port_ids is not None
            and provider_packet_port_ids is not None
            and reviewed_frequency_port_ids != provider_packet_port_ids
            else (
                "REVIEWED_FREQUENCY_PORTS"
                if reviewed_frequency_port_ids is not None
                else (
                    "PROVIDER_PACKET_PORTS_ONLY"
                    if provider_packet_port_ids is not None
                    else "PORT_BINDING_WITHHELD"
                )
            )
        )
        source_digests = identity.get("provider_source_digests", ())
        result_digests = identity.get("provider_result_digests", ())
        requests.append({
            "request_id": "/".join(str(part) for part in key),
            "event_id": row.get("event_id"),
            "asset_id": row.get("asset_id"),
            "component_id": identity.get("component_id", row.get("component_id")),
            "release_branch_id": row.get("release_branch_id"),
            "annual_condition_id": row.get("annual_condition_id"),
            "scenario_families": families,
            "current_status": status,
            "gap_class": _case_gap_class(
                status,
                identity=identity,
                qualification_gap=qualification_gap,
            ),
            "current_release_boundary": _release_boundary_summary(row),
            "current_boundary_gaps": _release_boundary_gaps(row, status=status),
            "request_kind": "QUALIFIED_PROVIDER_PACKET",
            "qualification_required": qualification_gap,
            "frequency_port_ids": reviewed_frequency_port_ids,
            "provider_packet_port_ids": provider_packet_port_ids,
            "port_binding": {
                "status": port_binding_status,
                "reviewed_frequency_port_ids": reviewed_frequency_port_ids,
                "provider_packet_port_ids": provider_packet_port_ids,
                "frequency_inference_allowed": False,
            },
            "exact_match_required": {
                "event_id": row.get("event_id"),
                "component_id": identity.get("component_id", row.get("component_id")),
                "port_ids": requested_port_ids or [],
                "reviewed_frequency_port_ids": reviewed_frequency_port_ids,
                "provider_source_digests": list(source_digests) if isinstance(source_digests, Sequence) and not isinstance(source_digests, (str, bytes)) else [],
                "provider_result_digests": list(result_digests) if isinstance(result_digests, Sequence) and not isinstance(result_digests, (str, bytes)) else [],
            },
            "current_provider_packet_identity": dict(identity),
            "required_provider_evidence": list(dict.fromkeys(
                [*_COMMON_REQUIREMENTS, *family_requirements]
            )),
            "blocking_reasons": list(dict.fromkeys(reasons)),
        })
    return requests


def build_facility_evidence_request(
    assessment: Mapping[str, Any],
    scope_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an evidence request from the current assessment and scope matrix.

    ``assessment`` is the full facility-assessment record.  ``scope_matrix`` is
    the merged accident-family matrix.  Both are treated as evidence only;
    their frequencies are copied nowhere into a new risk calculation.
    """
    assessment = _mapping(assessment, "assessment")
    scope_matrix = _mapping(scope_matrix, "scope_matrix")
    ledger = _mapping(assessment.get("facility_risk_ledger"), "assessment.facility_risk_ledger")
    matrix_rows = _rows(scope_matrix.get("rows", ()), "scope_matrix.rows")
    facility_promotion_gate = (
        assessment.get("facility_total_risk_available") is True
        and assessment.get("qualified_facility_qra_available") is True
        and assessment.get("complete_facility_qra_claim") is True
    )

    family_rows: list[dict[str, Any]] = []
    for row in matrix_rows:
        family = row.get("family")
        if not isinstance(family, str) or not family.strip():
            raise ValueError("scope_matrix row family must be a non-empty string")
        family = family.strip()
        status = _status(row)
        conditional_status = row.get("conditional_status", status)
        if not isinstance(conditional_status, str) or not conditional_status.strip():
            conditional_status = status
        not_applicable = status == "NOT_APPLICABLE"
        additional = _FAMILY_REQUIREMENTS.get(
            family,
            ("provider-specific accident history for the declared family",),
        )
        strict_uncomputed_case_count = row.get(
            "strict_uncomputed_case_count", row.get("uncomputed_case_count", 0)
        )
        gate_categories = _gate_categories(row, status, strict_uncomputed_case_count)
        family_scope_ready = (
            not_applicable
            or (status == "EXECUTED" and strict_uncomputed_case_count == 0)
        )
        family_rows.append(
            {
                "family": family,
                "current_status": status,
                "conditional_status": conditional_status,
                "applicability": "NOT_APPLICABLE" if not_applicable else "APPLICABLE",
                "evidence_required": not not_applicable,
                "generated_event_count": row.get("generated_event_count", 0),
                "executed_case_count": row.get("executed_case_count", 0),
                "uncomputed_case_count": row.get("uncomputed_case_count", 0),
                "not_numerically_executed_case_count": row.get(
                    "not_numerically_executed_case_count",
                    row.get("failed_case_count", 0),
                ),
                "qualified_evidence_withheld_case_count": row.get(
                    "qualified_evidence_withheld_case_count",
                    int(row.get("operator_limited_case_count", 0) or 0)
                    + int(row.get("domain_incomplete_case_count", 0) or 0),
                ),
                "numerically_executed_case_count": row.get(
                    "numerically_executed_case_count",
                    row.get("conditional_executed_case_count", row.get("executed_case_count", 0)),
                ),
                "strict_uncomputed_case_count": strict_uncomputed_case_count,
                "conditional_executed_case_count": row.get(
                    "conditional_executed_case_count", row.get("executed_case_count", 0)
                ),
                "conditional_uncomputed_case_count": row.get(
                    "conditional_uncomputed_case_count", row.get("uncomputed_case_count", 0)
                ),
                "operator_limited_case_count": row.get("operator_limited_case_count", 0),
                "strict_gate_categories": gate_categories,
                "gap_class": row.get("gap_class"),
                "gap_reasons": list(row.get("gap_reasons", ()))
                if isinstance(row.get("gap_reasons", ()), Sequence)
                and not isinstance(row.get("gap_reasons", ()), (str, bytes))
                else [],
                "closure_requirements": list(row.get("closure_requirements", ()))
                if isinstance(row.get("closure_requirements", ()), Sequence)
                and not isinstance(row.get("closure_requirements", ()), (str, bytes))
                else [],
                "case_status_counts": dict(row.get("case_status_counts", {}))
                if isinstance(row.get("case_status_counts", {}), Mapping)
                else {},
                "strict_gate_requirements": [
                    _GATE_REQUIREMENTS[category] for category in gate_categories
                ],
                "event_ids": list(row.get("event_ids", ())),
                "strict_blocking_reason": (
                    None
                    if not_applicable or status == "EXECUTED"
                    else f"{family}: {status}"
                ),
                "required_provider_evidence": (
                    [] if not_applicable else list(_COMMON_REQUIREMENTS + additional)
                ),
                "promotion_allowed_now": (
                    not_applicable
                    or family_scope_ready
                ),
                "family_scope_ready": family_scope_ready,
                "facility_promotion_allowed_now": family_scope_ready and facility_promotion_gate,
                "facility_promotion_blocking_reasons": (
                    []
                    if family_scope_ready and facility_promotion_gate
                    else list(dict.fromkeys([
                        *([] if family_scope_ready else [f"{family}: {status}"]),
                        *([] if facility_promotion_gate else [
                            "facility qualified IR/F-N gate is closed"
                        ]),
                    ]))
                ),
            }
        )

    component_statuses = ledger.get("component_statuses", {})
    if not isinstance(component_statuses, Mapping):
        raise ValueError("assessment.facility_risk_ledger.component_statuses must be an object")
    component_coverage = ledger.get("component_coverage", {})
    if not isinstance(component_coverage, Mapping):
        component_coverage = {}
    components: list[dict[str, Any]] = []
    for component_id, status in sorted(component_statuses.items()):
        if str(status) == "EXCLUDED":
            continue
        coverage = component_coverage.get(str(component_id), {})
        if not isinstance(coverage, Mapping):
            coverage = {}
        gate_categories = [
            str(category) for category in coverage.get("strict_gate_categories", ())
        ]
        components.append(
            {
                "component_id": str(component_id),
                "current_status": str(status),
                "event_count": coverage.get("event_count", 0),
                "conditional_case_count": coverage.get("conditional_case_count", 0),
                "conditional_executed_case_count": coverage.get(
                    "conditional_executed_case_count", 0
                ),
                "conditional_uncomputed_case_count": coverage.get(
                    "conditional_uncomputed_case_count", 0
                ),
                "strict_uncomputed_case_count": coverage.get(
                    "strict_uncomputed_case_count", 0
                ),
                "not_numerically_executed_case_count": coverage.get(
                    "not_numerically_executed_case_count", 0
                ),
                "qualified_evidence_withheld_case_count": coverage.get(
                    "qualified_evidence_withheld_case_count", 0
                ),
                "numerically_executed_case_count": coverage.get(
                    "numerically_executed_case_count", 0
                ),
                "operator_limited_case_count": coverage.get(
                    "operator_limited_case_count", 0
                ),
                "risk_atom_count": coverage.get("risk_atom_count", 0),
                "strict_gate_categories": gate_categories,
                "strict_gate_requirements": [
                    _GATE_REQUIREMENTS[category]
                    for category in gate_categories
                    if category in _GATE_REQUIREMENTS
                ],
                "required_evidence": list(_COMMON_REQUIREMENTS)
                + [
                    _GATE_REQUIREMENTS[category]
                    for category in gate_categories
                    if category in _GATE_REQUIREMENTS
                ],
            }
        )
    excluded_components = [
        {"component_id": str(component_id), "current_status": str(status)}
        for component_id, status in sorted(component_statuses.items())
        if str(status) == "EXCLUDED"
    ]

    blockers = ledger.get("blocking_reasons", ())
    if not isinstance(blockers, Sequence) or isinstance(blockers, (str, bytes)):
        raise ValueError("assessment.facility_risk_ledger.blocking_reasons must be an array")

    gate_categories = sorted({
        category
        for row in family_rows
        for category in row["strict_gate_categories"]
    } | {
        category
        for component in components
        for category in component["strict_gate_categories"]
    })
    case_requests = _build_case_requests(ledger)

    return {
        "schema_version": SCHEMA,
        "facility_id": assessment.get("facility_id", ledger.get("facility_id", scope_matrix.get("facility_id"))),
        "scope": "outdoor_major_accidents",
        "provider_export_schema_required": PROVIDER_SCHEMA,
        "status": "OPEN_EVIDENCE_REQUEST",
        "current_assessment": {
            "status": ledger.get("status"),
            "event_count": ledger.get("event_count", 0),
            "case_count": ledger.get("case_count", 0),
            "uncomputed_case_count": ledger.get("uncomputed_case_count", 0),
            "strict_uncomputed_case_count": ledger.get(
                "conditional_diagnostic_facility_coverage", {}
            ).get("strict_uncomputed_case_count", ledger.get("uncomputed_case_count", 0)),
            "conditional_case_count": ledger.get("conditional_case_count", ledger.get("case_count", 0)),
            "conditional_executed_case_count": ledger.get(
                "conditional_executed_case_count", 0
            ),
            "conditional_uncomputed_case_count": ledger.get(
                "conditional_uncomputed_case_count", 0
            ),
            "not_numerically_executed_case_count": ledger.get(
                "not_numerically_executed_case_count", 0
            ),
            "qualified_evidence_withheld_case_count": ledger.get(
                "qualified_evidence_withheld_case_count", 0
            ),
            "numerically_executed_case_count": ledger.get(
                "numerically_executed_case_count", 0
            ),
            "risk_atom_count": len(ledger.get("risk_atoms", ())) if isinstance(ledger.get("risk_atoms"), Sequence) else 0,
            "facility_total_risk_available": ledger.get("facility_total_risk_available", False),
            "physical_validation_claim": ledger.get("physical_validation_claim", False),
            "provider_packet_case_count": ledger.get("provider_packet_case_count", 0),
            "qualified_provider_packet_case_count": ledger.get(
                "qualified_provider_packet_case_count", 0
            ),
            "provider_packet_promoted": ledger.get("provider_packet_promoted", False),
            "qualified_facility_qra_available": ledger.get(
                "qualified_facility_qra_available", False
            ),
            "complete_facility_qra_claim": ledger.get(
                "complete_facility_qra_claim", False
            ),
            "facility_promotion_allowed_now": facility_promotion_gate,
            "strict_gate_categories": gate_categories,
        },
        "blocking_reasons": list(dict.fromkeys(str(item) for item in blockers)),
        "scope_gap_summary": dict(scope_matrix.get("gap_summary", {}))
        if isinstance(scope_matrix.get("gap_summary", {}), Mapping)
        else {},
        "family_requests": family_rows,
        "case_request_count": len(case_requests),
        "case_requests": case_requests,
        "component_requests": components,
        "excluded_components": excluded_components,
        "frequency_policy": {
            "use_documented_literature_frequency_only": True,
            "infer_frequency_from_provider_or_sensor": False,
            "reallocate_frequency_between_families": False,
        },
        "promotion_gate": {
            "qualified_provider_packet_required": True,
            "provider_packet_evidence_schema": "prism.provider_packet_evidence.v1",
            "provider_qualification_schema": "prism.provider_qualification_evidence.v1",
            "exact_event_component_port_and_digest_match_required": True,
            "independent_physical_validation_required": True,
            "complete_declared_scope_required": True,
            "facility_ir_fn_remains_withheld_until_all_true": True,
        },
        "strict_gate_catalog": {
            category: _GATE_REQUIREMENTS[category]
            for category in sorted(_GATE_REQUIREMENTS)
        },
    }


__all__ = ["SCHEMA", "PROVIDER_SCHEMA", "build_facility_evidence_request"]
