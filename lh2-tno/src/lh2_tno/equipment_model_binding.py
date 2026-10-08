"""Audit the generic LH2 equipment-model binding before release promotion.

The equipment model library can provide normal process-state calculations for
many component kinds while still lacking an accidental-release export.  This
module records that distinction per component kind.  It never treats a model
class name, a normal-flow result, or a regression test as a provider release
packet, a frequency, or a facility-QRA result.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .equipment_manifest import EquipmentManifest


MODEL_BINDING_SCHEMA = "prism.equipment_model_binding.v1"
_STATE_STATUSES = {"supported", "partial", "missing"}
_RELEASE_STATUSES = {"supported", "screening_only", "missing"}
_LEDGER_STATUSES = {"provider_termination_and_mass", "normal_flow_only", "missing"}


class EquipmentModelBindingError(ValueError):
    """Raised when a model-binding catalog is malformed or incomplete."""


def _read_object(value: Mapping[str, Any] | str | Path, label: str) -> tuple[dict[str, Any], str | None]:
    if isinstance(value, (str, Path)):
        path = Path(value).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EquipmentModelBindingError(f"cannot read {label}: {path}") from error
        if not isinstance(payload, dict):
            raise EquipmentModelBindingError(f"{label} must be a JSON object")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return payload, digest
    if not isinstance(value, Mapping):
        raise EquipmentModelBindingError(f"{label} must be an object")
    return dict(value), None


def _nonempty(row: Mapping[str, Any], key: str, label: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EquipmentModelBindingError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def audit_equipment_model_binding(
    manifest: EquipmentManifest | str | Path,
    binding_catalog: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Return per-component model coverage without promoting a QRA claim.

    A ``STATE_ONLY_BOUND`` result means every manifest component kind has a
    declared model class and normal-state export status, while one or more
    accident-release exports are still missing.  ``ACCIDENT_RELEASE_INTERFACE``
    means the catalog declares the packet interface for every kind; it still
    does not prove that a packet was produced or independently validated.
    """
    if isinstance(manifest, EquipmentManifest):
        manifest_obj = manifest
    else:
        try:
            manifest_obj = EquipmentManifest.from_json(manifest)
        except (OSError, UnicodeDecodeError, ValueError, TypeError) as error:
            raise EquipmentModelBindingError("invalid equipment manifest") from error
    catalog, catalog_digest = _read_object(binding_catalog, "model binding catalog")
    if catalog.get("schema_version") != MODEL_BINDING_SCHEMA:
        raise EquipmentModelBindingError(
            f"binding catalog schema_version must be {MODEL_BINDING_SCHEMA}"
        )
    if catalog.get("facility_neutral") is not True:
        raise EquipmentModelBindingError("binding catalog must declare facility_neutral=true")
    raw_bindings = catalog.get("bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise EquipmentModelBindingError("binding catalog bindings must be a non-empty list")

    by_kind: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for index, raw in enumerate(raw_bindings):
        if not isinstance(raw, Mapping):
            raise EquipmentModelBindingError(f"bindings[{index}] must be an object")
        kind = _nonempty(raw, "component_kind", f"bindings[{index}]")
        if kind in by_kind:
            raise EquipmentModelBindingError(f"duplicate component_kind binding: {kind}")
        model_package = _nonempty(raw, "model_package", f"bindings[{index}]")
        model_class = _nonempty(raw, "model_class", f"bindings[{index}]")
        model_revision = _nonempty(raw, "model_revision", f"bindings[{index}]")
        state_status = raw.get("state_export_status")
        release_status = raw.get("accident_release_export_status")
        ledger_status = raw.get("termination_ledger_status")
        if state_status not in _STATE_STATUSES:
            raise EquipmentModelBindingError(
                f"bindings[{index}].state_export_status must be one of {_STATE_STATUSES}"
            )
        if release_status not in _RELEASE_STATUSES:
            raise EquipmentModelBindingError(
                f"bindings[{index}].accident_release_export_status must be one of {_RELEASE_STATUSES}"
            )
        if ledger_status not in _LEDGER_STATUSES:
            raise EquipmentModelBindingError(
                f"bindings[{index}].termination_ledger_status must be one of {_LEDGER_STATUSES}"
            )
        provider_schema = raw.get("provider_export_schema")
        if provider_schema is not None and not isinstance(provider_schema, str):
            raise EquipmentModelBindingError(
                f"bindings[{index}].provider_export_schema must be a string or null"
            )
        if release_status == "supported" and provider_schema != "prism.resolved_release.v1":
            blockers.append(f"{kind}: supported accident release requires prism.resolved_release.v1")
        if release_status != "supported" and provider_schema is not None:
            blockers.append(f"{kind}: non-supported accident release must not advertise a provider schema")
        by_kind[kind] = {
            "component_kind": kind,
            "model_package": model_package,
            "model_class": model_class,
            "model_revision": model_revision,
            "state_export_status": state_status,
            "accident_release_export_status": release_status,
            "termination_ledger_status": ledger_status,
            "provider_export_schema": provider_schema,
            "qualification": raw.get("qualification"),
            "source_path": raw.get("source_path"),
        }

    component_rows: list[dict[str, Any]] = []
    manifest_kinds = sorted({component.kind for component in manifest_obj.components})
    for component in manifest_obj.components:
        binding = by_kind.get(component.kind)
        if binding is None:
            blockers.append(f"{component.id}: no model binding for component kind {component.kind}")
            component_rows.append({
                "component_id": component.id,
                "component_kind": component.kind,
                "status": "UNBOUND",
                "blocking_reasons": ["no model binding for component kind"],
            })
            continue
        row = dict(binding)
        row["component_id"] = component.id
        row["status"] = (
            "ACCIDENT_RELEASE_INTERFACE_BOUND"
            if binding["state_export_status"] == "supported"
            and binding["accident_release_export_status"] == "supported"
            and binding["termination_ledger_status"] == "provider_termination_and_mass"
            else "STATE_ONLY_BOUND"
            if binding["state_export_status"] == "supported"
            else "PARTIAL"
        )
        row["blocking_reasons"] = []
        if binding["state_export_status"] != "supported":
            row["blocking_reasons"].append("normal process-state export is not fully supported")
        if binding["accident_release_export_status"] != "supported":
            row["blocking_reasons"].append("accident provider packet export is not available")
        if binding["termination_ledger_status"] != "provider_termination_and_mass":
            row["blocking_reasons"].append("provider termination and mass ledger is not available")
        component_rows.append(row)

    unused_kinds = sorted(set(by_kind) - set(manifest_kinds))
    if unused_kinds:
        blockers.extend(f"binding has no manifest component for kind {kind}" for kind in unused_kinds)
    state_complete = bool(component_rows) and all(
        row["status"] in {"STATE_ONLY_BOUND", "ACCIDENT_RELEASE_INTERFACE_BOUND"}
        for row in component_rows
    ) and not any("no model binding" in reason for reason in blockers)
    release_complete = state_complete and all(
        row["status"] == "ACCIDENT_RELEASE_INTERFACE_BOUND" for row in component_rows
    ) and not blockers
    status = (
        "ACCIDENT_RELEASE_INTERFACE_BOUND"
        if release_complete
        else "STATE_ONLY_BOUND"
        if state_complete
        else "PARTIAL_MODEL_BINDING"
    )
    return {
        "schema_version": MODEL_BINDING_SCHEMA,
        "status": status,
        "facility_id": manifest_obj.facility_id,
        "manifest_digest": manifest_obj.digest(),
        "binding_catalog_sha256": catalog_digest,
        "component_count": len(manifest_obj.components),
        "component_rows": component_rows,
        "unused_binding_kinds": unused_kinds,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "physical_validation_claim": False,
        "accident_release_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "promotion_policy": {
            "normal_state_model_is_not_an_accident_release": True,
            "model_class_name_is_not_a_provider_packet": True,
            "provider_schema_requires_actual_packet": True,
            "frequency_is_bound_outside_model_catalog": True,
            "accident_export_interface": {
                "schema_version": "prism.equipment_accident_export_request.v1",
                "provider_method": "export_accident_history(request)",
                "contract_module": "lh2_tno.equipment_accident_export",
                "evaluate_simulate_fallback": False,
            },
        },
    }


__all__ = ["EquipmentModelBindingError", "audit_equipment_model_binding", "MODEL_BINDING_SCHEMA"]
