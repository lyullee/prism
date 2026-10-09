"""Reconcile the declared model-binding catalog with the native source audit.

The external ``lh2dt`` source audit can prove that a class exposes
``export_accident_history(request)``.  The equipment binding catalog is a
separate declaration used by the campaign worklist.  Keeping the two records
separate is useful, but allowing them to drift silently is dangerous: a
worklist may then report a normal-state-only model even though a native
accident interface was implemented, or the reverse.

This module checks only that interface declarations agree.  It does not
create a release packet, qualify a provider, infer a frequency, or unlock a
facility IR/F-N result.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


NATIVE_BINDING_RECONCILIATION_SCHEMA = "prism.native_binding_reconciliation.v1"


class NativeBindingReconciliationError(ValueError):
    """Raised when one of the reconciliation inputs is malformed."""


def _read_object(value: Mapping[str, Any] | str | Path, label: str) -> tuple[dict[str, Any], str | None]:
    if isinstance(value, (str, Path)):
        path = Path(value).resolve()
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NativeBindingReconciliationError(f"cannot read {label}: {path}") from error
        if not isinstance(payload, dict):
            raise NativeBindingReconciliationError(f"{label} must be a JSON object")
        return payload, hashlib.sha256(raw).hexdigest()
    if not isinstance(value, Mapping):
        raise NativeBindingReconciliationError(f"{label} must be an object")
    return dict(value), None


def reconcile_native_binding_catalog(
    binding_catalog: Mapping[str, Any] | str | Path,
    contract_audit: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Return a fail-closed consistency report for native accident interfaces."""
    catalog, catalog_digest = _read_object(binding_catalog, "binding catalog")
    audit, audit_digest = _read_object(contract_audit, "native contract audit")
    if catalog.get("schema_version") != "prism.equipment_model_binding.v1":
        raise NativeBindingReconciliationError("binding catalog schema_version is invalid")
    if audit.get("schema_version") != "prism.external_model_contract_audit.v1":
        raise NativeBindingReconciliationError("native contract audit schema_version is invalid")
    raw_bindings = catalog.get("bindings")
    audit_rows = audit.get("rows")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise NativeBindingReconciliationError("binding catalog bindings must be a non-empty list")
    if not isinstance(audit_rows, list) or not audit_rows:
        raise NativeBindingReconciliationError("native contract audit rows must be a non-empty list")

    bindings: dict[str, Mapping[str, Any]] = {}
    for row in raw_bindings:
        if not isinstance(row, Mapping) or not isinstance(row.get("component_kind"), str):
            raise NativeBindingReconciliationError("every binding must name component_kind")
        kind = row["component_kind"]
        if kind in bindings:
            raise NativeBindingReconciliationError(f"duplicate binding component_kind: {kind}")
        bindings[kind] = row

    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    native_count = 0
    reconciled_count = 0
    for audit_row in audit_rows:
        if not isinstance(audit_row, Mapping):
            raise NativeBindingReconciliationError("native contract audit rows must be objects")
        kind = audit_row.get("component_kind")
        if not isinstance(kind, str) or not kind:
            raise NativeBindingReconciliationError("native audit row must name component_kind")
        binding = bindings.get(kind)
        is_external = str(audit_row.get("model_package", "")).startswith("lh2dt.")
        native_export = audit_row.get("native_accident_export_method") is True
        row_blockers: list[str] = []
        if binding is None:
            row_blockers.append("native audit component has no binding-catalog row")
        elif is_external and native_export:
            native_count += 1
            if binding.get("accident_release_export_status") != "supported":
                row_blockers.append("catalog does not declare the native accident export as supported")
            if binding.get("termination_ledger_status") != "provider_termination_and_mass":
                row_blockers.append("catalog does not declare provider termination and mass ledger")
            if binding.get("provider_export_schema") != "prism.resolved_release.v1":
                row_blockers.append("catalog does not declare the PRISM resolved release schema")
            if not row_blockers:
                reconciled_count += 1
        elif is_external and not native_export:
            # A missing native method may remain intentionally state-only.
            if binding is not None and binding.get("accident_release_export_status") == "supported":
                row_blockers.append("catalog claims accident export although the native method is absent")
        row = {
            "component_kind": kind,
            "model_package": audit_row.get("model_package"),
            "native_accident_export_method": native_export,
            "catalog_accident_release_export_status": None if binding is None else binding.get("accident_release_export_status"),
            "catalog_termination_ledger_status": None if binding is None else binding.get("termination_ledger_status"),
            "catalog_provider_export_schema": None if binding is None else binding.get("provider_export_schema"),
            "status": "RECONCILED" if not row_blockers else "BLOCKED",
            "blocking_reasons": row_blockers,
        }
        rows.append(row)
        blockers.extend(f"{kind}: {reason}" for reason in row_blockers)

    status = "RECONCILED_NATIVE_INTERFACES" if not blockers else "BLOCKED_STALE_NATIVE_BINDING"
    return {
        "schema_version": NATIVE_BINDING_RECONCILIATION_SCHEMA,
        "status": status,
        "binding_catalog_sha256": catalog_digest,
        "contract_audit_sha256": audit_digest,
        "binding_count": len(raw_bindings),
        "contract_audit_row_count": len(audit_rows),
        "native_accident_export_component_count": native_count,
        "reconciled_native_component_count": reconciled_count,
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "provider_packet_promoted": False,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "source_method_presence_is_interface_evidence_only": True,
            "catalog_reconciliation_does_not_create_packets": True,
            "native_export_requires_separate_runtime_and_qualification_evidence": True,
            "facility_ir_fn_remains_withheld_until_scope_and_provider_gates_pass": True,
        },
    }


__all__ = [
    "NATIVE_BINDING_RECONCILIATION_SCHEMA",
    "NativeBindingReconciliationError",
    "reconcile_native_binding_catalog",
]
