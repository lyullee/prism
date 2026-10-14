"""Preflight the observed-HAZOP to provider/consequence execution boundary.

The preflight is intentionally stricter than the identity-only binding audit.
It reads the actual provider packet catalog and checks the packet event kind,
component/port identity, termination basis, duration, and mass ledger against
the selected HAZOP family.  It does not create a packet or infer a missing
termination basis.  A caller may execute only rows returned as
``READY_FOR_PROVIDER_CHAIN``; all other rows remain explicit withheld work.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .accident_scenario_catalog import scenario_definition


SCHEMA = "prism.observed_hazop_provider_consequence_chain.v1"
RUNTIME_SCHEMA = "prism.observed_hazop_runtime_audit.v1"
BINDING_SCHEMA = "prism.observed_hazop_provider_event_binding.v1"

_PROFILE_TO_COMPONENT_KIND = {
    "LH2_VESSEL": "storage_tank",
    "TNO_RELIEF_DEVICE": "vent_stack",
    "TNO_HX_OUTSIDE_TUBES": "vaporizer",
    "TNO_PIPE": "pipe",
    "TNO_VALVE": "valve",
    "TNO_PUMP": "pump",
    "TNO_RELIQUEFIER": "reliquefier",
}


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        result.append(row)
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _selected_scenarios(runtime_audit: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for row in _rows(runtime_audit.get("rows"), "runtime_audit.rows"):
        selected.extend(_rows(row.get("selected_scenarios"), "selected_scenarios"))
    return selected


def _packet_paths(packet_root: Path, packet_evidence: Mapping[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for row in _rows(packet_evidence.get("rows"), "packet_evidence.rows"):
        event_id = _text(row.get("event_id"))
        evidence = row.get("evidence")
        if not event_id or not isinstance(evidence, Mapping):
            continue
        resolved = evidence.get("resolved_packet_paths")
        if isinstance(resolved, Sequence) and not isinstance(resolved, (str, bytes)) and resolved:
            candidate = packet_root / str(resolved[0])
            paths[event_id] = candidate
    return paths


def _read_packet(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def audit_observed_hazop_consequence_preflight(
    observed_hazop_runtime_audit: Mapping[str, Any],
    observed_hazop_provider_binding: Mapping[str, Any],
    provider_worklist: Mapping[str, Any],
    packet_evidence: Mapping[str, Any],
    *,
    packet_root: str | Path,
) -> dict[str, Any]:
    """Return executable and withheld selected HAZOP provider work items."""
    if observed_hazop_runtime_audit.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError(f"runtime audit schema_version must be {RUNTIME_SCHEMA}")
    if observed_hazop_provider_binding.get("schema_version") != BINDING_SCHEMA:
        raise ValueError(f"provider binding schema_version must be {BINDING_SCHEMA}")
    if observed_hazop_provider_binding.get("status") != "OBSERVED_HAZOP_PROVIDER_EVENT_BINDINGS_DIAGNOSTIC":
        raise ValueError("provider binding must be a successful identity audit")

    selected = _selected_scenarios(observed_hazop_runtime_audit)
    runtime_context: dict[str, Mapping[str, Any]] = {}
    for runtime_row in _rows(observed_hazop_runtime_audit.get("rows"), "runtime_audit.rows"):
        for scenario in _rows(runtime_row.get("selected_scenarios"), "selected_scenarios"):
            scenario_id = _text(scenario.get("scenario_id"))
            runtime_context[scenario_id] = runtime_row
    work_items = _rows(provider_worklist.get("work_items"), "provider_worklist.work_items")
    worklist_by_event = {
        _text(row.get("event_id")): row
        for row in work_items
        if _text(row.get("event_id"))
    }
    binding_rows = _rows(observed_hazop_provider_binding.get("rows"), "provider_binding.rows")
    binding_by_scenario = {
        _text(row.get("scenario_id")): row
        for row in binding_rows
        if _text(row.get("scenario_id"))
    }
    paths = _packet_paths(Path(packet_root), packet_evidence)
    rows: list[dict[str, Any]] = []
    for scenario in selected:
        scenario_id = _text(scenario.get("scenario_id"))
        binding = binding_by_scenario.get(scenario_id)
        event_id = _text(binding.get("provider_event_id")) if binding else ""
        work_item = worklist_by_event.get(event_id)
        packet_path = paths.get(event_id)
        packet = _read_packet(packet_path) if packet_path is not None else None
        family = _text(scenario.get("scenario_family"))
        context = runtime_context.get(scenario_id, {})
        definition = scenario_definition(family) if family else None
        checks: dict[str, bool] = {
            "binding_present": binding is not None,
            "worklist_event_present": work_item is not None,
            "packet_evidence_path_present": packet_path is not None,
            "packet_file_present": packet_path is not None and packet_path.exists(),
            "packet_event_identity": False,
            "packet_component_identity": False,
            "packet_port_identity": False,
            "event_kind_compatible": False,
            "termination_basis_compatible": False,
            "duration_present": False,
            "mass_ledger_nonnegative": False,
        }
        expected_component = _text(binding.get("provider_component_id")) if binding else ""
        expected_port = _text(binding.get("provider_port_id")) if binding else ""
        if packet is not None:
            checks["packet_event_identity"] = _text(packet.get("event_id")) == event_id
            checks["packet_component_identity"] = _text(packet.get("component_id")) == expected_component
            checks["packet_port_identity"] = _text(packet.get("port_id")) == expected_port
            expected_kind = (
                "emergency_relief"
                if _text(scenario.get("release_mode")) == "maximum_relief_discharge"
                else "accidental_leak"
            )
            checks["event_kind_compatible"] = _text(packet.get("event_kind")) == expected_kind
            termination = _text(packet.get("termination_basis"))
            checks["termination_basis_compatible"] = bool(
                definition is not None and termination in definition["termination_bases"]
            )
            checks["duration_present"] = _finite_nonnegative(packet.get("duration_s")) and float(packet.get("duration_s", 0.0)) > 0.0
            checks["mass_ledger_nonnegative"] = (
                _finite_nonnegative(packet.get("available_mass_kg"))
                and _finite_nonnegative(packet.get("cumulative_mass_out_kg"))
                and float(packet.get("cumulative_mass_out_kg", 0.0)) <= float(packet.get("available_mass_kg", 0.0)) + 1.0e-9
            )
        valid = all(checks.values())
        reason = None if valid else ", ".join(key for key, value in checks.items() if not value)
        rows.append({
            "scenario_id": scenario_id,
            "hazop_row_id": scenario.get("hazop_row_id"),
            "observed_component_id": scenario.get("component_id"),
            "source_id": context.get("source_id"),
            "captured_at_s": context.get("captured_at_s"),
            "state_snapshot_digest": context.get("state_snapshot_digest"),
            "operating_mode": scenario.get("operating_mode"),
            "scenario_family": family,
            "release_mode": scenario.get("release_mode"),
            "provider_event_id": event_id or None,
            "provider_component_id": expected_component or None,
            "provider_component_kind": (
                _PROFILE_TO_COMPONENT_KIND.get(_text(work_item.get("profile")))
                if work_item is not None else None
            ),
            "provider_port_id": expected_port or None,
            "provider_packet_path": str(packet_path) if packet_path is not None else None,
            "provider_packet_status": packet.get("input_origin") if packet else None,
            "provider_termination_basis": packet.get("termination_basis") if packet else None,
            "provider_duration_s": packet.get("duration_s") if packet else None,
            "checks": checks,
            "status": "READY_FOR_PROVIDER_CHAIN" if valid else "WITHHELD_PROVIDER_CHAIN",
            "blocking_reason": reason,
        })

    ready_count = sum(row["status"] == "READY_FOR_PROVIDER_CHAIN" for row in rows)
    return {
        "schema_version": SCHEMA,
        "status": (
            "OBSERVED_HAZOP_PROVIDER_CHAIN_PREFLIGHT_READY"
            if rows and ready_count == len(rows)
            else "OBSERVED_HAZOP_PROVIDER_CHAIN_PREFLIGHT_PARTIAL"
            if ready_count
            else "OBSERVED_HAZOP_PROVIDER_CHAIN_PREFLIGHT_WITHHELD"
        ),
        "selected_scenario_count": len(rows),
        "ready_for_provider_chain_count": ready_count,
        "withheld_provider_chain_count": len(rows) - ready_count,
        "rows": rows,
        "blocking_reasons": [
            f"{row['scenario_id']}: {row['blocking_reason']}"
            for row in rows
            if row.get("blocking_reason")
        ],
        "policy": {
            "packet_created_by_prism": False,
            "termination_inferred": False,
            "frequency_assignment_performed": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Only packets whose actual event identity, port, event kind, termination "
            "basis, duration, and mass ledger satisfy the selected HAZOP family's "
            "contract may enter the consequence runner. Other scenarios remain withheld."
        ),
    }


__all__ = ["SCHEMA", "audit_observed_hazop_consequence_preflight"]
