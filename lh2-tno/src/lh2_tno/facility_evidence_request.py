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
                "strict_uncomputed_case_count": row.get("uncomputed_case_count", 0),
                "conditional_executed_case_count": row.get(
                    "conditional_executed_case_count", row.get("executed_case_count", 0)
                ),
                "conditional_uncomputed_case_count": row.get(
                    "conditional_uncomputed_case_count", row.get("uncomputed_case_count", 0)
                ),
                "operator_limited_case_count": row.get("operator_limited_case_count", 0),
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
                    or (status == "EXECUTED" and row.get("uncomputed_case_count", 0) == 0)
                ),
            }
        )

    component_statuses = ledger.get("component_statuses", {})
    if not isinstance(component_statuses, Mapping):
        raise ValueError("assessment.facility_risk_ledger.component_statuses must be an object")
    components = [
        {
            "component_id": str(component_id),
            "current_status": str(status),
            "required_evidence": list(_COMMON_REQUIREMENTS),
        }
        for component_id, status in sorted(component_statuses.items())
        if str(status) != "EXCLUDED"
    ]
    excluded_components = [
        {"component_id": str(component_id), "current_status": str(status)}
        for component_id, status in sorted(component_statuses.items())
        if str(status) == "EXCLUDED"
    ]

    blockers = ledger.get("blocking_reasons", ())
    if not isinstance(blockers, Sequence) or isinstance(blockers, (str, bytes)):
        raise ValueError("assessment.facility_risk_ledger.blocking_reasons must be an array")

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
        },
        "blocking_reasons": list(dict.fromkeys(str(item) for item in blockers)),
        "family_requests": family_rows,
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
    }


__all__ = ["SCHEMA", "PROVIDER_SCHEMA", "build_facility_evidence_request"]
