"""Audit the HAZOP-selection to frequency-event expansion boundary.

One selected HAZOP deviation can intentionally expand to several literature
LOC events (for example, a storage-tank deviation to five hole-size bins).
This module checks that expansion explicitly by component, operating mode,
scenario family, release mode, and event identity.  It never assigns a rate,
creates a provider packet, or infers a missing HAZOP mode.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.hazop_event_selection_binding_audit.v1"
RUNTIME_SCHEMA = "prism.observed_hazop_runtime_audit.v1"
MODE_BINDING_SCHEMA = "prism.hazop_event_mode_binding.v1"


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bindings(value: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        raw = value.get("bindings")
        if raw is None and value.get("event_id") is not None:
            raw = [value]
    else:
        raw = value
    return _rows(raw, "mode_bindings.bindings")


def _selected(runtime_audit: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for row in _rows(runtime_audit.get("rows"), "runtime_audit.rows"):
        # Blocked HAZOP rows intentionally omit ``selected_scenarios``.  Treat
        # that as zero selections so the event-binding report can remain
        # fail-closed and explain the missing binding instead of crashing.
        if "selected_scenarios" not in row:
            continue
        selected.extend(_rows(row.get("selected_scenarios"), "selected_scenarios"))
    return selected


def audit_hazop_selection_event_bindings(
    runtime_audit: Mapping[str, Any],
    mode_bindings: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    frequency_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check explicit HAZOP selections against event-level frequency rows.

    The relationship is deliberately many-to-one: each frequency event must
    match one selected HAZOP scenario, while one selected scenario may match
    multiple event bins.  A scenario family is taken from the event catalogue
    when it is not repeated in the binding input; it is never inferred from a
    pressure, release size, equipment kind, or frequency value.
    """
    if runtime_audit.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError(f"runtime_audit schema_version must be {RUNTIME_SCHEMA}")
    if isinstance(mode_bindings, Mapping) and mode_bindings.get("schema_version") not in {
        None,
        MODE_BINDING_SCHEMA,
    }:
        raise ValueError(f"mode_bindings schema_version must be {MODE_BINDING_SCHEMA}")

    selected = _selected(runtime_audit)
    bindings = _bindings(mode_bindings)
    events = _rows(frequency_events, "frequency_events")
    events_by_id: dict[str, Mapping[str, Any]] = {}
    errors: list[str] = []
    for index, event in enumerate(events):
        event_id = _text(event.get("id"))
        if not event_id:
            errors.append(f"frequency_events[{index}] has no id")
        elif event_id in events_by_id:
            errors.append(f"duplicate frequency event id: {event_id}")
        else:
            events_by_id[event_id] = event

    binding_by_event: dict[str, Mapping[str, Any]] = {}
    for index, binding in enumerate(bindings):
        event_id = _text(binding.get("event_id"))
        if not event_id:
            errors.append(f"mode_bindings[{index}] has no event_id")
        elif event_id in binding_by_event:
            errors.append(f"duplicate mode binding event_id: {event_id}")
        else:
            binding_by_event[event_id] = binding

    selected_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    matched_selected_ids: set[str] = set()

    def candidates_for(
        *, component_id: str, operating_mode: str, scenario_family: str, release_mode: str
    ) -> list[tuple[int, Mapping[str, Any]]]:
        return [
            (index, scenario)
            for index, scenario in enumerate(selected)
            if _text(scenario.get("component_id")) == component_id
            and _text(scenario.get("operating_mode")) == operating_mode
            and _text(scenario.get("scenario_family")) == scenario_family
            and _text(scenario.get("release_mode")) == release_mode
        ]

    for binding_index, binding in enumerate(bindings):
        event_id = _text(binding.get("event_id"))
        event = events_by_id.get(event_id)
        component_id = _text(binding.get("component_id"))
        operating_mode = _text(binding.get("operating_mode"))
        binding_release_mode = _text(binding.get("release_mode"))
        event_release_mode = _text((event.get("release") or {}).get("mode")) if event else ""
        event_component_id = _text(event.get("model_component_id")) if event else ""
        families = event.get("scenario_families", []) if event else []
        if not isinstance(families, Sequence) or isinstance(families, (str, bytes)):
            families = []
        families = [_text(family) for family in families if _text(family)]
        family = _text(binding.get("scenario_family"))
        if family and family not in families:
            errors.append(f"event {event_id}: binding scenario_family is absent from event catalogue")
        family_candidates = [family] if family else families
        matching: list[tuple[int, Mapping[str, Any]]] = []
        for candidate_family in family_candidates:
            matching.extend(
                candidates_for(
                    component_id=component_id,
                    operating_mode=operating_mode,
                    scenario_family=candidate_family,
                    release_mode=binding_release_mode,
                )
            )
        checks = {
            "event_present": event is not None,
            "component_matches_event": bool(event and component_id and component_id == event_component_id),
            "release_mode_matches_event": bool(event and binding_release_mode == event_release_mode),
            "scenario_family_present": bool(family_candidates),
            "selected_hazop_scenario_match": bool(matching),
        }
        if not all(checks.values()):
            errors.append(
                f"event {event_id or '<missing>'}: "
                + ", ".join(name for name, passed in checks.items() if not passed)
            )
        for index, scenario in matching:
            matched_selected_ids.add(_text(scenario.get("scenario_id")))
        event_rows.append({
            "event_id": event_id,
            "component_id": component_id,
            "operating_mode": operating_mode,
            "hazop_scenario_id": _text(binding.get("hazop_scenario_id")) or None,
            "scenario_families": family_candidates,
            "frequency_event_component_id": event_component_id or None,
            "frequency_event_release_mode": event_release_mode or None,
            "selected_hazop_scenario_ids": sorted(
                {_text(scenario.get("scenario_id")) for _, scenario in matching if _text(scenario.get("scenario_id"))}
            ),
            "checks": checks,
            "status": "BOUND" if all(checks.values()) else "BINDING_BLOCKED",
            "frequency_assignment_performed": False,
        })

    for index, scenario in enumerate(selected):
        scenario_id = _text(scenario.get("scenario_id"))
        if scenario_id not in matched_selected_ids:
            errors.append(
                f"selected HAZOP scenario {scenario_id or f'<row {index}>'} has no frequency event binding"
            )
        selected_rows.append({
            "scenario_id": scenario_id,
            "component_id": _text(scenario.get("component_id")),
            "operating_mode": _text(scenario.get("operating_mode")),
            "scenario_family": _text(scenario.get("scenario_family")),
            "release_mode": _text(scenario.get("release_mode")),
            "matched_event_count": sum(
                scenario_id in row["selected_hazop_scenario_ids"] for row in event_rows
            ),
            "status": "BOUND" if scenario_id in matched_selected_ids else "BINDING_REQUIRED",
        })

    complete = bool(selected) and bool(bindings) and not errors and all(
        row["status"] == "BOUND" for row in event_rows
    )
    return {
        "schema_version": SCHEMA,
        "status": "HAZOP_SELECTION_EVENT_BINDING_COMPLETE" if complete else "HAZOP_SELECTION_EVENT_BINDING_REQUIRED",
        "selected_scenario_count": len(selected),
        "frequency_event_count": len(events),
        "mode_binding_count": len(bindings),
        "bound_event_count": sum(row["status"] == "BOUND" for row in event_rows),
        "unbound_event_count": sum(row["status"] != "BOUND" for row in event_rows),
        "selected_scenarios": selected_rows,
        "event_rows": event_rows,
        "errors": list(dict.fromkeys(errors)),
        "policy": {
            "operating_mode_taken_from_explicit_runtime_input": True,
            "scenario_family_inference_performed": False,
            "frequency_assignment_performed": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Explicit HAZOP selections are expanded to matching literature event bins. "
            "The audit proves identity compatibility only; frequency remains an external "
            "literature input and no release or consequence is created here."
        ),
    }


__all__ = ["MODE_BINDING_SCHEMA", "RUNTIME_SCHEMA", "SCHEMA", "audit_hazop_selection_event_bindings"]
