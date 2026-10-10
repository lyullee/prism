"""Audit equipment-to-accident-scenario coverage before release promotion.

An equipment model can expose a normal process state without identifying the
physical P&ID port or producing an accident release history.  This module
keeps those questions separate.  It maps only an explicit, user-supplied
asset crosswalk to the generic outdoor LH2 scenario catalogue; it never
guesses a component kind from a tag or a model class and never creates a
frequency or a release packet.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .accident_scenario_catalog import (
    ACCIDENT_SCENARIO_CATALOG_SCHEMA,
    accident_scenario_catalog,
)


AUDIT_SCHEMA = "prism.equipment_scenario_coverage_audit.v1"
CROSSWALK_SCHEMA = "prism.equipment_kind_crosswalk.v1"
_KNOWN_KINDS = {
    "storage_tank",
    "pipe",
    "valve",
    "vent_stack",
    "pump",
    "vaporizer",
    "reliquefier",
}


class EquipmentScenarioCoverageAuditError(ValueError):
    """Raised when a scenario coverage audit input is malformed."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EquipmentScenarioCoverageAuditError(f"{label} must be an object")
    return value


def _assets(equipment_audit: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = equipment_audit.get("assets")
    if not isinstance(rows, list):
        raise EquipmentScenarioCoverageAuditError("equipment audit assets must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise EquipmentScenarioCoverageAuditError(f"assets[{index}] must be an object")
        result.append(row)
    return result


def _crosswalk_rows(crosswalk: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if crosswalk is None:
        return {}
    if crosswalk.get("schema_version") != CROSSWALK_SCHEMA:
        raise EquipmentScenarioCoverageAuditError(
            f"crosswalk schema_version must be {CROSSWALK_SCHEMA}"
        )
    if crosswalk.get("facility_neutral") is not True:
        raise EquipmentScenarioCoverageAuditError("crosswalk must declare facility_neutral=true")
    rows = crosswalk.get("rows")
    if not isinstance(rows, list):
        raise EquipmentScenarioCoverageAuditError("crosswalk rows must be an array")
    by_asset: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise EquipmentScenarioCoverageAuditError(f"crosswalk rows[{index}] must be an object")
        asset_id = raw.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise EquipmentScenarioCoverageAuditError(
                f"crosswalk rows[{index}].asset_id must be a non-empty string"
            )
        asset_id = asset_id.strip()
        if asset_id in by_asset:
            raise EquipmentScenarioCoverageAuditError(f"duplicate crosswalk asset_id: {asset_id}")
        kind = raw.get("component_kind")
        if kind not in _KNOWN_KINDS:
            raise EquipmentScenarioCoverageAuditError(
                f"crosswalk rows[{index}].component_kind must be one of {sorted(_KNOWN_KINDS)}"
            )
        identity_status = raw.get("identity_status")
        if identity_status not in {"resolved", "candidate"}:
            raise EquipmentScenarioCoverageAuditError(
                f"crosswalk rows[{index}].identity_status must be resolved or candidate"
            )
        basis = raw.get("identity_basis")
        if not isinstance(basis, str) or not basis.strip():
            raise EquipmentScenarioCoverageAuditError(
                f"crosswalk rows[{index}].identity_basis must be a non-empty string"
            )
        by_asset[asset_id] = raw
    return by_asset


def audit_equipment_scenario_coverage(
    equipment_audit: Mapping[str, Any],
    *,
    kind_crosswalk: Mapping[str, Any] | None = None,
    required_families: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return explicit per-asset scenario coverage without release promotion."""
    equipment = _object(equipment_audit, "equipment_audit")
    assets = _assets(equipment)
    selected_families = tuple(required_families) if required_families is not None else None
    crosswalk = _crosswalk_rows(kind_crosswalk)
    family_definitions = accident_scenario_catalog(selected_families)
    known_asset_ids = {str(row.get("asset_id")) for row in assets if row.get("asset_id")}
    extra_crosswalk_ids = sorted(set(crosswalk) - known_asset_ids)

    asset_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    mapped_asset_count = 0
    resolved_asset_count = 0
    state_ready_mapped_asset_count = 0

    for raw in assets:
        asset_id = str(raw.get("asset_id") or "")
        crosswalk_row = crosswalk.get(asset_id)
        kind = crosswalk_row.get("component_kind") if crosswalk_row else None
        identity_status = crosswalk_row.get("identity_status") if crosswalk_row else "unmapped"
        state_ready = raw.get("ready_for_state_model_input") is True
        if kind is not None:
            mapped_asset_count += 1
        if identity_status == "resolved":
            resolved_asset_count += 1
        if state_ready and identity_status == "resolved":
            state_ready_mapped_asset_count += 1
        if crosswalk_row is None:
            asset_status = "UNMAPPED_IDENTITY"
            asset_blockers = ["explicit asset-to-P&ID component crosswalk is required"]
        elif identity_status != "resolved":
            asset_status = "CANDIDATE_IDENTITY_ONLY"
            asset_blockers = ["candidate identity cannot open an accident scenario"]
        elif not state_ready:
            asset_status = "IDENTITY_RESOLVED_STATE_MODEL_INCOMPLETE"
            asset_blockers = ["state-model input is not ready"]
        else:
            asset_status = "SCENARIO_COVERAGE_DECLARED_RELEASE_UNVERIFIED"
            asset_blockers = ["provider accident release packet is not supplied"]
        if asset_blockers:
            blockers.extend(f"{asset_id}: {reason}" for reason in asset_blockers)
        asset_rows.append({
            "asset_id": asset_id,
            "external_component_model": raw.get("component_model"),
            "component_kind": kind,
            "identity_status": identity_status,
            "ready_for_state_model_input": state_ready,
            "status": asset_status,
            "blocking_reasons": asset_blockers,
            "scenario_families": [],
        })

    for definition in family_definitions:
        applicable = [
            row for row in asset_rows
            if row["identity_status"] == "resolved"
            and row["component_kind"] in definition["equipment_kinds"]
        ]
        for row in applicable:
            row["scenario_families"].append(definition["family"])
        family_status = "UNMAPPED_IDENTITY"
        family_blockers = ["no resolved asset identity is available for this accident family"]
        if applicable:
            family_status = "RELEASE_BOUNDARY_UNVERIFIED"
            family_blockers = ["provider packet with duration, isolation, inventory, and mass balance is required"]
            if any(row["ready_for_state_model_input"] for row in applicable):
                family_status = "STATE_MODEL_READY_RELEASE_BOUNDARY_UNVERIFIED"
        family_rows.append({
            "family": definition["family"],
            "equipment_kinds": list(definition["equipment_kinds"]),
            "applicable_asset_ids": [row["asset_id"] for row in applicable],
            "status": family_status,
            "required_source_operators": list(definition["required_source_operators"]),
            "termination_bases": list(definition["termination_bases"]),
            "consequence_path": definition["consequence_path"],
            "blocking_reasons": family_blockers,
        })

    if not crosswalk:
        blockers.insert(0, "no facility-neutral asset-to-component crosswalk was supplied")
    if extra_crosswalk_ids:
        blockers.append("crosswalk contains assets absent from equipment audit: " + ", ".join(extra_crosswalk_ids))
    if selected_families is not None:
        family_names = {row["family"] for row in family_rows}
        missing_requested = sorted(set(selected_families) - family_names)
        if missing_requested:
            blockers.append("requested families are not in the scenario catalogue: " + ", ".join(missing_requested))

    if not crosswalk:
        status = "CROSSWALK_REQUIRED"
    elif extra_crosswalk_ids or resolved_asset_count < mapped_asset_count:
        status = "PARTIAL_CROSSWALK_RELEASE_BOUNDARY_UNVERIFIED"
    elif resolved_asset_count == len(assets) and assets:
        status = "SCENARIO_CATALOG_BOUND_RELEASE_BOUNDARY_UNVERIFIED"
    else:
        status = "PARTIAL_CROSSWALK_RELEASE_BOUNDARY_UNVERIFIED"

    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "scope": "generic outdoor LH2 equipment-to-accident-scenario coverage",
        "scenario_catalog_schema": ACCIDENT_SCENARIO_CATALOG_SCHEMA,
        "asset_count": len(assets),
        "mapped_asset_count": mapped_asset_count,
        "resolved_asset_count": resolved_asset_count,
        "state_model_ready_mapped_asset_count": state_ready_mapped_asset_count,
        "scenario_family_count": len(family_rows),
        "assets": asset_rows,
        "scenario_families": family_rows,
        "extra_crosswalk_asset_ids": extra_crosswalk_ids,
        "promotion_gates": {
            "scenario_mapping_allowed": resolved_asset_count > 0,
            "accident_release_packet_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "required_next_evidence": [
            "facility-neutral asset ID, P&ID port, and component-kind crosswalk",
            "provider accident release packet for every declared family",
            "duration, isolation, inventory-depletion, and mass-balance echo",
            "independent holdout consequence comparison",
        ],
        "policy": {
            "component_kind_is_never_inferred_from_tag": True,
            "candidate_identity_is_not_resolved_identity": True,
            "scenario_catalog_does_not_create_release": True,
            "scenario_mapping_is_not_frequency": True,
            "no_automatic_facility_qra_promotion": True,
        },
        "source_equipment_audit_status": equipment.get("status"),
        "_record_path": equipment.get("_record_path"),
    }


__all__ = [
    "AUDIT_SCHEMA",
    "CROSSWALK_SCHEMA",
    "EquipmentScenarioCoverageAuditError",
    "audit_equipment_scenario_coverage",
]
