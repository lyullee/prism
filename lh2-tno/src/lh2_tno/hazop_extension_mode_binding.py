"""Bind explicitly configured HAZOP modes to namespaced LH2 extensions.

The extension campaigns are created independently from the base HAZOP runtime.
This module joins them only when a caller supplies an explicit operating mode,
scenario family, release mode, and HAZOP scenario identity.  It never derives a
mode from an asset name, release size, frequency, or provider result.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .contracts import canonical_digest
from .hazop_event_selection_audit import audit_hazop_selection_event_bindings


RUNTIME_SCHEMA = "prism.observed_hazop_runtime_audit.v1"
MODE_BINDING_SCHEMA = "prism.hazop_event_mode_binding.v1"
CONFIG_SCHEMA = "prism.hazop_extension_mode_config.v1"


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _rows(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    output: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        output.append(dict(row))
    return output


def _required_text(row: Mapping[str, Any], key: str, label: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return value


def _event_scenario_families(
    events: Sequence[Mapping[str, Any]], cases: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    families_by_event: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        event_id = str(case.get("event_id") or "").strip()
        if not event_id:
            continue
        families = case.get("scenario_families", [])
        if not isinstance(families, Sequence) or isinstance(families, (str, bytes)):
            continue
        families_by_event[event_id].update(
            str(family).strip() for family in families if str(family).strip()
        )
    output: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        event_id = str(row.get("id") or "").strip()
        event_families = {
            str(family).strip()
            for family in (row.get("scenario_families") or [])
            if str(family).strip()
        }
        row["scenario_families"] = sorted(
            event_families | families_by_event.get(event_id, set())
        )
        output.append(row)
    return output


def bind_hazop_extension_modes(
    runtime_audit: Mapping[str, Any],
    mode_binding: Mapping[str, Any],
    campaign_result: Mapping[str, Any],
    extension_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return merged runtime/binding/audit records for explicit extensions."""

    runtime = deepcopy(_object(runtime_audit, "runtime_audit"))
    binding = deepcopy(_object(mode_binding, "mode_binding"))
    campaign = _object(campaign_result, "campaign_result")
    config = _object(extension_config, "extension_config")
    if runtime.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError(f"runtime_audit must be {RUNTIME_SCHEMA}")
    if binding.get("schema_version") not in {None, MODE_BINDING_SCHEMA}:
        raise ValueError(f"mode_binding must be {MODE_BINDING_SCHEMA}")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError(f"extension_config must be {CONFIG_SCHEMA}")

    events = _rows(campaign.get("events", []), "campaign_result.events")
    cases = _rows(campaign.get("cases", []), "campaign_result.cases")
    event_rows = _event_scenario_families(events, cases)
    events_by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in event_rows:
        component_id = str(event.get("model_component_id") or "").strip()
        event_id = str(event.get("id") or "").strip()
        if component_id and event_id:
            events_by_component[component_id].append(event)
    cases_by_event = {
        str(case.get("event_id")): case
        for case in cases
        if str(case.get("event_id") or "").strip()
    }

    base_runtime_rows = _rows(runtime.get("rows", []), "runtime_audit.rows")
    base_bindings = _rows(binding.get("bindings", []), "mode_binding.bindings")
    extension_rows = _rows(config.get("extensions", []), "extension_config.extensions")
    configured_components: set[str] = set()
    extension_runtime_rows: list[dict[str, Any]] = []
    extension_bindings: list[dict[str, Any]] = []
    for index, configured in enumerate(extension_rows):
        label = f"extension_config.extensions[{index}]"
        component_id = _required_text(configured, "component_id", label)
        operating_mode = _required_text(configured, "operating_mode", label)
        scenario_family = _required_text(configured, "scenario_family", label)
        release_mode = _required_text(configured, "release_mode", label)
        scenario_id = _required_text(configured, "hazop_scenario_id", label)
        event_prefix = _required_text(configured, "event_prefix", label)
        if component_id in configured_components:
            raise ValueError(f"duplicate extension component configuration: {component_id}")
        configured_components.add(component_id)
        matched_events = [
            event
            for event in events_by_component.get(component_id, [])
            if str(event.get("id", "")).startswith(event_prefix)
        ]
        if not matched_events:
            raise ValueError(
                f"{label} matches no campaign events for component {component_id!r}"
            )
        mismatched = [
            str(event.get("id"))
            for event in matched_events
            if scenario_family not in set(event.get("scenario_families") or [])
            or str((event.get("release") or {}).get("mode") or "") != release_mode
        ]
        if mismatched:
            raise ValueError(
                f"{label} does not match event family/release mode: {', '.join(mismatched)}"
            )
        source_provenance = _required_text(configured, "source_provenance", label)
        table_id = _required_text(configured, "table_id", label)
        state_case = cases_by_event.get(str(matched_events[0]["id"])) or {}
        identity = state_case.get("provider_packet_identity")
        state_digest = (
            identity.get("state_snapshot_digest")
            if isinstance(identity, Mapping)
            else None
        )
        selected_scenario = {
            "scenario_id": scenario_id,
            "hazop_row_id": _required_text(configured, "hazop_row_id", label),
            "component_id": component_id,
            "component_kind": str(configured.get("component_kind") or "pipe"),
            "operating_mode": operating_mode,
            "scenario_family": scenario_family,
            "release_mode": release_mode,
            "priority": str(configured.get("priority") or "high"),
            "provider_release_status": "REQUIRED_NOT_CREATED",
            "provider_release_required": True,
            "frequency_assignment": "not_performed; bind an explicit literature event downstream",
            "source": source_provenance,
        }
        extension_runtime_rows.append(
            {
                "component_id": component_id,
                "source_id": _required_text(configured, "source_id", label),
                "captured_at_s": float(configured.get("captured_at_s", 0.0)),
                "operating_mode": operating_mode,
                "state_snapshot_digest": state_digest,
                "table_id": table_id,
                "table_digest": canonical_digest(configured),
                "state_digest": state_digest,
                "status": "SCENARIOS_SELECTED",
                "active_deviation_count": 1,
                "selected_scenario_count": 1,
                "selected_scenarios": [selected_scenario],
                "checks": [],
                "blocking_reasons": [],
                "source_provenance": source_provenance,
            }
        )
        for event in matched_events:
            extension_bindings.append(
                {
                    "event_id": event["id"],
                    "component_id": component_id,
                    "operating_mode": operating_mode,
                    "hazop_scenario_id": scenario_id,
                    "scenario_family": scenario_family,
                    "release_mode": release_mode,
                    "source_provenance": source_provenance,
                }
            )

    runtime["rows"] = base_runtime_rows + extension_runtime_rows
    runtime["status"] = "OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED"
    runtime["source_provenance"] = (
        str(runtime.get("source_provenance") or "").strip()
        + "; explicit extension HAZOP mode configuration"
    ).strip("; ").strip()
    binding["bindings"] = base_bindings + extension_bindings
    binding["status"] = "EXPLICIT_DIAGNOSTIC_BINDING"
    binding["source_provenance"] = (
        str(binding.get("source_provenance") or "").strip()
        + "; explicit extension HAZOP mode configuration"
    ).strip("; ").strip()
    audit = audit_hazop_selection_event_bindings(runtime, binding, event_rows)
    return {
        "runtime_audit": runtime,
        "mode_binding": binding,
        "selection_event_audit": audit,
        "extension_component_count": len(extension_rows),
        "extension_event_count": len(extension_bindings),
        "frequency_assignment_performed": False,
        "provider_release_created": False,
        "facility_qra_claim": False,
    }


__all__ = ["CONFIG_SCHEMA", "MODE_BINDING_SCHEMA", "RUNTIME_SCHEMA", "bind_hazop_extension_modes"]
