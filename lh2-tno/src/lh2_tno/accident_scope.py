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
from .accident_scenario_catalog import (
    audit_catalog_manifest,
    audit_worklist_scope_alignment,
    scenario_definition,
    scenario_families_for_request,
)


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
    return set(scenario_families_for_request(None, "hole", request))


def _event_families(
    event: dict[str, Any],
    requests: Iterable[ConsequenceRequest],
    component_kinds: dict[str, str],
) -> set[str]:
    families: set[str] = set()
    base = _base_hole_family(
        component_kinds.get(event.get("model_component_id")), event.get("profile")
    )
    if event.get("release", {}).get("mode") in {"hole", "maximum_relief_discharge"} and base is not None:
        families.add(base)
    if event.get("release", {}).get("mode") == "two_sided_rupture":
        families.add("two_sided_rupture")
    if event.get("release", {}).get("mode") == "inventory_over_600s":
        families.add("inventory_over_600s")
    if event.get("release", {}).get("mode") == "instantaneous_inventory":
        families.add("inventory_depletion")
    # The liquid/two-phase mechanism is a declared cross-cutting family.  It
    # must remain visible for every applicable event even when its provider
    # packet is still missing; otherwise the scope matrix drops uncomputed
    # events while the facility ledger retains them.
    if (
        event.get("release", {}).get("mode") in {"hole", "instantaneous_inventory", "inventory_over_600s"}
        and component_kinds.get(event.get("model_component_id")) in {
            "storage_tank", "pipe", "valve", "pump", "vaporizer", "reliquefier",
        }
    ):
        families.add("liquid_two_phase")
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


