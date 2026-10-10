"""Build an explicit provider-release worklist from frequency events.

The worklist is a bridge between an initiating-event frequency plan and an
equipment digital twin.  It describes the packet that must be supplied for
each event, but never fabricates a release history or promotes a normal-flow
export into an accident.  Missing packets remain ``UNCOMPUTED``.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Literal, Mapping

from .contracts import Contract, Name, Positive
from .equipment_manifest import EquipmentManifest, audit_manifest
from .equipment_model_binding import audit_equipment_model_binding
from .frequency import FrequencyPlan, generate_events
from .provider_evidence import ACCIDENT_RELEASE_EXPORT_REQUEST
from .scenario_evidence import PROVIDER_RELEASE_REQUIRED_FIELDS
from .accident_scenario_catalog import scenario_families_for_release


WORKLIST_SCHEMA = "prism.provider_release_worklist.v1"

_EMERGENCY_RELIEF_FIELDS = tuple(
    field for field in PROVIDER_RELEASE_REQUIRED_FIELDS
    if field != "failure_opening_diameter_m"
)
_LIQUID_PACKET_FIELDS = tuple(
    sorted(ACCIDENT_RELEASE_EXPORT_REQUEST["liquid_required_fields"])
)


class ProviderReleaseWorkItem(Contract):
    """One exact frequency event awaiting an equipment release packet."""

    id: Name
    event_id: Name
    asset_id: Name
    component_id: Name
    profile: Name
    loc: Name
    annual_frequency_per_year: float
    release_mode: Literal[
        "hole",
        "instantaneous_inventory",
        "inventory_over_600s",
        "two_sided_rupture",
        "maximum_relief_discharge",
    ]
    scenario_families: tuple[Name, ...]
    provider_event_kind: Literal["accidental_leak", "emergency_relief"]
    provider_release_schema: Literal[
        "prism.resolved_release.v1", "prism.resolved_release_set.v1"
    ]
    provider_endpoint_count: int
    accident_port_ids: tuple[Name, ...]
    acceptable_source_operators: tuple[Name, ...]
    required_termination_basis: Name
    required_duration_s: Positive | None = None
    required_opening_diameter_m: Positive | None = None
    required_packet_fields: tuple[Name, ...]
    provider_boundary_variants: tuple[
        Literal["resolved_atmospheric_gas_exit", "resolved_atmospheric_liquid_exit"], ...
    ] = ("resolved_atmospheric_gas_exit",)
    liquid_packet_fields: tuple[Name, ...] = ()
    status: Literal["UNCOMPUTED_PROVIDER_PACKET", "UNCOMPUTED_NO_ACCIDENT_PORT"]
    model_binding_status: str | None = None
    model_accident_release_export_status: str | None = None
    model_diagnostic_release_adapter_status: str | None = None
    model_diagnostic_release_adapter_module: str | None = None
    blocking_reasons: tuple[str, ...] = ()


def _requirements(event) -> dict:
    mode = event.release.mode
    if mode == "hole":
        return {
            "provider_event_kind": "accidental_leak",
            "provider_release_schema": "prism.resolved_release.v1",
            "provider_endpoint_count": 1,
            "acceptable_source_operators": (
                "integrated_transient",
                "equipment_liquid_release",
            ),
            "required_termination_basis": "explicit_provider_termination",
            "required_duration_s": None,
            "required_opening_diameter_m": event.release.hole_diameter_m,
            "required_packet_fields": PROVIDER_RELEASE_REQUIRED_FIELDS,
            "provider_boundary_variants": (
                "resolved_atmospheric_gas_exit",
                "resolved_atmospheric_liquid_exit",
            ),
            "liquid_packet_fields": _LIQUID_PACKET_FIELDS,
        }
    if mode == "instantaneous_inventory":
        return {
            "provider_event_kind": "accidental_leak",
            "provider_release_schema": "prism.resolved_release.v1",
            "provider_endpoint_count": 1,
            "acceptable_source_operators": (
                "equipment_inventory_depletion",
                "equipment_liquid_release",
            ),
            "required_termination_basis": "inventory_depletion",
            "required_duration_s": None,
            "required_opening_diameter_m": None,
            "required_packet_fields": PROVIDER_RELEASE_REQUIRED_FIELDS,
            "provider_boundary_variants": (
                "resolved_atmospheric_gas_exit",
                "resolved_atmospheric_liquid_exit",
            ),
            "liquid_packet_fields": _LIQUID_PACKET_FIELDS,
        }
    if mode == "inventory_over_600s":
        return {
            "provider_event_kind": "accidental_leak",
            "provider_release_schema": "prism.resolved_release.v1",
            "provider_endpoint_count": 1,
            "acceptable_source_operators": (
                "equipment_inventory_over_600s",
                "equipment_liquid_over_600s",
            ),
            "required_termination_basis": "inventory_over_600s",
            "required_duration_s": 600.0,
            "required_opening_diameter_m": None,
            "required_packet_fields": PROVIDER_RELEASE_REQUIRED_FIELDS,
            "provider_boundary_variants": (
                "resolved_atmospheric_gas_exit",
                "resolved_atmospheric_liquid_exit",
            ),
            "liquid_packet_fields": _LIQUID_PACKET_FIELDS,
        }
    if mode == "two_sided_rupture":
        return {
            "provider_event_kind": "accidental_leak",
            "provider_release_schema": "prism.resolved_release_set.v1",
            "provider_endpoint_count": 2,
            "acceptable_source_operators": ("equipment_two_sided_rupture",),
            "required_termination_basis": "two_sided_rupture",
            "required_duration_s": None,
            "required_opening_diameter_m": event.release.hole_diameter_m,
            "required_packet_fields": (
                "provider_export_schema",
                "releases[0]",
                "releases[1]",
                "component_id",
                "available_mass_kg",
                "duration_s",
                "termination_provenance",
                "provider_source_digest",
                "provider_result_digest",
            ),
            "provider_boundary_variants": ("resolved_atmospheric_gas_exit",),
            "liquid_packet_fields": (),
        }
    if mode == "maximum_relief_discharge":
        return {
            "provider_event_kind": "emergency_relief",
            "provider_release_schema": "prism.resolved_release.v1",
            "provider_endpoint_count": 1,
            "acceptable_source_operators": ("equipment_emergency_relief",),
            "required_termination_basis": "emergency_relief_discharge",
            "required_duration_s": None,
            "required_opening_diameter_m": None,
            "required_packet_fields": _EMERGENCY_RELIEF_FIELDS,
            "provider_boundary_variants": ("resolved_atmospheric_gas_exit",),
            "liquid_packet_fields": (),
        }
    raise ValueError(f"unsupported release mode: {mode}")


def build_provider_release_worklist(
    manifest: EquipmentManifest,
    frequency_plan: FrequencyPlan,
    *,
    model_binding: Mapping[str, Any] | str | Path | None = None,
) -> dict:
    """Return a fail-closed packet request list for every frequency event.

    ``model_binding`` is optional so existing worklists remain reproducible.
    When supplied, it annotates each item with the component model's state and
    accident-export status; it never turns a normal-state model into a packet.
    """
    manifest_audit = audit_manifest(manifest)
    if manifest_audit["status"] != "EXECUTABLE":
        return {
            "schema": WORKLIST_SCHEMA,
            "status": "BLOCKED_MANIFEST",
            "manifest_status": manifest_audit["status"],
            "blocking_reasons": list(manifest_audit["blocking_reasons"]),
            "generated_event_count": 0,
            "provider_packet_count": 0,
            "work_items": [],
        }

    frequency_port_binding_warning = None
    try:
        events = generate_events(manifest.to_facility(), frequency_plan)
    except ValueError as error:
        # A missing mapped accident port must remain visible as an uncomputed
        # work item. Re-run only event generation with port annotations
        # stripped so the component-level worklist can report the missing
        # physical exit; never use this fallback to create a packet.
        message = str(error)
        if "references unknown port" not in message:
            raise
        raw_plan = frequency_plan.model_dump(mode="json")
        for asset in raw_plan["assets"]:
            asset.pop("port_ids", None)
            asset.pop("port_ids_by_loc", None)
        unbound_plan = FrequencyPlan.model_validate_json(
            json.dumps(raw_plan, allow_nan=False)
        )
        events = generate_events(manifest.to_facility(), unbound_plan)
        frequency_port_binding_warning = message
    model_binding_report = None
    model_binding_by_kind: dict[str, dict[str, Any]] = {}
    if model_binding is not None:
        model_binding_report = audit_equipment_model_binding(manifest, model_binding)
        model_binding_by_kind = {
            str(row["component_kind"]): row
            for row in model_binding_report["component_rows"]
            if row.get("component_kind")
        }
    ports_by_component: dict[str, tuple] = {}
    for component_id in {component.id for component in manifest.components}:
        ports_by_component[component_id] = tuple(
            port for port in manifest.ports
            if port.component_id == component_id
            and port.direction in {"out", "bidirectional"}
            and "accident" in port.id
        )

    items: list[ProviderReleaseWorkItem] = []
    for event in events:
        requirements = _requirements(event)
        if event.port_ids is not None:
            ports_by_id = {
                port.id: port
                for port in manifest.ports
                if port.component_id == event.model_component_id
            }
            ports = tuple(
                ports_by_id[port_id]
                for port_id in event.port_ids
                if port_id in ports_by_id
            )
            missing_requested_ports = tuple(
                port_id for port_id in event.port_ids if port_id not in ports_by_id
            )
        else:
            ports = ports_by_component.get(event.model_component_id, ())
            missing_requested_ports = ()
        component_kind = next(
            (component.kind for component in manifest.components if component.id == event.model_component_id),
            None,
        )
        binding_row = model_binding_by_kind.get(component_kind or "")
        reasons: list[str] = []
        port_missing = bool(missing_requested_ports) or len(ports) < requirements["provider_endpoint_count"]
        if port_missing:
            if missing_requested_ports:
                reasons.append(
                    "frequency event references missing accident port(s): "
                    + ", ".join(missing_requested_ports)
                )
            reasons.append(
                f"requires {requirements['provider_endpoint_count']} explicit accident port(s); "
                f"found {len(ports)}"
            )
        if binding_row is not None and binding_row.get("accident_release_export_status") != "supported":
            reasons.append("bound equipment model has no accident-release provider export")
            adapter = binding_row.get("diagnostic_release_adapter") or {}
            if adapter.get("status") == "available":
                reasons.append(
                    "diagnostic adapter is synthetic/screening evidence; qualified provider export remains required"
                )
        status = (
            "UNCOMPUTED_NO_ACCIDENT_PORT"
            if port_missing
            else "UNCOMPUTED_PROVIDER_PACKET"
        )
        items.append(
            ProviderReleaseWorkItem(
                id=f"{event.id}/provider-release",
                event_id=event.id,
                asset_id=event.asset_id,
                component_id=event.model_component_id,
                profile=event.profile,
                loc=event.loc,
                annual_frequency_per_year=event.annual_frequency_per_year,
                release_mode=event.release.mode,
                scenario_families=scenario_families_for_release(
                    component_kind, event.release.mode
                ),
                **requirements,
                accident_port_ids=tuple(port.id for port in ports),
                model_binding_status=(binding_row or {}).get("status"),
                model_accident_release_export_status=(binding_row or {}).get(
                    "accident_release_export_status"
                ),
                model_diagnostic_release_adapter_status=(
                    (binding_row or {}).get("diagnostic_release_adapter") or {}
                ).get("status"),
                model_diagnostic_release_adapter_module=(
                    (binding_row or {}).get("diagnostic_release_adapter") or {}
                ).get("module"),
                status=status,
                blocking_reasons=tuple(reasons),
            )
        )

    status_counts = Counter(item.status for item in items)
    scenario_family_counts = Counter(
        family for item in items for family in item.scenario_families
    )
    overall = (
        "READY_FOR_PROVIDER_PACKETS"
        if items and not status_counts["UNCOMPUTED_NO_ACCIDENT_PORT"]
        else "PARTIAL_MISSING_ACCIDENT_PORT"
    )
    return {
        "schema": WORKLIST_SCHEMA,
        "status": overall,
        "manifest_status": manifest_audit["status"],
        "frequency_plan_id": frequency_plan.id,
        "model_binding_status": (
            model_binding_report.get("status") if model_binding_report is not None else None
        ),
        "model_binding_accident_release_supported_component_count": (
            sum(
                row.get("accident_release_export_status") == "supported"
                for row in model_binding_report.get("component_rows", ())
            )
            if model_binding_report is not None
            else None
        ),
        "model_binding_diagnostic_release_adapter_component_count": (
            sum(
                ((row.get("diagnostic_release_adapter") or {}).get("status") == "available")
                for row in model_binding_report.get("component_rows", ())
            )
            if model_binding_report is not None
            else None
        ),
        "model_binding_blocking_reasons": (
            list(model_binding_report.get("blocking_reasons", ()))
            if model_binding_report is not None
            else []
        ),
        "generated_event_count": len(events),
        "frequency_port_binding_warning": frequency_port_binding_warning,
        "provider_packet_count": 0,
        "status_counts": dict(status_counts),
        "scenario_family_counts": dict(sorted(scenario_family_counts.items())),
        "promotion_policy": (
            "The worklist requests provider-owned release histories. It does not "
            "infer mass flow, duration, isolation, inventory, frequency, or a "
            "consequence request from normal-flow telemetry."
        ),
        "work_items": [item.model_dump(mode="json") for item in items],
    }
