"""Build an explicit full-scope HAZOP selection audit.

The live multi-equipment diagnostic intentionally dispatches one HAZOP row per
equipment kind.  The declared literature campaign contains additional release
families for some equipment (for example, the vaporizer 600 s and hole bins
and the reliquefier hole bin).  This module expands the *qualitative* HAZOP
table for those exact event families before the frequency/event identity audit.

The expansion is deliberately narrow: it copies the reviewed runtime signal
and threshold from the existing diagnostic row, adds only a declared family
and release mode already present in the campaign event, and never creates a
provider packet, assigns a frequency, or runs a consequence model.  The rows
remain synthetic scope-audit evidence until they are replaced with reviewed
facility HAZOP/P&ID data.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from .accident_scenario_catalog import scenario_definition
from .hazop_event_selection_audit import audit_hazop_selection_event_bindings
from .observed_hazop_runtime import audit_observed_hazop_runtime


TABLE_SET_SCHEMA = "prism.hazop_runtime_table_set.v1"
SCHEMA = "prism.full_scope_hazop_runtime_audit.v1"
MODE_BINDING_SCHEMA = "prism.hazop_event_mode_binding.v1"


def _rows(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(dict(row))
    return rows


def _bindings(value: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        if value.get("schema_version") not in {None, MODE_BINDING_SCHEMA}:
            raise ValueError(f"mode_bindings schema_version must be {MODE_BINDING_SCHEMA}")
        raw = value.get("bindings")
        if raw is None and value.get("event_id") is not None:
            raw = [value]
    else:
        raw = value
    return _rows(raw, "mode_bindings.bindings")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _families_by_event(cases: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    families: dict[str, set[str]] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise ValueError(f"cases[{index}] must be an object")
        event_id = _text(case.get("event_id"))
        raw = case.get("scenario_families")
        if not event_id or not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            continue
        families.setdefault(event_id, set()).update(
            _text(family) for family in raw if _text(family)
        )
    return {event_id: tuple(sorted(values)) for event_id, values in families.items()}


def _event_rows_from_campaign(campaign_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_events = _rows(campaign_result.get("events"), "campaign_result.events")
    families_by_event = _families_by_event(_rows(campaign_result.get("cases"), "campaign_result.cases"))
    rows: list[dict[str, Any]] = []
    for event in raw_events:
        event_id = _text(event.get("id"))
        rows.append({
            **event,
            "scenario_families": list(families_by_event.get(event_id, ())),
        })
    return rows


def _release_mode(event: Mapping[str, Any]) -> str:
    release = event.get("release")
    if not isinstance(release, Mapping):
        return ""
    return _text(release.get("mode"))


def build_full_scope_hazop_table_set(
    base_table_set: Mapping[str, Any],
    campaign_result: Mapping[str, Any],
    mode_bindings: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Add only the declared event families absent from a representative table.

    The function returns a table set even when a required identity is missing;
    the returned ``blocking_reasons`` make the gap explicit and the downstream
    audit remains fail-closed.
    """
    if base_table_set.get("schema_version") != TABLE_SET_SCHEMA:
        raise ValueError(f"base_table_set schema_version must be {TABLE_SET_SCHEMA}")
    raw_tables = base_table_set.get("tables")
    if not isinstance(raw_tables, Mapping) or not raw_tables:
        raise ValueError("base_table_set.tables must be a non-empty object")
    tables = {str(component_id): copy.deepcopy(dict(table)) for component_id, table in raw_tables.items()}
    events = _event_rows_from_campaign(campaign_result)
    bindings = _bindings(mode_bindings)
    binding_by_event = {_text(row.get("event_id")): row for row in bindings if _text(row.get("event_id"))}
    blocking: list[str] = []
    added_rows: list[dict[str, Any]] = []

    for event in events:
        event_id = _text(event.get("id"))
        binding = binding_by_event.get(event_id)
        component_id = _text(binding.get("component_id")) if binding else ""
        operating_mode = _text(binding.get("operating_mode")) if binding else ""
        release_mode = _release_mode(event)
        families = tuple(_text(family) for family in event.get("scenario_families", ()) if _text(family))
        if not event_id or not binding or not component_id or not operating_mode or not release_mode or not families:
            blocking.append(f"event {event_id or '<missing>'}: missing explicit component/mode/release/family identity")
            continue
        table = tables.get(component_id)
        if table is None:
            blocking.append(f"event {event_id}: no HAZOP table for component {component_id}")
            continue
        rows = _rows(table.get("rows"), f"tables[{component_id}].rows")
        matched = any(
            _text(row.get("component_id")) == component_id
            and operating_mode in tuple(row.get("operating_modes", ()))
            and _text(row.get("release_mode")) == release_mode
            and _text(row.get("scenario_family")) in families
            for row in rows
        )
        if matched:
            continue
        supported = []
        for family in families:
            try:
                definition = scenario_definition(family)
            except ValueError:
                blocking.append(f"event {event_id}: unknown scenario family {family}")
                continue
            if release_mode in definition["release_modes"]:
                supported.append(family)
        if not supported:
            blocking.append(
                f"event {event_id}: no event scenario family supports release mode {release_mode}"
            )
            continue
        template = next(
            (
                row for row in rows
                if _text(row.get("component_id")) == component_id
                and operating_mode in tuple(row.get("operating_modes", ()))
            ),
            None,
        )
        if template is None:
            blocking.append(f"event {event_id}: no signal/threshold template for component {component_id}")
            continue
        # There should normally be one exact family for a missing event.  Add
        # every explicitly declared compatible family rather than choosing a
        # representative by inference.
        for family in supported:
            row_id = f"{component_id}-full-scope-{family}"
            if any(_text(row.get("id")) == row_id for row in rows):
                continue
            added = {
                **copy.deepcopy(template),
                "id": row_id,
                "operating_modes": [operating_mode],
                "scenario_family": family,
                "release_mode": release_mode,
                "deviation_label": f"full-scope {family} deviation",
                "cause_summary": "explicit campaign event family requires a HAZOP selection row",
                "consequence_summary": "qualitative scope binding only; provider release remains separate",
                "provenance": (
                    "synthetic full-scope HAZOP selection-audit row derived from the explicit "
                    "campaign family; replace with reviewed facility HAZOP/P&ID evidence"
                ),
            }
            rows.append(added)
            added_rows.append({
                "event_id": event_id,
                "component_id": component_id,
                "operating_mode": operating_mode,
                "scenario_family": family,
                "release_mode": release_mode,
                "hazop_row_id": row_id,
            })
        table["rows"] = rows
        note = (
            "Full-scope selection audit rows were added from explicit campaign event families; "
            "they are synthetic qualitative bindings and do not create provider packets or frequencies."
        )
        notes = list(table.get("notes", []))
        if note not in notes:
            notes.append(note)
        table["notes"] = notes

    return {
        **copy.deepcopy(dict(base_table_set)),
        "tables": tables,
        "scope_audit": {
            "status": "FULL_SCOPE_HAZOP_ROWS_EXPANDED" if not blocking else "FULL_SCOPE_HAZOP_ROWS_REQUIRED",
            "base_table_count": len(raw_tables),
            "added_row_count": len(added_rows),
            "added_rows": added_rows,
            "blocking_reasons": list(dict.fromkeys(blocking)),
            "frequency_inference_performed": False,
            "provider_release_created": False,
            "consequence_calculated": False,
            "facility_qra_claim": False,
        },
    }


