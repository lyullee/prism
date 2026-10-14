"""Audit explicit HAZOP operating-mode bindings for facility events.

An accident frequency event does not identify its operating mode by itself.
This module therefore treats a missing mode or scenario identity as an open
binding request.  It never guesses a mode from equipment kind, release size,
profile, or frequency bin.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from typing import Any


SCHEMA = "prism.hazop_event_mode_binding_audit.v1"
_BOUND_STATUSES = {"MODE_PRESENT", "MODE_BOUND"}


def _rows(value: Any, key: str) -> list[Mapping[str, Any]]:
    rows = value.get(key, ()) if isinstance(value, Mapping) else ()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _campaign_payload(campaign_result: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = campaign_result.get("campaign")
    return nested if isinstance(nested, Mapping) else campaign_result


def _normalise_bindings(value: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        raw_rows = value.get("bindings", value)
        if isinstance(raw_rows, Mapping):
            rows = []
            for event_id, row in raw_rows.items():
                if not isinstance(row, Mapping):
                    raise ValueError(f"mode binding {event_id} must be an object")
                rows.append({**dict(row), "event_id": row.get("event_id", event_id)})
        elif isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)):
            rows = list(raw_rows)
        else:
            raise ValueError("mode bindings must be an event mapping or an array")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        rows = list(value)
    else:
        raise ValueError("mode bindings must be an object or an array")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ValueError(f"mode bindings[{index}] must be an object")
        event_id = raw.get("event_id")
        operating_mode = raw.get("operating_mode")
        scenario_id = raw.get("hazop_scenario_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"mode bindings[{index}] has no event_id")
        if not isinstance(operating_mode, str) or not operating_mode.strip():
            raise ValueError(f"mode binding {event_id} has no operating_mode")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError(f"mode binding {event_id} has no hazop_scenario_id")
        key = event_id.strip()
        if key in result:
            raise ValueError(f"duplicate mode binding for event {key}")
        result[key] = {
            **dict(raw),
            "event_id": key,
            "operating_mode": operating_mode.strip(),
            "hazop_scenario_id": scenario_id.strip(),
        }
    return result


def apply_hazop_event_mode_bindings(
    campaign: Mapping[str, Any],
    mode_bindings: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    require_all: bool = True,
) -> dict[str, Any]:
    """Attach an explicit HAZOP mode/scenario pair to campaign routes.

    This is a metadata handoff only.  The caller must provide an exact
    event-level binding; the helper never derives a mode from equipment or
    release values.  Requests already carrying a mode/scenario pair must
    agree with the supplied binding.
    """
    if not isinstance(campaign, Mapping):
        raise TypeError("campaign must be an object")
    bindings = _normalise_bindings(mode_bindings)
    output = copy.deepcopy(dict(campaign))
    routes = output.get("event_routes")
    if not isinstance(routes, list):
        raise ValueError("campaign event_routes must be an array")
    route_ids = {
        route.get("event_id")
        for route in routes
        if isinstance(route, Mapping) and isinstance(route.get("event_id"), str)
    }
    unknown = sorted(set(bindings) - route_ids)
    if unknown:
        raise ValueError("mode binding references unknown campaign event(s): " + ", ".join(unknown))
    missing = sorted(route_ids - set(bindings))
    if require_all and missing:
        raise ValueError("mode binding is missing campaign event(s): " + ", ".join(missing))
    for route in routes:
        if not isinstance(route, dict):
            raise ValueError("campaign event route must be an object")
        event_id = route.get("event_id")
        binding = bindings.get(event_id)
        if binding is None:
            continue
        component_id = binding.get("component_id")
        if component_id is not None:
            branches = route.get("branches", [])
            request_components = {
                branch.get("request", {}).get("component_id")
                for branch in branches
                if isinstance(branch, Mapping) and isinstance(branch.get("request"), Mapping)
            }
            if request_components and request_components != {component_id}:
                raise ValueError(f"mode binding component_id disagrees with route {event_id}")
        for key in ("operating_mode", "hazop_scenario_id"):
            existing = route.get(key)
            if existing is not None and existing != binding[key]:
                raise ValueError(f"route {event_id} has conflicting {key}")
            route[key] = binding[key]
        for branch in route.get("branches", []):
            if not isinstance(branch, dict) or not isinstance(branch.get("request"), dict):
                continue
            request = branch["request"]
            for key in ("operating_mode", "hazop_scenario_id"):
                existing = request.get(key)
                if existing is not None and existing != binding[key]:
                    raise ValueError(f"request {event_id} has conflicting {key}")
                request[key] = binding[key]
    return output


def mode_bindings_from_diagnostic(diagnostic_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract only explicitly echoed event/mode/scenario triples.

    The multi-equipment HAZOP handoff stores these triples in
    ``facility_ledger.component_coverage``.  The extractor refuses a row when
    the three lists are not one-to-one; it never pairs a mode with an event by
    equipment kind or list position unless the diagnostic ledger has already
    declared a single exact row.
    """
    if not isinstance(diagnostic_result, Mapping):
        raise TypeError("diagnostic_result must be a mapping")
    handoff = diagnostic_result.get("facility_handoff")
    handoff = handoff if isinstance(handoff, Mapping) else {}
    ledger = handoff.get("facility_ledger")
    ledger = ledger if isinstance(ledger, Mapping) else {}
    coverage = ledger.get("component_coverage")
    if not isinstance(coverage, Mapping):
        raise ValueError("diagnostic result has no facility_ledger.component_coverage")
    bindings: list[dict[str, Any]] = []
    for component_id, raw in coverage.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"diagnostic component coverage {component_id} must be an object")
        event_ids = raw.get("event_ids")
        scenario_ids = raw.get("hazop_scenario_ids")
        modes = raw.get("operating_modes")
        if not all(isinstance(value, list) for value in (event_ids, scenario_ids, modes)):
            raise ValueError(f"diagnostic component coverage {component_id} lacks explicit event/mode/scenario arrays")
        if not (len(event_ids) == len(scenario_ids) == len(modes)):
            raise ValueError(
                f"diagnostic component coverage {component_id} cannot be paired: "
                "event_ids, hazop_scenario_ids, and operating_modes have different lengths"
            )
        if len(event_ids) != 1:
            raise ValueError(
                f"diagnostic component coverage {component_id} contains multiple rows without exact event-level pairing"
            )
        event_id, scenario_id, mode = event_ids[0], scenario_ids[0], modes[0]
        if not all(isinstance(value, str) and value.strip() for value in (event_id, scenario_id, mode)):
            raise ValueError(f"diagnostic component coverage {component_id} has an empty event/mode/scenario value")
        bindings.append({
            "event_id": event_id.strip(),
            "component_id": str(component_id),
            "operating_mode": mode.strip(),
            "hazop_scenario_id": scenario_id.strip(),
            "source_provenance": "explicit multi-equipment HAZOP facility ledger component_coverage",
        })
    return bindings


