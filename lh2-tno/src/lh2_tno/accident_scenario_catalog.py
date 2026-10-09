"""Declared outdoor LH2 major-accident scenario catalogue.

The catalogue is the contract between the equipment manifest, initiating
frequency plan, provider release packet, and consequence chain.  It describes
what a complete calculation would require; it never creates a release packet
or treats a diagnostic adapter as qualified evidence.
"""
from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any, Iterable


ACCIDENT_SCENARIO_CATALOG_SCHEMA = "prism.accident_scenario_catalog.v1"


# The identifiers intentionally match ``MAJOR_ACCIDENT_FAMILIES`` in
# accident_scope.py.  Keep the fields JSON-friendly so the same definitions
# can be written into an audit record and into a paper methods table.
_SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "family": "vessel_hole",
        "name": "LH2 vessel wall hole",
        "equipment_kinds": ("storage_tank",),
        "release_modes": ("hole",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "model_pressure_equalization"),
        "required_source_operators": ("integrated_transient", "equipment_liquid_release"),
        "consequence_path": "resolved gas or liquid release -> SLABx-LH2/TNO dispersion -> ignition/IR/F-N",
        "uncomputed_default_reason": "provider-resolved vessel accident history is required",
    },
    {
        "family": "pipe_hole",
        "name": "LH2 transfer pipe hole",
        "equipment_kinds": ("pipe",),
        "release_modes": ("hole",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "model_pressure_equalization"),
        "required_source_operators": ("integrated_transient", "equipment_liquid_release"),
        "consequence_path": "pipe outlet state -> two-phase/gas release -> SLABx-LH2/TNO damage chain",
        "uncomputed_default_reason": "provider-resolved pipe accident history is required",
    },
    {
        "family": "valve_hole",
        "name": "LH2 valve body or stem hole",
        "equipment_kinds": ("valve",),
        "release_modes": ("hole",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "model_pressure_equalization"),
        "required_source_operators": ("integrated_transient", "equipment_liquid_release"),
        "consequence_path": "valve state and upstream inventory -> resolved release -> TNO consequence chain",
        "uncomputed_default_reason": "provider-resolved valve accident history is required",
    },
    {
        "family": "vent_hole",
        "name": "relief or vent discharge",
        "equipment_kinds": ("vent_stack",),
        "release_modes": ("maximum_relief_discharge", "hole"),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("emergency_relief_discharge", "explicit_provider_termination"),
        "required_source_operators": ("equipment_emergency_relief", "integrated_transient"),
        "consequence_path": "relief/vent outlet -> gas plume -> ignition/thermal radiation/overpressure",
        "uncomputed_default_reason": "qualified relief set-point and discharge history are required",
    },
    {
        "family": "pump_hole",
        "name": "LH2 pump casing or seal hole",
        "equipment_kinds": ("pump",),
        "release_modes": ("hole",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "model_pressure_equalization"),
        "required_source_operators": ("integrated_transient", "equipment_liquid_release"),
        "consequence_path": "pump state and seal/casing opening -> liquid/gas release -> TNO damage chain",
        "uncomputed_default_reason": "provider-resolved pump accident history is required",
    },
    {
        "family": "vaporizer_hole",
        "name": "vaporizer tube or shell hole",
        "equipment_kinds": ("vaporizer",),
        "release_modes": ("hole",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "model_pressure_equalization"),
        "required_source_operators": ("integrated_transient", "equipment_liquid_release"),
        "consequence_path": "vaporizer state -> phase-resolved release -> SLABx-LH2/TNO damage chain",
        "uncomputed_default_reason": "provider-resolved vaporizer accident history is required",
    },
    {
        "family": "reliquefier_hole",
        "name": "reliquefier weak-shell or line hole",
        "equipment_kinds": ("reliquefier",),
        "release_modes": ("hole",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "model_pressure_equalization"),
        "required_source_operators": ("integrated_transient", "equipment_liquid_release"),
        "consequence_path": "reliquefier state -> resolved gas/liquid release -> TNO damage chain",
        "uncomputed_default_reason": "provider-resolved reliquefier accident history is required",
    },
    {
        "family": "liquid_two_phase",
        "name": "liquid LH2 two-phase release",
        "equipment_kinds": ("storage_tank", "pipe", "valve", "pump", "vaporizer", "reliquefier"),
        "release_modes": ("hole", "instantaneous_inventory", "inventory_over_600s"),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "inventory_depletion", "inventory_over_600s"),
        "required_source_operators": ("equipment_liquid_release", "equipment_inventory_depletion", "equipment_inventory_over_600s", "equipment_liquid_over_600s"),
        "consequence_path": "liquid thermodynamic state -> flash/two-phase source -> SLABx-LH2 -> TNO damage chain",
        "uncomputed_default_reason": "liquid outlet packet with phase and enthalpy ledger is required",
    },
    {
        "family": "inventory_depletion",
        "name": "finite-inventory depletion",
        "equipment_kinds": ("storage_tank", "pipe", "valve", "pump", "vaporizer", "reliquefier"),
        "release_modes": ("instantaneous_inventory",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("inventory_depletion",),
        "required_source_operators": ("equipment_inventory_depletion", "equipment_liquid_release"),
        "consequence_path": "inventory ledger reaches zero -> finite release -> TNO consequence chain",
        "uncomputed_default_reason": "provider packet must close the mass inventory at depletion",
    },
    {
        "family": "inventory_over_600s",
        "name": "600-second bounded inventory release",
        "equipment_kinds": ("storage_tank", "pipe", "valve", "pump", "vaporizer", "reliquefier"),
        "release_modes": ("inventory_over_600s",),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("inventory_over_600s",),
        "required_source_operators": ("equipment_inventory_over_600s", "equipment_liquid_over_600s"),
        "consequence_path": "600 s provider history -> bounded release -> SLABx-LH2/TNO damage chain",
        "uncomputed_default_reason": "provider must supply exactly 600 s and a closed mass ledger",
    },
    {
        "family": "two_sided_rupture",
        "name": "pipe two-sided rupture",
        "equipment_kinds": ("pipe", "valve"),
        "release_modes": ("two_sided_rupture",),
        "provider_schemas": ("prism.resolved_release_set.v1",),
        "termination_bases": ("two_sided_rupture",),
        "required_source_operators": ("equipment_two_sided_rupture",),
        "consequence_path": "upstream and downstream endpoint releases -> union harm -> TNO IR/F-N",
        "uncomputed_default_reason": "two endpoint packets and shared inventory closure are required",
    },
    {
        "family": "vertical_handoff",
        "name": "vertical vent to horizontal dispersion handoff",
        "equipment_kinds": ("vent_stack", "pipe", "valve"),
        "release_modes": ("hole", "maximum_relief_discharge"),
        "provider_schemas": ("prism.resolved_release.v1",),
        "termination_bases": ("explicit_provider_termination", "emergency_relief_discharge"),
        "required_source_operators": ("integrated_transient", "equipment_emergency_relief"),
        "consequence_path": "vertical jet state -> horizontal SLABx handoff -> TNO damage chain",
        "uncomputed_default_reason": "validated vertical free-jet and handoff state are required",
    },
)


