"""Audit literature-frequency binding to resolved LH2 equipment scenarios.

This is the bridge between the reviewed frequency catalogue and the generic
equipment/scenario crosswalk.  It accepts only explicit literature events;
sensor alarms, normal-state observations, and local incident guesses cannot
create an event.  A valid frequency binding still does not create a provider
release packet or a facility QRA result.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .accident_scenario_catalog import scenario_families_for_release


AUDIT_SCHEMA = "prism.equipment_frequency_binding_audit.v1"
FREQUENCY_PROVENANCE_SCHEMA = "prism.frequency_provenance.v1"
_RELEASE_MODES = {
    "instantaneous_inventory",
    "inventory_over_600s",
    "hole",
    "two_sided_rupture",
    "maximum_relief_discharge",
}


class EquipmentFrequencyBindingAuditError(ValueError):
    """Raised when a frequency binding audit input is malformed."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EquipmentFrequencyBindingAuditError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_nonnegative(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise EquipmentFrequencyBindingAuditError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise EquipmentFrequencyBindingAuditError(f"{field} must be numeric") from error
    if not math.isfinite(number) or number < 0.0:
        raise EquipmentFrequencyBindingAuditError(f"{field} must be finite and non-negative")
    return number


def _coverage_assets(coverage: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if coverage.get("schema_version") != "prism.equipment_scenario_coverage_audit.v1":
        raise EquipmentFrequencyBindingAuditError(
            "coverage must be prism.equipment_scenario_coverage_audit.v1"
        )
    rows = coverage.get("assets")
    if not isinstance(rows, list):
        raise EquipmentFrequencyBindingAuditError("coverage assets must be an array")
    result: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise EquipmentFrequencyBindingAuditError(f"coverage assets[{index}] must be an object")
        asset_id = _text(row.get("asset_id"), f"coverage assets[{index}].asset_id")
        if asset_id in result:
            raise EquipmentFrequencyBindingAuditError(f"duplicate coverage asset_id: {asset_id}")
        reviewed_ports = row.get("reviewed_accident_port_ids")
        if reviewed_ports is not None and (
            not isinstance(reviewed_ports, list)
            or any(not isinstance(value, str) or not value.strip() for value in reviewed_ports)
            or len(set(reviewed_ports)) != len(reviewed_ports)
        ):
            raise EquipmentFrequencyBindingAuditError(
                f"coverage assets[{index}].reviewed_accident_port_ids must be a unique string array"
            )
        result[asset_id] = row
    return result


def _events_from_provenance(
    frequency_provenance: Mapping[str, Any] | None,
    frequency_events: Sequence[Mapping[str, Any]] | None,
) -> tuple[list[Mapping[str, Any]], str | None]:
    if frequency_provenance is not None:
        if frequency_provenance.get("schema_version") != FREQUENCY_PROVENANCE_SCHEMA:
            raise EquipmentFrequencyBindingAuditError(
                f"frequency provenance must be {FREQUENCY_PROVENANCE_SCHEMA}"
            )
        raw = frequency_provenance.get("generated_events")
        if not isinstance(raw, list):
            raise EquipmentFrequencyBindingAuditError(
                "frequency provenance generated_events must be an array"
            )
        rows: list[Mapping[str, Any]] = []
        for index, row in enumerate(raw):
            if not isinstance(row, Mapping):
                raise EquipmentFrequencyBindingAuditError(
                    f"frequency provenance generated_events[{index}] must be an object"
                )
            rows.append(row)
        return rows, frequency_provenance.get("_record_path")
    if frequency_events is None:
        return [], None
    if not isinstance(frequency_events, Sequence) or isinstance(frequency_events, (str, bytes)):
        raise EquipmentFrequencyBindingAuditError("frequency_events must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(frequency_events):
        if not isinstance(row, Mapping):
            raise EquipmentFrequencyBindingAuditError(f"frequency_events[{index}] must be an object")
        rows.append(row)
    return rows, None


def audit_equipment_frequency_binding(
    equipment_scenario_coverage: Mapping[str, Any],
    *,
    frequency_provenance: Mapping[str, Any] | None = None,
    frequency_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bind explicit literature events to resolved equipment families."""
    coverage = equipment_scenario_coverage
    if not isinstance(coverage, Mapping):
        raise EquipmentFrequencyBindingAuditError("equipment_scenario_coverage must be an object")
    assets = _coverage_assets(coverage)
    events, provenance_path = _events_from_provenance(frequency_provenance, frequency_events)
    family_rows = coverage.get("scenario_families")
    if not isinstance(family_rows, list):
        raise EquipmentFrequencyBindingAuditError("coverage scenario_families must be an array")
    family_by_name: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(family_rows):
        if not isinstance(row, Mapping):
            raise EquipmentFrequencyBindingAuditError(
                f"coverage scenario_families[{index}] must be an object"
            )
        family = _text(row.get("family"), f"coverage scenario_families[{index}].family")
        if family in family_by_name:
            raise EquipmentFrequencyBindingAuditError(f"duplicate scenario family: {family}")
        family_by_name[family] = row
    family_rows_for_output: list[dict[str, Any]] = []

    resolved_assets = {
        asset_id: row for asset_id, row in assets.items()
        if row.get("identity_status") == "resolved"
        and isinstance(row.get("component_kind"), str)
    }
    seen_event_ids: set[str] = set()
    event_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    family_event_ids: dict[str, list[str]] = {family: [] for family in family_by_name}
    valid_event_count = 0

    for index, event in enumerate(events):
        event_id = event.get("id") or event.get("event_id")
        try:
            event_id = _text(event_id, f"frequency event[{index}].id")
            asset_id = _text(event.get("asset_id"), f"frequency event {event_id}.asset_id")
            profile = _text(event.get("profile"), f"frequency event {event_id}.profile")
            basis = _text(event.get("basis"), f"frequency event {event_id}.basis")
            source = _text(event.get("source"), f"frequency event {event_id}.source")
            source_sha256 = _text(
                event.get("source_sha256"), f"frequency event {event_id}.source_sha256"
            )
            raw_port_ids = event.get("port_ids")
            if raw_port_ids is None:
                event_port_ids: tuple[str, ...] | None = None
            elif (
                not isinstance(raw_port_ids, list)
                or not raw_port_ids
                or any(not isinstance(value, str) or not value.strip() for value in raw_port_ids)
                or len(set(raw_port_ids)) != len(raw_port_ids)
            ):
                raise EquipmentFrequencyBindingAuditError(
                    f"frequency event {event_id}.port_ids must be a unique string array"
                )
            else:
                event_port_ids = tuple(raw_port_ids)
            release = event.get("release")
            if not isinstance(release, Mapping):
                raise EquipmentFrequencyBindingAuditError(
                    f"frequency event {event_id}.release must be an object"
                )
            release_mode = release.get("mode")
            if release_mode not in _RELEASE_MODES:
                raise EquipmentFrequencyBindingAuditError(
                    f"frequency event {event_id}.release.mode is unsupported"
                )
            annual_rate = _finite_nonnegative(
                event.get("annual_frequency_per_year"),
                f"frequency event {event_id}.annual_frequency_per_year",
            )
            limitations = event.get("limitations", [])
            if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
                raise EquipmentFrequencyBindingAuditError(
                    f"frequency event {event_id}.limitations must be an array of strings"
                )
        except EquipmentFrequencyBindingAuditError as error:
            blockers.append(str(error))
            event_rows.append({
                "event_id": event_id if isinstance(event_id, str) else None,
                "status": "INVALID_PROVENANCE",
                "blocking_reasons": [str(error)],
            })
            continue

        row_blockers: list[str] = []
        if event_id in seen_event_ids:
            row_blockers.append("duplicate frequency event ID")
        seen_event_ids.add(event_id)
        asset = assets.get(asset_id)
        if asset is None:
            row_blockers.append("frequency event asset is absent from scenario coverage")
            component_kind = None
        else:
            component_kind = asset.get("component_kind")
            if asset_id not in resolved_assets:
                row_blockers.append("frequency cannot bind to an unresolved asset identity")
        port_binding_status = "UNBOUND_COMPONENT_EVENT"
        if event_port_ids is not None:
            reviewed_port_ids = (
                tuple(asset.get("reviewed_accident_port_ids", ()))
                if asset is not None
                else ()
            )
            if not reviewed_port_ids:
                row_blockers.append(
                    "frequency event has reviewed port_ids but coverage has no accident-port crosswalk"
                )
                port_binding_status = "PORT_BINDING_WITHHELD"
            elif any(port_id not in reviewed_port_ids for port_id in event_port_ids):
                row_blockers.append(
                    "frequency event port_ids are absent from the asset accident-port crosswalk"
                )
                port_binding_status = "PORT_BINDING_WITHHELD"
            else:
                port_binding_status = "BOUND_REVIEWED_PORT"
        expected_families = (
            scenario_families_for_release(component_kind, release_mode)
            if isinstance(component_kind, str)
            else ()
        )
        coverage_family_names = set(family_by_name)
        missing_families = sorted(set(expected_families) - coverage_family_names)
        if missing_families:
            row_blockers.append(
                "scenario coverage omits expected families: " + ", ".join(missing_families)
            )
        for family in expected_families:
            family_row = family_by_name.get(family)
            if family_row is None:
                continue
            applicable_ids = family_row.get("applicable_asset_ids", [])
            if not isinstance(applicable_ids, list) or asset_id not in applicable_ids:
                row_blockers.append(
                    f"scenario family {family} is not declared applicable to asset {asset_id}"
                )
        # A family is frequency-bound only when the complete event identity,
        # resolved asset and declared family applicability all validate.  Do
        # not leave a misleading family event ID behind for candidate assets,
        # duplicate IDs, absent assets, or malformed provenance rows.
        if not row_blockers:
            for family in expected_families:
                if family in family_by_name:
                    family_event_ids.setdefault(family, []).append(event_id)
        if not row_blockers:
            valid_event_count += 1
        else:
            blockers.extend(f"{event_id}: {reason}" for reason in row_blockers)
        event_rows.append({
            "event_id": event_id,
            "asset_id": asset_id,
            "component_kind": component_kind,
            "profile": profile,
            "basis": basis,
            "source": source,
            "source_sha256": source_sha256,
            "port_ids": None if event_port_ids is None else list(event_port_ids),
            "port_binding_status": port_binding_status,
            "annual_frequency_per_year": annual_rate,
            "release_mode": release_mode,
            "expected_scenario_families": list(expected_families),
            "status": "BOUND_LITERATURE_EVENT" if not row_blockers else "BLOCKED",
            "blocking_reasons": row_blockers,
            "limitations": list(limitations),
        })

    uncomputed_families = []
    for family, row in family_by_name.items():
        applicable_ids = row.get("applicable_asset_ids", [])
        if not isinstance(applicable_ids, list):
            applicable_ids = []
        event_ids = family_event_ids.get(family, [])
        family_status = "UNCOMPUTED_NO_RESOLVED_ASSET" if not applicable_ids else (
            "FREQUENCY_BOUND_RELEASE_UNVERIFIED" if event_ids else "UNCOMPUTED_NO_FREQUENCY_EVENT"
        )
        family_row = {
            "family": family,
            "applicable_asset_ids": list(applicable_ids),
            "frequency_event_ids": list(dict.fromkeys(event_ids)),
            "status": family_status,
            "frequency_bound": bool(event_ids),
            "provider_release_required": True,
        }
        if not event_ids:
            uncomputed_families.append(family)
        family_row["blocking_reasons"] = [] if event_ids else [
            "provider release packet remains uncomputed"
        ]
        # Replace the source coverage row with a frequency view only in the
        # returned sidecar; the input coverage audit stays immutable.
        family_rows_for_output.append(family_row)

    has_resolved_asset = bool(resolved_assets)
    if not has_resolved_asset:
        blockers.append("no resolved asset identity is available for literature frequency binding")
    if not events:
        blockers.append("no literature frequency events were supplied")
    status = (
        "FREQUENCY_BINDING_WITHHELD"
        if not has_resolved_asset or not events
        else "PARTIAL_FREQUENCY_BINDING"
        if blockers
        else "LITERATURE_FREQUENCY_BOUND_RELEASE_UNVERIFIED"
    )
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "scope": "generic outdoor LH2 literature frequency binding; no field frequency learning",
        "coverage_record": coverage.get("_record_path"),
        "frequency_provenance_record": provenance_path,
        "asset_count": len(assets),
        "resolved_asset_count": len(resolved_assets),
        "frequency_event_count": len(events),
        "valid_frequency_event_count": valid_event_count,
        "bound_family_count": sum(bool(ids) for ids in family_event_ids.values()),
        "uncomputed_family_count": len(uncomputed_families),
        "uncomputed_families": uncomputed_families,
        "frequency_port_binding": {
            "schema_version": "prism.frequency_port_binding.v1",
            "reviewed_port_bound_event_count": sum(
                row.get("port_binding_status") == "BOUND_REVIEWED_PORT"
                for row in event_rows
            ),
            "port_unbound_event_count": sum(
                row.get("port_binding_status") == "UNBOUND_COMPONENT_EVENT"
                for row in event_rows
            ),
            "port_binding_withheld_event_count": sum(
                row.get("port_binding_status") == "PORT_BINDING_WITHHELD"
                for row in event_rows
            ),
            "all_supplied_port_scopes_valid": not any(
                row.get("port_binding_status") == "PORT_BINDING_WITHHELD"
                for row in event_rows
            ),
            "strict_facility_qra_gate": False,
        },
        "events": event_rows,
        "scenario_families": family_rows_for_output,
        "frequency_uncertainty": {
            "literature_baseline_used": bool(events),
            "event_limitations_retained": True,
            "marginal_p05_p95_are_not_facility_credible_interval": True,
            "facility_credible_interval": False,
            "statistical_confidence_interval": False,
        },
        "promotion_gates": {
            "literature_frequency_binding_allowed": valid_event_count > 0 and not blockers,
            "provider_release_required": True,
            "consequence_binding_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "provider_packet_promoted": False,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "policy": {
            "literature_frequency_is_not_field_validated": True,
            "sensor_frequency_learning_used": False,
            "normal_state_observations_do_not_create_frequency": True,
            "unresolved_assets_do_not_receive_zero_frequency": True,
            "unmapped_families_remain_uncomputed": True,
            "frequency_does_not_create_provider_release": True,
            "reviewed_port_ids_are_never_inferred": True,
            "provider_release_required_before_consequence": True,
            "facility_qra_requires_complete_family_and_packet_coverage": True,
        },
    }


__all__ = [
    "AUDIT_SCHEMA",
    "EquipmentFrequencyBindingAuditError",
    "audit_equipment_frequency_binding",
]