def _conditional_status(case_rows: list[dict[str, Any]], request_count: int) -> str:
    """Classify numerical execution while keeping provider qualification separate.

    ``EXECUTED_OPERATOR_LIMITED`` and ``EXECUTED_DOMAIN_INCOMPLETE`` have a
    numerical result, but they are not qualified facility evidence.  The
    strict status above therefore remains ``PARTIAL``; this second status says
    whether the consequence chain produced a number for every case.
    """
    if not case_rows:
        return "UNCOMPUTED" if request_count == 0 else "NO_CASE_EXECUTED"
    statuses = {str(row.get("status")) for row in case_rows}
    if all(status.startswith("EXECUTED") for status in statuses):
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
    provider_worklist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fail-closed mechanism coverage matrix for one campaign result."""
    unknown = sorted(set(required_families) - set(MAJOR_ACCIDENT_FAMILIES))
    if unknown:
        raise ValueError(f"unknown accident families: {', '.join(unknown)}")
    audit = audit_manifest(manifest)
    component_kinds = _component_kind(manifest)
    catalog_audit = audit_catalog_manifest(
        ({"id": component.id, "kind": component.kind} for component in manifest.components),
        required_families,
    )
    manifest_family_components: dict[str, list[str]] = defaultdict(list)
    for component in manifest.components:
        family = _base_hole_family(component.kind, None)
        if family is not None:
            manifest_family_components[family].append(component.id)
    # Cross-cutting families (liquid/two-phase, inventory and handoff) apply
    # to several equipment kinds, so the base-hole map above is not enough to
    # decide whether a family is relevant to this particular facility.
    manifest_scenario_components: dict[str, list[str]] = {}
    for family in required_families:
        applicable_kinds = set(scenario_definition(family)["equipment_kinds"])
        manifest_scenario_components[family] = sorted(
            component.id
            for component in manifest.components
            if component.kind in applicable_kinds
        )
    selected_frequency_components = sorted(
        asset.model_component_id for asset in campaign.frequency_plan.assets
    )
    excluded_frequency_components = sorted(campaign.frequency_plan.excluded_model_components)
    events = {str(row["id"]): row for row in result.get("events", []) if isinstance(row, dict) and row.get("id")}
    routes = {route.event_id: route for route in campaign.event_routes}
    cases = [row for row in result.get("cases", []) if isinstance(row, dict)]
    cases_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        if case.get("event_id"):
            cases_by_event[str(case["event_id"])].append(case)

    event_families: dict[str, set[str]] = {}
    event_request_count: dict[str, int] = {}
    event_uncomputed_branch_count: dict[str, int] = {}
    barrier_branches: set[str] = set()
    for event_id, event in events.items():
        route = routes.get(event_id)
        branches = tuple(route.branches) if route is not None else ()
        requests = tuple(branch.request for branch in branches if branch.request is not None)
        event_request_count[event_id] = len(requests)
        event_uncomputed_branch_count[event_id] = sum(
            branch.request is None for branch in branches
        )
        event_families[event_id] = _event_families(event, requests, component_kinds)
        barrier_branches.update(str(branch.id) for branch in branches)

    worklist_alignment = (
        audit_worklist_scope_alignment(
            provider_worklist,
            event_families,
            {
                event_id: (
                    tuple(event.get("port_ids"))
                    if isinstance(event.get("port_ids"), list)
                    else None
                )
                for event_id, event in events.items()
            },
        )
        if provider_worklist is not None
        else None
    )

    rows: list[dict[str, Any]] = []
    for family in required_families:
        event_ids = sorted(event_id for event_id, families in event_families.items() if family in families)
        family_cases = [case for event_id in event_ids for case in cases_by_event.get(event_id, ())]
        events_without_cases = [
            event_id for event_id in event_ids if not cases_by_event.get(event_id)
        ]
        request_count = sum(event_request_count.get(event_id, 0) for event_id in event_ids)
        uncomputed_branch_count = sum(
            event_uncomputed_branch_count.get(event_id, 0) for event_id in event_ids
        )
        event_frequency = sum(float(events[event_id].get("annual_frequency_per_year", 0.0)) for event_id in event_ids)
        declared_component_ids = list(manifest_scenario_components.get(family, ()))
        generated_component_ids = sorted({
            str(events[event_id].get("model_component_id"))
            for event_id in event_ids
            if events[event_id].get("model_component_id") is not None
        })
        if not event_ids and not declared_component_ids:
            status = "NOT_APPLICABLE"
        elif not event_ids:
            status = "NO_EVENT_GENERATED"
        elif events_without_cases:
            status = "NO_CASE_EXECUTED" if not family_cases else "PARTIAL"
        elif uncomputed_branch_count:
            status = "UNCOMPUTED" if not family_cases else "PARTIAL"
        else:
            status = _status(family_cases, request_count)
        conditional_status = _conditional_status(family_cases, request_count)
        conditional_executed_case_count = sum(
            str(case.get("status", "")).startswith("EXECUTED") for case in family_cases
        )
        rows.append({
            "family": family,
            "scenario_definition": scenario_definition(family),
            "status": status,
            "conditional_status": (
                "NOT_APPLICABLE" if status == "NOT_APPLICABLE" else conditional_status
            ),
            "event_ids": event_ids,
            "generated_event_count": len(event_ids),
            "applicability": "NOT_APPLICABLE" if not declared_component_ids else "APPLICABLE",
            "event_without_case_count": len(events_without_cases),
            "event_ids_without_cases": events_without_cases,
            "generated_initiation_frequency_per_year": event_frequency,
            "manifest_component_ids": declared_component_ids,
            "manifest_component_count": len(declared_component_ids),
            "generated_component_ids": generated_component_ids,
            "components_without_generated_event": sorted(
                set(declared_component_ids) - set(generated_component_ids)
            ),
            "request_branch_count": request_count,
            "uncomputed_branch_count": uncomputed_branch_count,
            "case_count": len(family_cases),
            "executed_case_count": sum(str(case.get("status", "")).startswith("EXECUTED") for case in family_cases),
            "conditional_executed_case_count": conditional_executed_case_count,
            "conditional_uncomputed_case_count": len(family_cases) - conditional_executed_case_count,
            "fully_validated_case_count": sum(case.get("status") == "EXECUTED" for case in family_cases),
            "operator_limited_case_count": sum(case.get("status") == "EXECUTED_OPERATOR_LIMITED" for case in family_cases),
            "domain_incomplete_case_count": sum(case.get("status") == "EXECUTED_DOMAIN_INCOMPLETE" for case in family_cases),
            "failed_case_count": sum(case.get("status") == "FAILED" for case in family_cases),
            "uncomputed_case_count": sum(case.get("status") in _PARTIAL_STATUSES for case in family_cases),
            "not_numerically_executed_case_count": sum(
                case.get("status") in {"UNCOMPUTED", "FAILED"} for case in family_cases
            ),
            "qualified_evidence_withheld_case_count": sum(
                case.get("status") in {"EXECUTED_OPERATOR_LIMITED", "EXECUTED_DOMAIN_INCOMPLETE"}
                for case in family_cases
            ),
            "numerically_executed_case_count": sum(
                str(case.get("status", "")).startswith("EXECUTED") for case in family_cases
            ),
            "uncomputed_reasons": sorted({str(case.get("reason")) for case in family_cases if case.get("status") != "EXECUTED" and case.get("reason")}),
            "frequency_rows_are_not_additive_across_families": True,
        })

    blocking: list[str] = []
    conditional_blocking: list[str] = []
    if audit["status"] != "EXECUTABLE":
        blocking.append("equipment manifest is not executable")
    for row in rows:
        if row["status"] not in {"EXECUTED", "NOT_APPLICABLE"}:
            blocking.append(f"{row['family']}: {row['status']}")
        if row["conditional_status"] not in {"EXECUTED", "NOT_APPLICABLE"}:
            conditional_blocking.append(f"{row['family']}: {row['conditional_status']}")
    if result.get("total_facility_annual_ir_low_high") is None:
        blocking.append("campaign does not provide total facility annual IR")
    if worklist_alignment is not None and worklist_alignment["status"] != "ALIGNED":
        blocking.extend(
            f"provider worklist alignment: {reason}"
            for reason in worklist_alignment["blocking_reasons"]
        )
    return {
        "schema_version": "prism.major_accident_scope.v1",
        "environment": manifest.environment,
        "scope": "outdoor_major_accidents",
        "required_families": list(required_families),
        "scenario_catalog": catalog_audit,
        "provider_worklist_alignment": worklist_alignment,
        "rows": rows,
        "barrier_branch_ids": sorted(barrier_branches),
        "manifest_family_component_ids": {
            family: sorted(ids) for family, ids in sorted(manifest_family_components.items())
        },
        "manifest_scenario_component_ids": {
            family: sorted(ids) for family, ids in sorted(manifest_scenario_components.items())
        },
        "frequency_scope_selected_component_ids": selected_frequency_components,
        "frequency_scope_excluded_component_ids": excluded_frequency_components,
        "manifest_audit_status": audit["status"],
        "campaign_status": result.get("status"),
        "declared_scope_numerically_complete": all(
            row["status"] in {"EXECUTED", "NOT_APPLICABLE"} for row in rows
        ),
        "conditional_chain_complete": not conditional_blocking,
        "conditional_chain_blocking_reasons": list(dict.fromkeys(conditional_blocking)),
        "facility_total_risk_available": result.get("total_facility_annual_ir_low_high") is not None,
        "matrix_complete": not blocking,
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "physical_validation_claim": False,
        "interpretation": "Mechanism and execution coverage accounting; rows with no generated event are explicit and frequency sums across rows must not be added.",
    }
