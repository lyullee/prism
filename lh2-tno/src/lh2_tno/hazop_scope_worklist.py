"""Join a HAZOP dispatch result to the exact provider-release worklist.

The multi-equipment HAZOP diagnostic intentionally exercises only a small
representative set of rows.  The provider worklist, on the other hand, is
generated from the complete initiating-frequency plan.  This module joins
those two views without turning a diagnostic row into a qualified provider
packet and without silently replacing an undispatched accident family.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .accident_scenario_catalog import accident_scenario_catalog
from .accident_scope import MAJOR_ACCIDENT_FAMILIES
from .equipment_manifest import EquipmentManifest


SCOPE_WORKLIST_SCHEMA = "prism.hazop_scope_worklist.v1"
_SCOPE_STATUSES = {"DISPATCHED_DIAGNOSTIC", "APPLICABLE_NOT_DISPATCHED", "NOT_APPLICABLE"}
_PROVIDER_STATUSES = {
    "UNCOMPUTED_PROVIDER_PACKET",
    "UNCOMPUTED_NO_ACCIDENT_PORT",
}


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _validate_scope_catalog(
    scope_catalog: Mapping[str, Any],
    applicable_by_family: Mapping[str, tuple[str, ...]],
) -> dict[str, dict[str, Any]]:
    raw_rows = scope_catalog.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("scope catalog rows must be an array")
    rows: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_rows):
        row = _require_mapping(raw, f"scope catalog rows[{index}]")
        family = str(row.get("family", ""))
        if family not in applicable_by_family:
            raise ValueError(f"scope catalog contains unknown family: {family}")
        if family in rows:
            raise ValueError(f"scope catalog contains duplicate family: {family}")
        status = str(row.get("status", ""))
        if status not in _SCOPE_STATUSES:
            raise ValueError(f"scope catalog family {family} has unsupported status: {status}")
        observed = row.get("observed_component_ids", [])
        if not isinstance(observed, list) or any(not str(item) for item in observed):
            raise ValueError(f"scope catalog family {family} observed_component_ids must be a string array")
        observed_ids = tuple(dict.fromkeys(str(item) for item in observed))
        applicable = set(applicable_by_family[family])
        invalid_observed = sorted(set(observed_ids) - applicable)
        if invalid_observed:
            raise ValueError(
                f"scope catalog family {family} observes non-applicable component(s): "
                + ", ".join(invalid_observed)
            )
        if status == "NOT_APPLICABLE" and applicable:
            raise ValueError(f"scope catalog marks applicable family {family} as NOT_APPLICABLE")
        if status == "DISPATCHED_DIAGNOSTIC" and not observed_ids:
            raise ValueError(f"scope catalog marks {family} dispatched without an observed component")
        rows[family] = {
            **dict(row),
            "family": family,
            "status": status,
            "observed_component_ids": list(observed_ids),
        }
    missing = sorted(set(applicable_by_family) - set(rows))
    if missing:
        raise ValueError("scope catalog is missing family row(s): " + ", ".join(missing))
    return rows


def _validate_provider_items(
    provider_worklist: Mapping[str, Any],
    manifest_component_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw_items = provider_worklist.get("work_items")
    if not isinstance(raw_items, list):
        raise ValueError("provider worklist work_items must be an array")
    items: list[dict[str, Any]] = []
    by_event: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_items):
        item = _require_mapping(raw, f"provider worklist work_items[{index}]")
        event_id = str(item.get("event_id", ""))
        component_id = str(item.get("component_id", ""))
        if not event_id:
            raise ValueError(f"provider worklist work_items[{index}] has no event_id")
        if event_id in by_event:
            raise ValueError(f"provider worklist contains duplicate event_id: {event_id}")
        if component_id not in manifest_component_ids:
            raise ValueError(
                f"provider worklist event {event_id} references unknown component: {component_id}"
            )
        families = item.get("scenario_families")
        if not isinstance(families, list) or not families:
            raise ValueError(f"provider worklist event {event_id} has no scenario_families")
        unknown = sorted(set(str(value) for value in families) - set(MAJOR_ACCIDENT_FAMILIES))
        if unknown:
            raise ValueError(
                f"provider worklist event {event_id} contains unknown family(ies): "
                + ", ".join(unknown)
            )
        status = str(item.get("status", ""))
        if status not in _PROVIDER_STATUSES:
            # A future packet status is retained for auditing, but the row is
            # never interpreted as computed unless the caller supplies the
            # exact provider status explicitly.
            if not status:
                raise ValueError(f"provider worklist event {event_id} has no status")
        normalized = {
            **dict(item),
            "event_id": event_id,
            "component_id": component_id,
            "scenario_families": list(dict.fromkeys(str(value) for value in families)),
            "status": status,
        }
        items.append(normalized)
        by_event[event_id] = normalized
    return items, by_event


def _runtime_traces(runtime: Mapping[str, Any] | None) -> dict[tuple[str, str], list[str]]:
    if runtime is None:
        return {}
    raw = runtime.get("component_traces", [])
    if not isinstance(raw, list):
        raise ValueError("runtime component_traces must be an array")
    traces: dict[tuple[str, str], list[str]] = defaultdict(list)
    for index, item in enumerate(raw):
        row = _require_mapping(item, f"runtime component_traces[{index}]")
        component_id = str(row.get("component_id", ""))
        family = str(row.get("scenario_family", ""))
        scenario_id = str(row.get("scenario_id", ""))
        if not component_id or not family or not scenario_id:
            raise ValueError(
                f"runtime component_traces[{index}] must contain component_id, scenario_family, and scenario_id"
            )
        if family not in MAJOR_ACCIDENT_FAMILIES:
            raise ValueError(f"runtime trace contains unknown scenario family: {family}")
        key = (component_id, family)
        if scenario_id not in traces[key]:
            traces[key].append(scenario_id)
    return dict(traces)


def build_hazop_scope_worklist(
    manifest: EquipmentManifest,
    scope_catalog: Mapping[str, Any],
    provider_worklist: Mapping[str, Any],
    *,
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an explicit family/component and frequency-event worklist.

    ``DISPATCHED_DIAGNOSTIC`` means that a HAZOP row reached the diagnostic
    runtime.  It does *not* mean the provider packet is qualified or that a
    frequency event was consumed.  Provider event rows therefore retain the
    original ``UNCOMPUTED_*`` status from ``provider_worklist``.
    """
    if not isinstance(manifest, EquipmentManifest):
        raise ValueError("manifest must be an EquipmentManifest")
    component_rows = tuple(manifest.components)
    component_ids = {str(component.id) for component in component_rows}
    definitions = {
        row["family"]: row for row in accident_scenario_catalog(MAJOR_ACCIDENT_FAMILIES)
    }
    applicable_by_family = {
        family: tuple(
            sorted(
                str(component.id)
                for component in component_rows
                if component.kind in set(definitions[family]["equipment_kinds"])
            )
        )
        for family in MAJOR_ACCIDENT_FAMILIES
    }
    scope_rows = _validate_scope_catalog(_require_mapping(scope_catalog, "scope_catalog"), applicable_by_family)
    provider_items, _ = _validate_provider_items(
        _require_mapping(provider_worklist, "provider_worklist"), component_ids
    )
    trace_by_key = _runtime_traces(runtime)

    event_ids_by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    event_rows: list[dict[str, Any]] = []
    for item in provider_items:
        links = []
        status_by_family: dict[str, str] = {}
        for family in item["scenario_families"]:
            key = (item["component_id"], family)
            event_ids_by_key[key].append(item["event_id"])
            scope_status = scope_rows[family]["status"]
            status_by_family[family] = scope_status
            links.append({
                "family": family,
                "scope_status": scope_status,
                "diagnostic_scenario_ids": list(trace_by_key.get(key, ())),
            })
        event_rows.append({
            "event_id": item["event_id"],
            "provider_work_item_id": item.get("id"),
            "component_id": item["component_id"],
            "profile": item.get("profile"),
            "loc": item.get("loc"),
            "release_mode": item.get("release_mode"),
            "annual_frequency_per_year": item.get("annual_frequency_per_year"),
            "scenario_families": list(item["scenario_families"]),
            "provider_status": item["status"],
            "provider_packet_required": True,
            "scope_status_by_family": status_by_family,
            "scope_links": links,
            "frequency_preserved": True,
            "frequency_inference_performed": False,
            "packet_substitution_performed": False,
            "blocking_reasons": list(item.get("blocking_reasons", [])),
        })

    family_rows: list[dict[str, Any]] = []
    for family in MAJOR_ACCIDENT_FAMILIES:
        definition = definitions[family]
        scope = scope_rows[family]
        for component_id in applicable_by_family[family]:
            key = (component_id, family)
            provider_ids = sorted(dict.fromkeys(event_ids_by_key.get(key, ())))
            diagnostic_ids = list(trace_by_key.get(key, ()))
            if not applicable_by_family[family]:
                status = "NOT_APPLICABLE"
            elif component_id in set(scope["observed_component_ids"]):
                status = "DISPATCHED_DIAGNOSTIC"
            else:
                status = "APPLICABLE_NOT_DISPATCHED"
            blocking: list[str] = []
            if status == "APPLICABLE_NOT_DISPATCHED":
                blocking.append(str(scope.get("uncomputed_default_reason") or definition["uncomputed_default_reason"]))
            if not provider_ids:
                blocking.append("no exact initiating-frequency event is bound to this family/component pair")
                status = "NO_FREQUENCY_EVENT_BINDING"
            family_rows.append({
                "family": family,
                "component_id": component_id,
                "equipment_kind": next(
                    component.kind for component in component_rows if str(component.id) == component_id
                ),
                "scope_status": status,
                "scope_catalog_status": scope["status"],
                "diagnostic_scenario_ids": diagnostic_ids,
                "provider_event_ids": provider_ids,
                "provider_event_count": len(provider_ids),
                "provider_uncomputed_event_count": sum(
                    row["provider_status"] in _PROVIDER_STATUSES
                    for row in event_rows
                    if row["event_id"] in provider_ids
                ),
                "required_release_modes": list(definition["release_modes"]),
                "required_provider_schemas": list(definition["provider_schemas"]),
                "required_termination_bases": list(definition["termination_bases"]),
                "required_source_operators": list(definition["required_source_operators"]),
                "uncomputed_default_reason": scope.get("uncomputed_default_reason") or definition["uncomputed_default_reason"],
                "blocking_reasons": list(dict.fromkeys(blocking)),
                "frequency_inference_performed": False,
                "packet_substitution_performed": False,
            })

    # A NOT_APPLICABLE family has no rows by construction.  Keep a family
    # summary anyway so an absent equipment kind cannot disappear from the
    # report.
    family_summary = []
    for family in MAJOR_ACCIDENT_FAMILIES:
        rows = [row for row in family_rows if row["family"] == family]
        scope = scope_rows[family]
        family_summary.append({
            "family": family,
            "scope_catalog_status": scope["status"],
            "applicable_component_count": len(applicable_by_family[family]),
            "family_component_row_count": len(rows),
            "dispatched_diagnostic_component_count": sum(row["scope_status"] == "DISPATCHED_DIAGNOSTIC" for row in rows),
            "applicable_not_dispatched_component_count": sum(row["scope_status"] == "APPLICABLE_NOT_DISPATCHED" for row in rows),
            "no_frequency_binding_component_count": sum(row["scope_status"] == "NO_FREQUENCY_EVENT_BINDING" for row in rows),
            "provider_event_count": sum(row["provider_event_count"] for row in rows),
        })

    provider_uncomputed = sum(row["provider_status"] in _PROVIDER_STATUSES for row in event_rows)
    no_binding = sum(row["scope_status"] == "NO_FREQUENCY_EVENT_BINDING" for row in family_rows)
    undispatched = sum(row["scope_status"] == "APPLICABLE_NOT_DISPATCHED" for row in family_rows)
    dispatched = sum(row["scope_status"] == "DISPATCHED_DIAGNOSTIC" for row in family_rows)
    blocking = []
    if undispatched:
        blocking.append(f"{undispatched} applicable family/component pair(s) were not dispatched by HAZOP")
    if no_binding:
        blocking.append(f"{no_binding} applicable family/component pair(s) have no exact frequency-event binding")
    if provider_uncomputed:
        blocking.append(f"{provider_uncomputed} exact frequency event(s) still require provider release packets")
    return {
        "schema": SCOPE_WORKLIST_SCHEMA,
        "status": "SCOPE_GAPS_EXPLICIT" if blocking else "PROVIDER_SCOPE_COMPLETE",
        "manifest_environment": manifest.environment,
        "manifest_component_count": len(component_rows),
        "required_family_count": len(MAJOR_ACCIDENT_FAMILIES),
        "family_summary": family_summary,
        "family_component_rows": family_rows,
        "provider_event_rows": event_rows,
        "summary": {
            "family_component_row_count": len(family_rows),
            "dispatched_diagnostic_component_count": dispatched,
            "applicable_not_dispatched_component_count": undispatched,
            "no_frequency_binding_component_count": no_binding,
            "provider_event_count": len(event_rows),
            "provider_uncomputed_event_count": provider_uncomputed,
            "frequency_inference_performed": False,
            "packet_substitution_performed": False,
        },
        "blocking_reasons": blocking,
        "policy": {
            "diagnostic_dispatch_does_not_promote_provider_packet": True,
            "missing_family_is_not_substituted": True,
            "frequency_inference_performed": False,
            "provider_packet_created": False,
            "frequency_preserved_per_event": True,
        },
    }

