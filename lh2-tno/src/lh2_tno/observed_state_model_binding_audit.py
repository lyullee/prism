"""Audit observed process signals against the facility-neutral model catalog.

This is the bridge between a state-only telemetry ledger and a normal-state
digital-twin component model.  It checks signal coverage and model metadata,
but it never turns a normal-state model or its diagnostic adapter into an
accident release, frequency, or facility-QRA result.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .observed_component_mapping_audit import audit_observed_component_mapping


SCHEMA = "prism.observed_state_model_binding_audit.v1"
MODEL_BINDING_SCHEMA = "prism.equipment_model_binding.v1"


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        result.append(row)
    return result


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    values = [str(item).strip() for item in value]
    if any(not item for item in values) or len(set(values)) != len(values):
        raise ValueError(f"{label} must contain unique non-empty strings")
    return values


def audit_observed_state_model_binding(
    observed_state_evidence: Mapping[str, Any],
    component_mapping_manifest: Mapping[str, Any],
    model_binding_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed observed-state to normal-model audit."""
    mapping_audit = audit_observed_component_mapping(
        observed_state_evidence, component_mapping_manifest
    )
    if not isinstance(model_binding_catalog, Mapping):
        raise ValueError("model_binding_catalog must be an object")
    if model_binding_catalog.get("schema_version") != MODEL_BINDING_SCHEMA:
        raise ValueError(f"model_binding_catalog schema_version must be {MODEL_BINDING_SCHEMA}")
    if model_binding_catalog.get("facility_neutral") is not True:
        raise ValueError("model_binding_catalog must declare facility_neutral=true")

    source_by_component: dict[str, dict[str, Any]] = {}
    for source in _rows(observed_state_evidence.get("source_rows", []), "source_rows"):
        component_id = str(source.get("component_id") or "").strip()
        if not component_id:
            raise ValueError("source rows require component_id")
        signal_map = source.get("signal_map")
        if not isinstance(signal_map, Mapping):
            raise ValueError(f"source {source.get('source_id')} requires signal_map")
        source_by_component.setdefault(component_id, {"source_ids": [], "quantities": set()})
        source_by_component[component_id]["source_ids"].append(
            str(source.get("source_id") or "").strip()
        )
        source_by_component[component_id]["quantities"].update(str(key) for key in signal_map)

    binding_by_kind: dict[str, Mapping[str, Any]] = {}
    for index, binding in enumerate(_rows(model_binding_catalog.get("bindings", []), "bindings")):
        kind = str(binding.get("component_kind") or "").strip()
        if not kind:
            raise ValueError(f"bindings[{index}] requires component_kind")
        if kind in binding_by_kind:
            raise ValueError(f"duplicate model binding component_kind: {kind}")
        binding_by_kind[kind] = binding

    mapping_rows = _rows(component_mapping_manifest.get("mappings", []), "mappings")
    rows: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    state_bound_count = 0
    adapter_count = 0
    for mapping in mapping_rows:
        mapping_id = str(mapping.get("mapping_id") or "").strip()
        component_id = str(mapping.get("observed_component_id") or "").strip()
        model_kind = str(mapping.get("model_component_kind") or "").strip()
        required = _strings(
            mapping.get("required_state_quantities", []),
            f"mapping {mapping_id}.required_state_quantities",
        )
        reasons: list[str] = []
        observed = source_by_component.get(component_id)
        if observed is None:
            reasons.append("observed component has no state evidence")
        binding = binding_by_kind.get(model_kind)
        if binding is None:
            reasons.append(f"model catalog has no component_kind {model_kind}")
        else:
            if binding.get("state_export_status") != "supported":
                reasons.append("normal-state model export is not supported")
            missing_quantities = sorted(set(required) - set(observed["quantities"] if observed else ()))
            if missing_quantities:
                reasons.append(f"required state quantities are missing: {missing_quantities}")
        adapter = binding.get("diagnostic_release_adapter", {}) if binding else {}
        adapter_status = adapter.get("status", "missing") if isinstance(adapter, Mapping) else "missing"
        status = (
            "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE"
            if not reasons
            else "STATE_MODEL_BINDING_UNQUALIFIED"
        )
        if status == "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE":
            state_bound_count += 1
            if adapter_status == "available":
                adapter_count += 1
        else:
            blocking_reasons.extend(f"{component_id}: {reason}" for reason in reasons)
        rows.append({
            "mapping_id": mapping_id,
            "observed_component_id": component_id,
            "source_ids": list(observed["source_ids"] if observed else ()),
            "model_component_kind": model_kind,
            "required_state_quantities": required,
            "observed_state_quantities": sorted(observed["quantities"] if observed else ()),
            "model_package": binding.get("model_package") if binding else None,
            "model_class": binding.get("model_class") if binding else None,
            "model_revision": binding.get("model_revision") if binding else None,
            "state_export_status": binding.get("state_export_status") if binding else None,
            "diagnostic_release_adapter_status": adapter_status,
            "accident_release_export_status": binding.get("accident_release_export_status") if binding else None,
            "termination_ledger_status": binding.get("termination_ledger_status") if binding else None,
            "status": status,
            "blocking_reasons": list(dict.fromkeys(reasons)),
        })

    complete = (
        mapping_audit["status"] in {
            "CANDIDATE_COMPONENT_CLASS_MAPPINGS_ONLY",
            "EXACT_COMPONENT_MAPPINGS_NO_RELEASE",
            "MIXED_COMPONENT_MAPPINGS_NO_RELEASE",
        }
        and len(rows) == len(source_by_component)
        and state_bound_count == len(source_by_component)
        and not blocking_reasons
    )
    return {
        "schema": SCHEMA,
        "status": "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY" if complete else "PARTIAL_STATE_MODEL_BINDINGS",
        "mapping_audit_status": mapping_audit["status"],
        "observed_component_count": len(source_by_component),
        "state_model_bound_component_count": state_bound_count,
        "diagnostic_release_adapter_component_count": adapter_count,
        "qualified_provider_packet_count": 0,
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "policy": {
            "normal_state_model_is_not_accident_release": True,
            "diagnostic_adapter_is_not_qualified_provider": True,
            "release_event_binding_is_not_created": True,
            "frequency_is_not_assigned": True,
            "facility_ir_fn_promotion": False,
            "diagnostic_only": True,
        },
    }


__all__ = ["MODEL_BINDING_SCHEMA", "SCHEMA", "audit_observed_state_model_binding"]
