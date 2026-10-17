"""Audit qualification sidecars for the native full-scope request catalog.

The native catalog groups release requests under event rows, whereas the
generic sidecar auditor consumes one flat request per release identity.  This
adapter performs only that structural normalization and path resolution.  It
does not close a release boundary, infer a frequency, or promote a facility
QRA claim.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
from typing import Any

from .generic_provider_evidence_audit import audit_generic_provider_evidence


SCHEMA = "prism.native_full_scope_provider_qualification_audit.v1"
NATIVE_REQUEST_SCHEMA = "prism.native_full_scope_provider_qualification_requests.v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_packet(raw: str, *, catalogue_path: Path, packet_root: Path | None) -> Path:
    """Resolve portable and legacy absolute packet paths without rewriting evidence."""
    value = Path(raw)
    package_root = Path(__file__).resolve().parents[2]
    candidates = [value]
    if not value.is_absolute():
        candidates.extend(
            [catalogue_path.parent / value, Path.cwd() / value]
        )
        if packet_root is not None:
            candidates.append(packet_root / value)
    # Older exports embedded a differently encoded local checkout path.  The
    # repository-relative results suffix remains safe to reuse when present.
    match = re.search(r"lh2-tno[\\/](results[\\/].*)$", raw, re.IGNORECASE)
    if match:
        candidates.append(package_root / Path(match.group(1).replace("\\", "/")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return value


def _native_to_generic(
    value: Mapping[str, Any],
    *,
    catalogue_path: Path,
    packet_root: Path | None,
) -> tuple[dict[str, Any], int, dict[str, int]]:
    rows = value.get("requests")
    if not isinstance(rows, list):
        raise ValueError("native qualification request rows must be an array")
    flattened: list[dict[str, Any]] = []
    request_kind_counts: dict[str, int] = {}
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"native qualification request row {row_index} must be an object")
        nested = row.get("requests")
        if not isinstance(nested, list):
            raise ValueError(f"native qualification request row {row_index} lacks requests")
        for request_index, request in enumerate(nested):
            if not isinstance(request, Mapping):
                raise ValueError(
                    f"native qualification request row {row_index} item {request_index} must be an object"
                )
            current = request.get("current_packet")
            if not isinstance(current, Mapping):
                raise ValueError(
                    f"native qualification request row {row_index} item {request_index} lacks current_packet"
                )
            packet_path = request.get("packet_path") or row.get("packet_path")
            if not isinstance(packet_path, str) or not packet_path.strip():
                raise ValueError(
                    f"native qualification request row {row_index} item {request_index} lacks packet_path"
                )
            normalized = dict(request)
            normalized["packet_path"] = str(
                _resolve_packet(packet_path, catalogue_path=catalogue_path, packet_root=packet_root)
            )
            # Native readiness is deliberately not treated as release closure.
            # A future provider export may carry an explicit closure status; the
            # current catalog defaults to an open closure so an exact sidecar
            # remains diagnostic-only.
            normalized["closure_status"] = str(
                request.get("closure_status")
                or row.get("closure_status")
                or "CLOSURE_EVIDENCE_OPEN"
            )
            kind = str(request.get("request_kind") or row.get("request_kind") or "unknown")
            request_kind_counts[kind] = request_kind_counts.get(kind, 0) + 1
            flattened.append(normalized)
    return (
        {
            "schema_version": "prism.generic_provider_evidence_requests.v1",
            "packet_count": len(flattened),
            "requests": flattened,
        },
        len(rows),
        request_kind_counts,
    )


def audit_native_full_scope_provider_qualification(
    catalogue: Mapping[str, Any] | str | Path,
    *,
    packet_root: str | Path | None = None,
    sidecar_manifest: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Audit native full-scope requests while preserving the strict gates."""
    if isinstance(catalogue, (str, Path)):
        catalogue_path = Path(catalogue).resolve()
        value = _load(catalogue_path)
    else:
        catalogue_path = Path.cwd() / "native_provider_qualification_requests.json"
        value = catalogue
    if not isinstance(value, Mapping):
        raise ValueError("native qualification request catalogue must be an object")
    if value.get("schema_version") != NATIVE_REQUEST_SCHEMA:
        raise ValueError("unsupported native qualification request schema")
    root = Path(packet_root).resolve() if packet_root is not None else None
    generic, event_row_count, request_kind_counts = _native_to_generic(
        value, catalogue_path=catalogue_path, packet_root=root
    )
    report = audit_generic_provider_evidence(
        generic,
        packet_root=root or catalogue_path.parent,
        sidecar_manifest=sidecar_manifest,
    )
    return {
        "schema_version": SCHEMA,
        "status": report["status"],
        "source_schema_version": value.get("schema_version"),
        "source_catalogue_record": str(catalogue_path),
        "event_row_count": event_row_count,
        "release_identity_request_count": report["request_count"],
        "request_kind_counts": request_kind_counts,
        "qualification_sidecar_present_count": report["qualification_sidecar_present_count"],
        "exact_match_count": report["exact_match_count"],
        "qualified_provider_packet_count": report["qualified_provider_packet_count"],
        # These aliases intentionally follow ``build_facility_assessment``'s
        # provider-coverage contract so the audit can be consumed directly by
        # a facility assessment reconciliation step.
        "qualification_assessed": True,
        "qualification_status": report["status"],
        "worklist_event_count": report["request_count"],
        "unqualified_exact_match_count": max(
            0, report["exact_match_count"] - report["qualified_provider_packet_count"]
        ),
        "missing_packet_count": report["missing_packet_count"],
        "missing_sidecar_count": report["missing_sidecar_count"],
        "invalid_count": report["invalid_count"],
        "identity_mismatch_count": report["identity_mismatch_count"],
        "digest_mismatch_count": report["digest_mismatch_count"],
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "physical_validation_claim": False,
        "diagnostic_only": True,
        "sidecar_manifest_record": str(sidecar_manifest) if isinstance(sidecar_manifest, (str, Path)) else None,
        "rows": report["rows"],
        "interpretation": (
            "Native event rows are flattened only for identity auditing. An exact sidecar "
            "match remains diagnostic until release closure, independent physical validation, "
            "frequency binding and facility QRA gates are separately satisfied."
        ),
    }


__all__ = ["audit_native_full_scope_provider_qualification"]