def build_full_scope_hazop_runtime_audit(
    base_table_set: Mapping[str, Any],
    runtime_frames: Mapping[str, Any],
    campaign_result: Mapping[str, Any],
    mode_bindings: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    now_s: float,
) -> dict[str, Any]:
    """Build and audit the expanded HAZOP runtime/event identity boundary."""
    table_set = build_full_scope_hazop_table_set(base_table_set, campaign_result, mode_bindings)
    runtime_audit = audit_observed_hazop_runtime(runtime_frames, table_set, now_s=float(now_s))
    event_rows = _event_rows_from_campaign(campaign_result)
    event_binding_audit = audit_hazop_selection_event_bindings(
        runtime_audit,
        mode_bindings,
        event_rows,
    )
    blocking = list(table_set["scope_audit"].get("blocking_reasons", []))
    if runtime_audit.get("status") != "OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED":
        blocking.append("expanded HAZOP runtime audit did not select clean scenarios")
    if event_binding_audit.get("status") != "HAZOP_SELECTION_EVENT_BINDING_COMPLETE":
        blocking.append("selected HAZOP scenarios do not bind every frequency event")
    status = (
        "FULL_SCOPE_HAZOP_SELECTION_EVENT_BINDING_COMPLETE"
        if not blocking
        else "FULL_SCOPE_HAZOP_SELECTION_EVENT_BINDING_REQUIRED"
    )
    return {
        "schema_version": SCHEMA,
        "status": status,
        "table_set": table_set,
        "observed_hazop_runtime_audit": runtime_audit,
        "hazop_selection_event_binding": event_binding_audit,
        "selected_scenario_count": runtime_audit.get("selected_scenario_count", 0),
        "frequency_event_count": event_binding_audit.get("frequency_event_count", 0),
        "bound_event_count": event_binding_audit.get("bound_event_count", 0),
        "unbound_event_count": event_binding_audit.get("unbound_event_count", 0),
        "blocking_reasons": list(dict.fromkeys(blocking)),
        "policy": {
            "operating_mode_taken_from_explicit_runtime_input": True,
            "scenario_family_inference_performed": False,
            "frequency_assignment_performed": False,
            "frequency_inference_performed": False,
            "provider_release_created": False,
            "consequence_calculated": False,
            "facility_qra_claim": False,
            "synthetic_scope_rows_present": bool(table_set["scope_audit"].get("added_row_count")),
            "diagnostic_only": True,
        },
        "interpretation": (
            "The expanded table explicitly selects every family represented by the declared "
            "frequency campaign. This is a qualitative identity audit only; provider release "
            "qualification, SLABx-LH2 execution, facility IR/F-N and physical validation remain separate gates."
        ),
    }


__all__ = [
    "SCHEMA",
    "TABLE_SET_SCHEMA",
    "build_full_scope_hazop_table_set",
    "build_full_scope_hazop_runtime_audit",
]
