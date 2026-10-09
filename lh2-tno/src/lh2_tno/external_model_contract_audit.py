"""Statically audit an external LH2 model against the PRISM release contract.

The audit deliberately does not execute the external model.  It answers a
narrow question that is easy to get wrong in a digital-twin integration:
does the external model class itself expose the PRISM accident-release
method, or is the available method only a PRISM-side diagnostic wrapper?

Normal-state methods, class names, and wrapper smoke tests are recorded as
evidence, but they never promote a provider packet, frequency, or facility
QRA result.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


EXTERNAL_MODEL_CONTRACT_AUDIT_SCHEMA = "prism.external_model_contract_audit.v1"
_NORMAL_METHOD_NAMES = {"simulate", "step", "evaluate", "run"}
_TERMINATION_METHOD_NAMES = {
    "export_accident_history",
    "termination_ledger",
    "inventory_depletion",
    "inventory_state",
}


class ExternalModelContractAuditError(ValueError):
    """Raised when a binding catalog cannot be audited."""


def _read_json(value: Mapping[str, Any] | str | Path, label: str) -> tuple[dict[str, Any], str | None]:
    if isinstance(value, (str, Path)):
        path = Path(value).resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExternalModelContractAuditError(f"cannot read {label}: {path}") from error
        if not isinstance(payload, dict):
            raise ExternalModelContractAuditError(f"{label} must be a JSON object")
        return payload, hashlib.sha256(path.read_bytes()).hexdigest()
    if not isinstance(value, Mapping):
        raise ExternalModelContractAuditError(f"{label} must be an object")
    return dict(value), None


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    for path in files:
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _source_path(external_root: Path, source_path: str | None, model_package: str) -> Path | None:
    if isinstance(source_path, str) and source_path.strip():
        normalized = source_path.replace("\\", "/")
        marker = "/src/"
        if marker in normalized:
            return external_root / "src" / normalized.split(marker, 1)[1]
        if normalized.startswith("src/"):
            return external_root / normalized
    if model_package.startswith("lh2dt."):
        return external_root / "src" / (model_package.replace(".", "/") + ".py")
    return None


def _parse_class(path: Path, class_name: str) -> tuple[set[str], list[str], str | None]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        return set(), [], f"source_parse_error: {error}"
    wanted = class_name.split("+", 1)[0].strip()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == wanted:
            methods = {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            bases = [ast.unparse(base) for base in node.bases]
            return methods, bases, None
    return set(), [], f"class_not_found: {wanted}"


def _audit_row(row: Mapping[str, Any], external_root: Path, prism_root: Path) -> dict[str, Any]:
    kind = row.get("component_kind")
    package = row.get("model_package")
    class_name = row.get("model_class")
    if not all(isinstance(value, str) and value.strip() for value in (kind, package, class_name)):
        raise ExternalModelContractAuditError("each binding requires component_kind, model_package, and model_class")
    source = _source_path(external_root, row.get("source_path"), package)
    result: dict[str, Any] = {
        "component_kind": kind,
        "model_package": package,
        "model_class": class_name,
        "source_path": str(source) if source is not None else None,
        "source_exists": bool(source and source.is_file()),
        "native_accident_export_method": False,
        "native_termination_ledger_methods": [],
        "native_normal_state_methods": [],
        "native_class_bases": [],
        "native_audit_status": "NOT_EXTERNAL_MODEL" if not package.startswith("lh2dt.") else "EXTERNAL_SOURCE_UNRESOLVED",
        "diagnostic_adapter": dict(row.get("diagnostic_release_adapter") or {"status": "missing"}),
        "diagnostic_adapter_contract_verified": False,
        "blocking_reasons": [],
    }
    if not package.startswith("lh2dt."):
        result["source_exists"] = False
    elif source is None or not source.is_file():
        result["blocking_reasons"].append("external model source file is missing or outside the supplied root")
    else:
        methods, bases, parse_error = _parse_class(source, class_name)
        result["native_class_bases"] = bases
        result["native_normal_state_methods"] = sorted(methods & _NORMAL_METHOD_NAMES)
        result["native_termination_ledger_methods"] = sorted(methods & _TERMINATION_METHOD_NAMES)
        result["native_accident_export_method"] = "export_accident_history" in methods
        if parse_error:
            result["blocking_reasons"].append(parse_error)
        elif not methods:
            result["blocking_reasons"].append("external model class was not found")
        elif result["native_accident_export_method"]:
            result["native_audit_status"] = "NATIVE_ACCIDENT_EXPORT_METHOD_FOUND"
        else:
            result["native_audit_status"] = "NATIVE_ACCIDENT_EXPORT_MISSING"
            result["blocking_reasons"].append("external model class has no export_accident_history(request) method")

    adapter = result["diagnostic_adapter"]
    if adapter.get("status") == "available":
        module = adapter.get("module")
        provider_class = adapter.get("provider_class")
        if isinstance(module, str) and isinstance(provider_class, str):
            adapter_path = Path(module)
            if not adapter_path.is_absolute():
                adapter_path = prism_root / adapter_path
            if adapter_path.is_file():
                adapter_methods, _, adapter_error = _parse_class(adapter_path, provider_class)
                result["diagnostic_adapter_contract_verified"] = (
                    adapter_error is None and "export_accident_history" in adapter_methods
                )
                if not result["diagnostic_adapter_contract_verified"]:
                    result["blocking_reasons"].append(
                        "declared PRISM diagnostic adapter lacks export_accident_history(request)"
                    )
            else:
                result["blocking_reasons"].append("declared PRISM diagnostic adapter source file is missing")
        else:
            result["blocking_reasons"].append("diagnostic adapter metadata is incomplete")
    return result


def audit_external_model_contract(
    binding_catalog: Mapping[str, Any] | str | Path,
    external_root: str | Path,
    prism_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a static native-vs-wrapper contract audit for every binding."""
    catalog, catalog_digest = _read_json(binding_catalog, "binding catalog")
    if catalog.get("schema_version") != "prism.equipment_model_binding.v1":
        raise ExternalModelContractAuditError("binding catalog schema_version must be prism.equipment_model_binding.v1")
    bindings = catalog.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ExternalModelContractAuditError("binding catalog bindings must be a non-empty list")
    root = Path(external_root).resolve()
    if not root.is_dir():
        raise ExternalModelContractAuditError(f"external model root is not a directory: {root}")
    prism = Path(prism_root).resolve() if prism_root is not None else Path.cwd().resolve()
    rows = [_audit_row(row, root, prism) for row in bindings if isinstance(row, Mapping)]
    if len(rows) != len(bindings):
        raise ExternalModelContractAuditError("binding catalog entries must be objects")
    native_missing = [
        row["component_kind"]
        for row in rows
        if row["model_package"].startswith("lh2dt.")
        and not row["native_accident_export_method"]
    ]
    unresolved = [row["component_kind"] for row in rows if row["native_audit_status"] == "EXTERNAL_SOURCE_UNRESOLVED"]
    adapter_verified = sum(bool(row["diagnostic_adapter_contract_verified"]) for row in rows)
    status = (
        "CONTRACT_AUDIT_INCOMPLETE"
        if unresolved
        else "NATIVE_ACCIDENT_EXPORT_MISSING"
        if native_missing
        else "NATIVE_ACCIDENT_EXPORT_METHODS_FOUND"
    )
    return {
        "schema_version": EXTERNAL_MODEL_CONTRACT_AUDIT_SCHEMA,
        "status": status,
        "external_model_root": str(root),
        "external_model_source_digest": _tree_digest(root),
        "binding_catalog_sha256": catalog_digest,
        "binding_count": len(rows),
        "native_accident_export_component_count": sum(row["native_accident_export_method"] for row in rows),
        "native_accident_export_missing_components": native_missing,
        "unresolved_components": unresolved,
        "diagnostic_adapter_contract_verified_count": adapter_verified,
        "rows": rows,
        "blocking_reasons": [
            *(["one or more external model classes lacks export_accident_history(request)"] if native_missing else []),
            *(["one or more external model source files could not be resolved"] if unresolved else []),
        ],
        "provider_packet_promoted": False,
        "frequency_inference_performed": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "native_method_presence_is_not_a_qualified_packet": True,
            "diagnostic_wrapper_is_not_native_external_model": True,
            "normal_state_method_is_not_an_accident_release": True,
            "evaluate_simulate_fallback": False,
        },
    }


__all__ = [
    "EXTERNAL_MODEL_CONTRACT_AUDIT_SCHEMA",
    "ExternalModelContractAuditError",
    "audit_external_model_contract",
]