def accident_scenario_catalog(
    required_families: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return independent JSON-ready definitions for the requested families."""
    selected = tuple(required_families) if required_families is not None else tuple(
        row["family"] for row in _SCENARIOS
    )
    known = {row["family"] for row in _SCENARIOS}
    unknown = sorted(set(selected) - known)
    if unknown:
        raise ValueError(f"unknown accident scenario families: {', '.join(unknown)}")
    by_family = {row["family"]: row for row in _SCENARIOS}
    return tuple(deepcopy(by_family[family]) for family in selected)


def scenario_definition(family: str) -> dict[str, Any]:
    """Return one independent scenario definition."""
    rows = accident_scenario_catalog((family,))
    return rows[0]


def scenario_families_for_release(
    component_kind: str | None,
    release_mode: str,
) -> tuple[str, ...]:
    """Map one initiating release event to declared scenario families.

    The first family is the component/mechanism family. Additional families
    are cross-cutting physical cases that the provider packet must satisfy. A
    vertical handoff is excluded because it is known only after the provider
    supplies a validated handoff state.
    """
    base_by_kind = {
        "storage_tank": "vessel_hole",
        "pipe": "pipe_hole",
        "valve": "valve_hole",
        "vent_stack": "vent_hole",
        "pump": "pump_hole",
        "vaporizer": "vaporizer_hole",
        "reliquefier": "reliquefier_hole",
    }
    families: list[str] = []
    if release_mode == "maximum_relief_discharge":
        if component_kind == "vent_stack":
            families.append("vent_hole")
    elif release_mode == "two_sided_rupture":
        families.append("two_sided_rupture")
    elif release_mode == "instantaneous_inventory":
        families.append("inventory_depletion")
    elif release_mode == "inventory_over_600s":
        families.append("inventory_over_600s")
    elif release_mode == "hole" and component_kind in base_by_kind:
        families.append(base_by_kind[component_kind])
    if release_mode in {"hole", "instantaneous_inventory", "inventory_over_600s"} and component_kind in {
        "storage_tank", "pipe", "valve", "pump", "vaporizer", "reliquefier"
    }:
        families.append("liquid_two_phase")
    return tuple(dict.fromkeys(families))


def scenario_families_for_request(
    component_kind: str | None,
    release_mode: str,
    request: Any | None = None,
) -> tuple[str, ...]:
    """Map a release and its consumed provider request to scenario families.

    A release event alone cannot prove that a provider supplied a vertical
    handoff, an endpoint set, or an inventory-specific termination. Once a
    ``ConsequenceRequest`` is attached to a campaign branch, those properties
    are known and must be visible in serialized case and risk-atom metadata.
    ``request`` is duck-typed to keep this catalog independent from the
    consequence model and avoid an import cycle.
    """
    families = list(scenario_families_for_release(component_kind, release_mode))
    if request is None:
        return tuple(families)

    if getattr(request, "resolved_liquid_release", None) is not None:
        families.append("liquid_two_phase")
    if (
        getattr(request, "resolved_release_set", None) is not None
        or getattr(request, "source_operator", None) == "equipment_two_sided_rupture"
    ):
        families.append("two_sided_rupture")

    release = getattr(request, "resolved_release", None)
    if release is not None:
        if getattr(release, "vertical_handoff", None) is not None:
            families.append("vertical_handoff")
        if getattr(release, "event_kind", None) == "emergency_relief":
            families.append("vent_hole")

    source_operator = getattr(request, "source_operator", None)
    if source_operator in {
        "inventory_liquid_jet",
        "equipment_inventory_depletion",
        "equipment_liquid_release",
    }:
        families.append("inventory_depletion")
    if source_operator in {
        "inventory_over_600s",
        "equipment_inventory_over_600s",
        "equipment_liquid_over_600s",
    }:
        families.append("inventory_over_600s")
    return tuple(dict.fromkeys(families))


def audit_catalog_manifest(
    component_rows: Iterable[dict[str, Any]],
    required_families: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Map manifest component kinds to the declared accident scenarios.

    ``component_rows`` only needs ``id`` and ``kind`` keys.  The function is
    deliberately separate from the equipment manifest model so it can be used
    by audit scripts without creating or modifying a facility model.
    """
    definitions = accident_scenario_catalog(required_families)
    components = tuple(component_rows)
    rows = []
    for definition in definitions:
        kinds = set(definition["equipment_kinds"])
        applicable = sorted(
            str(component["id"])
            for component in components
            if component.get("kind") in kinds and component.get("id")
        )
        rows.append({
            "family": definition["family"],
            "equipment_kinds": list(definition["equipment_kinds"]),
            "applicable_component_ids": applicable,
            "applicable_component_count": len(applicable),
            "scenario_declared": True,
        })
    return {
        "schema": ACCIDENT_SCENARIO_CATALOG_SCHEMA,
        "scenario_count": len(rows),
        "rows": rows,
        "all_requested_families_declared": True,
    }


def audit_worklist_scope_alignment(
    provider_worklist: Mapping[str, Any],
    event_families: Mapping[str, set[str]],
) -> dict[str, Any]:
    """Check that worklist event IDs and primary families reach a scope matrix.

    The worklist is the requested provider boundary and ``event_families`` is
    the family observed by a campaign result.  Cross-cutting families such as
    ``liquid_two_phase`` may be absent before a provider packet is consumed, so
    only the first (mechanism) family is required for structural alignment.
    """
    items = provider_worklist.get("work_items")
    if not isinstance(items, list):
        raise ValueError("provider worklist work_items must be an array")
    known = {row["family"] for row in _SCENARIOS}
    seen: set[str] = set()
    missing_event_ids: list[str] = []
    duplicate_event_ids: list[str] = []
    empty_family_item_ids: list[str] = []
    unknown_family_item_ids: list[str] = []
    primary_family_mismatches: list[dict[str, Any]] = []
    aligned_event_ids: list[str] = []
    family_counts: dict[str, int] = {}
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(f"provider worklist work_items[{index}] must be an object")
        event_id = str(item.get("event_id", ""))
        item_id = str(item.get("id", event_id or f"work-item-{index}"))
        if not event_id:
            missing_event_ids.append(item_id)
            continue
        if event_id in seen:
            duplicate_event_ids.append(event_id)
        seen.add(event_id)
        raw_families = item.get("scenario_families")
        families = tuple(str(value) for value in raw_families) if isinstance(raw_families, list) else ()
        if not families:
            empty_family_item_ids.append(item_id)
            continue
        unknown = sorted(set(families) - known)
        if unknown:
            unknown_family_item_ids.append(item_id)
            continue
        primary = families[0]
        family_counts[primary] = family_counts.get(primary, 0) + 1
        observed = event_families.get(event_id)
        if observed is None:
            missing_event_ids.append(event_id)
        elif primary not in observed:
            primary_family_mismatches.append({
                "event_id": event_id,
                "worklist_primary_family": primary,
                "observed_families": sorted(observed),
            })
        else:
            aligned_event_ids.append(event_id)
    worklist_event_ids = set(seen)
    campaign_event_ids = set(event_families)
    extra_campaign_event_ids = sorted(campaign_event_ids - worklist_event_ids)
    blocking: list[str] = []
    if missing_event_ids:
        blocking.append("worklist event is missing from the campaign scope")
    if duplicate_event_ids:
        blocking.append("provider worklist contains duplicate event IDs")
    if empty_family_item_ids:
        blocking.append("provider worklist event has no scenario family")
    if unknown_family_item_ids:
        blocking.append("provider worklist event has an unknown scenario family")
    if primary_family_mismatches:
        blocking.append("worklist primary accident family disagrees with campaign scope")
    if extra_campaign_event_ids:
        blocking.append("campaign scope contains an event absent from the provider worklist")
    return {
        "schema": "prism.accident_scenario_worklist_alignment.v1",
        "status": "ALIGNED" if not blocking else "PARTIAL_ALIGNMENT",
        "worklist_event_count": len(items),
        "campaign_event_count": len(campaign_event_ids),
        "aligned_event_count": len(aligned_event_ids),
        "missing_event_ids": sorted(set(missing_event_ids)),
        "duplicate_event_ids": sorted(set(duplicate_event_ids)),
        "empty_family_item_ids": sorted(set(empty_family_item_ids)),
        "unknown_family_item_ids": sorted(set(unknown_family_item_ids)),
        "primary_family_mismatches": primary_family_mismatches,
        "extra_campaign_event_ids": extra_campaign_event_ids,
        "primary_family_counts": dict(sorted(family_counts.items())),
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "frequency_inference_performed": False,
        "provider_packet_created": False,
    }
