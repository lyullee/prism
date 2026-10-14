"""Audit external validation evidence without promoting a provider packet.

External reports often contain useful physics checks, but a report about a
thermodynamic boundary or a gaseous nozzle is not, by itself, a qualified
liquid-hydrogen accident-release provider.  This module makes that distinction
machine-readable.  It accepts a small review manifest, hashes every source,
summarises the declared evidence scope, and fail-closes provider promotion.

The output is intended to be consumed by the validation-evidence matrix and by
IJHE audit material.  It deliberately never infers a frequency, a release
duration, or a facility-QRA claim from a validation report.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "prism.external_provider_validation_intake.v1"
STATUS = "RESTRICTED_PROVIDER_COMPONENT_EVIDENCE"


class ExternalProviderValidationError(ValueError):
    """Raised when an external validation intake is malformed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ExternalProviderValidationError(f"{label} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExternalProviderValidationError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ExternalProviderValidationError(f"{label} must be a JSON object: {path}")
    return payload


def _as_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ExternalProviderValidationError(f"{label} must be a list")
    return value


def _artifact_origin(payload: Mapping[str, Any]) -> str | None:
    direct = payload.get("input_origin")
    if isinstance(direct, str):
        return direct
    provenance = payload.get("upstream_service_provenance")
    if isinstance(provenance, Mapping):
        for key in ("input_origin", "origin", "source_origin"):
            value = provenance.get(key)
            if isinstance(value, str):
                return value
    for key in ("source_state", "provenance", "metadata"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            for nested in ("input_origin", "origin", "source_origin"):
                origin = value.get(nested)
                if isinstance(origin, str):
                    return origin
    return None


def _provider_artifact_summary(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {
            "root": None,
            "artifact_file_count": 0,
            "parsed_artifact_count": 0,
            "actual_origin_count": 0,
            "synthetic_or_model_prediction_count": 0,
            "qualification_sidecar_count": 0,
            "exact_validation_match_count": 0,
            "artifacts": [],
        }
    if not root.is_dir():
        raise ExternalProviderValidationError(f"provider artifact root is missing: {root}")
    paths = sorted(
        path
        for pattern in ("resolved_release.json", "resolved_release_set.json")
        for path in root.rglob(pattern)
        if path.is_file()
    )
    rows: list[dict[str, Any]] = []
    actual = 0
    synthetic = 0
    sidecars = 0
    for path in paths:
        try:
            payload = _read_json(path, "provider artifact")
        except ExternalProviderValidationError as error:
            rows.append({
                "path": str(path),
                "sha256": _sha256(path),
                "status": "PARSE_ERROR",
                "error": str(error),
            })
            continue
        origin = _artifact_origin(payload)
        origin_lower = (origin or "").lower()
        if origin_lower in {"actual", "field_actual", "reviewed_actual", "measured"}:
            actual += 1
        if origin_lower in {"synthetic", "model_prediction", "screening", "operator_declared"}:
            synthetic += 1
        nested_qualification = payload.get("provider_qualification_evidence")
        if isinstance(nested_qualification, Mapping):
            sidecars += 1
        rows.append({
            "path": str(path),
            "sha256": _sha256(path),
            "schema": payload.get("provider_export_schema") or payload.get("schema"),
            "component_id": payload.get("component_id"),
            "event_id": payload.get("event_id"),
            "input_origin": origin,
            "termination_basis": payload.get("termination_basis"),
            "qualification_sidecar_embedded": isinstance(nested_qualification, Mapping),
        })
    return {
        "root": str(root),
        "artifact_file_count": len(paths),
        "parsed_artifact_count": sum(row.get("status") != "PARSE_ERROR" for row in rows),
        "actual_origin_count": actual,
        "synthetic_or_model_prediction_count": synthetic,
        "qualification_sidecar_count": sidecars,
        "exact_validation_match_count": 0,
        "artifacts": rows,
    }


def _review_row(
    manifest_row: Mapping[str, Any],
    manifest_path: Path,
    provider_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_id = manifest_row.get("evidence_id")
    source_path_value = manifest_row.get("path")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise ExternalProviderValidationError("each evidence row needs a non-empty evidence_id")
    if not isinstance(source_path_value, str) or not source_path_value.strip():
        raise ExternalProviderValidationError(f"{evidence_id} needs a source path")
    source_path = Path(source_path_value)
    if not source_path.is_absolute():
        source_path = (manifest_path.parent / source_path).resolve()
    payload = _read_json(source_path, f"evidence source {evidence_id}")
    supports = _as_list(manifest_row.get("supports"), f"{evidence_id}.supports")
    excludes = _as_list(manifest_row.get("does_not_support"), f"{evidence_id}.does_not_support")
    blockers = _as_list(manifest_row.get("blocking_reasons"), f"{evidence_id}.blocking_reasons")
    if not supports:
        raise ExternalProviderValidationError(f"{evidence_id} must declare at least one supported scope")
    if not excludes:
        raise ExternalProviderValidationError(f"{evidence_id} must declare excluded scope")
    if not blockers:
        blockers = [
            "exact provider event/component/port identity is not demonstrated",
            "provider qualification sidecar is not bound to this validation source",
            "independent full-chain facility validation remains open",
        ]
    origin = manifest_row.get("source_origin", "external_public_or_reviewed")
    if not isinstance(origin, str) or not origin:
        raise ExternalProviderValidationError(f"{evidence_id}.source_origin must be a string")
    declared_match = manifest_row.get("provider_packet_match", False)
    if declared_match is not False:
        raise ExternalProviderValidationError(
            f"{evidence_id} cannot declare provider_packet_match=true in a restricted intake"
        )
    metrics = manifest_row.get("metrics")
    if metrics is None:
        metrics = {}
    if not isinstance(metrics, Mapping):
        raise ExternalProviderValidationError(f"{evidence_id}.metrics must be an object")
    return {
        "evidence_id": evidence_id,
        "kind": manifest_row.get("kind", "unspecified"),
        "source": {
            "path": str(source_path),
            "sha256": _sha256(source_path),
            "status": payload.get("status") or payload.get("qualification") or payload.get("decision"),
            "dataset_doi": payload.get("dataset_doi"),
        },
        "source_origin": origin,
        "declared_scope": {
            "supports": [str(item) for item in supports],
            "does_not_support": [str(item) for item in excludes],
        },
        "metrics": dict(metrics),
        "promotion": {
            "provider_packet_match": False,
            "qualification_status": "NOT_QUALIFIED",
            "promotion_status": "PROMOTION_BLOCKED",
            "blocking_reasons": [str(item) for item in blockers],
            "provider_artifact_count_seen": provider_artifacts.get("artifact_file_count", 0),
            "exact_provider_validation_match_count": provider_artifacts.get(
                "exact_validation_match_count", 0
            ),
        },
    }


def audit_external_provider_validation(
    manifest_path: str | Path,
    *,
    provider_artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build a restricted external-provider validation evidence ledger."""
    manifest_path = Path(manifest_path).resolve()
    manifest = _read_json(manifest_path, "external validation manifest")
    rows = _as_list(manifest.get("evidence"), "manifest.evidence")
    if not rows:
        raise ExternalProviderValidationError("manifest.evidence must not be empty")
    provider_root = None if provider_artifact_root is None else Path(provider_artifact_root).resolve()
    artifacts = _provider_artifact_summary(provider_root)
    evidence = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ExternalProviderValidationError(f"manifest.evidence[{index}] must be an object")
        item = _review_row(row, manifest_path, artifacts)
        if item["evidence_id"] in seen:
            raise ExternalProviderValidationError(f"duplicate evidence_id: {item['evidence_id']}")
        seen.add(item["evidence_id"])
        evidence.append(item)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "manifest": {
            "path": str(manifest_path),
            "sha256": _sha256(manifest_path),
            "reviewed_evidence_count": len(evidence),
        },
        "provider_artifacts": artifacts,
        "evidence": evidence,
        "summary": {
            "evidence_count": len(evidence),
            "promotion_blocked_count": len(evidence),
            "provider_packet_match_count": 0,
            "independent_full_chain_validation_count": 0,
            "provider_qualification_sidecar_count": artifacts["qualification_sidecar_count"],
            "actual_origin_provider_artifact_count": artifacts["actual_origin_count"],
            "synthetic_or_model_prediction_provider_artifact_count": artifacts[
                "synthetic_or_model_prediction_count"
            ],
        },
        "provider_qualification_claim": False,
        "accident_release_validation_claim": False,
        "independent_physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "promotion_policy": {
            "boundary_or_component_evidence_does_not_qualify_provider": True,
            "provider_artifact_origin_is_not_inferred": True,
            "sensor_or_validation_data_does_not_create_frequency": True,
            "facility_qra_requires_exact_provider_and_independent_full_chain_validation": True,
        },
        "required_for_provider_promotion": [
            "actual reviewed provider release packet with exact event, component, port and source/result digests",
            "explicit release duration, isolation branch and inventory-depletion closure",
            "provider qualification sidecar bound to the exact packet",
            "independent physical validation of the same release model and operating regime",
            "facility scope closure before IR/F-N promotion",
        ],
    }


__all__ = [
    "SCHEMA_VERSION",
    "STATUS",
    "ExternalProviderValidationError",
    "audit_external_provider_validation",
]