def _provider_event_ids(provider_worklist: Mapping[str, Any] | None) -> set[str]:
    if provider_worklist is None:
        return set()
    raw = provider_worklist.get("work_items")
    if not isinstance(raw, list):
        raise ValueError("provider worklist work_items must be an array")
    ids: set[str] = set()
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping) or not isinstance(row.get("event_id"), str) or not row["event_id"].strip():
            raise ValueError(f"provider worklist work_items[{index}] has no event_id")
        event_id = row["event_id"].strip()
        if event_id in ids:
            raise ValueError(f"provider worklist contains duplicate event_id: {event_id}")
        ids.add(event_id)
    return ids


def audit_hazop_event_mode_binding(
    campaign_result: Mapping[str, Any],
    *,
    provider_worklist: Mapping[str, Any] | None = None,
    mode_bindings: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return an explicit mode/scenario binding audit for every event.

    Existing fields are accepted only when they agree across event, case, and
    risk-atom rows.  A supplied binding is validated against the event's
    component and release mode; it is reported as a binding request and does
    not mutate or re-run the campaign.
    """
    if not isinstance(campaign_result, Mapping):
        raise TypeError("campaign_result must be a mapping")
    campaign = _campaign_payload(campaign_result)
    events = _rows(campaign, "events")
    cases = _rows(campaign, "cases")
    atoms = _rows(campaign, "risk_atoms")
    bindings = _normalise_bindings(mode_bindings)
    provider_ids = _provider_event_ids(provider_worklist)
    event_rows: list[dict[str, Any]] = []
    event_by_id: dict[str, Mapping[str, Any]] = {}
    errors: list[str] = []
    seen_event_ids: set[str] = set()
    cases_by_event: dict[str, list[Mapping[str, Any]]] = {}
    atoms_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in cases:
        event_id = row.get("event_id")
        if isinstance(event_id, str):
            cases_by_event.setdefault(event_id, []).append(row)
    for row in atoms:
        event_id = row.get("event_id")
        if isinstance(event_id, str):
            atoms_by_event.setdefault(event_id, []).append(row)

    for index, event in enumerate(events):
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            errors.append(f"events[{index}] has no event id")
            continue
        event_id = event_id.strip()
        if event_id in seen_event_ids:
            errors.append(f"duplicate campaign event id: {event_id}")
            continue
        seen_event_ids.add(event_id)
        event_by_id[event_id] = event
        supplied = bindings.get(event_id)
        event_mode = event.get("operating_mode")
        event_scenario = event.get("hazop_scenario_id")
        binding_errors: list[str] = []
        if supplied is not None:
            if supplied.get("component_id") is not None and supplied.get("component_id") != event.get("model_component_id"):
                binding_errors.append("mode binding component_id does not match event")
            release_mode = (event.get("release") or {}).get("mode") if isinstance(event.get("release"), Mapping) else None
            if supplied.get("release_mode") is not None and supplied.get("release_mode") != release_mode:
                binding_errors.append("mode binding release_mode does not match event")
            mode = supplied["operating_mode"]
            scenario_id = supplied["hazop_scenario_id"]
            source = "explicit_mode_binding"
        elif isinstance(event_mode, str) and event_mode.strip() and isinstance(event_scenario, str) and event_scenario.strip():
            mode = event_mode.strip()
            scenario_id = event_scenario.strip()
            source = "campaign_event_fields"
        elif isinstance(event_mode, str) and event_mode.strip():
            mode = event_mode.strip()
            scenario_id = None
            source = "campaign_event_mode_only"
            binding_errors.append("event has operating_mode but no hazop_scenario_id")
        else:
            mode = None
            scenario_id = None
            source = "missing_explicit_binding"

        related_cases = cases_by_event.get(event_id, [])
        related_atoms = atoms_by_event.get(event_id, [])
        case_modes = sorted({str(row.get("operating_mode")) for row in related_cases if isinstance(row.get("operating_mode"), str) and row.get("operating_mode").strip()})
        case_scenarios = sorted({str(row.get("hazop_scenario_id")) for row in related_cases if isinstance(row.get("hazop_scenario_id"), str) and row.get("hazop_scenario_id").strip()})
        atom_modes = sorted({str(row.get("operating_mode")) for row in related_atoms if isinstance(row.get("operating_mode"), str) and row.get("operating_mode").strip()})
        atom_scenarios = sorted({str(row.get("hazop_scenario_id")) for row in related_atoms if isinstance(row.get("hazop_scenario_id"), str) and row.get("hazop_scenario_id").strip()})
        if mode is not None:
            if case_modes and case_modes != [mode]:
                binding_errors.append("case operating_mode does not match event binding")
            if atom_modes and atom_modes != [mode]:
                binding_errors.append("risk atom operating_mode does not match event binding")
            if case_scenarios and scenario_id is not None and case_scenarios != [scenario_id]:
                binding_errors.append("case hazop_scenario_id does not match event binding")
            if atom_scenarios and scenario_id is not None and atom_scenarios != [scenario_id]:
                binding_errors.append("risk atom hazop_scenario_id does not match event binding")
        missing_case_mode_count = sum(not isinstance(row.get("operating_mode"), str) or not row.get("operating_mode").strip() for row in related_cases)
        missing_case_scenario_count = sum(not isinstance(row.get("hazop_scenario_id"), str) or not row.get("hazop_scenario_id").strip() for row in related_cases)
        missing_atom_mode_count = sum(not isinstance(row.get("operating_mode"), str) or not row.get("operating_mode").strip() for row in related_atoms)
        missing_atom_scenario_count = sum(not isinstance(row.get("hazop_scenario_id"), str) or not row.get("hazop_scenario_id").strip() for row in related_atoms)
        if binding_errors:
            status = "MODE_BINDING_CONFLICT"
            errors.extend(f"event {event_id}: {reason}" for reason in binding_errors)
        elif mode is None:
            status = "MODE_REQUIRED"
        elif scenario_id is None:
            status = "SCENARIO_ID_REQUIRED"
        else:
            status = "MODE_BOUND" if supplied is not None else "MODE_PRESENT"
        event_rows.append({
            "event_id": event_id,
            "component_id": event.get("model_component_id"),
            "profile": event.get("profile"),
            "release_mode": ((event.get("release") or {}).get("mode") if isinstance(event.get("release"), Mapping) else None),
            "annual_frequency_per_year": event.get("annual_frequency_per_year"),
            "status": status,
            "operating_mode": mode,
            "hazop_scenario_id": scenario_id,
            "binding_source": source,
            "binding_errors": binding_errors,
            "case_count": len(related_cases),
            "risk_atom_count": len(related_atoms),
            "case_modes": case_modes,
            "case_scenario_ids": case_scenarios,
            "risk_atom_modes": atom_modes,
            "risk_atom_scenario_ids": atom_scenarios,
            "missing_case_mode_count": missing_case_mode_count,
            "missing_case_scenario_count": missing_case_scenario_count,
            "missing_risk_atom_mode_count": missing_atom_mode_count,
            "missing_risk_atom_scenario_count": missing_atom_scenario_count,
            "provider_event_declared": event_id in provider_ids if provider_ids else None,
            "mode_inference_performed": False,
            "scenario_inference_performed": False,
        })

    campaign_event_ids = set(event_by_id)
    orphan_bindings = sorted(set(bindings) - campaign_event_ids)
    if orphan_bindings:
        errors.extend(f"mode binding references unknown campaign event: {event_id}" for event_id in orphan_bindings)
    if provider_ids:
        missing_from_campaign = sorted(provider_ids - campaign_event_ids)
        if missing_from_campaign:
            errors.extend(f"provider event is absent from campaign result: {event_id}" for event_id in missing_from_campaign)
    mode_required_count = sum(row["status"] == "MODE_REQUIRED" for row in event_rows)
    scenario_required_count = sum(row["status"] == "SCENARIO_ID_REQUIRED" for row in event_rows)
    conflict_count = sum(row["status"] == "MODE_BINDING_CONFLICT" for row in event_rows)
    bound_count = sum(row["status"] in _BOUND_STATUSES for row in event_rows)
    status = "HAZOP_EVENT_MODE_BINDING_COMPLETE" if not errors and mode_required_count == 0 and scenario_required_count == 0 and conflict_count == 0 else "HAZOP_EVENT_MODE_BINDING_REQUIRED"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "event_count": len(event_rows),
        "mode_bound_event_count": bound_count,
        "mode_required_event_count": mode_required_count,
        "scenario_id_required_event_count": scenario_required_count,
        "mode_conflict_event_count": conflict_count,
        "provider_event_count": len(provider_ids),
        "orphan_mode_binding_count": len(orphan_bindings),
        "event_rows": event_rows,
        "errors": errors,
        "policy": {
            "operating_mode_taken_from_input": True,
            "mode_inference_performed": False,
            "scenario_inference_performed": False,
            "missing_mode_withheld": True,
            "frequency_inference_performed": False,
            "facility_qra_promotion": False,
            "physical_validation_claim": False,
        },
        "interpretation": (
            "Every campaign event has an explicit HAZOP operating-mode/scenario binding."
            if status == "HAZOP_EVENT_MODE_BINDING_COMPLETE"
            else "Events without an explicit operating-mode/scenario binding remain open requests; no mode is inferred from equipment or release data."
        ),
    }


__all__ = [
    "SCHEMA",
    "apply_hazop_event_mode_bindings",
    "audit_hazop_event_mode_binding",
    "mode_bindings_from_diagnostic",
]

