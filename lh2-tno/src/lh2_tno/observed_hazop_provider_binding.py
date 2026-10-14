"""Bind observed HAZOP scenarios to explicit literature provider events.

This module closes the identity boundary between the qualitative runtime
selector and the provider worklist.  It deliberately does not calculate a
frequency, infer one from a sensor, or create a resolved release packet.  A
successful result only proves that every selected scenario has an explicit
provider-event, component, and accident-port mapping that is compatible with
the declared scenario family and release mode.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.observed_hazop_provider_event_binding.v1"
RUNTIME_SCHEMA = "prism.observed_hazop_runtime_audit.v1"
MAP_SCHEMA = "prism.observed_hazop_provider_event_binding_map.v1"


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


def _finite_positive(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and value not in (float("inf"), float("-inf"))
        and value > 0
    )


def audit_observed_hazop_provider_binding(
    observed_hazop_runtime_audit: Mapping[str, Any],
    provider_worklist: Mapping[str, Any],
    binding_map: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit explicit HAZOP-scenario to literature-event identity mappings."""
    if observed_hazop_runtime_audit.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError(
            f"observed_hazop_runtime_audit schema_version must be {RUNTIME_SCHEMA}"
        )
    if binding_map.get("schema_version") != MAP_SCHEMA:
        raise ValueError(f"binding_map schema_version must be {MAP_SCHEMA}")

    work_items = _rows(provider_worklist.get("work_items"), "provider_worklist.work_items")
    binding_rows = _rows(binding_map.get("bindings"), "binding_map.bindings")
    worklist_by_event: dict[str, Mapping[str, Any]] = {}
    duplicate_worklist_events: list[str] = []
    for item in work_items:
        event_id = _text(item.get("event_id"))
        if not event_id:
            continue
        if event_id in worklist_by_event:
            duplicate_worklist_events.append(event_id)
        worklist_by_event[event_id] = item

    mapping_by_scenario: dict[str, Mapping[str, Any]] = {}
    duplicate_scenario_ids: list[str] = []
    for row in binding_rows:
        scenario_id = _text(row.get("scenario_id"))
        if not scenario_id:
            continue
        if scenario_id in mapping_by_scenario:
            duplicate_scenario_ids.append(scenario_id)
        mapping_by_scenario[scenario_id] = row

    selected: list[Mapping[str, Any]] = []
    for runtime_row in _rows(
        observed_hazop_runtime_audit.get("rows"),
        "observed_hazop_runtime_audit.rows",
    ):
        for scenario in _rows(runtime_row.get("selected_scenarios"), "selected_scenarios"):
            selected.append(scenario)

    rows: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    for scenario in selected:
        scenario_id = _text(scenario.get("scenario_id"))
        mapping = mapping_by_scenario.get(scenario_id)
        checks: dict[str, bool] = {
            "explicit_mapping_present": mapping is not None,
            "provider_event_present": False,
            "provider_component_matches_mapping": False,
            "provider_port_present": False,
            "scenario_family_compatible": False,
            "release_mode_compatible": False,
            "literature_frequency_present": False,
        }
        event: Mapping[str, Any] | None = None
        event_id = _text(mapping.get("provider_event_id")) if mapping else ""
        if mapping is not None:
            event = worklist_by_event.get(event_id)
            checks["provider_event_present"] = event is not None
            mapped_component = _text(mapping.get("provider_component_id"))
            mapped_port = _text(mapping.get("provider_port_id"))
            checks["provider_component_matches_mapping"] = bool(
                event is not None and mapped_component and mapped_component == _text(event.get("component_id"))
            )
            ports = event.get("accident_port_ids", []) if event is not None else []
            checks["provider_port_present"] = bool(mapped_port and mapped_port in ports)
            families = event.get("scenario_families", []) if event is not None else []
            checks["scenario_family_compatible"] = (
                _text(scenario.get("scenario_family")) in families
            )
            checks["release_mode_compatible"] = (
                _text(scenario.get("release_mode")) == _text(event.get("release_mode"))
                if event is not None
                else False
            )
            checks["literature_frequency_present"] = _finite_positive(
                event.get("annual_frequency_per_year") if event is not None else None
            )

        valid = all(checks.values()) and bool(scenario_id)
        if not valid:
            failed = [name for name, passed in checks.items() if not passed]
            blocking_reasons.append(
                f"{scenario_id or '<missing scenario_id>'}: " + ", ".join(failed)
            )
        rows.append(
            {
                "scenario_id": scenario_id,
                "hazop_row_id": scenario.get("hazop_row_id"),
                "observed_component_id": scenario.get("component_id"),
                "operating_mode": scenario.get("operating_mode"),
                "scenario_family": scenario.get("scenario_family"),
                "release_mode": scenario.get("release_mode"),
                "provider_event_id": event_id or None,
                "provider_component_id": (
                    event.get("component_id") if event is not None else None
                ),
                "provider_port_id": (
                    mapping.get("provider_port_id") if mapping is not None else None
                ),
                "provider_event_kind": event.get("provider_event_kind") if event else None,
                "provider_release_status": event.get("status") if event else None,
                "annual_frequency_per_year": (
                    event.get("annual_frequency_per_year") if event else None
                ),
                "checks": checks,
                "status": "EXPLICIT_PROVIDER_EVENT_BOUND" if valid else "PROVIDER_EVENT_BINDING_BLOCKED",
                "frequency_assignment": "not_performed; literature event identity only",
                "provider_release_created": False,
            }
        )

    if duplicate_worklist_events:
        blocking_reasons.append(
            "provider_worklist has duplicate event_id values: "
            + ", ".join(sorted(set(duplicate_worklist_events)))
        )
    if duplicate_scenario_ids:
        blocking_reasons.append(
            "binding map has duplicate scenario_id values: "
            + ", ".join(sorted(set(duplicate_scenario_ids)))
        )
    mapped_ids = set(mapping_by_scenario)
    selected_ids = { _text(scenario.get("scenario_id")) for scenario in selected }
    extra_ids = sorted(mapped_ids - selected_ids)
    if extra_ids:
        blocking_reasons.append(
            "binding map contains scenarios not selected by observed HAZOP: "
            + ", ".join(extra_ids)
        )

    valid = bool(selected) and not blocking_reasons and all(
        row["status"] == "EXPLICIT_PROVIDER_EVENT_BOUND" for row in rows
    )
    return {
        "schema_version": SCHEMA,
        "status": (
            "OBSERVED_HAZOP_PROVIDER_EVENT_BINDINGS_DIAGNOSTIC"
            if valid
            else "OBSERVED_HAZOP_PROVIDER_EVENT_BINDING_AUDIT_BLOCKED"
        ),
        "selected_scenario_count": len(selected),
        "bound_scenario_count": sum(
            row["status"] == "EXPLICIT_PROVIDER_EVENT_BOUND" for row in rows
        ),
        "provider_worklist_event_count": len(work_items),
        "binding_map_count": len(binding_rows),
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "policy": {
            "operating_mode_taken_from_explicit_runtime_input": True,
            "operating_mode_inferred": False,
            "literature_event_identity_bound": valid,
            "frequency_assignment_performed": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "consequence_calculated": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Each selected observed HAZOP scenario is checked against an explicit "
            "literature provider event, component, and accident port. The event's "
            "frequency is recorded for traceability only; it is not assigned to "
            "the sensor frame and no release packet or consequence is created."
        ),
    }


__all__ = ["MAP_SCHEMA", "RUNTIME_SCHEMA", "SCHEMA", "audit_observed_hazop_provider_binding"]
