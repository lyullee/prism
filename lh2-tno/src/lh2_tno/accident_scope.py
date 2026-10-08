"""Audit declared outdoor major-accident coverage for an LH2 campaign.

The campaign result already reports event and component coverage.  This
module adds the accident-mechanism view needed for an IJHE methods table:
which release/termination adapter was actually represented, which weather
cases reached the damage chain, and which mechanisms were never generated or
remain uncomputed.  It is an accounting report, not a consequence solver.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .campaign import RiskCampaign
from .consequences import ConsequenceRequest
from .equipment_manifest import EquipmentManifest, audit_manifest


MAJOR_ACCIDENT_FAMILIES = (
    "vessel_hole",
    "pipe_hole",
    "valve_hole",
    "vent_hole",
    "pump_hole",
    "vaporizer_hole",
    "reliquefier_hole",
    "liquid_two_phase",
    "inventory_depletion",
    "inventory_over_600s",
    "two_sided_rupture",
    "vertical_handoff",
)
_PARTIAL_STATUSES = {
    "UNCOMPUTED",
    "FAILED",
    "EXECUTED_DOMAIN_INCOMPLETE",
    "EXECUTED_OPERATOR_LIMITED",
}


def _component_kind(manifest: EquipmentManifest) -> dict[str, str]:
    return {component.id: component.kind for component in manifest.components}


def _base_hole_family(kind: str | None, profile: str | None) -> str | None:
    if profile == "LH2_PIPE" or kind == "pipe":
        return "pipe_hole"
    if kind == "storage_tank":
        return "vessel_hole"
    if kind == "valve":
        return "valve_hole"
    if kind == "vent_stack":
        return "vent_hole"
    if kind == "pump":
        return "pump_hole"
    if kind == "vaporizer":
        return "vaporizer_hole"
    if kind == "reliquefier":
        return "reliquefier_hole"
    return "vessel_hole" if profile == "LH2_VESSEL" else None


def _request_families(request: ConsequenceRequest | None) -> set[str]:
    if request is None:
        return set()
    families: set[str] = set()
    if request.resolved_liquid_release is not None:
        families.add("liquid_two_phase")
    if request.resolved_release_set is not None or request.source_operator == "equipment_two_sided_rupture":
        families.add("two_sided_rupture")
    if request.resolved_release is not None and request.resolved_release.vertical_handoff is not None:
        families.add("vertical_handoff")
    if request.source_operator in {"inventory_liquid_jet", "equipment_inventory_depletion", "equipment_liquid_release"}:
        families.add("inventory_depletion")
    if request.source_operator == "inventory_over_600s":
        families.add("inventory_over_600s")
    return families


def _event_families(
    event: dict[str, Any],
    requests: Iterable[ConsequenceRequest],
    component_kinds: dict[str, str],
) -> set[str]:
    families: set[str] = set()
    base = _base_hole_family(
        component_kinds.get(event.get("model_component_id")), event.get("profile")
    )
    if event.get("release", {}).get("mode") == "hole" and base is not None:
        families.add(base)
    if event.get("release", {}).get("mode") == "two_sided_rupture":
        families.add("two_sided_rupture")
    if event.get("release", {}).get("mode") == "inventory_over_600s":
        families.add("inventory_over_600s")
    if event.get("release", {}).get("mode") == "instantaneous_inventory":
        families.add("inventory_depletion")
    for request in requests:
        families.update(_request_families(request))
    return families


def _status(case_rows: list[dict[str, Any]], request_count: int) -> str:
    if not case_rows:
        return "UNCOMPUTED" if request_count == 0 else "NO_CASE_EXECUTED"
    statuses = {str(row.get("status")) for row in case_rows}
    if statuses == {"EXECUTED"}:
        return "EXECUTED"
    if any(status.startswith("EXECUTED") for status in statuses):
        return "PARTIAL"
    if statuses == {"FAILED"}:
        return "FAILED"
    return "UNCOMPUTED"


def build_accident_scope_matrix(
    campaign: RiskCampaign,
    result: dict[str, Any],
    manifest: EquipmentManifest,
    *,
    required_families: tuple[str, ...] = MAJOR_ACCIDENT_FAMILIES,
) -> dict[str, Any]:
    """Return a fail-closed mechanism coverage matrix for one campaign result."""
    unknown = sorted(set(required_families) - set(MAJOR_ACCIDENT_FAMILIES))
    if unknown:
        raise ValueError(f"unknown accident families: {', '.join(unknown)}")
    audit = audit_manifest(manifest)
    component_kinds = _component_kind(manifest)
    events = {str(row["id"]): row for row in result.get("events", []) if isinstance(row, dict) and row.get("id")}
    routes = {route.event_id: route for route in campaign.event_routes}
    cases = [row for row in result.get("cases", []) if isinstance(row, dict)]
    cases_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        if case.get("event_id"):
            cases_by_event[str(case["event_id"])].append(case)

    event_families: dict[str, set[str]] = {}
    event_request_count: dict[str, int] = {}
    barrier_branches: set[str] = set()
    for event_id, event in events.items():
        route = routes.get(event_id)
        branches = tuple(route.branches) if route is not None else ()
        requests = tuple(branch.request for branch in branches if branch.request is not None)
        event_request_count[event_id] = len(requests)
        event_families[event_id] = _event_families(event, requests, component_kinds)
        barrier_branches.update(str(branch.id) for branch in branches)

    rows: list[dict[str, Any]] = []
    for family in required_families:
        event_ids = sorted(event_id for event_id, families in event_families.items() if family in families)
        family_cases = [case for event_id in event_ids for case in cases_by_event.get(event_id, ())]
        request_count = sum(event_request_count.get(event_id, 0) for event_id in event_ids)
        event_frequency = sum(float(events[event_id].get("annual_frequency_per_year", 0.0)) for event_id in event_ids)
        status = "NO_EVENT_GENERATED" if not event_ids else _status(family_cases, request_count)
        rows.append({
            "family": family,
            "status": status,
            "event_ids": event_ids,
            "generated_event_count": len(event_ids),
            "generated_initiation_frequency_per_year": event_frequency,
            "request_branch_count": request_count,
            "case_count": len(family_cases),
            "executed_case_count": sum(str(case.get("status", "")).startswith("EXECUTED") for case in family_cases),
            "fully_validated_case_count": sum(case.get("status") == "EXECUTED" for case in family_cases),
            "operator_limited_case_count": sum(case.get("status") == "EXECUTED_OPERATOR_LIMITED" for case in family_cases),
            "domain_incomplete_case_count": sum(case.get("status") == "EXECUTED_DOMAIN_INCOMPLETE" for case in family_cases),
            "failed_case_count": sum(case.get("status") == "FAILED" for case in family_cases),
            "uncomputed_case_count": sum(case.get("status") in _PARTIAL_STATUSES for case in family_cases),
            "uncomputed_reasons": sorted({str(case.get("reason")) for case in family_cases if case.get("status") != "EXECUTED" and case.get("reason")}),
            "frequency_rows_are_not_additive_across_families": True,
        })

    blocking: list[str] = []
    if audit["status"] != "EXECUTABLE":
        blocking.append("equipment manifest is not executable")
    for row in rows:
        if row["status"] != "EXECUTED":
            blocking.append(f"{row['family']}: {row['status']}")
    if result.get("total_facility_annual_ir_low_high") is None:
        blocking.append("campaign does not provide total facility annual IR")
    return {
        "schema_version": "prism.major_accident_scope.v1",
        "environment": manifest.environment,
        "scope": "outdoor_major_accidents",
        "required_families": list(required_families),
        "rows": rows,
        "barrier_branch_ids": sorted(barrier_branches),
        "manifest_audit_status": audit["status"],
        "campaign_status": result.get("status"),
        "declared_scope_numerically_complete": all(row["status"] == "EXECUTED" for row in rows),
        "facility_total_risk_available": result.get("total_facility_annual_ir_low_high") is not None,
        "matrix_complete": not blocking,
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "physical_validation_claim": False,
        "interpretation": "Mechanism and execution coverage accounting; rows with no generated event are explicit and frequency sums across rows must not be added.",
    }
